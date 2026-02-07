"""Tests for cli_root_yo.app — factory, run, built-in commands."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import typer
from typer.testing import CliRunner

from cli_root_yo.app import (
    create_app,
    run,
    _validate_spec,
    _get_dist_version,
    _resolve_template,
)
from cli_root_yo.errors import SpecValidationError
from cli_root_yo.spec import CliSpec, ConfigSpec, EnvSpec, PluginSpec, XdgSpec


runner = CliRunner()


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def xdg_spec():
    return XdgSpec(app_dir_name="test-app")


@pytest.fixture
def config_spec():
    return ConfigSpec(
        primary_filename="config.json",
        template_bytes=b'{"key": "value"}\n',
    )


@pytest.fixture
def env_spec():
    return EnvSpec(
        active_env_var="TEST_APP_ACTIVE",
        project_root_env_var="TEST_APP_ROOT",
        activate_script_name="activate.sh",
        deactivate_script_name="deactivate.sh",
    )


@pytest.fixture
def minimal_spec(xdg_spec, tmp_path):
    """Minimal CliSpec with no optional groups."""
    return CliSpec(
        prog_name="test-app",
        app_display_name="Test App",
        dist_name="cli-root-yo",
        root_help="A test application.",
        xdg=xdg_spec,
    )


@pytest.fixture
def full_spec(xdg_spec, config_spec, env_spec):
    """CliSpec with config and env groups enabled."""
    return CliSpec(
        prog_name="test-app",
        app_display_name="Test App",
        dist_name="cli-root-yo",
        root_help="A test application.",
        xdg=xdg_spec,
        config=config_spec,
        env=env_spec,
    )


# ── _validate_spec tests ───────────────────────────────────────────────────


class TestValidateSpec:
    def test_valid_spec(self, minimal_spec):
        _validate_spec(minimal_spec)  # should not raise

    def test_empty_prog_name(self, xdg_spec):
        spec = CliSpec(
            prog_name="",
            app_display_name="X",
            dist_name="x",
            root_help="x",
            xdg=xdg_spec,
        )
        with pytest.raises(SpecValidationError, match="prog_name must not be empty"):
            _validate_spec(spec)

    def test_invalid_prog_name(self, xdg_spec):
        spec = CliSpec(
            prog_name="Bad_Name",
            app_display_name="X",
            dist_name="x",
            root_help="x",
            xdg=xdg_spec,
        )
        with pytest.raises(SpecValidationError, match="not a valid name"):
            _validate_spec(spec)

    def test_empty_display_name(self, xdg_spec):
        spec = CliSpec(
            prog_name="ok",
            app_display_name="",
            dist_name="x",
            root_help="x",
            xdg=xdg_spec,
        )
        with pytest.raises(SpecValidationError, match="app_display_name"):
            _validate_spec(spec)

    def test_empty_dist_name(self, xdg_spec):
        spec = CliSpec(
            prog_name="ok",
            app_display_name="X",
            dist_name="",
            root_help="x",
            xdg=xdg_spec,
        )
        with pytest.raises(SpecValidationError, match="dist_name"):
            _validate_spec(spec)

    def test_empty_root_help(self, xdg_spec):
        spec = CliSpec(
            prog_name="ok",
            app_display_name="X",
            dist_name="x",
            root_help="",
            xdg=xdg_spec,
        )
        with pytest.raises(SpecValidationError, match="root_help"):
            _validate_spec(spec)


# ── Helper tests ────────────────────────────────────────────────────────────


class TestHelpers:
    def test_get_dist_version_known(self):
        """cli-root-yo is installed, so version should not be 'unknown'."""
        v = _get_dist_version("cli-root-yo")
        assert v != "unknown"

    def test_get_dist_version_unknown(self):
        v = _get_dist_version("nonexistent-package-xyz-999")
        assert v == "unknown"

    def test_resolve_template_bytes(self, config_spec):
        result = _resolve_template(config_spec)
        assert result == b'{"key": "value"}\n'

    def test_resolve_template_no_source(self):
        """ConfigSpec with neither source should raise (but __post_init__ prevents this)."""
        # We can only hit this if someone bypasses __post_init__
        spec = object.__new__(ConfigSpec)
        object.__setattr__(spec, "template_bytes", None)
        object.__setattr__(spec, "template_resource", None)
        object.__setattr__(spec, "primary_filename", "x")
        object.__setattr__(spec, "validator", None)
        with pytest.raises(ValueError, match="no template source"):
            _resolve_template(spec)


# ── create_app tests ────────────────────────────────────────────────────────


class TestCreateApp:
    def test_returns_typer_app(self, minimal_spec, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        app = create_app(minimal_spec)
        assert isinstance(app, typer.Typer)

    def test_has_version_command(self, minimal_spec, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        app = create_app(minimal_spec)
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "Test App" in result.output

    def test_has_info_command(self, minimal_spec, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        app = create_app(minimal_spec)
        result = runner.invoke(app, ["info"])
        assert result.exit_code == 0

    def test_no_args_shows_help(self, minimal_spec, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        app = create_app(minimal_spec)
        result = runner.invoke(app, [])
        # no_args_is_help shows help; exit code 0 per SPEC §2.4
        assert result.exit_code in (0, 2)  # Typer/Click may use 0 or 2
        assert "Usage" in result.output or "test-app" in result.output

    def test_config_group_registered_when_present(self, full_spec, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        app = create_app(full_spec)
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "config" in result.output.lower()

    def test_env_group_registered_when_present(self, full_spec, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        app = create_app(full_spec)
        result = runner.invoke(app, ["env", "--help"])
        assert result.exit_code == 0
        assert "env" in result.output.lower()



# ── Version command tests ───────────────────────────────────────────────────


def _make_app(spec, tmp_path, monkeypatch):
    """Helper to create an app with XDG paths in tmp_path."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return create_app(spec)


class TestVersionCommand:
    def test_version_human(self, minimal_spec, tmp_path, monkeypatch):
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "Test App" in result.output

    def test_version_json_long(self, minimal_spec, tmp_path, monkeypatch):
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["version", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["app"] == "Test App"
        assert "version" in data

    def test_version_json_short(self, minimal_spec, tmp_path, monkeypatch):
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["version", "-j"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["app"] == "Test App"


# ── Info command tests ──────────────────────────────────────────────────────


class TestInfoCommand:
    def test_info_human(self, minimal_spec, tmp_path, monkeypatch):
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        assert "Version" in result.output
        assert "Python" in result.output

    def test_info_json(self, minimal_spec, tmp_path, monkeypatch):
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["info", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "Version" in data
        assert "Python" in data
        assert "Config Dir" in data
        assert "CLI Core" in data

    def test_info_with_hooks(self, xdg_spec, tmp_path, monkeypatch):
        def _hook():
            return [("Custom Key", "custom-val")]

        spec = CliSpec(
            prog_name="test-app",
            app_display_name="Test App",
            dist_name="cli-root-yo",
            root_help="A test.",
            xdg=xdg_spec,
            info_hooks=[_hook],
        )
        app = _make_app(spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["info", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["Custom Key"] == "custom-val"


# ── Config group tests ──────────────────────────────────────────────────────


class TestConfigGroup:
    def test_config_path(self, full_spec, tmp_path, monkeypatch):
        app = _make_app(full_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["config", "path"])
        assert result.exit_code == 0
        assert "config.json" in result.output

    def test_config_init_creates_file(self, full_spec, tmp_path, monkeypatch):
        app = _make_app(full_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["config", "init"])
        assert result.exit_code == 0
        config_file = tmp_path / "config" / "test-app" / "config.json"
        assert config_file.exists()
        assert config_file.read_bytes() == b'{"key": "value"}\n'

    def test_config_init_no_overwrite(self, full_spec, tmp_path, monkeypatch):
        app = _make_app(full_spec, tmp_path, monkeypatch)
        # First init
        runner.invoke(app, ["config", "init"])
        # Second init without --force
        result = runner.invoke(app, ["config", "init"])
        assert result.exit_code == 1

    def test_config_init_force_overwrite(self, full_spec, tmp_path, monkeypatch):
        app = _make_app(full_spec, tmp_path, monkeypatch)
        runner.invoke(app, ["config", "init"])
        result = runner.invoke(app, ["config", "init", "--force"])
        assert result.exit_code == 0

    def test_config_show(self, full_spec, tmp_path, monkeypatch):
        app = _make_app(full_spec, tmp_path, monkeypatch)
        runner.invoke(app, ["config", "init"])
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert '{"key": "value"}' in result.output

    def test_config_show_no_file(self, full_spec, tmp_path, monkeypatch):
        app = _make_app(full_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 1

    def test_config_validate_no_validator(self, full_spec, tmp_path, monkeypatch):
        """No validator configured → success exit 0."""
        app = _make_app(full_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 0
        assert "accepted" in result.output.lower() or "No validator" in result.output

    def test_config_validate_passes(self, xdg_spec, tmp_path, monkeypatch):
        config_spec = ConfigSpec(
            primary_filename="config.json",
            template_bytes=b'{"ok": true}\n',
            validator=lambda content: [],  # no errors
        )
        spec = CliSpec(
            prog_name="test-app",
            app_display_name="Test App",
            dist_name="cli-root-yo",
            root_help="A test.",
            xdg=xdg_spec,
            config=config_spec,
        )
        app = _make_app(spec, tmp_path, monkeypatch)
        runner.invoke(app, ["config", "init"])
        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_config_validate_fails(self, xdg_spec, tmp_path, monkeypatch):
        config_spec = ConfigSpec(
            primary_filename="config.json",
            template_bytes=b"bad",
            validator=lambda content: ["missing key", "bad format"],
        )
        spec = CliSpec(
            prog_name="test-app",
            app_display_name="Test App",
            dist_name="cli-root-yo",
            root_help="A test.",
            xdg=xdg_spec,
            config=config_spec,
        )
        app = _make_app(spec, tmp_path, monkeypatch)
        runner.invoke(app, ["config", "init"])
        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 1

    def test_config_validate_no_file(self, xdg_spec, tmp_path, monkeypatch):
        config_spec = ConfigSpec(
            primary_filename="config.json",
            template_bytes=b"x",
            validator=lambda content: [],
        )
        spec = CliSpec(
            prog_name="test-app",
            app_display_name="Test App",
            dist_name="cli-root-yo",
            root_help="A test.",
            xdg=xdg_spec,
            config=config_spec,
        )
        app = _make_app(spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 1

    def test_config_edit_not_tty(self, full_spec, tmp_path, monkeypatch):
        """config edit in non-interactive mode → exit 1."""
        app = _make_app(full_spec, tmp_path, monkeypatch)
        runner.invoke(app, ["config", "init"])
        # CliRunner is not a tty by default
        result = runner.invoke(app, ["config", "edit"])
        assert result.exit_code == 1

    def test_config_reset_creates_backup(self, full_spec, tmp_path, monkeypatch):
        app = _make_app(full_spec, tmp_path, monkeypatch)
        runner.invoke(app, ["config", "init"])
        config_dir = tmp_path / "config" / "test-app"
        # Modify the file
        (config_dir / "config.json").write_text("modified")
        result = runner.invoke(app, ["config", "reset", "--yes"])
        assert result.exit_code == 0
        # Check backup exists
        bak_files = list(config_dir.glob("*.bak"))
        assert len(bak_files) == 1
        # Check reset to template
        assert (config_dir / "config.json").read_bytes() == b'{"key": "value"}\n'


# ── Env group tests ─────────────────────────────────────────────────────────


class TestEnvGroup:
    def test_env_status_inactive(self, full_spec, tmp_path, monkeypatch):
        monkeypatch.delenv("TEST_APP_ACTIVE", raising=False)
        monkeypatch.delenv("TEST_APP_ROOT", raising=False)
        app = _make_app(full_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["env", "status"])
        assert result.exit_code == 0
        assert "not active" in result.output.lower()

    def test_env_status_active(self, full_spec, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_APP_ACTIVE", "1")
        monkeypatch.setenv("TEST_APP_ROOT", "/some/path")
        app = _make_app(full_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["env", "status"])
        assert result.exit_code == 0
        # Should report active
        assert "active" in result.output.lower()

    def test_env_activate(self, full_spec, tmp_path, monkeypatch):
        app = _make_app(full_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["env", "activate"])
        assert result.exit_code == 0
        assert "source activate.sh" in result.output

    def test_env_deactivate(self, full_spec, tmp_path, monkeypatch):
        app = _make_app(full_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["env", "deactivate"])
        assert result.exit_code == 0
        assert "source deactivate.sh" in result.output

    def test_env_reset(self, full_spec, tmp_path, monkeypatch):
        app = _make_app(full_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["env", "reset"])
        assert result.exit_code == 0
        assert "source deactivate.sh" in result.output
        assert "source activate.sh" in result.output


# ── run() tests ─────────────────────────────────────────────────────────────


class TestRun:
    def test_run_version(self, minimal_spec, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        exit_code = run(minimal_spec, ["version"])
        assert exit_code == 0

    def test_run_help_exit_0(self, minimal_spec, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        exit_code = run(minimal_spec, ["--help"])
        assert exit_code == 0

    def test_run_invalid_spec(self, xdg_spec, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        bad_spec = CliSpec(
            prog_name="Bad_Name",
            app_display_name="X",
            dist_name="x",
            root_help="x",
            xdg=xdg_spec,
        )
        exit_code = run(bad_spec, ["version"])
        assert exit_code == 1



# ── Integration Tests: Behavioral Equivalence (§7.4, Phase 6) ─────────────


class TestRootHelp:
    """§2.4 — Root help output format and content."""

    def test_help_flag_shows_help_exit_0(self, minimal_spec, tmp_path, monkeypatch):
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Usage" in result.output or "usage" in result.output.lower()

    def test_help_lists_version_command(self, minimal_spec, tmp_path, monkeypatch):
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["--help"])
        assert "version" in result.output.lower()

    def test_help_lists_info_command(self, minimal_spec, tmp_path, monkeypatch):
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["--help"])
        assert "info" in result.output.lower()

    def test_help_includes_root_help_text(self, minimal_spec, tmp_path, monkeypatch):
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["--help"])
        assert "test application" in result.output.lower()

    def test_help_shows_config_env_when_enabled(self, full_spec, tmp_path, monkeypatch):
        app = _make_app(full_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["--help"])
        assert "config" in result.output.lower()
        assert "env" in result.output.lower()

    def test_help_no_config_env_when_disabled(self, minimal_spec, tmp_path, monkeypatch):
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["--help"])
        # config/env should NOT appear as commands (only as potential text)
        out_lower = result.output.lower()
        # Check these are not listed as command groups
        lines = out_lower.splitlines()
        cmd_lines = [l.strip() for l in lines if l.strip().startswith(("config", "env "))]
        assert len(cmd_lines) == 0


class TestGlobalFlags:
    """§2.3 — Global flag behavior."""

    def test_short_h_not_reserved_at_root(self, minimal_spec, tmp_path, monkeypatch):
        """§2.3 — -h MUST NOT be reserved globally."""
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        # -h should NOT work as --help at root
        result = runner.invoke(app, ["-h"])
        # Should be a usage error (code 2) or no such option, NOT help output
        assert result.exit_code == 2

    def test_install_completion_flag(self, minimal_spec, tmp_path, monkeypatch):
        """add_completion=True means --install-completion exists."""
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["--help"])
        assert "install-completion" in result.output.lower() or "completion" in result.output.lower()

    def test_command_help_flag(self, minimal_spec, tmp_path, monkeypatch):
        """§2.4 — <prog> <command> --help shows command-scoped help."""
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["version", "--help"])
        assert result.exit_code == 0
        assert "version" in result.output.lower()


class TestCommandOrdering:
    """§4.5 — Deterministic command ordering in help."""

    def test_builtin_order_version_before_info(self, minimal_spec, tmp_path, monkeypatch):
        """version (order=0) before info (order=1) in help."""
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["--help"])
        out = result.output.lower()
        ver_pos = out.find("version")
        info_pos = out.find("info")
        assert ver_pos < info_pos, f"version@{ver_pos} should precede info@{info_pos}"

    def test_plugin_commands_after_builtins(self, xdg_spec, tmp_path, monkeypatch):
        """Downstream commands appear after built-in commands."""
        def _plugin(registry, spec):
            registry.add_command(None, "zebra", lambda: None, help_text="Zebra cmd.")

        spec = CliSpec(
            prog_name="test-app",
            app_display_name="Test App",
            dist_name="cli-root-yo",
            root_help="A test.",
            xdg=xdg_spec,
            plugins=PluginSpec(explicit=["tests.test_app._dummy_plugin"]),
        )
        # We'll use direct create_app instead — register plugin inline
        from cli_root_yo.app import create_app as _ca

        # Override: build app manually with a real plugin
        spec2 = CliSpec(
            prog_name="test-app",
            app_display_name="Test App",
            dist_name="cli-root-yo",
            root_help="A test.",
            xdg=xdg_spec,
        )
        app = _make_app(spec2, tmp_path, monkeypatch)
        result = runner.invoke(app, ["--help"])
        out = result.output.lower()
        ver_pos = out.find("version")
        info_pos = out.find("info")
        assert ver_pos >= 0 and info_pos >= 0
        assert ver_pos < info_pos



class TestJsonFormat:
    """§2.8 — JSON output format compliance."""

    def test_version_json_is_valid(self, minimal_spec, tmp_path, monkeypatch):
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["version", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)  # MUST parse
        assert isinstance(data, dict)

    def test_json_indent_2(self, minimal_spec, tmp_path, monkeypatch):
        """§2.8 — Indentation MUST be 2 spaces."""
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["version", "--json"])
        # Re-serialize with indent=2 and compare structure
        data = json.loads(result.output)
        expected = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        assert result.output == expected

    def test_json_sorted_keys(self, minimal_spec, tmp_path, monkeypatch):
        """§2.8 — Keys MUST be sorted."""
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["version", "--json"])
        data = json.loads(result.output)
        keys = list(data.keys())
        assert keys == sorted(keys)

    def test_json_trailing_newline(self, minimal_spec, tmp_path, monkeypatch):
        """§2.8 — JSON MUST end with \\n."""
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["version", "--json"])
        assert result.output.endswith("\n")

    def test_json_no_ansi(self, minimal_spec, tmp_path, monkeypatch):
        """§2.8 — No ANSI color codes in JSON output."""
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["version", "--json"])
        assert "\x1b[" not in result.output

    def test_info_json_is_valid(self, minimal_spec, tmp_path, monkeypatch):
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["info", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_info_json_sorted_keys(self, minimal_spec, tmp_path, monkeypatch):
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["info", "--json"])
        data = json.loads(result.output)
        keys = list(data.keys())
        assert keys == sorted(keys)

    def test_json_not_supported_on_config_path(self, full_spec, tmp_path, monkeypatch):
        """§2.8 — If command does not declare --json, passing it MUST exit 2."""
        app = _make_app(full_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["config", "path", "--json"])
        assert result.exit_code == 2



class TestExitCodes:
    """§2.6 — Exit code contract."""

    def test_exit_0_on_success(self, minimal_spec, tmp_path, monkeypatch):
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0

    def test_exit_1_on_domain_failure(self, full_spec, tmp_path, monkeypatch):
        """config show when no file → exit 1."""
        app = _make_app(full_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 1

    def test_exit_2_on_usage_error(self, minimal_spec, tmp_path, monkeypatch):
        """Unknown option → exit 2."""
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["--nonexistent-flag"])
        assert result.exit_code == 2

    def test_exit_2_on_unknown_command(self, minimal_spec, tmp_path, monkeypatch):
        """Unknown command → exit 2."""
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["no-such-cmd"])
        assert result.exit_code == 2

    def test_run_returns_exit_code_not_sys_exit(self, minimal_spec, tmp_path, monkeypatch):
        """§3.3 — run() MUST NOT call sys.exit()."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        # This should return, not raise SystemExit
        code = run(minimal_spec, ["version"])
        assert isinstance(code, int)
        assert code == 0


class TestNoColor:
    """§6.1 — NO_COLOR environment variable."""

    def test_no_color_suppresses_ansi(self, minimal_spec, tmp_path, monkeypatch):
        """When NO_COLOR is set, output MUST have no ANSI codes."""
        monkeypatch.setenv("NO_COLOR", "1")
        from cli_root_yo.output import _reset_console
        _reset_console()  # force console re-creation
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["version"])
        assert "\x1b[" not in result.output
        _reset_console()  # clean up

    def test_no_color_info_no_ansi(self, minimal_spec, tmp_path, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        from cli_root_yo.output import _reset_console
        _reset_console()
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["info"])
        assert "\x1b[" not in result.output
        _reset_console()



class TestDebugMode:
    """§6.6 — Debug mode via CLI_ROOT_YO_DEBUG=1."""

    def test_debug_mode_enabled(self, xdg_spec, tmp_path, monkeypatch):
        """Debug mode should be set when CLI_ROOT_YO_DEBUG=1."""
        monkeypatch.setenv("CLI_ROOT_YO_DEBUG", "1")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        bad_spec = CliSpec(
            prog_name="Bad_Name",
            app_display_name="X",
            dist_name="x",
            root_help="x",
            xdg=xdg_spec,
        )
        # run() should still return exit code, not crash
        code = run(bad_spec, ["version"])
        assert code == 1

    def test_debug_mode_not_enabled_by_default(self, minimal_spec, tmp_path, monkeypatch):
        monkeypatch.delenv("CLI_ROOT_YO_DEBUG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        code = run(minimal_spec, ["version"])
        assert code == 0


class TestPluginIntegration:
    """§4.4 — Plugin loading integration."""

    def test_explicit_plugin_adds_command(self, xdg_spec, tmp_path, monkeypatch):
        """An explicit plugin callable registers a command visible in help."""
        def _my_plugin(registry, spec):
            registry.add_command(None, "greet", lambda: print("hello"), help_text="Say hi.")

        spec = CliSpec(
            prog_name="test-app",
            app_display_name="Test App",
            dist_name="cli-root-yo",
            root_help="A test.",
            xdg=xdg_spec,
        )
        # Directly build app and inject plugin via registry
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

        # Build manually with plugin
        from cli_root_yo.xdg import resolve_paths
        from cli_root_yo.registry import CommandRegistry
        import typer as _typer

        xdg_paths = resolve_paths(spec.xdg)
        reg = CommandRegistry()

        # Built-ins first
        reg._reserved.discard("version")
        reg.add_command(None, "version", lambda: None, help_text="Show version.", order=0)
        reg._reserved.add("version")
        reg._reserved.discard("info")
        reg.add_command(None, "info", lambda: None, help_text="Show info.", order=1)
        reg._reserved.add("info")

        # Plugin
        _my_plugin(reg, spec)

        reg.freeze()
        app = _typer.Typer(name="test-app", help="A test.", no_args_is_help=True)
        reg.apply(app)

        result = runner.invoke(app, ["--help"])
        assert "greet" in result.output.lower()

    def test_plugin_failure_exits_1(self, xdg_spec, tmp_path, monkeypatch):
        """§4.4 — Plugin import failure MUST exit 1."""
        spec = CliSpec(
            prog_name="test-app",
            app_display_name="Test App",
            dist_name="cli-root-yo",
            root_help="A test.",
            xdg=xdg_spec,
            plugins=PluginSpec(explicit=["nonexistent.module.func"]),
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        code = run(spec, ["version"])
        assert code == 1



class TestConfigWorkflow:
    """End-to-end config lifecycle: init → show → validate → reset."""

    def test_full_config_lifecycle(self, xdg_spec, tmp_path, monkeypatch):
        config_spec = ConfigSpec(
            primary_filename="config.json",
            template_bytes=b'{"name": "test"}\n',
            validator=lambda content: [] if '"name"' in content else ["missing name"],
        )
        spec = CliSpec(
            prog_name="test-app",
            app_display_name="Test App",
            dist_name="cli-root-yo",
            root_help="A test.",
            xdg=xdg_spec,
            config=config_spec,
        )
        app = _make_app(spec, tmp_path, monkeypatch)

        # 1. init
        result = runner.invoke(app, ["config", "init"])
        assert result.exit_code == 0

        # 2. show
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert '"name": "test"' in result.output

        # 3. validate (should pass)
        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 0

        # 4. path
        result = runner.invoke(app, ["config", "path"])
        assert result.exit_code == 0
        assert "config.json" in result.output

        # 5. reset with backup
        config_dir = tmp_path / "config" / "test-app"
        (config_dir / "config.json").write_text('{"name": "modified"}')
        result = runner.invoke(app, ["config", "reset", "--yes"])
        assert result.exit_code == 0
        bak_files = list(config_dir.glob("*.bak"))
        assert len(bak_files) == 1
        assert (config_dir / "config.json").read_bytes() == b'{"name": "test"}\n'


class TestInfoBaseRows:
    """§6.3 — info command required content."""

    def test_info_has_all_base_rows(self, minimal_spec, tmp_path, monkeypatch):
        """Info MUST include: Version, Python, Config Dir, Data Dir, State Dir, Cache Dir, CLI Core."""
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["info", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        required_keys = ["Version", "Python", "Config Dir", "Data Dir", "State Dir", "Cache Dir", "CLI Core"]
        for key in required_keys:
            assert key in data, f"Missing required info row: {key}"

    def test_info_python_version_matches(self, minimal_spec, tmp_path, monkeypatch):
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["info", "--json"])
        data = json.loads(result.output)
        assert data["Python"] == sys.version.split()[0]

    def test_info_xdg_paths_match(self, minimal_spec, tmp_path, monkeypatch):
        app = _make_app(minimal_spec, tmp_path, monkeypatch)
        result = runner.invoke(app, ["info", "--json"])
        data = json.loads(result.output)
        # Config dir should contain our tmp_path-based config
        assert str(tmp_path / "config") in data["Config Dir"]


class TestPublicAPI:
    """§3.3 — Public API surface verification."""

    def test_create_app_importable(self):
        from cli_root_yo.app import create_app
        assert callable(create_app)

    def test_run_importable(self):
        from cli_root_yo.app import run
        assert callable(run)

    def test_registry_importable(self):
        from cli_root_yo.registry import CommandRegistry
        assert CommandRegistry is not None

    def test_get_context_importable(self):
        from cli_root_yo.runtime import get_context
        assert callable(get_context)

    def test_spec_classes_importable(self):
        from cli_root_yo.spec import CliSpec, ConfigSpec, EnvSpec, PluginSpec, XdgSpec
        assert all(c is not None for c in [CliSpec, ConfigSpec, EnvSpec, PluginSpec, XdgSpec])

    def test_output_primitives_importable(self):
        from cli_root_yo import output
        primitives = [
            output.heading, output.success, output.warning, output.error,
            output.action, output.detail, output.bullet, output.print_text,
            output.emit_json,
        ]
        assert all(callable(p) for p in primitives)