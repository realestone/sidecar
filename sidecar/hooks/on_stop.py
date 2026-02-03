"""Stop hook: auto-analyze when Claude Code finishes a turn.

Entry point: python3 -m sidecar.hooks.on_stop
Reads session_id from stdin, spawns background analysis if not recently run.
Must exit in <50ms. Must NEVER return non-zero exit code.
"""

from __future__ import annotations

from .common import (
    cleanup_stale_locks,
    create_lock,
    is_locked,
    read_hook_stdin,
    spawn_background_analysis,
    write_hook_output,
)


def main() -> None:
    """Stop hook entry point."""
    try:
        data = read_hook_stdin()
        if not data:
            write_hook_output()
            return

        session_id = data.get("session_id", "")
        if not session_id:
            write_hook_output()
            return

        # Clean up old locks periodically
        cleanup_stale_locks()

        # Skip if recently analyzed
        if is_locked(session_id):
            write_hook_output()
            return

        # Create lock and spawn analysis
        create_lock(session_id)
        spawn_background_analysis(session_id)
        write_hook_output()

    except Exception:
        # NEVER let an exception propagate — it would show in Claude Code UI
        write_hook_output()


if __name__ == "__main__":
    main()
