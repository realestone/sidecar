"""MCP tools for session extraction."""

from __future__ import annotations

import json

from ..errors import SidecarError
from ..extraction.briefing import (
    get_status,
    list_briefings,
    load_briefing,
    run_pipeline,
)
from ..extraction.reader import list_sessions


def register_tools(mcp, storage) -> None:
    """Register session extraction MCP tools.

    Note: storage parameter accepted for API consistency with prompts.register_tools
    but not used directly — sessions read from Claude's filesystem, not our DB.
    """

    @mcp.tool()
    def session_analyze(
        session_id: str | None = None,
        project_path: str | None = None,
    ) -> str:
        """Analyze a Claude Code session and generate a development briefing.

        Uses the latest session if no session_id provided.
        """
        try:
            briefing = run_pipeline(
                session_id=session_id, project_path=project_path
            )
            return json.dumps(
                {
                    "status": "analyzed",
                    "session_id": briefing.session_id,
                    "summary": briefing.session_summary,
                    "briefing": briefing.to_dict(),
                }
            )
        except SidecarError:
            raise
        except Exception as e:
            raise SidecarError.analyzer_error(str(e)) from e

    @mcp.tool()
    def session_list(
        project_path: str | None = None,
    ) -> str:
        """List Claude Code sessions for a project."""
        sessions = list_sessions(project_path=project_path)
        return json.dumps([s.to_dict() for s in sessions])

    @mcp.tool()
    def session_briefing(
        session_id: str | None = None,
    ) -> str:
        """Get a previously generated briefing for a session.

        If no session_id, returns the most recent briefing.
        """
        if session_id:
            briefing = load_briefing(session_id)
            if not briefing:
                raise SidecarError.session_not_found(session_id)
            return json.dumps(briefing.to_dict())
        else:
            briefings = list_briefings()
            if not briefings:
                return json.dumps(
                    {"status": "no_briefings", "message": "No briefings generated yet."}
                )
            return json.dumps(briefings)

    @mcp.tool()
    def sidecar_status() -> str:
        """Get overall sidecar status: sessions, briefings, insights."""
        status = get_status()
        return json.dumps(status)
