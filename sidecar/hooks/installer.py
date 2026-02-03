"""Installer for Sidecar hooks in Claude Code settings."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

# Hook identification marker
SIDECAR_HOOK_MARKER = "sidecar.hooks.on_"


def _get_sidecar_hooks() -> dict:
    """Get Sidecar hook configuration using current Python executable."""
    return {
        "Stop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{sys.executable} -m sidecar.hooks.on_stop",
                        "timeout": 5,
                    }
                ]
            }
        ],
        "PreCompact": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{sys.executable} -m sidecar.hooks.on_pre_compact",
                        "timeout": 5,
                    }
                ]
            }
        ],
    }


def _is_sidecar_hook(hook_config: dict) -> bool:
    """Check if a hook configuration belongs to Sidecar."""
    if not isinstance(hook_config, dict):
        return False
    command = hook_config.get("command", "")
    return SIDECAR_HOOK_MARKER in command


def _has_sidecar_hook(matchers: list) -> bool:
    """Check if any matcher group contains a Sidecar hook."""
    for matcher_group in matchers:
        if not isinstance(matcher_group, dict):
            continue
        hooks = matcher_group.get("hooks", [])
        for hook in hooks:
            if _is_sidecar_hook(hook):
                return True
    return False


def install_hooks(
    settings_path: Path | None = None,
) -> dict[str, str]:
    """Add Sidecar hooks to ~/.claude/settings.json.

    Merges with existing settings, does not overwrite other hooks.

    Args:
        settings_path: Override settings path (for testing).

    Returns:
        Dict of {event_name: "added" | "already_exists"}.
    """
    path = settings_path or SETTINGS_PATH

    # Load existing settings
    if path.exists():
        try:
            settings = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            settings = {}
    else:
        settings = {}

    # Ensure hooks dict exists
    if "hooks" not in settings:
        settings["hooks"] = {}

    sidecar_hooks = _get_sidecar_hooks()
    results = {}

    for event_name, matchers in sidecar_hooks.items():
        existing = settings["hooks"].get(event_name, [])

        if _has_sidecar_hook(existing):
            results[event_name] = "already_exists"
        else:
            # Append our matcher group(s)
            if not isinstance(existing, list):
                existing = []
            existing.extend(matchers)
            settings["hooks"][event_name] = existing
            results[event_name] = "added"

    # Write back
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2))

    return results


def uninstall_hooks(
    settings_path: Path | None = None,
) -> dict[str, str]:
    """Remove only Sidecar hooks from settings.json.

    Preserves all other hooks.

    Args:
        settings_path: Override settings path (for testing).

    Returns:
        Dict of {event_name: "removed" | "not_found"}.
    """
    path = settings_path or SETTINGS_PATH

    if not path.exists():
        return {"Stop": "not_found", "PreCompact": "not_found"}

    try:
        settings = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"Stop": "not_found", "PreCompact": "not_found"}

    hooks = settings.get("hooks", {})
    sidecar_hooks = _get_sidecar_hooks()
    results = {}

    for event_name in sidecar_hooks:
        matchers = hooks.get(event_name, [])

        if not _has_sidecar_hook(matchers):
            results[event_name] = "not_found"
            continue

        # Filter out sidecar matcher groups
        new_matchers = []
        for matcher_group in matchers:
            if not isinstance(matcher_group, dict):
                new_matchers.append(matcher_group)
                continue
            hook_list = matcher_group.get("hooks", [])
            # Keep only hooks that are NOT sidecar hooks
            filtered_hooks = [h for h in hook_list if not _is_sidecar_hook(h)]
            if filtered_hooks:
                # Keep the matcher group with remaining hooks
                matcher_group["hooks"] = filtered_hooks
                new_matchers.append(matcher_group)
            # If no hooks left, drop the entire matcher group

        if new_matchers:
            hooks[event_name] = new_matchers
        else:
            # Remove empty event key
            hooks.pop(event_name, None)

        results[event_name] = "removed"

    settings["hooks"] = hooks
    path.write_text(json.dumps(settings, indent=2))

    return results


def check_hooks(
    settings_path: Path | None = None,
) -> dict[str, bool]:
    """Check which Sidecar hooks are currently registered.

    Args:
        settings_path: Override settings path (for testing).

    Returns:
        Dict of {event_name: is_registered}.
    """
    path = settings_path or SETTINGS_PATH

    if not path.exists():
        return {"Stop": False, "PreCompact": False}

    try:
        settings = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"Stop": False, "PreCompact": False}

    hooks = settings.get("hooks", {})
    sidecar_hooks = _get_sidecar_hooks()
    results = {}

    for event_name in sidecar_hooks:
        matchers = hooks.get(event_name, [])
        results[event_name] = _has_sidecar_hook(matchers)

    return results
