"""Read Claude Code sessions from ~/.claude/projects/."""

from __future__ import annotations

import json
from pathlib import Path

from ..errors import SidecarError
from .models import SessionInfo, SessionMessage

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def list_sessions(
    project_path: str | None = None,
    projects_dir: Path | None = None,
) -> list[SessionInfo]:
    """List available sessions, optionally filtered by project path.

    Args:
        project_path: Original project path to filter by (e.g. /Users/lukas/Desktop/sidecar).
        projects_dir: Override the projects directory (for testing).
    """
    base = projects_dir or CLAUDE_PROJECTS_DIR
    if not base.is_dir():
        return []

    sessions: list[SessionInfo] = []

    for project_dir in sorted(base.iterdir()):
        if not project_dir.is_dir():
            continue

        index_path = project_dir / "sessions-index.json"
        if not index_path.exists():
            continue

        try:
            index = json.loads(index_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        original_path = index.get("originalPath", "")

        if project_path and original_path != project_path:
            continue

        for entry in index.get("entries", []):
            sessions.append(
                SessionInfo(
                    session_id=entry.get("sessionId", ""),
                    full_path=entry.get("fullPath", ""),
                    first_prompt=entry.get("firstPrompt", ""),
                    summary=entry.get("summary", ""),
                    message_count=entry.get("messageCount", 0),
                    created=entry.get("created", ""),
                    modified=entry.get("modified", ""),
                    git_branch=entry.get("gitBranch", ""),
                    project_path=entry.get("projectPath", original_path),
                )
            )

    # Sort by modified time, most recent first
    sessions.sort(key=lambda s: s.modified, reverse=True)
    return sessions


def read_session(
    session_id: str,
    project_path: str | None = None,
    projects_dir: Path | None = None,
) -> list[SessionMessage]:
    """Read all messages from a session JSONL file.

    Args:
        session_id: The session UUID.
        project_path: Optional project path to narrow the search.
        projects_dir: Override the projects directory (for testing).

    Returns:
        List of SessionMessage objects.

    Raises:
        SidecarError: If the session is not found or cannot be read.
    """
    # First find the session file
    sessions = list_sessions(project_path=project_path, projects_dir=projects_dir)
    session_info = None
    for s in sessions:
        if s.session_id == session_id:
            session_info = s
            break

    if session_info is None:
        raise SidecarError.session_not_found(session_id)

    jsonl_path = Path(session_info.full_path)
    if not jsonl_path.exists():
        raise SidecarError.session_read(f"JSONL file not found: {jsonl_path}")

    return parse_jsonl(jsonl_path)


def parse_jsonl(path: Path) -> list[SessionMessage]:
    """Parse a session JSONL file into SessionMessage objects."""
    messages: list[SessionMessage] = []

    try:
        text = path.read_text()
    except OSError as e:
        raise SidecarError.session_read(str(e)) from e

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = raw.get("type", "")

        # Build content list from the message payload
        content: list[dict] = []
        role = ""

        if msg_type in ("user", "assistant"):
            inner = raw.get("message", {})
            role = inner.get("role", msg_type)
            raw_content = inner.get("content", "")

            if isinstance(raw_content, str):
                content = [{"type": "text", "text": raw_content}]
            elif isinstance(raw_content, list):
                content = raw_content
            else:
                content = []
        elif msg_type == "summary":
            content = [{"type": "text", "text": raw.get("summary", "")}]

        messages.append(
            SessionMessage(
                type=msg_type,
                uuid=raw.get("uuid", ""),
                parent_uuid=raw.get("parentUuid", ""),
                timestamp=raw.get("timestamp", ""),
                role=role,
                content=content,
                raw=raw,
            )
        )

    return messages


def get_latest_session(
    project_path: str | None = None,
    projects_dir: Path | None = None,
) -> SessionInfo:
    """Get the most recently modified session.

    Raises:
        SidecarError: If no sessions are found.
    """
    sessions = list_sessions(project_path=project_path, projects_dir=projects_dir)
    if not sessions:
        raise SidecarError.session_not_found("no sessions found")
    return sessions[0]
