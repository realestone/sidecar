"""Tests for sidecar.extraction.differ."""

import subprocess

import pytest

from sidecar.extraction.differ import _parse_diff, _tool_call_diff, get_diff
from sidecar.extraction.models import SessionMessage


def _init_git_repo(path):
    """Create a git repo with an initial commit."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path,
        capture_output=True,
        check=True,
    )
    # Initial commit
    (path / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=path,
        capture_output=True,
        check=True,
    )


class TestGitDiff:
    def test_new_file(self, tmp_path):
        _init_git_repo(tmp_path)

        # Add a new file and commit
        (tmp_path / "new.py").write_text("print('hello')\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add new.py"],
            cwd=tmp_path,
            capture_output=True,
        )

        diff = get_diff(str(tmp_path))
        assert diff.source == "git"
        assert any(f.path == "new.py" for f in diff.files)

    def test_modified_file(self, tmp_path):
        _init_git_repo(tmp_path)

        # Modify README
        (tmp_path / "README.md").write_text("# Test\n\nUpdated content\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "update readme"],
            cwd=tmp_path,
            capture_output=True,
        )

        diff = get_diff(str(tmp_path))
        assert diff.source == "git"
        readme_diff = [f for f in diff.files if f.path == "README.md"]
        assert len(readme_diff) == 1
        assert readme_diff[0].additions > 0

    def test_not_a_git_repo_falls_back(self, tmp_path):
        diff = get_diff(str(tmp_path))
        assert diff.source == "tool_calls"
        assert diff.files == []

    def test_nonexistent_dir_falls_back(self, tmp_path):
        diff = get_diff(str(tmp_path / "nope"))
        assert diff.source == "tool_calls"


    def test_untracked_files_have_diff_text(self, tmp_path):
        """When all files are untracked, _status_to_diff should read their content."""
        _init_git_repo(tmp_path)

        # Add untracked files (don't git add)
        (tmp_path / "new.py").write_text("print('hello')\n")
        (tmp_path / "lib.py").write_text("x = 1\ny = 2\n")

        diff = get_diff(str(tmp_path))
        assert diff.source == "git"
        new_file = [f for f in diff.files if f.path == "new.py"]
        assert len(new_file) == 1
        assert new_file[0].additions == 1
        assert "+print('hello')" in new_file[0].diff_text
        assert diff.total_additions > 0


class TestParseDiff:
    def test_basic_diff(self):
        diff_text = """diff --git a/hello.py b/hello.py
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/hello.py
@@ -0,0 +1,3 @@
+def hello():
+    print("hello")
+    return True
"""
        result = _parse_diff(diff_text)
        assert len(result.files) == 1
        assert result.files[0].path == "hello.py"
        assert result.files[0].status == "added"
        assert result.files[0].additions == 3
        assert result.total_additions == 3

    def test_modified_file_diff(self):
        diff_text = """diff --git a/README.md b/README.md
index abc1234..def5678 100644
--- a/README.md
+++ b/README.md
@@ -1 +1,3 @@
-# Old
+# New
+
+Added line
"""
        result = _parse_diff(diff_text)
        assert len(result.files) == 1
        assert result.files[0].status == "modified"
        assert result.files[0].additions == 3
        assert result.files[0].deletions == 1

    def test_truncation(self):
        diff_text = "diff --git a/big.py b/big.py\n" + "+" * 50_000
        result = _parse_diff(diff_text)
        assert result.truncated is True

    def test_multiple_files(self):
        diff_text = """diff --git a/a.py b/a.py
new file mode 100644
--- /dev/null
+++ b/a.py
@@ -0,0 +1 @@
+pass
diff --git a/b.py b/b.py
new file mode 100644
--- /dev/null
+++ b/b.py
@@ -0,0 +1 @@
+pass
"""
        result = _parse_diff(diff_text)
        assert len(result.files) == 2


class TestToolCallDiff:
    def test_extracts_write_calls(self):
        msgs = [
            SessionMessage(
                type="assistant",
                role="assistant",
                content=[
                    {
                        "type": "tool_use",
                        "name": "Write",
                        "input": {"file_path": "/tmp/new.py", "content": "..."},
                    }
                ],
            )
        ]
        result = _tool_call_diff(msgs)
        assert result.source == "tool_calls"
        assert len(result.files) == 1
        assert result.files[0].path == "/tmp/new.py"
        assert result.files[0].status == "added"

    def test_extracts_edit_calls(self):
        msgs = [
            SessionMessage(
                type="assistant",
                role="assistant",
                content=[
                    {
                        "type": "tool_use",
                        "name": "Edit",
                        "input": {
                            "file_path": "/tmp/existing.py",
                            "old_string": "a",
                            "new_string": "b",
                        },
                    }
                ],
            )
        ]
        result = _tool_call_diff(msgs)
        assert len(result.files) == 1
        assert result.files[0].status == "modified"

    def test_deduplicates_files(self):
        msgs = [
            SessionMessage(
                type="assistant",
                role="assistant",
                content=[
                    {
                        "type": "tool_use",
                        "name": "Write",
                        "input": {"file_path": "/tmp/f.py", "content": "v1"},
                    },
                    {
                        "type": "tool_use",
                        "name": "Edit",
                        "input": {
                            "file_path": "/tmp/f.py",
                            "old_string": "a",
                            "new_string": "b",
                        },
                    },
                ],
            )
        ]
        result = _tool_call_diff(msgs)
        assert len(result.files) == 1
        # Write came first so it's "added", Edit doesn't override
        assert result.files[0].status == "added"

    def test_skips_non_assistant(self):
        msgs = [
            SessionMessage(
                type="user",
                role="user",
                content=[
                    {
                        "type": "tool_use",
                        "name": "Write",
                        "input": {"file_path": "/tmp/f.py", "content": "x"},
                    }
                ],
            )
        ]
        result = _tool_call_diff(msgs)
        assert len(result.files) == 0

    def test_handles_filtered_tool_blocks(self):
        """After filtering, tool blocks may have file_path at top level."""
        msgs = [
            SessionMessage(
                type="assistant",
                role="assistant",
                content=[
                    {
                        "type": "tool_use",
                        "name": "Write",
                        "file_path": "/tmp/f.py",
                    }
                ],
            )
        ]
        result = _tool_call_diff(msgs)
        assert len(result.files) == 1
        assert result.files[0].path == "/tmp/f.py"
