"""Tests for sidecar.hooks.on_stop."""

from __future__ import annotations

import io
import json
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from sidecar.hooks import on_stop


class TestOnStopMain:
    """Tests for on_stop.main."""

    def test_normal_flow(self, tmp_path, monkeypatch):
        """Valid stdin, no existing lock -> spawn called, lock created."""
        session_id = "test-session-abc"
        stdin_data = {"session_id": session_id}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stdin_data)))

        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout)

        # Mock spawn to avoid actual subprocess
        mock_spawn = MagicMock()
        monkeypatch.setattr(on_stop, "spawn_background_analysis", mock_spawn)

        # Override lock directories
        monkeypatch.setattr("sidecar.hooks.common.LOCKS_DIR", tmp_path)
        monkeypatch.setattr("sidecar.hooks.on_stop.cleanup_stale_locks", lambda: None)
        monkeypatch.setattr(
            "sidecar.hooks.on_stop.is_locked",
            lambda sid: False,
        )
        monkeypatch.setattr(
            "sidecar.hooks.on_stop.create_lock",
            lambda sid: tmp_path / f"{sid}.lock",
        )

        on_stop.main()

        # Verify spawn was called
        mock_spawn.assert_called_once_with(session_id)

        # Verify hook output was written
        output = json.loads(stdout.getvalue())
        assert output["continue"] is True

    def test_skips_when_locked(self, tmp_path, monkeypatch):
        """Existing recent lock -> spawn NOT called."""
        session_id = "locked-session"
        stdin_data = {"session_id": session_id}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stdin_data)))

        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout)

        mock_spawn = MagicMock()
        monkeypatch.setattr(on_stop, "spawn_background_analysis", mock_spawn)
        monkeypatch.setattr("sidecar.hooks.on_stop.cleanup_stale_locks", lambda: None)
        monkeypatch.setattr(
            "sidecar.hooks.on_stop.is_locked",
            lambda sid: True,  # Locked!
        )

        on_stop.main()

        # Spawn should NOT be called
        mock_spawn.assert_not_called()

        # But output should still be written
        output = json.loads(stdout.getvalue())
        assert output["continue"] is True

    def test_stale_lock_allows_rerun(self, tmp_path, monkeypatch):
        """Stale lock -> spawn called."""
        session_id = "stale-lock-session"
        stdin_data = {"session_id": session_id}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stdin_data)))

        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout)

        mock_spawn = MagicMock()
        monkeypatch.setattr(on_stop, "spawn_background_analysis", mock_spawn)
        monkeypatch.setattr("sidecar.hooks.on_stop.cleanup_stale_locks", lambda: None)
        monkeypatch.setattr(
            "sidecar.hooks.on_stop.is_locked",
            lambda sid: False,  # Stale lock treated as not locked
        )
        monkeypatch.setattr(
            "sidecar.hooks.on_stop.create_lock",
            lambda sid: tmp_path / f"{sid}.lock",
        )

        on_stop.main()

        mock_spawn.assert_called_once_with(session_id)

    def test_missing_session_id(self, monkeypatch):
        """Stdin without session_id -> exits cleanly, no spawn."""
        stdin_data = {"cwd": "/some/path"}  # No session_id
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stdin_data)))

        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout)

        mock_spawn = MagicMock()
        monkeypatch.setattr(on_stop, "spawn_background_analysis", mock_spawn)

        on_stop.main()

        mock_spawn.assert_not_called()
        output = json.loads(stdout.getvalue())
        assert output["continue"] is True

    def test_empty_session_id(self, monkeypatch):
        """Empty session_id -> exits cleanly, no spawn."""
        stdin_data = {"session_id": ""}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stdin_data)))

        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout)

        mock_spawn = MagicMock()
        monkeypatch.setattr(on_stop, "spawn_background_analysis", mock_spawn)

        on_stop.main()

        mock_spawn.assert_not_called()

    def test_empty_stdin(self, monkeypatch):
        """No stdin data -> exits cleanly."""
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))

        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout)

        mock_spawn = MagicMock()
        monkeypatch.setattr(on_stop, "spawn_background_analysis", mock_spawn)

        on_stop.main()

        mock_spawn.assert_not_called()
        output = json.loads(stdout.getvalue())
        assert output["continue"] is True

    def test_exception_still_outputs(self, monkeypatch):
        """Force an exception -> hook output still written, exit 0."""
        stdin_data = {"session_id": "error-session"}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stdin_data)))

        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout)

        # Force an exception during is_locked
        monkeypatch.setattr("sidecar.hooks.on_stop.cleanup_stale_locks", lambda: None)
        monkeypatch.setattr(
            "sidecar.hooks.on_stop.is_locked",
            MagicMock(side_effect=RuntimeError("Forced error")),
        )

        # Should not raise
        on_stop.main()

        # Output should still be written
        output = json.loads(stdout.getvalue())
        assert output["continue"] is True

    def test_cleanup_called(self, tmp_path, monkeypatch):
        """Verify cleanup_stale_locks is called."""
        stdin_data = {"session_id": "cleanup-test"}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stdin_data)))

        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout)

        mock_cleanup = MagicMock()
        monkeypatch.setattr("sidecar.hooks.on_stop.cleanup_stale_locks", mock_cleanup)
        monkeypatch.setattr("sidecar.hooks.on_stop.is_locked", lambda sid: True)

        on_stop.main()

        mock_cleanup.assert_called_once()
