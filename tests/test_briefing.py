"""Tests for sidecar.extraction.briefing — persistence and pipeline helpers."""

import json

import pytest

from sidecar.extraction.briefing import (
    list_briefings,
    load_briefing,
    save_briefing,
    update_insights,
    get_status,
)
from sidecar.extraction.models import AccumulatedInsights, SessionBriefing


def _sample_briefing(**overrides) -> SessionBriefing:
    defaults = dict(
        session_id="test-session-1",
        project_path="/Users/test/project",
        session_summary="Built a test project with two modules.",
        what_got_built=[
            {
                "file": "main.py",
                "description": "Entry point",
                "key_code": "main() function",
                "key_decisions": ["Used click for CLI"],
            }
        ],
        how_pieces_connect="main.py imports from lib.py.",
        patterns_used=[
            {
                "pattern": "Factory method",
                "where": "lib.py:create",
                "explained": "Creates instances dynamically.",
            }
        ],
        will_bite_you={
            "issue": "No error handling",
            "where": "main.py:run",
            "why": "Exceptions propagate uncaught",
            "what_to_check": "Add try/except in main",
        },
        concepts_touched=[
            {
                "concept": "Click CLI",
                "in_code": "main.py",
                "developer_understood": True,
                "evidence": "User asked about click groups",
            }
        ],
    )
    defaults.update(overrides)
    return SessionBriefing(**defaults)


class TestSaveBriefing:
    def test_creates_json_and_md(self, tmp_path):
        briefing = _sample_briefing()
        json_path, md_path = save_briefing(briefing, briefings_dir=tmp_path)

        assert json_path.exists()
        assert md_path.exists()
        assert json_path.name == "test-session-1.json"
        assert md_path.name == "test-session-1.md"

    def test_json_content_valid(self, tmp_path):
        briefing = _sample_briefing()
        json_path, _ = save_briefing(briefing, briefings_dir=tmp_path)

        data = json.loads(json_path.read_text())
        assert data["session_id"] == "test-session-1"
        assert data["session_summary"] == "Built a test project with two modules."
        assert len(data["what_got_built"]) == 1
        assert data["what_got_built"][0]["file"] == "main.py"

    def test_md_content(self, tmp_path):
        briefing = _sample_briefing()
        _, md_path = save_briefing(briefing, briefings_dir=tmp_path)

        md = md_path.read_text()
        assert "# Session Briefing:" in md
        assert "Built a test project" in md
        assert "main.py" in md
        assert "Factory method" in md
        assert "No error handling" in md

    def test_creates_dir_if_missing(self, tmp_path):
        out = tmp_path / "sub" / "dir"
        save_briefing(_sample_briefing(), briefings_dir=out)
        assert out.is_dir()


class TestLoadBriefing:
    def test_round_trip(self, tmp_path):
        original = _sample_briefing()
        save_briefing(original, briefings_dir=tmp_path)
        loaded = load_briefing("test-session-1", briefings_dir=tmp_path)

        assert loaded is not None
        assert loaded.session_id == original.session_id
        assert loaded.session_summary == original.session_summary
        assert loaded.what_got_built == original.what_got_built
        assert loaded.patterns_used == original.patterns_used

    def test_not_found(self, tmp_path):
        result = load_briefing("nonexistent", briefings_dir=tmp_path)
        assert result is None


class TestListBriefings:
    def test_empty(self, tmp_path):
        assert list_briefings(briefings_dir=tmp_path) == []

    def test_lists_saved(self, tmp_path):
        save_briefing(_sample_briefing(session_id="s1"), briefings_dir=tmp_path)
        save_briefing(_sample_briefing(session_id="s2"), briefings_dir=tmp_path)

        result = list_briefings(briefings_dir=tmp_path)
        assert len(result) == 2
        ids = {b["session_id"] for b in result}
        assert ids == {"s1", "s2"}

    def test_nonexistent_dir(self, tmp_path):
        assert list_briefings(briefings_dir=tmp_path / "nope") == []


class TestUpdateInsights:
    def test_creates_new_insights(self, tmp_path):
        path = tmp_path / "insights.json"
        briefing = _sample_briefing()
        result = update_insights(briefing, insights_path=path)

        assert path.exists()
        assert result.briefing_count == 1
        assert "Factory method" in result.recurring_patterns
        assert "No error handling" in result.known_issues

    def test_merges_with_existing(self, tmp_path):
        path = tmp_path / "insights.json"

        # First briefing
        update_insights(_sample_briefing(), insights_path=path)

        # Second briefing with different pattern
        b2 = _sample_briefing(
            session_id="s2",
            patterns_used=[
                {"pattern": "Singleton", "where": "db.py", "explained": "One instance"}
            ],
            will_bite_you={"issue": "Memory leak", "where": "cache.py"},
        )
        result = update_insights(b2, insights_path=path)

        assert result.briefing_count == 2
        assert "Factory method" in result.recurring_patterns
        assert "Singleton" in result.recurring_patterns
        assert "No error handling" in result.known_issues
        assert "Memory leak" in result.known_issues

    def test_deduplicates(self, tmp_path):
        path = tmp_path / "insights.json"

        # Same briefing twice
        update_insights(_sample_briefing(), insights_path=path)
        result = update_insights(_sample_briefing(), insights_path=path)

        assert result.recurring_patterns.count("Factory method") == 1
        assert result.known_issues.count("No error handling") == 1


class TestGetStatus:
    def test_empty(self, tmp_path):
        status = get_status(
            projects_dir=tmp_path / "projects",
            briefings_dir=tmp_path / "briefings",
            insights_path=tmp_path / "insights.json",
        )
        assert status["total_sessions"] == 0
        assert status["total_briefings"] == 0
        assert status["insights"] == {}
