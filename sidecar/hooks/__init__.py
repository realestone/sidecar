"""Sidecar hooks for Claude Code integration."""

from .common import (
    cleanup_stale_locks,
    create_lock,
    is_locked,
    read_hook_stdin,
    remove_lock,
    spawn_background_analysis,
    write_hook_output,
)
from .installer import check_hooks, install_hooks, uninstall_hooks

__all__ = [
    "read_hook_stdin",
    "write_hook_output",
    "is_locked",
    "create_lock",
    "remove_lock",
    "cleanup_stale_locks",
    "spawn_background_analysis",
    "install_hooks",
    "uninstall_hooks",
    "check_hooks",
]
