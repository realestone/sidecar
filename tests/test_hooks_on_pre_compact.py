"""Tests for sidecar.hooks.on_pre_compact."""

from __future__ import annotations

import io
import json
import sys
from unittest.mock import MagicMock

import pytest

from sidecar.hooks import on_pre_compact


class TestOnPreCompactMain:
    """Tests for on_pre_compact.main."""

    def test_spawns_with_snapshot(self, monkeypatch):
        """Verify spawn_background_analysis called with snapshot=True."""
        session_id = "pre-compact-session"
        stdin_data = {"session_id": session_id}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stdin_data)))

        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout)

        mock_spawn = MagicMock()
        monkeypatch.setattr(on_pre_compact, "spawn_background_analysis", mock_spawn)

        on_pre_compact.main()

        # Verify spawn was called with snapshot=True
        mock_spawn.assert_called_once_with(session_id, snapshot=True)

        # Verify hook output
        output = json.loads(stdout.getvalue())
        assert output["continue"] is True

    def test_no_dedup(self, monkeypatch):
        """Verify no lock checking (PreCompact doesn't need it)."""
        session_id = "no-dedup-session"
        stdin_data = {"session_id": session_id}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stdin_data)))

        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout)

        mock_spawn = MagicMock()
        monkeypatch.setattr(on_pre_compact, "spawn_background_analysis", mock_spawn)

        # No lock-related functions should be called
        on_pre_compact.main()

        mock_spawn.assert_called_once()

    def test_missing_session_id(self, monkeypatch):
        """Stdin without session_id -> exits cleanly."""
        stdin_data = {"cwd": "/some/path"}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stdin_data)))

        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout)

        mock_spawn = MagicMock()
        monkeypatch.setattr(on_pre_compact, "spawn_background_analysis", mock_spawn)

        on_pre_compact.main()

        mock_spawn.assert_not_called()
        output = json.loads(stdout.getvalue())
        assert output["continue"] is True

    def test_empty_stdin(self, monkeypatch):
        """No stdin data -> exits cleanly."""
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))

        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout)

        mock_spawn = MagicMock()
        monkeypatch.setattr(on_pre_compact, "spawn_background_analysis", mock_spawn)

        on_pre_compact.main()

        mock_spawn.assert_not_called()

    def test_exception_still_outputs(self, monkeypatch):
        """Exception is caught, hook output still written."""
        stdin_data = {"session_id": "error-session"}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stdin_data)))

        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout)

        # Force spawn to fail
        mock_spawn = MagicMock(side_effect=RuntimeError("Spawn failed"))
        monkeypatch.setattr(on_pre_compact, "spawn_background_analysis", mock_spawn)

        # Should not raise
        on_pre_compact.main()

        # Output should still be written
        output = json.loads(stdout.getvalue())
        assert output["continue"] is True
