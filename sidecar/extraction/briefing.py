"""Pipeline orchestrator: reader → filter → differ → analyzer → briefing persistence."""

from __future__ import annotations

import json
from pathlib import Path

from ..errors import SidecarError
from .analyzer import analyze_session
from .differ import get_diff
from .filter import filter_session
from .models import AccumulatedInsights, SessionBriefing
from .reader import get_latest_session, list_sessions, read_session

BRIEFINGS_DIR = Path.home() / ".config" / "sidecar" / "briefings"
INSIGHTS_PATH = Path.home() / ".config" / "sidecar" / "insights.json"


def run_pipeline(
    session_id: str | None = None,
    project_path: str | None = None,
    projects_dir: Path | None = None,
    briefings_dir: Path | None = None,
) -> SessionBriefing:
    """Run the full extraction pipeline on a session.

    1. Read session messages
    2. Filter to high-signal content
    3. Get code diff
    4. Analyze via Haiku
    5. Persist briefing

    Args:
        session_id: Session to analyze. If None, uses latest.
        project_path: Filter to this project.
        projects_dir: Override Claude projects dir (for testing).
        briefings_dir: Override briefings dir (for testing).

    Returns:
        The generated SessionBriefing.
    """
    # Step 1: Resolve session
    if session_id is None:
        session_info = get_latest_session(
            project_path=project_path, projects_dir=projects_dir
        )
        session_id = session_info.session_id
        if not project_path:
            project_path = session_info.project_path

    # Step 2: Read messages
    messages = read_session(
        session_id, project_path=project_path, projects_dir=projects_dir
    )

    # Determine project path from first user message if not set
    if not project_path:
        for msg in messages:
            cwd = msg.raw.get("cwd", "")
            if cwd:
                project_path = cwd
                break
    if not project_path:
        project_path = ""

    # Step 3: Filter
    filtered = filter_session(session_id, messages)

    # Step 4: Diff
    diff = get_diff(project_path, messages)

    # Step 5: Analyze
    briefing = analyze_session(filtered, diff, project_path)

    # Step 6: Persist
    save_briefing(briefing, briefings_dir=briefings_dir)
    update_insights(briefing)

    return briefing


def save_briefing(
    briefing: SessionBriefing,
    briefings_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Save briefing as JSON and Markdown.

    Returns:
        Tuple of (json_path, md_path).
    """
    out_dir = briefings_dir or BRIEFINGS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"{briefing.session_id}.json"
    md_path = out_dir / f"{briefing.session_id}.md"

    json_path.write_text(json.dumps(briefing.to_dict(), indent=2))
    md_path.write_text(briefing.to_markdown())

    return json_path, md_path


def load_briefing(
    session_id: str,
    briefings_dir: Path | None = None,
) -> SessionBriefing | None:
    """Load a previously saved briefing by session ID."""
    out_dir = briefings_dir or BRIEFINGS_DIR
    json_path = out_dir / f"{session_id}.json"

    if not json_path.exists():
        return None

    try:
        data = json.loads(json_path.read_text())
        return SessionBriefing(
            session_id=data.get("session_id", session_id),
            project_path=data.get("project_path", ""),
            session_summary=data.get("session_summary", ""),
            what_got_built=data.get("what_got_built", []),
            how_pieces_connect=data.get("how_pieces_connect", ""),
            patterns_used=data.get("patterns_used", []),
            will_bite_you=data.get("will_bite_you", {}),
            concepts_touched=data.get("concepts_touched", []),
            created_at=data.get("created_at", ""),
        )
    except (json.JSONDecodeError, OSError) as e:
        raise SidecarError.briefing_error(f"Failed to load briefing: {e}") from e


def list_briefings(
    briefings_dir: Path | None = None,
) -> list[dict]:
    """List all saved briefings (summary info only)."""
    out_dir = briefings_dir or BRIEFINGS_DIR
    if not out_dir.is_dir():
        return []

    briefings = []
    for json_file in sorted(out_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(json_file.read_text())
            briefings.append(
                {
                    "session_id": data.get("session_id", json_file.stem),
                    "project_path": data.get("project_path", ""),
                    "session_summary": data.get("session_summary", ""),
                    "created_at": data.get("created_at", ""),
                }
            )
        except (json.JSONDecodeError, OSError):
            continue

    return briefings


def update_insights(
    briefing: SessionBriefing,
    insights_path: Path | None = None,
) -> AccumulatedInsights:
    """Update accumulated insights with data from a new briefing."""
    path = insights_path or INSIGHTS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing
    if path.exists():
        try:
            data = json.loads(path.read_text())
            insights = AccumulatedInsights.from_dict(data)
        except (json.JSONDecodeError, OSError):
            insights = AccumulatedInsights(project_path=briefing.project_path)
    else:
        insights = AccumulatedInsights(project_path=briefing.project_path)

    # Merge patterns
    for p in briefing.patterns_used:
        pattern_name = p.get("pattern", "")
        if pattern_name and pattern_name not in insights.recurring_patterns:
            insights.recurring_patterns.append(pattern_name)

    # Merge issues
    issue = briefing.will_bite_you.get("issue", "")
    if issue and issue not in insights.known_issues:
        insights.known_issues.append(issue)

    # Merge architecture notes
    if briefing.how_pieces_connect:
        note = briefing.how_pieces_connect
        if note not in insights.architecture_notes:
            insights.architecture_notes.append(note)

    insights.briefing_count += 1

    from datetime import datetime, timezone

    insights.last_updated = datetime.now(timezone.utc).isoformat()

    # Save
    path.write_text(json.dumps(insights.to_dict(), indent=2))

    return insights


def get_status(
    projects_dir: Path | None = None,
    briefings_dir: Path | None = None,
    insights_path: Path | None = None,
) -> dict:
    """Get overall sidecar status."""
    sessions = list_sessions(projects_dir=projects_dir)
    briefings = list_briefings(briefings_dir=briefings_dir)

    path = insights_path or INSIGHTS_PATH
    insights_data = {}
    if path.exists():
        try:
            insights_data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "total_sessions": len(sessions),
        "total_briefings": len(briefings),
        "insights": insights_data,
        "projects": list({s.project_path for s in sessions}),
    }
