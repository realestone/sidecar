"""Common utilities for Sidecar hooks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

LOCKS_DIR = Path.home() / ".config" / "sidecar" / "locks"
LOGS_DIR = Path.home() / ".config" / "sidecar" / "logs"


def read_hook_stdin() -> dict | None:
    """Read and parse JSON from stdin.

    Returns:
        Parsed JSON dict, or None on failure (never raises).
    """
    try:
        data = sys.stdin.read()
        if not data or not data.strip():
            return None
        return json.loads(data)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def write_hook_output(continue_: bool = True, suppress: bool = True) -> None:
    """Write hook JSON response to stdout.

    Args:
        continue_: Whether to continue normal execution.
        suppress: Whether to suppress hook output in Claude Code UI.
    """
    response = {"continue": continue_, "suppressOutput": suppress}
    try:
        sys.stdout.write(json.dumps(response))
        sys.stdout.flush()
    except OSError:
        pass


def is_locked(
    session_id: str,
    max_age_seconds: int = 60,
    locks_dir: Path | None = None,
) -> bool:
    """Check if a lock file exists and is younger than max_age_seconds.

    Args:
        session_id: Session ID to check.
        max_age_seconds: Maximum age in seconds for lock to be valid.
        locks_dir: Override locks directory (for testing).

    Returns:
        True if a valid (non-stale) lock exists.
    """
    lock_dir = locks_dir or LOCKS_DIR
    lock_path = lock_dir / f"{session_id}.lock"

    if not lock_path.exists():
        return False

    try:
        timestamp = float(lock_path.read_text().strip())
        age = time.time() - timestamp
        return age < max_age_seconds
    except (OSError, ValueError):
        return False


def create_lock(
    session_id: str,
    locks_dir: Path | None = None,
) -> Path:
    """Create lock file, return path.

    Creates locks directory if needed.

    Args:
        session_id: Session ID to lock.
        locks_dir: Override locks directory (for testing).

    Returns:
        Path to the created lock file.
    """
    lock_dir = locks_dir or LOCKS_DIR
    lock_dir.mkdir(parents=True, exist_ok=True)

    lock_path = lock_dir / f"{session_id}.lock"
    lock_path.write_text(str(time.time()))

    return lock_path


def remove_lock(
    session_id: str,
    locks_dir: Path | None = None,
) -> None:
    """Remove lock file if it exists.

    Args:
        session_id: Session ID to unlock.
        locks_dir: Override locks directory (for testing).
    """
    lock_dir = locks_dir or LOCKS_DIR
    lock_path = lock_dir / f"{session_id}.lock"

    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass


def cleanup_stale_locks(
    max_age_seconds: int = 300,
    locks_dir: Path | None = None,
) -> None:
    """Remove lock files older than max_age_seconds (5 min default).

    Args:
        max_age_seconds: Maximum age before a lock is considered stale.
        locks_dir: Override locks directory (for testing).
    """
    lock_dir = locks_dir or LOCKS_DIR

    if not lock_dir.exists():
        return

    now = time.time()

    try:
        for lock_file in lock_dir.glob("*.lock"):
            try:
                timestamp = float(lock_file.read_text().strip())
                if now - timestamp > max_age_seconds:
                    lock_file.unlink(missing_ok=True)
            except (OSError, ValueError):
                # Can't read or parse — remove it
                try:
                    lock_file.unlink(missing_ok=True)
                except OSError:
                    pass
    except OSError:
        pass


def spawn_background_analysis(
    session_id: str,
    snapshot: bool = False,
    logs_dir: Path | None = None,
) -> None:
    """Spawn detached: sidecar-cli analyze --session-id <id> --background [--snapshot]

    Uses subprocess.Popen with start_new_session=True.
    Redirects stdout/stderr to log file.
    Returns immediately without blocking.

    Args:
        session_id: Session ID to analyze.
        snapshot: If True, adds --snapshot flag (for pre-compact).
        logs_dir: Override logs directory (for testing).
    """
    log_dir = logs_dir or LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    log_path = log_dir / f"analyze-{session_id}.log"

    cmd = [
        sys.executable,
        "-m",
        "sidecar.cli",
        "analyze",
        "--session-id",
        session_id,
        "--background",
    ]

    if snapshot:
        cmd.append("--snapshot")

    try:
        with open(log_path, "a") as log_file:
            subprocess.Popen(
                cmd,
                start_new_session=True,
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.DEVNULL,
                cwd=os.path.expanduser("~"),
            )
    except OSError:
        # Spawn failed — nothing we can do
        pass
