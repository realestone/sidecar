"""Extract code diffs from git or fall back to tool_call extraction."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..errors import SidecarError
from .models import CodeDiff, FileDiff, SessionMessage

# Max chars for diff text sent to analyzer (~8k tokens ≈ 32k chars)
MAX_DIFF_CHARS = 32_000


def get_diff(
    project_path: str,
    messages: list[SessionMessage] | None = None,
) -> CodeDiff:
    """Get code diff for a session.

    Tries git diff first (comparing working tree to HEAD~1 or initial commit).
    Falls back to extracting file paths from tool_use blocks in messages.
    """
    try:
        return _git_diff(project_path)
    except (SidecarError, Exception):
        if messages:
            return _tool_call_diff(messages)
        return CodeDiff(source="tool_calls")


def _git_diff(project_path: str) -> CodeDiff:
    """Get diff from git."""
    cwd = Path(project_path)
    if not cwd.is_dir():
        raise SidecarError.git_error(f"Not a directory: {project_path}")

    # Check if it's a git repo
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=cwd,
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise SidecarError.git_error(f"Not a git repo: {project_path}") from e

    # Try diff against HEAD~1, fall back to diff of all tracked + untracked
    diff_text = ""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD~1"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            diff_text = result.stdout
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        pass

    if not diff_text:
        # Fall back to diff of staged + unstaged changes
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            diff_text = result.stdout

    if not diff_text:
        # Try diff of everything including untracked
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            # There are changes but no commit to diff against
            return _status_to_diff(result.stdout, cwd)

    if not diff_text:
        return CodeDiff(source="git")

    return _parse_diff(diff_text)


def _parse_diff(diff_text: str) -> CodeDiff:
    """Parse git diff output into a CodeDiff."""
    files: list[FileDiff] = []
    total_add = 0
    total_del = 0
    truncated = False

    if len(diff_text) > MAX_DIFF_CHARS:
        diff_text = diff_text[:MAX_DIFF_CHARS]
        truncated = True

    # Parse --stat lines for file summary
    # Format: " path/to/file | 10 ++---"
    current_file: str | None = None
    current_diff_lines: list[str] = []

    for line in diff_text.split("\n"):
        # Detect diff header for a new file
        if line.startswith("diff --git"):
            if current_file:
                files.append(_build_file_diff(current_file, current_diff_lines))
            match = re.search(r"b/(.+)$", line)
            current_file = match.group(1) if match else "unknown"
            current_diff_lines = [line]
        elif current_file:
            current_diff_lines.append(line)

    # Don't forget the last file
    if current_file:
        files.append(_build_file_diff(current_file, current_diff_lines))

    for f in files:
        total_add += f.additions
        total_del += f.deletions

    return CodeDiff(
        files=files,
        total_additions=total_add,
        total_deletions=total_del,
        truncated=truncated,
        source="git",
    )


def _build_file_diff(path: str, lines: list[str]) -> FileDiff:
    """Build a FileDiff from collected diff lines for a file."""
    additions = 0
    deletions = 0
    status = "modified"

    for line in lines:
        if line.startswith("new file"):
            status = "added"
        elif line.startswith("deleted file"):
            status = "deleted"
        elif line.startswith("rename"):
            status = "renamed"
        elif line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1

    return FileDiff(
        path=path,
        status=status,
        additions=additions,
        deletions=deletions,
        diff_text="\n".join(lines),
    )


def _status_to_diff(status_output: str, cwd: Path) -> CodeDiff:
    """Convert git status --porcelain output to a CodeDiff.

    For untracked/new files, reads file content to produce actual diff text
    so the analyzer has something to work with.
    """
    files: list[FileDiff] = []
    total_add = 0
    total_del = 0
    total_chars = 0

    for line in status_output.strip().split("\n"):
        if len(line) < 4:
            continue
        status_code = line[:2].strip()
        filepath = line[3:].strip()

        if status_code in ("??", "A"):
            status = "added"
        elif status_code == "D":
            status = "deleted"
        elif status_code == "R":
            status = "renamed"
        else:
            status = "modified"

        # Try to read file content for added/modified files
        diff_text = ""
        additions = 0
        deletions = 0
        if status in ("added", "modified") and total_chars < MAX_DIFF_CHARS:
            full_path = cwd / filepath
            if full_path.is_file():
                try:
                    content = full_path.read_text(errors="replace")
                    file_lines = content.splitlines()
                    additions = len(file_lines)
                    diff_lines = [f"+{l}" for l in file_lines]
                    diff_text = (
                        f"diff --git a/{filepath} b/{filepath}\n"
                        f"new file\n"
                        f"--- /dev/null\n"
                        f"+++ b/{filepath}\n"
                        + "\n".join(diff_lines)
                    )
                    total_chars += len(diff_text)
                except OSError:
                    pass

        total_add += additions
        total_del += deletions
        files.append(
            FileDiff(
                path=filepath,
                status=status,
                additions=additions,
                deletions=deletions,
                diff_text=diff_text,
            )
        )

    truncated = total_chars >= MAX_DIFF_CHARS
    return CodeDiff(
        files=files,
        total_additions=total_add,
        total_deletions=total_del,
        truncated=truncated,
        source="git",
    )


def _tool_call_diff(messages: list[SessionMessage]) -> CodeDiff:
    """Extract file changes from Write/Edit tool_use blocks in messages."""
    seen: dict[str, str] = {}  # path -> status

    for msg in messages:
        if msg.role != "assistant":
            continue
        for block in msg.content:
            if block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            inp = block.get("input", {})
            path = inp.get("file_path", "") or block.get("file_path", "")

            if not path:
                continue

            if name == "Write":
                if path not in seen:
                    seen[path] = "added"
            elif name == "Edit":
                seen[path] = seen.get(path, "modified")

    files = [FileDiff(path=p, status=s) for p, s in seen.items()]
    return CodeDiff(files=files, source="tool_calls")
