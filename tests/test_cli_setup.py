"""Tests for the CLI setup command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from sidecar.cli import cli
from sidecar.hooks.installer import SIDECAR_HOOK_MARKER


@pytest.fixture
def runner():
    return CliRunner()


class TestSetupInstall:
    """Tests for setup command (install mode)."""

    def test_setup_install(self, runner, tmp_path):
        """Invoke setup -> verify hooks added, cost warning printed."""
        settings_path = tmp_path / "settings.json"

        with patch("sidecar.hooks.installer.SETTINGS_PATH", settings_path):
            result = runner.invoke(cli, ["setup"])

        assert result.exit_code == 0
        assert "Installing Sidecar Hooks" in result.output
        assert "Stop" in result.output
        assert "PreCompact" in result.output

        # Cost warning should be present (may be split by Rich's line wrapping)
        assert "Anthropic" in result.output
        assert "API" in result.output
        assert "claude-haiku" in result.output
        assert "ANTHROPIC_API_KEY" in result.output

        # Verify settings file
        settings = json.loads(settings_path.read_text())
        assert "hooks" in settings
        assert "Stop" in settings["hooks"]
        assert "PreCompact" in settings["hooks"]

    def test_setup_already_installed(self, runner, tmp_path):
        """Install twice -> shows 'already exists'."""
        settings_path = tmp_path / "settings.json"

        with patch("sidecar.hooks.installer.SETTINGS_PATH", settings_path):
            runner.invoke(cli, ["setup"])
            result = runner.invoke(cli, ["setup"])

        assert result.exit_code == 0
        assert "already exists" in result.output


class TestSetupRemove:
    """Tests for setup --remove."""

    def test_setup_remove(self, runner, tmp_path):
        """Invoke setup --remove -> verify hooks removed."""
        settings_path = tmp_path / "settings.json"

        with patch("sidecar.hooks.installer.SETTINGS_PATH", settings_path):
            # First install
            runner.invoke(cli, ["setup"])

            # Then remove
            result = runner.invoke(cli, ["setup", "--remove"])

        assert result.exit_code == 0
        assert "Removing Sidecar Hooks" in result.output
        assert "removed" in result.output

        # Verify hooks are gone
        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {})

        # Check no sidecar hooks remain
        for event, matchers in hooks.items():
            for matcher_group in matchers:
                for hook in matcher_group.get("hooks", []):
                    assert SIDECAR_HOOK_MARKER not in hook.get("command", "")

    def test_setup_remove_not_installed(self, runner, tmp_path):
        """Remove when not installed -> shows 'not found'."""
        settings_path = tmp_path / "settings.json"
        settings_path.write_text("{}")

        with patch("sidecar.hooks.installer.SETTINGS_PATH", settings_path):
            result = runner.invoke(cli, ["setup", "--remove"])

        assert result.exit_code == 0
        assert "not found" in result.output


class TestSetupStatus:
    """Tests for setup --status."""

    def test_setup_status_installed(self, runner, tmp_path):
        """After install, setup --status shows registered."""
        settings_path = tmp_path / "settings.json"

        with patch("sidecar.hooks.installer.SETTINGS_PATH", settings_path):
            runner.invoke(cli, ["setup"])
            result = runner.invoke(cli, ["setup", "--status"])

        assert result.exit_code == 0
        assert "Hook Registration Status" in result.output
        assert "Stop" in result.output
        assert "registered" in result.output

    def test_setup_status_not_installed(self, runner, tmp_path):
        """Before install, shows not registered."""
        settings_path = tmp_path / "settings.json"
        settings_path.write_text("{}")

        with patch("sidecar.hooks.installer.SETTINGS_PATH", settings_path):
            result = runner.invoke(cli, ["setup", "--status"])

        assert result.exit_code == 0
        assert "not registered" in result.output
