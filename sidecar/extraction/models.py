from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class SessionInfo:
    """Metadata about a Claude Code session from sessions-index.json."""

    session_id: str
    full_path: str
    first_prompt: str
    summary: str
    message_count: int
    created: str
    modified: str
    git_branch: str
    project_path: str

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "full_path": self.full_path,
            "first_prompt": self.first_prompt,
            "summary": self.summary,
            "message_count": self.message_count,
            "created": self.created,
            "modified": self.modified,
            "git_branch": self.git_branch,
            "project_path": self.project_path,
        }


@dataclass
class SessionMessage:
    """A single message from a session JSONL file."""

    type: str  # "user", "assistant", "progress", "summary", "file-history-snapshot"
    uuid: str = ""
    parent_uuid: str = ""
    timestamp: str = ""
    role: str = ""  # "user" or "assistant"
    content: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class FileDiff:
    """A single file's diff information."""

    path: str
    status: str  # "added", "modified", "deleted", "renamed"
    additions: int = 0
    deletions: int = 0
    diff_text: str = ""


@dataclass
class CodeDiff:
    """Aggregate diff for a session."""

    files: list[FileDiff] = field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0
    truncated: bool = False
    source: str = "git"  # "git" or "tool_calls"


@dataclass
class FilterStats:
    """Statistics from the filter stage."""

    original_count: int = 0
    kept_count: int = 0
    removed_progress: int = 0
    removed_file_history: int = 0
    truncated_messages: int = 0
    stripped_tool_content: int = 0


@dataclass
class FilteredSession:
    """Output of the filter stage."""

    session_id: str
    messages: list[SessionMessage] = field(default_factory=list)
    stats: FilterStats = field(default_factory=FilterStats)


@dataclass
class SessionBriefing:
    """Analyzer output matching the spec's JSON schema."""

    session_id: str
    project_path: str
    session_summary: str = ""
    what_got_built: list[dict] = field(default_factory=list)
    how_pieces_connect: str = ""
    patterns_used: list[dict] = field(default_factory=list)
    will_bite_you: dict = field(default_factory=dict)
    concepts_touched: list[dict] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "project_path": self.project_path,
            "session_summary": self.session_summary,
            "what_got_built": self.what_got_built,
            "how_pieces_connect": self.how_pieces_connect,
            "patterns_used": self.patterns_used,
            "will_bite_you": self.will_bite_you,
            "concepts_touched": self.concepts_touched,
            "created_at": self.created_at,
        }

    def to_markdown(self) -> str:
        lines = [f"# Session Briefing: {self.session_id}", ""]
        lines.append(f"**Project:** {self.project_path}")
        lines.append(f"**Generated:** {self.created_at}")
        lines.append("")

        lines.append("## Summary")
        lines.append(self.session_summary)
        lines.append("")

        if self.what_got_built:
            lines.append("## What Got Built")
            for item in self.what_got_built:
                lines.append(f"### `{item.get('file', 'unknown')}`")
                lines.append(item.get("description", ""))
                if item.get("key_code"):
                    lines.append(f"- **Key code:** {item['key_code']}")
                for decision in item.get("key_decisions", []):
                    lines.append(f"- {decision}")
                lines.append("")

        if self.how_pieces_connect:
            lines.append("## How Pieces Connect")
            lines.append(self.how_pieces_connect)
            lines.append("")

        if self.patterns_used:
            lines.append("## Patterns Used")
            for p in self.patterns_used:
                lines.append(
                    f"- **{p.get('pattern', '')}** ({p.get('where', '')}): "
                    f"{p.get('explained', '')}"
                )
            lines.append("")

        if self.will_bite_you:
            lines.append("## Will Bite You")
            lines.append(f"**Issue:** {self.will_bite_you.get('issue', '')}")
            lines.append(f"**Where:** {self.will_bite_you.get('where', '')}")
            lines.append(f"**Why:** {self.will_bite_you.get('why', '')}")
            lines.append(
                f"**What to check:** {self.will_bite_you.get('what_to_check', '')}"
            )
            lines.append("")

        if self.concepts_touched:
            lines.append("## Concepts Touched")
            for c in self.concepts_touched:
                understood = c.get("developer_understood", False)
                marker = "Y" if understood else "N"
                lines.append(
                    f"- **{c.get('concept', '')}** [{marker}] "
                    f"({c.get('in_code', '')}): {c.get('evidence', '')}"
                )
            lines.append("")

        return "\n".join(lines)


@dataclass
class AccumulatedInsights:
    """Cross-session tracking, persisted to insights.json."""

    project_path: str
    recurring_patterns: list[str] = field(default_factory=list)
    known_issues: list[str] = field(default_factory=list)
    architecture_notes: list[str] = field(default_factory=list)
    last_updated: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    briefing_count: int = 0

    def to_dict(self) -> dict:
        return {
            "project_path": self.project_path,
            "recurring_patterns": self.recurring_patterns,
            "known_issues": self.known_issues,
            "architecture_notes": self.architecture_notes,
            "last_updated": self.last_updated,
            "briefing_count": self.briefing_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AccumulatedInsights:
        return cls(
            project_path=data.get("project_path", ""),
            recurring_patterns=data.get("recurring_patterns", []),
            known_issues=data.get("known_issues", []),
            architecture_notes=data.get("architecture_notes", []),
            last_updated=data.get("last_updated", ""),
            briefing_count=data.get("briefing_count", 0),
        )
