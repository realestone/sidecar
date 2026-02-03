"""Tests for sidecar.extraction.filter."""

from sidecar.extraction.filter import filter_session
from sidecar.extraction.models import SessionMessage


def _msg(type_: str, role: str = "", content: list[dict] | None = None, **kw):
    """Shorthand to build a SessionMessage."""
    return SessionMessage(
        type=type_,
        role=role,
        content=content or [],
        **kw,
    )


def _text(text: str) -> dict:
    return {"type": "text", "text": text}


def _tool_use(name: str, **inputs) -> dict:
    return {"type": "tool_use", "id": "t1", "name": name, "input": inputs}


class TestRemoveTypes:
    def test_removes_progress(self):
        msgs = [
            _msg("progress"),
            _msg("user", "user", [_text("hello")]),
            _msg("progress"),
        ]
        result = filter_session("s1", msgs)
        assert len(result.messages) == 1
        assert result.stats.removed_progress == 2

    def test_removes_file_history(self):
        msgs = [
            _msg("file-history-snapshot"),
            _msg("user", "user", [_text("hello")]),
        ]
        result = filter_session("s1", msgs)
        assert len(result.messages) == 1
        assert result.stats.removed_file_history == 1


class TestKeepSummary:
    def test_keeps_summary(self):
        msgs = [_msg("summary", content=[_text("Session about testing")])]
        result = filter_session("s1", msgs)
        assert len(result.messages) == 1
        assert result.messages[0].type == "summary"


class TestUserMessages:
    def test_user_messages_kept_in_full(self):
        long_text = "x" * 1000
        msgs = [_msg("user", "user", [_text(long_text)])]
        result = filter_session("s1", msgs)
        assert len(result.messages) == 1
        assert result.messages[0].content[0]["text"] == long_text


class TestShortAssistant:
    def test_removes_short_assistant(self):
        msgs = [_msg("assistant", "assistant", [_text("OK")])]
        result = filter_session("s1", msgs)
        assert len(result.messages) == 0

    def test_keeps_longer_assistant(self):
        msgs = [_msg("assistant", "assistant", [_text("x" * 60)])]
        result = filter_session("s1", msgs)
        assert len(result.messages) == 1


class TestTruncation:
    def test_truncates_long_assistant(self):
        text = "a" * 600
        msgs = [_msg("assistant", "assistant", [_text(text)])]
        result = filter_session("s1", msgs)
        assert len(result.messages) == 1
        content_text = result.messages[0].content[0]["text"]
        assert len(content_text) == 303  # 300 + "..."
        assert content_text.endswith("...")
        assert result.stats.truncated_messages == 1


class TestToolStripping:
    def test_write_keeps_file_path(self):
        msgs = [
            _msg(
                "assistant",
                "assistant",
                [
                    _text("Let me write that file."),
                    _tool_use(
                        "Write", file_path="/tmp/test.py", content="print('hello')"
                    ),
                ],
            )
        ]
        result = filter_session("s1", msgs)
        assert len(result.messages) == 1
        tool_block = result.messages[0].content[1]
        assert tool_block["name"] == "Write"
        assert tool_block["file_path"] == "/tmp/test.py"
        assert "content" not in tool_block
        assert result.stats.stripped_tool_content == 1

    def test_edit_keeps_file_path(self):
        msgs = [
            _msg(
                "assistant",
                "assistant",
                [
                    _text("Editing the file now."),
                    _tool_use(
                        "Edit",
                        file_path="/tmp/test.py",
                        old_string="old",
                        new_string="new",
                    ),
                ],
            )
        ]
        result = filter_session("s1", msgs)
        tool_block = result.messages[0].content[1]
        assert tool_block["name"] == "Edit"
        assert tool_block["file_path"] == "/tmp/test.py"
        assert "old_string" not in tool_block
        assert "new_string" not in tool_block

    def test_read_keeps_file_path(self):
        msgs = [
            _msg(
                "assistant",
                "assistant",
                [
                    _text("Reading the file now." + "x" * 40),
                    _tool_use("Read", file_path="/tmp/test.py"),
                ],
            )
        ]
        result = filter_session("s1", msgs)
        tool_block = result.messages[0].content[1]
        assert tool_block["name"] == "Read"
        assert tool_block["file_path"] == "/tmp/test.py"

    def test_bash_keeps_command_preview(self):
        long_cmd = "echo " + "x" * 200
        msgs = [
            _msg(
                "assistant",
                "assistant",
                [
                    _text("Running a command now to test things."),
                    _tool_use(
                        "Bash", command=long_cmd, description="Echo a long string"
                    ),
                ],
            )
        ]
        result = filter_session("s1", msgs)
        tool_block = result.messages[0].content[1]
        assert tool_block["name"] == "Bash"
        assert tool_block["description"] == "Echo a long string"
        assert len(tool_block["command_preview"]) == 100

    def test_other_tool_keeps_name_only(self):
        msgs = [
            _msg(
                "assistant",
                "assistant",
                [
                    _text("Searching for something interesting."),
                    _tool_use("WebSearch", query="test query"),
                ],
            )
        ]
        result = filter_session("s1", msgs)
        tool_block = result.messages[0].content[1]
        assert tool_block == {"type": "tool_use", "name": "WebSearch"}


class TestFilterStats:
    def test_stats_correct(self):
        msgs = [
            _msg("progress"),
            _msg("progress"),
            _msg("file-history-snapshot"),
            _msg("user", "user", [_text("hello")]),
            _msg("assistant", "assistant", [_text("OK")]),
            _msg("assistant", "assistant", [_text("a" * 600)]),
            _msg(
                "assistant",
                "assistant",
                [
                    _text("Let me write that file for you now."),
                    _tool_use("Write", file_path="/tmp/f.py", content="data"),
                ],
            ),
            _msg("summary", content=[_text("done")]),
        ]
        result = filter_session("s1", msgs)
        s = result.stats
        assert s.original_count == 8
        assert s.removed_progress == 2
        assert s.removed_file_history == 1
        assert s.truncated_messages == 1
        assert s.stripped_tool_content == 1
        # Kept: user + truncated assistant + assistant w/ tool + summary = 4
        assert s.kept_count == 4


class TestMixedContent:
    def test_assistant_with_tool_only_not_short_filtered(self):
        """An assistant msg with only a tool_use should be kept even if no text."""
        msgs = [
            _msg(
                "assistant",
                "assistant",
                [_tool_use("Write", file_path="/tmp/f.py", content="x")],
            )
        ]
        result = filter_session("s1", msgs)
        assert len(result.messages) == 1
