"""Tests for sidecar.hooks.common."""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sidecar.hooks.common import (
    cleanup_stale_locks,
    create_lock,
    is_locked,
    read_hook_stdin,
    remove_lock,
    spawn_background_analysis,
    write_hook_output,
)


class TestReadHookStdin:
    """Tests for read_hook_stdin."""

    def test_valid_json(self, monkeypatch):
        """Valid JSON input is parsed correctly."""
        data = {"session_id": "abc123", "cwd": "/home/user"}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(data)))

        result = read_hook_stdin()

        assert result == data
        assert result["session_id"] == "abc123"

    def test_empty_stdin(self, monkeypatch):
        """Empty stdin returns None."""
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))

        result = read_hook_stdin()

        assert result is None

    def test_whitespace_only(self, monkeypatch):
        """Whitespace-only stdin returns None."""
        monkeypatch.setattr(sys, "stdin", io.StringIO("   \n\t  "))

        result = read_hook_stdin()

        assert result is None

    def test_invalid_json(self, monkeypatch):
        """Invalid JSON returns None (no exception)."""
        monkeypatch.setattr(sys, "stdin", io.StringIO("not valid json {{{"))

        result = read_hook_stdin()

        assert result is None

    def test_read_error(self, monkeypatch):
        """OSError during read returns None."""
        mock_stdin = MagicMock()
        mock_stdin.read.side_effect = OSError("Read error")
        monkeypatch.setattr(sys, "stdin", mock_stdin)

        result = read_hook_stdin()

        assert result is None


class TestWriteHookOutput:
    """Tests for write_hook_output."""

    def test_default_output(self, monkeypatch):
        """Default output has continue=true and suppressOutput=true."""
        output = io.StringIO()
        monkeypatch.setattr(sys, "stdout", output)

        write_hook_output()

        result = json.loads(output.getvalue())
        assert result["continue"] is True
        assert result["suppressOutput"] is True

    def test_custom_values(self, monkeypatch):
        """Custom values are respected."""
        output = io.StringIO()
        monkeypatch.setattr(sys, "stdout", output)

        write_hook_output(continue_=False, suppress=False)

        result = json.loads(output.getvalue())
        assert result["continue"] is False
        assert result["suppressOutput"] is False

    def test_write_error_handled(self, monkeypatch):
        """OSError during write is silently handled."""
        mock_stdout = MagicMock()
        mock_stdout.write.side_effect = OSError("Write error")
        monkeypatch.setattr(sys, "stdout", mock_stdout)

        # Should not raise
        write_hook_output()


class TestLockFunctions:
    """Tests for lock file functions."""

    def test_create_and_check_lock(self, tmp_path):
        """Create lock, verify is_locked returns True."""
        session_id = "test-session-123"

        lock_path = create_lock(session_id, locks_dir=tmp_path)

        assert lock_path.exists()
        assert lock_path.name == f"{session_id}.lock"
        assert is_locked(session_id, locks_dir=tmp_path)

    def test_not_locked(self, tmp_path):
        """No lock file, is_locked returns False."""
        session_id = "nonexistent-session"

        assert not is_locked(session_id, locks_dir=tmp_path)

    def test_stale_lock(self, tmp_path):
        """Stale lock (old timestamp) returns False."""
        session_id = "stale-session"
        lock_path = tmp_path / f"{session_id}.lock"

        # Create lock with timestamp from 2 minutes ago
        old_time = time.time() - 120
        lock_path.write_text(str(old_time))

        # With default max_age of 60s, this should be stale
        assert not is_locked(session_id, max_age_seconds=60, locks_dir=tmp_path)

    def test_fresh_lock(self, tmp_path):
        """Fresh lock within max_age returns True."""
        session_id = "fresh-session"
        lock_path = tmp_path / f"{session_id}.lock"

        # Create lock with current timestamp
        lock_path.write_text(str(time.time()))

        assert is_locked(session_id, max_age_seconds=60, locks_dir=tmp_path)

    def test_remove_lock(self, tmp_path):
        """Remove lock file if it exists."""
        session_id = "removable-session"
        create_lock(session_id, locks_dir=tmp_path)

        assert is_locked(session_id, locks_dir=tmp_path)

        remove_lock(session_id, locks_dir=tmp_path)

        assert not is_locked(session_id, locks_dir=tmp_path)

    def test_remove_nonexistent_lock(self, tmp_path):
        """Removing nonexistent lock doesn't raise."""
        session_id = "nonexistent"

        # Should not raise
        remove_lock(session_id, locks_dir=tmp_path)

    def test_invalid_lock_content(self, tmp_path):
        """Invalid lock content (not a float) returns False."""
        session_id = "invalid-lock"
        lock_path = tmp_path / f"{session_id}.lock"
        lock_path.write_text("not a timestamp")

        assert not is_locked(session_id, locks_dir=tmp_path)


class TestCleanupStaleLocks:
    """Tests for cleanup_stale_locks."""

    def test_cleanup_removes_stale(self, tmp_path):
        """Stale locks are removed, fresh locks preserved."""
        # Create stale lock (5 minutes old)
        stale_lock = tmp_path / "stale.lock"
        stale_lock.write_text(str(time.time() - 400))

        # Create fresh lock
        fresh_lock = tmp_path / "fresh.lock"
        fresh_lock.write_text(str(time.time()))

        cleanup_stale_locks(max_age_seconds=300, locks_dir=tmp_path)

        assert not stale_lock.exists()
        assert fresh_lock.exists()

    def test_cleanup_removes_invalid(self, tmp_path):
        """Locks with invalid content are removed."""
        invalid_lock = tmp_path / "invalid.lock"
        invalid_lock.write_text("garbage")

        cleanup_stale_locks(locks_dir=tmp_path)

        assert not invalid_lock.exists()

    def test_cleanup_nonexistent_dir(self, tmp_path):
        """Cleanup on nonexistent dir doesn't raise."""
        nonexistent = tmp_path / "nonexistent"

        # Should not raise
        cleanup_stale_locks(locks_dir=nonexistent)

    def test_cleanup_empty_dir(self, tmp_path):
        """Cleanup on empty dir works."""
        cleanup_stale_locks(locks_dir=tmp_path)


class TestSpawnBackgroundAnalysis:
    """Tests for spawn_background_analysis."""

    def test_spawns_with_correct_args(self, tmp_path, monkeypatch):
        """Verify subprocess.Popen called with correct arguments."""
        mock_popen = MagicMock()
        monkeypatch.setattr("sidecar.hooks.common.subprocess.Popen", mock_popen)

        session_id = "test-session"
        spawn_background_analysis(session_id, logs_dir=tmp_path)

        mock_popen.assert_called_once()
        args = mock_popen.call_args

        # Check command
        cmd = args[0][0]
        assert "-m" in cmd
        assert "sidecar.cli" in cmd
        assert "analyze" in cmd
        assert "--session-id" in cmd
        assert session_id in cmd
        assert "--background" in cmd
        assert "--snapshot" not in cmd

        # Check kwargs
        assert args[1]["start_new_session"] is True
        assert args[1]["stdin"] is not None

    def test_spawn_with_snapshot_flag(self, tmp_path, monkeypatch):
        """Verify --snapshot flag included when snapshot=True."""
        mock_popen = MagicMock()
        monkeypatch.setattr("sidecar.hooks.common.subprocess.Popen", mock_popen)

        session_id = "test-session"
        spawn_background_analysis(session_id, snapshot=True, logs_dir=tmp_path)

        cmd = mock_popen.call_args[0][0]
        assert "--snapshot" in cmd

    def test_spawn_creates_log_dir(self, tmp_path, monkeypatch):
        """Log directory is created if it doesn't exist."""
        mock_popen = MagicMock()
        monkeypatch.setattr("sidecar.hooks.common.subprocess.Popen", mock_popen)

        logs_dir = tmp_path / "logs" / "nested"
        spawn_background_analysis("session", logs_dir=logs_dir)

        assert logs_dir.exists()

    def test_spawn_error_handled(self, tmp_path, monkeypatch):
        """OSError during spawn is silently handled."""
        mock_popen = MagicMock(side_effect=OSError("Spawn failed"))
        monkeypatch.setattr("sidecar.hooks.common.subprocess.Popen", mock_popen)

        # Should not raise
        spawn_background_analysis("session", logs_dir=tmp_path)
