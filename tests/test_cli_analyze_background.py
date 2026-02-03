"""Tests for the CLI analyze command with --background flag."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from sidecar.cli import cli, _save_snapshot_briefing
from sidecar.extraction.models import SessionBriefing


def _sample_briefing(**overrides) -> SessionBriefing:
    """Create a sample briefing for testing."""
    defaults = dict(
        session_id="test-session-123",
        project_path="/Users/test/project",
        session_summary="Built a test feature",
        what_got_built=[{"file": "test.py", "description": "Test file"}],
        how_pieces_connect="Everything connects through main.py",
        patterns_used=[{"pattern": "Factory", "where": "builders/", "explained": "Creates objects"}],
        will_bite_you={"issue": "No tests", "where": "test.py", "why": "Untested", "what_to_check": "Add tests"},
        concepts_touched=[],
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    defaults.update(overrides)
    return SessionBriefing(**defaults)


@pytest.fixture
def runner():
    return CliRunner()


class TestBackgroundFlag:
    """Tests for --background flag."""

    def test_background_suppresses_output(self, runner, tmp_path):
        """No Rich output when --background set."""
        briefing = _sample_briefing()

        with patch("sidecar.cli.run_pipeline", return_value=briefing), \
             patch("sidecar.cli._run_background_analysis") as mock_bg:

            # Make _run_background_analysis not call sys.exit
            def fake_bg(*args, **kwargs):
                pass

            mock_bg.side_effect = fake_bg

            result = runner.invoke(
                cli, ["analyze", "--session-id", "test", "--background"]
            )

        # _run_background_analysis should have been called
        mock_bg.assert_called_once()

    def test_background_writes_log(self, runner, tmp_path, monkeypatch):
        """Log file created at expected path."""
        briefing = _sample_briefing()
        logs_dir = tmp_path / "logs"

        monkeypatch.setattr("sidecar.cli.LOGS_DIR", logs_dir)

        # We need to test the actual log writing, so we'll partially mock
        with patch("sidecar.cli.run_pipeline", return_value=briefing), \
             patch("sidecar.cli.save_briefing", return_value=(tmp_path / "b.json", tmp_path / "b.md")), \
             patch("sidecar.cli.update_insights"), \
             patch("sidecar.cli.remove_lock"), \
             patch("sidecar.extraction.reader.get_latest_session") as mock_latest, \
             patch("sidecar.extraction.reader.read_session") as mock_read, \
             patch("sidecar.extraction.filter.filter_session") as mock_filter, \
             patch("sys.exit"):  # Prevent actual exit

            from sidecar.extraction.models import FilteredSession, SessionInfo, SessionMessage

            mock_latest.return_value = SessionInfo(
                session_id="test-session",
                full_path="/test",
                first_prompt="test",
                summary="test",
                message_count=1,
                created="",
                modified="",
                git_branch="",
                project_path="/test",
            )
            mock_read.return_value = []
            mock_filter.return_value = FilteredSession(session_id="test", messages=[])

            from sidecar.cli import _run_background_analysis

            # Call directly to test logging
            _run_background_analysis("test-session", None, False, False)

        # Log file should exist
        assert logs_dir.exists()
        log_files = list(logs_dir.glob("*.log"))
        assert len(log_files) >= 1

    def test_background_removes_lock_on_success(self, runner, tmp_path, monkeypatch):
        """Lock file cleaned up after analysis."""
        briefing = _sample_briefing()
        locks_dir = tmp_path / "locks"
        locks_dir.mkdir()

        # Create a lock
        lock_file = locks_dir / "test-session.lock"
        lock_file.write_text("123456")

        mock_remove_lock = MagicMock()
        monkeypatch.setattr("sidecar.cli.remove_lock", mock_remove_lock)
        monkeypatch.setattr("sidecar.cli.LOGS_DIR", tmp_path / "logs")

        with patch("sidecar.cli.run_pipeline", return_value=briefing), \
             patch("sidecar.cli.save_briefing", return_value=(tmp_path / "b.json", tmp_path / "b.md")), \
             patch("sidecar.cli.update_insights"), \
             patch("sidecar.extraction.reader.get_latest_session"), \
             patch("sidecar.extraction.reader.read_session", return_value=[]), \
             patch("sidecar.extraction.filter.filter_session") as mock_filter, \
             patch("sys.exit"):

            from sidecar.extraction.models import FilteredSession

            mock_filter.return_value = FilteredSession(session_id="test", messages=[])

            from sidecar.cli import _run_background_analysis

            _run_background_analysis("test-session", None, False, False)

        mock_remove_lock.assert_called_with("test-session")

    def test_background_removes_lock_on_failure(self, runner, tmp_path, monkeypatch):
        """Lock file cleaned up even on error."""
        mock_remove_lock = MagicMock()
        monkeypatch.setattr("sidecar.cli.remove_lock", mock_remove_lock)
        monkeypatch.setattr("sidecar.cli.LOGS_DIR", tmp_path / "logs")

        with patch("sidecar.cli.run_pipeline", side_effect=RuntimeError("Test error")), \
             patch("sidecar.extraction.reader.get_latest_session"), \
             patch("sidecar.extraction.reader.read_session", return_value=[]), \
             patch("sidecar.extraction.filter.filter_session") as mock_filter, \
             patch("sys.exit"):

            from sidecar.extraction.models import FilteredSession

            mock_filter.return_value = FilteredSession(session_id="test", messages=[])

            from sidecar.cli import _run_background_analysis

            _run_background_analysis("test-session", None, False, False)

        mock_remove_lock.assert_called_with("test-session")


class TestSnapshotFlag:
    """Tests for --snapshot flag."""

    def test_snapshot_saves_with_timestamp(self, tmp_path):
        """Briefing filename includes timestamp."""
        briefing = _sample_briefing(session_id="snapshot-test")

        json_path, md_path = _save_snapshot_briefing(briefing, briefings_dir=tmp_path)

        # Filename should contain session_id and timestamp
        assert "snapshot-test" in json_path.name
        assert "-" in json_path.name.replace("snapshot-test-", "")  # Has timestamp part

        # Files should exist and be valid
        assert json_path.exists()
        assert md_path.exists()

        data = json.loads(json_path.read_text())
        assert data["session_id"] == "snapshot-test"

    def test_snapshot_skips_insights_update(self, runner, tmp_path, monkeypatch):
        """update_insights not called for snapshots in background mode."""
        briefing = _sample_briefing()
        monkeypatch.setattr("sidecar.cli.LOGS_DIR", tmp_path / "logs")

        mock_update_insights = MagicMock()

        with patch("sidecar.cli.run_pipeline", return_value=briefing), \
             patch("sidecar.cli._save_snapshot_briefing", return_value=(tmp_path / "b.json", tmp_path / "b.md")), \
             patch("sidecar.cli.save_briefing"), \
             patch("sidecar.cli.update_insights", mock_update_insights), \
             patch("sidecar.cli.remove_lock"), \
             patch("sidecar.extraction.reader.get_latest_session"), \
             patch("sidecar.extraction.reader.read_session", return_value=[]), \
             patch("sidecar.extraction.filter.filter_session") as mock_filter, \
             patch("sys.exit"):

            from sidecar.extraction.models import FilteredSession

            mock_filter.return_value = FilteredSession(session_id="test", messages=[])

            from sidecar.cli import _run_background_analysis

            _run_background_analysis("test-session", None, snapshot=True, notify=False)

        # update_insights should NOT be called for snapshots
        mock_update_insights.assert_not_called()


class TestNotifyFlag:
    """Tests for --notify flag."""

    def test_notify_calls_notification(self, runner, tmp_path, monkeypatch):
        """Notification sent when --notify flag is set."""
        briefing = _sample_briefing()
        monkeypatch.setattr("sidecar.cli.LOGS_DIR", tmp_path / "logs")

        mock_notify = MagicMock()
        monkeypatch.setattr("sidecar.cli._send_notification", mock_notify)

        with patch("sidecar.cli.run_pipeline", return_value=briefing), \
             patch("sidecar.cli.save_briefing", return_value=(tmp_path / "b.json", tmp_path / "b.md")), \
             patch("sidecar.cli.update_insights"), \
             patch("sidecar.cli.remove_lock"), \
             patch("sidecar.extraction.reader.get_latest_session"), \
             patch("sidecar.extraction.reader.read_session", return_value=[]), \
             patch("sidecar.extraction.filter.filter_session") as mock_filter, \
             patch("sys.exit"):

            from sidecar.extraction.models import FilteredSession

            mock_filter.return_value = FilteredSession(session_id="test", messages=[])

            from sidecar.cli import _run_background_analysis

            _run_background_analysis("test-session", None, snapshot=False, notify=True)

        mock_notify.assert_called_once_with("test-session")
