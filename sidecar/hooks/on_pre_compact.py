"""PreCompact hook: save session snapshot before context compaction.

Entry point: python3 -m sidecar.hooks.on_pre_compact
Reads session_id from stdin, spawns background analysis with --snapshot.
Must exit in <50ms. Must NEVER return non-zero exit code.
"""

from __future__ import annotations

from .common import (
    read_hook_stdin,
    spawn_background_analysis,
    write_hook_output,
)


def main() -> None:
    """PreCompact hook entry point."""
    try:
        data = read_hook_stdin()
        if not data:
            write_hook_output()
            return

        session_id = data.get("session_id", "")
        if not session_id:
            write_hook_output()
            return

        # PreCompact doesn't need dedup — it fires rarely and snapshots don't overwrite
        spawn_background_analysis(session_id, snapshot=True)
        write_hook_output()

    except Exception:
        # NEVER let an exception propagate — it would show in Claude Code UI
        write_hook_output()


if __name__ == "__main__":
    main()
