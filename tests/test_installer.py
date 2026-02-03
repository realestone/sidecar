"""Tests for sidecar.hooks.installer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sidecar.hooks.installer import (
    SIDECAR_HOOK_MARKER,
    check_hooks,
    install_hooks,
    uninstall_hooks,
)


class TestInstallHooks:
    """Tests for install_hooks."""

    def test_install_fresh(self, tmp_path):
        """No existing settings.json -> creates with hooks."""
        settings_path = tmp_path / "settings.json"

        results = install_hooks(settings_path=settings_path)

        assert settings_path.exists()
        assert results["Stop"] == "added"
        assert results["PreCompact"] == "added"

        settings = json.loads(settings_path.read_text())
        assert "hooks" in settings
        assert "Stop" in settings["hooks"]
        assert "PreCompact" in settings["hooks"]

    def test_install_existing_settings(self, tmp_path):
        """Existing settings without hooks -> adds hooks key."""
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps({"apiKey": "test-key"}))

        results = install_hooks(settings_path=settings_path)

        settings = json.loads(settings_path.read_text())
        assert settings["apiKey"] == "test-key"  # Preserved
        assert "hooks" in settings

    def test_install_existing_hooks(self, tmp_path):
        """Existing hooks from other tools -> merges without overwriting."""
        settings_path = tmp_path / "settings.json"
        other_hook = {
            "hooks": {
                "Stop": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "other-tool --analyze",
                            }
                        ]
                    }
                ]
            }
        }
        settings_path.write_text(json.dumps(other_hook))

        results = install_hooks(settings_path=settings_path)

        settings = json.loads(settings_path.read_text())
        stop_hooks = settings["hooks"]["Stop"]

        # Should have both: other tool's hook and sidecar's hook
        assert len(stop_hooks) == 2

        # Other tool's hook should be preserved
        commands = []
        for matcher_group in stop_hooks:
            for hook in matcher_group.get("hooks", []):
                commands.append(hook.get("command", ""))

        assert any("other-tool" in cmd for cmd in commands)
        assert any(SIDECAR_HOOK_MARKER in cmd for cmd in commands)

    def test_install_idempotent(self, tmp_path):
        """Run install twice -> same result, no duplicates."""
        settings_path = tmp_path / "settings.json"

        results1 = install_hooks(settings_path=settings_path)
        results2 = install_hooks(settings_path=settings_path)

        assert results1["Stop"] == "added"
        assert results2["Stop"] == "already_exists"

        settings = json.loads(settings_path.read_text())
        # Should still only have one matcher group for Stop
        assert len(settings["hooks"]["Stop"]) == 1


class TestUninstallHooks:
    """Tests for uninstall_hooks."""

    def test_uninstall(self, tmp_path):
        """After install, uninstall -> hooks removed, other settings preserved."""
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps({"apiKey": "test-key"}))

        install_hooks(settings_path=settings_path)
        results = uninstall_hooks(settings_path=settings_path)

        assert results["Stop"] == "removed"
        assert results["PreCompact"] == "removed"

        settings = json.loads(settings_path.read_text())
        assert settings["apiKey"] == "test-key"  # Preserved

        # Hooks should be empty or have no sidecar hooks
        hooks = settings.get("hooks", {})
        if "Stop" in hooks:
            for matcher_group in hooks["Stop"]:
                for hook in matcher_group.get("hooks", []):
                    assert SIDECAR_HOOK_MARKER not in hook.get("command", "")

    def test_uninstall_preserves_other_hooks(self, tmp_path):
        """Other plugins' hooks untouched."""
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "Stop": [
                            {
                                "hooks": [
                                    {"type": "command", "command": "other-tool"}
                                ]
                            }
                        ]
                    }
                }
            )
        )

        # Install sidecar hooks
        install_hooks(settings_path=settings_path)

        # Uninstall sidecar hooks
        results = uninstall_hooks(settings_path=settings_path)

        settings = json.loads(settings_path.read_text())

        # Other tool's hook should remain
        stop_hooks = settings["hooks"]["Stop"]
        assert len(stop_hooks) == 1
        assert "other-tool" in stop_hooks[0]["hooks"][0]["command"]

    def test_uninstall_when_not_installed(self, tmp_path):
        """No sidecar hooks -> graceful no-op."""
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps({"hooks": {}}))

        results = uninstall_hooks(settings_path=settings_path)

        assert results["Stop"] == "not_found"
        assert results["PreCompact"] == "not_found"

    def test_uninstall_no_settings_file(self, tmp_path):
        """No settings file -> graceful no-op."""
        settings_path = tmp_path / "nonexistent.json"

        results = uninstall_hooks(settings_path=settings_path)

        assert results["Stop"] == "not_found"
        assert results["PreCompact"] == "not_found"


class TestCheckHooks:
    """Tests for check_hooks."""

    def test_check_installed(self, tmp_path):
        """After install, check returns True for both events."""
        settings_path = tmp_path / "settings.json"

        install_hooks(settings_path=settings_path)
        status = check_hooks(settings_path=settings_path)

        assert status["Stop"] is True
        assert status["PreCompact"] is True

    def test_check_not_installed(self, tmp_path):
        """Before install, check returns False."""
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps({}))

        status = check_hooks(settings_path=settings_path)

        assert status["Stop"] is False
        assert status["PreCompact"] is False

    def test_check_no_settings_file(self, tmp_path):
        """No settings file -> returns False for both."""
        settings_path = tmp_path / "nonexistent.json"

        status = check_hooks(settings_path=settings_path)

        assert status["Stop"] is False
        assert status["PreCompact"] is False

    def test_check_invalid_json(self, tmp_path):
        """Invalid JSON in settings -> returns False."""
        settings_path = tmp_path / "settings.json"
        settings_path.write_text("not valid json {{{")

        status = check_hooks(settings_path=settings_path)

        assert status["Stop"] is False
        assert status["PreCompact"] is False

    def test_check_partial_install(self, tmp_path):
        """Only one event installed -> correct status for each."""
        settings_path = tmp_path / "settings.json"

        # Manually create settings with only Stop hook
        install_hooks(settings_path=settings_path)

        # Remove PreCompact manually
        settings = json.loads(settings_path.read_text())
        del settings["hooks"]["PreCompact"]
        settings_path.write_text(json.dumps(settings))

        status = check_hooks(settings_path=settings_path)

        assert status["Stop"] is True
        assert status["PreCompact"] is False
