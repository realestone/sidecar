"""Tests for sidecar.extraction.reader."""

import json
from pathlib import Path

import pytest

from sidecar.errors import SidecarError
from sidecar.extraction.reader import (
    get_latest_session,
    list_sessions,
    parse_jsonl,
    read_session,
)


def _make_project(
    base: Path,
    project_name: str,
    original_path: str,
    sessions: list[dict],
) -> Path:
    """Create a fake Claude project directory with sessions-index.json and JSONL files."""
    project_dir = base / project_name
    project_dir.mkdir(parents=True)

    entries = []
    for s in sessions:
        session_id = s["session_id"]
        jsonl_path = project_dir / f"{session_id}.jsonl"

        # Write JSONL messages
        lines = []
        for msg in s.get("messages", []):
            lines.append(json.dumps(msg))
        jsonl_path.write_text("\n".join(lines))

        entries.append(
            {
                "sessionId": session_id,
                "fullPath": str(jsonl_path),
                "firstPrompt": s.get("first_prompt", "hello"),
                "summary": s.get("summary", "test session"),
                "messageCount": len(s.get("messages", [])),
                "created": s.get("created", "2026-01-01T00:00:00Z"),
                "modified": s.get("modified", "2026-01-01T00:00:00Z"),
                "gitBranch": s.get("git_branch", ""),
                "projectPath": original_path,
            }
        )

    index = {
        "version": 1,
        "originalPath": original_path,
        "entries": entries,
    }
    (project_dir / "sessions-index.json").write_text(json.dumps(index))
    return project_dir


class TestListSessions:
    def test_empty_dir(self, tmp_path):
        sessions = list_sessions(projects_dir=tmp_path)
        assert sessions == []

    def test_nonexistent_dir(self, tmp_path):
        sessions = list_sessions(projects_dir=tmp_path / "nope")
        assert sessions == []

    def test_single_session(self, tmp_path):
        _make_project(
            tmp_path,
            "-Users-test-project",
            "/Users/test/project",
            [
                {
                    "session_id": "abc-123",
                    "modified": "2026-01-01T12:00:00Z",
                    "messages": [
                        {
                            "type": "user",
                            "uuid": "u1",
                            "timestamp": "2026-01-01T12:00:00Z",
                            "message": {"role": "user", "content": "hello"},
                        }
                    ],
                }
            ],
        )

        sessions = list_sessions(projects_dir=tmp_path)
        assert len(sessions) == 1
        assert sessions[0].session_id == "abc-123"
        assert sessions[0].project_path == "/Users/test/project"

    def test_filter_by_project_path(self, tmp_path):
        _make_project(
            tmp_path,
            "-Users-a-proj",
            "/Users/a/proj",
            [{"session_id": "s1", "modified": "2026-01-01T00:00:00Z", "messages": []}],
        )
        _make_project(
            tmp_path,
            "-Users-b-proj",
            "/Users/b/proj",
            [{"session_id": "s2", "modified": "2026-01-02T00:00:00Z", "messages": []}],
        )

        all_sessions = list_sessions(projects_dir=tmp_path)
        assert len(all_sessions) == 2

        filtered = list_sessions(project_path="/Users/a/proj", projects_dir=tmp_path)
        assert len(filtered) == 1
        assert filtered[0].session_id == "s1"

    def test_sorted_by_modified_desc(self, tmp_path):
        _make_project(
            tmp_path,
            "-Users-test-proj",
            "/Users/test/proj",
            [
                {"session_id": "old", "modified": "2026-01-01T00:00:00Z", "messages": []},
                {"session_id": "new", "modified": "2026-01-02T00:00:00Z", "messages": []},
            ],
        )

        sessions = list_sessions(projects_dir=tmp_path)
        assert sessions[0].session_id == "new"
        assert sessions[1].session_id == "old"

    def test_bad_index_json_skipped(self, tmp_path):
        project_dir = tmp_path / "-bad-project"
        project_dir.mkdir()
        (project_dir / "sessions-index.json").write_text("not json")

        sessions = list_sessions(projects_dir=tmp_path)
        assert sessions == []


class TestParseJsonl:
    def test_user_message_string_content(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        jsonl.write_text(
            json.dumps(
                {
                    "type": "user",
                    "uuid": "u1",
                    "parentUuid": None,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "message": {"role": "user", "content": "hello world"},
                }
            )
        )

        msgs = parse_jsonl(jsonl)
        assert len(msgs) == 1
        assert msgs[0].type == "user"
        assert msgs[0].role == "user"
        assert msgs[0].content == [{"type": "text", "text": "hello world"}]

    def test_assistant_message_with_tool_use(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        jsonl.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "uuid": "a1",
                    "parentUuid": "u1",
                    "timestamp": "2026-01-01T00:00:01Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "Let me read that."},
                            {
                                "type": "tool_use",
                                "id": "toolu_1",
                                "name": "Read",
                                "input": {"file_path": "/tmp/test.py"},
                            },
                        ],
                    },
                }
            )
        )

        msgs = parse_jsonl(jsonl)
        assert len(msgs) == 1
        assert msgs[0].type == "assistant"
        assert len(msgs[0].content) == 2
        assert msgs[0].content[1]["name"] == "Read"

    def test_progress_and_summary_messages(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        lines = [
            json.dumps({"type": "progress", "uuid": "p1", "data": {}}),
            json.dumps(
                {"type": "summary", "summary": "Session about testing", "leafUuid": "x"}
            ),
        ]
        jsonl.write_text("\n".join(lines))

        msgs = parse_jsonl(jsonl)
        assert len(msgs) == 2
        assert msgs[0].type == "progress"
        assert msgs[1].type == "summary"
        assert msgs[1].content == [{"type": "text", "text": "Session about testing"}]

    def test_skips_blank_lines_and_bad_json(self, tmp_path):
        jsonl = tmp_path / "test.jsonl"
        jsonl.write_text(
            '\n{"type":"user","uuid":"u1","message":{"role":"user","content":"hi"}}\n\nnot json\n'
        )

        msgs = parse_jsonl(jsonl)
        assert len(msgs) == 1

    def test_file_not_found(self, tmp_path):
        with pytest.raises(SidecarError) as exc_info:
            parse_jsonl(tmp_path / "nope.jsonl")
        assert exc_info.value.code.value == "session_read"


class TestReadSession:
    def test_reads_messages(self, tmp_path):
        _make_project(
            tmp_path,
            "-Users-test-proj",
            "/Users/test/proj",
            [
                {
                    "session_id": "sess-1",
                    "modified": "2026-01-01T00:00:00Z",
                    "messages": [
                        {
                            "type": "user",
                            "uuid": "u1",
                            "timestamp": "2026-01-01T00:00:00Z",
                            "message": {"role": "user", "content": "hello"},
                        },
                        {
                            "type": "assistant",
                            "uuid": "a1",
                            "parentUuid": "u1",
                            "timestamp": "2026-01-01T00:00:01Z",
                            "message": {
                                "role": "assistant",
                                "content": [{"type": "text", "text": "hi there"}],
                            },
                        },
                    ],
                }
            ],
        )

        msgs = read_session("sess-1", projects_dir=tmp_path)
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[1].role == "assistant"

    def test_session_not_found(self, tmp_path):
        _make_project(
            tmp_path,
            "-Users-test-proj",
            "/Users/test/proj",
            [{"session_id": "s1", "modified": "2026-01-01T00:00:00Z", "messages": []}],
        )

        with pytest.raises(SidecarError) as exc_info:
            read_session("nonexistent", projects_dir=tmp_path)
        assert exc_info.value.code.value == "session_not_found"


class TestGetLatestSession:
    def test_returns_most_recent(self, tmp_path):
        _make_project(
            tmp_path,
            "-Users-test-proj",
            "/Users/test/proj",
            [
                {"session_id": "old", "modified": "2026-01-01T00:00:00Z", "messages": []},
                {"session_id": "new", "modified": "2026-01-02T00:00:00Z", "messages": []},
            ],
        )

        latest = get_latest_session(projects_dir=tmp_path)
        assert latest.session_id == "new"

    def test_no_sessions_raises(self, tmp_path):
        with pytest.raises(SidecarError) as exc_info:
            get_latest_session(projects_dir=tmp_path)
        assert exc_info.value.code.value == "session_not_found"
