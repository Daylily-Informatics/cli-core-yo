"""Tests for cli_root_yo.plugins."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cli_root_yo.errors import PluginLoadError
from cli_root_yo.plugins import _EP_GROUP, load_plugins
from cli_root_yo.registry import CommandRegistry
from cli_root_yo.spec import CliSpec, PluginSpec, XdgSpec


@pytest.fixture()
def dummy_spec():
    return CliSpec(
        prog_name="test",
        app_display_name="Test",
        dist_name="test-app",
        root_help="Help.",
        xdg=XdgSpec(app_dir_name="test"),
    )


@pytest.fixture()
def registry():
    return CommandRegistry()


class TestExplicitPlugins:
    def test_loads_explicit_plugin(self, registry):
        calls = []

        def plugin_fn(reg, spec):
            calls.append((reg, spec))

        spec = CliSpec(
            prog_name="test",
            app_display_name="Test",
            dist_name="test-app",
            root_help="Help.",
            xdg=XdgSpec(app_dir_name="test"),
            plugins=PluginSpec(explicit=["fake_mod.register"]),
        )
        with patch("cli_root_yo.plugins.importlib") as mock_importlib:
            mock_module = MagicMock()
            mock_module.register = plugin_fn
            mock_importlib.import_module.return_value = mock_module
            load_plugins(registry, spec)

        assert len(calls) == 1
        assert calls[0][0] is registry
        assert calls[0][1] is spec

    def test_import_error_raises_plugin_load_error(self, registry):
        spec = CliSpec(
            prog_name="test",
            app_display_name="Test",
            dist_name="test-app",
            root_help="Help.",
            xdg=XdgSpec(app_dir_name="test"),
            plugins=PluginSpec(explicit=["nonexistent.module.register"]),
        )
        with pytest.raises(PluginLoadError, match="nonexistent.module"):
            load_plugins(registry, spec)

    def test_plugin_raises_during_registration(self, registry):
        def bad_plugin(reg, spec):
            raise RuntimeError("kaboom")

        spec = CliSpec(
            prog_name="test",
            app_display_name="Test",
            dist_name="test-app",
            root_help="Help.",
            xdg=XdgSpec(app_dir_name="test"),
            plugins=PluginSpec(explicit=["fake_mod.bad_plugin"]),
        )
        with patch("cli_root_yo.plugins.importlib") as mock_importlib:
            mock_module = MagicMock()
            mock_module.bad_plugin = bad_plugin
            mock_importlib.import_module.return_value = mock_module
            with pytest.raises(PluginLoadError, match="kaboom"):
                load_plugins(registry, spec)

    def test_invalid_import_path_raises(self, registry):
        spec = CliSpec(
            prog_name="test",
            app_display_name="Test",
            dist_name="test-app",
            root_help="Help.",
            xdg=XdgSpec(app_dir_name="test"),
            plugins=PluginSpec(explicit=["no_dots"]),
        )
        with pytest.raises(PluginLoadError, match="no_dots"):
            load_plugins(registry, spec)


class TestEntryPointPlugins:
    def test_missing_entry_point_raises(self, registry):
        spec = CliSpec(
            prog_name="test",
            app_display_name="Test",
            dist_name="test-app",
            root_help="Help.",
            xdg=XdgSpec(app_dir_name="test"),
            plugins=PluginSpec(entry_points=["nonexistent_ep"]),
        )
        with pytest.raises(PluginLoadError, match="nonexistent_ep"):
            load_plugins(registry, spec)

    def test_entry_point_invoked(self, registry):
        calls = []

        def ep_plugin(reg, spec):
            calls.append(True)

        mock_ep = MagicMock()
        mock_ep.load.return_value = ep_plugin

        spec = CliSpec(
            prog_name="test",
            app_display_name="Test",
            dist_name="test-app",
            root_help="Help.",
            xdg=XdgSpec(app_dir_name="test"),
            plugins=PluginSpec(entry_points=["my-ep"]),
        )
        with patch("cli_root_yo.plugins.entry_points", return_value=[mock_ep]):
            load_plugins(registry, spec)
        assert len(calls) == 1


class TestLoadOrder:
    def test_explicit_before_entry_points(self, registry):
        order = []

        def explicit_fn(reg, spec):
            order.append("explicit")

        def ep_fn(reg, spec):
            order.append("entry_point")

        mock_ep = MagicMock()
        mock_ep.load.return_value = ep_fn

        spec = CliSpec(
            prog_name="test",
            app_display_name="Test",
            dist_name="test-app",
            root_help="Help.",
            xdg=XdgSpec(app_dir_name="test"),
            plugins=PluginSpec(explicit=["mod.fn"], entry_points=["my-ep"]),
        )
        with (
            patch("cli_root_yo.plugins.importlib") as mock_importlib,
            patch("cli_root_yo.plugins.entry_points", return_value=[mock_ep]),
        ):
            mock_module = MagicMock()
            mock_module.fn = explicit_fn
            mock_importlib.import_module.return_value = mock_module
            load_plugins(registry, spec)

        assert order == ["explicit", "entry_point"]

