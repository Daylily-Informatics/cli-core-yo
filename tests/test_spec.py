"""Tests for cli_core_yo.spec."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli_core_yo.spec import (
    NAME_RE,
    CliSpec,
    ConfigSpec,
    EnvSpec,
    PluginSpec,
    XdgSpec,
)


class TestNameRegex:
    @pytest.mark.parametrize(
        "name",
        ["version", "info", "my-command", "a1", "config", "env-status", "x"],
    )
    def test_valid_names(self, name: str):
        assert NAME_RE.match(name)

    @pytest.mark.parametrize(
        "name",
        ["", "1start", "-dash", "UPPER", "camelCase", "under_score", "has space", "a.b"],
    )
    def test_invalid_names(self, name: str):
        assert not NAME_RE.match(name)


class TestXdgSpec:
    def test_minimal(self):
        spec = XdgSpec(app_dir_name="myapp")
        assert spec.app_dir_name == "myapp"

    def test_frozen(self):
        spec = XdgSpec(app_dir_name="myapp")
        with pytest.raises(AttributeError):
            spec.app_dir_name = "other"  # type: ignore[misc]


class TestConfigSpec:
    def test_with_xdg_relative_path_and_template_bytes(self):
        spec = ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}")
        assert spec.xdg_relative_path == "config.json"
        assert spec.absolute_path is None
        assert spec.template_bytes == b"{}"
        assert spec.template_resource is None

    def test_with_nested_xdg_relative_path_and_template_bytes(self):
        spec = ConfigSpec(xdg_relative_path="profiles/dev/config.json", template_bytes=b"{}")
        assert spec.xdg_relative_path == "profiles/dev/config.json"
        assert spec.absolute_path is None

    def test_with_absolute_path_and_template_resource(self):
        spec = ConfigSpec(
            absolute_path=Path("/tmp/config.json"),
            template_resource=("my_pkg", "default.json"),
        )
        assert spec.absolute_path == Path("/tmp/config.json")
        assert spec.xdg_relative_path is None
        assert spec.template_resource == ("my_pkg", "default.json")
        assert spec.template_bytes is None

    def test_location_both_null_raises(self):
        with pytest.raises(ValueError, match="Exactly one of xdg_relative_path or absolute_path"):
            ConfigSpec(template_bytes=b"{}")

    def test_location_both_set_raises(self):
        with pytest.raises(ValueError, match="Exactly one of xdg_relative_path or absolute_path"):
            ConfigSpec(
                xdg_relative_path="config.json",
                absolute_path="/tmp/config.json",
                template_bytes=b"{}",
            )

    def test_template_both_null_raises(self):
        with pytest.raises(ValueError, match="Exactly one"):
            ConfigSpec(xdg_relative_path="config.json")

    def test_template_both_set_raises(self):
        with pytest.raises(ValueError, match="Exactly one"):
            ConfigSpec(
                xdg_relative_path="config.json",
                template_bytes=b"{}",
                template_resource=("pkg", "res"),
            )

    def test_xdg_relative_path_must_be_relative(self):
        with pytest.raises(ValueError, match="xdg_relative_path must be relative"):
            ConfigSpec(xdg_relative_path="/tmp/config.json", template_bytes=b"{}")

    def test_xdg_relative_path_must_not_be_empty(self):
        with pytest.raises(ValueError, match="xdg_relative_path must not be empty"):
            ConfigSpec(xdg_relative_path="   ", template_bytes=b"{}")

    def test_xdg_relative_path_rejects_parent_traversal(self):
        with pytest.raises(ValueError, match="must not contain '..'"):
            ConfigSpec(xdg_relative_path="../config.json", template_bytes=b"{}")

    def test_absolute_path_must_be_absolute(self):
        with pytest.raises(ValueError, match="absolute_path must be absolute"):
            ConfigSpec(absolute_path="config.json", template_bytes=b"{}")

    def test_absolute_path_must_not_be_empty(self):
        with pytest.raises(ValueError, match="absolute_path must not be empty"):
            ConfigSpec(absolute_path="   ", template_bytes=b"{}")

    def test_absolute_path_may_use_tilde(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("HOME", str(tmp_path))
        spec = ConfigSpec(absolute_path="~/config.json", template_bytes=b"{}")
        assert spec.absolute_path == "~/config.json"

    def test_frozen(self):
        spec = ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}")
        with pytest.raises(AttributeError):
            spec.xdg_relative_path = "other"  # type: ignore[misc]


class TestEnvSpec:
    def test_fields(self):
        spec = EnvSpec(
            active_env_var="MY_ACTIVE",
            project_root_env_var="MY_ROOT",
            activate_script_name="activate.sh",
            deactivate_script_name="deactivate.sh",
        )
        assert spec.active_env_var == "MY_ACTIVE"
        assert spec.deactivate_script_name == "deactivate.sh"


class TestPluginSpec:
    def test_defaults(self):
        spec = PluginSpec()
        assert spec.explicit == []
        assert spec.entry_points == []


class TestCliSpec:
    def test_minimal(self):
        spec = CliSpec(
            prog_name="myapp",
            app_display_name="My App",
            dist_name="my-app",
            root_help="My application.",
            xdg=XdgSpec(app_dir_name="myapp"),
        )
        assert spec.prog_name == "myapp"
        assert spec.config is None
        assert spec.env is None
        assert spec.plugins == PluginSpec()
        assert spec.info_hooks == []

    def test_frozen(self):
        spec = CliSpec(
            prog_name="myapp",
            app_display_name="My App",
            dist_name="my-app",
            root_help="Help.",
            xdg=XdgSpec(app_dir_name="myapp"),
        )
        with pytest.raises(AttributeError):
            spec.prog_name = "other"  # type: ignore[misc]

    def test_with_config_and_env(self):
        spec = CliSpec(
            prog_name="myapp",
            app_display_name="My App",
            dist_name="my-app",
            root_help="Help.",
            xdg=XdgSpec(app_dir_name="myapp"),
            config=ConfigSpec(xdg_relative_path="cfg.json", template_bytes=b"{}"),
            env=EnvSpec(
                active_env_var="A",
                project_root_env_var="B",
                activate_script_name="a.sh",
                deactivate_script_name="d.sh",
            ),
        )
        assert spec.config is not None
        assert spec.env is not None
