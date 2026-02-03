"""Tests for sidecar.cli via Click's CliRunner."""

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from sidecar.cli import cli
from sidecar.extraction.models import SessionBriefing, SessionInfo


def _sample_briefing():
    return SessionBriefing(
        session_id="abc-123",
        project_path="/Users/test/project",
        session_summary="Built a test project.",
        what_got_built=[
            {"file": "main.py", "description": "Entry point", "key_code": "main()"}
        ],
        how_pieces_connect="main.py imports lib.py",
        patterns_used=[
            {"pattern": "Factory", "where": "lib.py:create", "explained": "Creates objects"}
        ],
        will_bite_you={
            "issue": "No tests",
            "where": "main.py",
            "why": "Untested code",
            "what_to_check": "Add tests",
        },
    )


def _sample_sessions():
    return [
        SessionInfo(
            session_id="s1",
            full_path="/tmp/s1.jsonl",
            first_prompt="hello",
            summary="Test session 1",
            message_count=10,
            created="2026-01-01T00:00:00Z",
            modified="2026-01-01T12:00:00Z",
            git_branch="main",
            project_path="/Users/test/project",
        ),
        SessionInfo(
            session_id="s2",
            full_path="/tmp/s2.jsonl",
            first_prompt="hi",
            summary="Test session 2",
            message_count=5,
            created="2026-01-02T00:00:00Z",
            modified="2026-01-02T12:00:00Z",
            git_branch="",
            project_path="/Users/test/project",
        ),
    ]


class TestAnalyzeCommand:
    def test_analyze_text_output(self):
        runner = CliRunner()
        with patch("sidecar.cli.run_pipeline", return_value=_sample_briefing()):
            result = runner.invoke(cli, ["analyze"])
        assert result.exit_code == 0
        assert "Built a test project" in result.output

    def test_analyze_json_output(self):
        runner = CliRunner()
        with patch("sidecar.cli.run_pipeline", return_value=_sample_briefing()):
            result = runner.invoke(cli, ["analyze", "-o", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["session_summary"] == "Built a test project."

    def test_analyze_markdown_output(self):
        runner = CliRunner()
        with patch("sidecar.cli.run_pipeline", return_value=_sample_briefing()):
            result = runner.invoke(cli, ["analyze", "-o", "markdown"])
        assert result.exit_code == 0
        assert "# Session Briefing:" in result.output

    def test_analyze_with_session_id(self):
        runner = CliRunner()
        with patch("sidecar.cli.run_pipeline", return_value=_sample_briefing()) as mock:
            result = runner.invoke(cli, ["analyze", "-s", "test-id"])
        assert result.exit_code == 0
        mock.assert_called_once_with(session_id="test-id", project_path=None)


class TestSessionsCommand:
    def test_lists_sessions(self):
        runner = CliRunner()
        with patch("sidecar.cli.list_sessions", return_value=_sample_sessions()):
            result = runner.invoke(cli, ["sessions"])
        assert result.exit_code == 0
        assert "Test session 1" in result.output
        assert "Test session 2" in result.output

    def test_empty_sessions(self):
        runner = CliRunner()
        with patch("sidecar.cli.list_sessions", return_value=[]):
            result = runner.invoke(cli, ["sessions"])
        assert result.exit_code == 0
        assert "No sessions found" in result.output


class TestBriefingCommand:
    def test_view_specific(self):
        runner = CliRunner()
        with patch("sidecar.cli.load_briefing", return_value=_sample_briefing()):
            result = runner.invoke(cli, ["briefing", "-s", "abc-123"])
        assert result.exit_code == 0
        assert "Built a test project" in result.output

    def test_not_found(self):
        runner = CliRunner()
        with patch("sidecar.cli.load_briefing", return_value=None):
            result = runner.invoke(cli, ["briefing", "-s", "nope"])
        assert result.exit_code == 1

    def test_list_briefings(self):
        runner = CliRunner()
        briefings = [
            {"session_id": "s1", "session_summary": "Session one", "created_at": "2026-01-01T00:00:00Z"},
            {"session_id": "s2", "session_summary": "Session two", "created_at": "2026-01-02T00:00:00Z"},
        ]
        with patch("sidecar.cli.list_briefings", return_value=briefings):
            result = runner.invoke(cli, ["briefing"])
        assert result.exit_code == 0
        assert "Session one" in result.output


class TestStatusCommand:
    def test_status(self):
        runner = CliRunner()
        mock_status = {
            "total_sessions": 5,
            "total_briefings": 2,
            "projects": ["/Users/test/project"],
            "insights": {"briefing_count": 2, "recurring_patterns": ["Factory"], "known_issues": []},
        }
        with patch("sidecar.cli.get_status", return_value=mock_status):
            result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "Sessions: 5" in result.output
        assert "Briefings: 2" in result.output
