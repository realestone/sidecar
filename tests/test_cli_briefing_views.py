"""Tests for briefing command progressive disclosure views."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from sidecar.cli import cli
from sidecar.extraction.models import SessionBriefing


def _sample_briefing(**overrides) -> SessionBriefing:
    """Create a sample briefing for testing."""
    defaults = dict(
        session_id="test-session-123",
        project_path="/Users/test/project",
        session_summary="Built a comprehensive test feature with multiple components",
        what_got_built=[
            {"file": "main.py", "description": "Entry point", "key_code": "def main(): ..."},
            {"file": "utils.py", "description": "Helper functions", "key_code": "def helper(): ..."},
        ],
        how_pieces_connect="main.py imports utils.py for helper functions",
        patterns_used=[
            {"pattern": "Factory", "where": "builders/", "explained": "Creates objects dynamically"},
            {"pattern": "Singleton", "where": "config.py", "explained": "Single config instance"},
        ],
        will_bite_you={
            "issue": "No input validation",
            "where": "main.py:42",
            "why": "User input not sanitized",
            "what_to_check": "Add validation to parse_args()",
        },
        concepts_touched=[
            {"concept": "Dependency Injection", "in_code": "main.py", "evidence": "Uses DI", "developer_understood": True},
        ],
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    defaults.update(overrides)
    return SessionBriefing(**defaults)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sample_briefing():
    return _sample_briefing()


class TestCompactView:
    """Tests for default compact view."""

    def test_compact_view_default(self, runner, sample_briefing):
        """No flags -> shows summary line, will_bite_you, file list only."""
        with patch("sidecar.cli.load_briefing", return_value=sample_briefing):
            result = runner.invoke(cli, ["briefing", "-s", "test-session-123"])

        assert result.exit_code == 0

        # Should show session ID and summary
        assert "test-ses" in result.output  # truncated ID (8 chars)
        assert "test feature" in result.output or "Built" in result.output

        # Should show file count
        assert "2 files" in result.output

        # Should show will_bite_you warning
        assert "Warning" in result.output or "validation" in result.output.lower()

        # Should show file names
        assert "main.py" in result.output
        assert "utils.py" in result.output

    def test_compact_hides_patterns(self, runner, sample_briefing):
        """Default view does NOT show patterns table."""
        with patch("sidecar.cli.load_briefing", return_value=sample_briefing):
            result = runner.invoke(cli, ["briefing", "-s", "test-session-123"])

        # Should not show pattern details
        assert "Factory" not in result.output
        assert "Singleton" not in result.output
        assert "Creates objects dynamically" not in result.output

    def test_compact_hides_concepts(self, runner, sample_briefing):
        """Default view does NOT show concepts."""
        with patch("sidecar.cli.load_briefing", return_value=sample_briefing):
            result = runner.invoke(cli, ["briefing", "-s", "test-session-123"])

        # Should not show concept details
        assert "Dependency Injection" not in result.output

    def test_compact_hides_descriptions(self, runner, sample_briefing):
        """Default view shows file names but not full descriptions."""
        with patch("sidecar.cli.load_briefing", return_value=sample_briefing):
            result = runner.invoke(cli, ["briefing", "-s", "test-session-123"])

        # File names shown
        assert "main.py" in result.output

        # But not the full "Entry point" description in compact mode
        # (it shows files as a comma-separated list)
        assert "Files:" in result.output


class TestDetailView:
    """Tests for --detail view."""

    def test_detail_view(self, runner, sample_briefing):
        """--detail -> includes what_got_built descriptions."""
        with patch("sidecar.cli.load_briefing", return_value=sample_briefing):
            result = runner.invoke(cli, ["briefing", "-s", "test-session-123", "--detail"])

        assert result.exit_code == 0

        # Should show summary
        assert "Summary" in result.output

        # Should show what_got_built with descriptions
        assert "What Got Built" in result.output
        assert "main.py" in result.output
        assert "Entry point" in result.output

        # Should show how_pieces_connect
        assert "How Pieces Connect" in result.output

        # Should show will_bite_you
        assert "Will Bite You" in result.output

    def test_detail_hides_patterns(self, runner, sample_briefing):
        """--detail view still hides patterns table."""
        with patch("sidecar.cli.load_briefing", return_value=sample_briefing):
            result = runner.invoke(cli, ["briefing", "-s", "test-session-123", "--detail"])

        # Patterns not shown in detail view
        assert "Patterns Used" not in result.output
        assert "Factory" not in result.output


class TestFullView:
    """Tests for --full view."""

    def test_full_view(self, runner, sample_briefing):
        """--full -> shows everything (patterns, concepts, etc.)."""
        with patch("sidecar.cli.load_briefing", return_value=sample_briefing):
            result = runner.invoke(cli, ["briefing", "-s", "test-session-123", "--full"])

        assert result.exit_code == 0

        # Should show all sections from markdown
        assert "Session Briefing" in result.output
        assert "Summary" in result.output
        assert "What Got Built" in result.output

        # Patterns shown
        assert "Patterns Used" in result.output
        assert "Factory" in result.output
        assert "Singleton" in result.output

        # Will bite you
        assert "Will Bite You" in result.output

        # Concepts
        assert "Concepts Touched" in result.output
        assert "Dependency Injection" in result.output


class TestBriefingNotFound:
    """Tests for briefing not found."""

    def test_briefing_not_found(self, runner):
        """Non-existent briefing shows error."""
        with patch("sidecar.cli.load_briefing", return_value=None):
            result = runner.invoke(cli, ["briefing", "-s", "nonexistent"])

        assert result.exit_code == 1
        assert "No briefing found" in result.output


class TestBriefingList:
    """Tests for briefing list (no session ID)."""

    def test_briefing_list(self, runner):
        """No session ID -> shows list of briefings."""
        briefings_list = [
            {
                "session_id": "session-1",
                "project_path": "/project1",
                "session_summary": "First session summary",
                "created_at": "2024-01-01T00:00:00Z",
            },
            {
                "session_id": "session-2",
                "project_path": "/project2",
                "session_summary": "Second session summary",
                "created_at": "2024-01-02T00:00:00Z",
            },
        ]

        with patch("sidecar.cli.list_briefings", return_value=briefings_list):
            result = runner.invoke(cli, ["briefing"])

        assert result.exit_code == 0
        assert "Generated Briefings" in result.output
        assert "session-1" in result.output
        assert "session-2" in result.output

    def test_briefing_list_empty(self, runner):
        """Empty briefings list shows message."""
        with patch("sidecar.cli.list_briefings", return_value=[]):
            result = runner.invoke(cli, ["briefing"])

        assert result.exit_code == 0
        assert "No briefings generated yet" in result.output

    def test_list_ignores_detail_flag(self, runner):
        """List view stays the same regardless of --detail flag."""
        briefings_list = [
            {"session_id": "session-1", "session_summary": "Test", "created_at": ""},
        ]

        with patch("sidecar.cli.list_briefings", return_value=briefings_list):
            result_normal = runner.invoke(cli, ["briefing"])
            result_detail = runner.invoke(cli, ["briefing", "--detail"])

        # Both should show the list
        assert "Generated Briefings" in result_normal.output
        assert "Generated Briefings" in result_detail.output
