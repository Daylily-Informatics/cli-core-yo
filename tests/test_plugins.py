"""Tests for plugin loading in v2."""

from __future__ import annotations

import sys
import types

import pytest

from cli_core_yo.errors import PluginLoadError
from cli_core_yo.plugins import _invoke_plugin, load_plugins
from cli_core_yo.registry import CommandRegistry
from cli_core_yo.spec import CliSpec, CommandPolicy, PluginSpec, PolicySpec, XdgSpec


def _spec(*, explicit: list[str] | None = None, entry_points: list[str] | None = None) -> CliSpec:
    return CliSpec(
        prog_name="demo",
        app_display_name="Demo",
        dist_name="demo",
        root_help="Demo CLI.",
        xdg=XdgSpec(app_dir_name="demo"),
        policy=PolicySpec(),
        plugins=PluginSpec(explicit=list(explicit or []), entry_points=list(entry_points or [])),
    )


def _register_command(registry: CommandRegistry, spec: CliSpec) -> None:
    registry.add_command(None, "hello", lambda: None, policy=CommandPolicy())


class TestLoadPlugins:
    def test_explicit_plugin_registers_commands(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = types.ModuleType("tests_plugin_ok")
        module.register = _register_command
        monkeypatch.setitem(sys.modules, module.__name__, module)

        registry = CommandRegistry()
        load_plugins(registry, _spec(explicit=[f"{module.__name__}.register"]))

        command = registry.get_command(("hello",))
        assert command is not None

    def test_invalid_explicit_import_raises(self) -> None:
        registry = CommandRegistry()
        with pytest.raises(PluginLoadError, match="does_not_exist"):
            load_plugins(registry, _spec(explicit=["does_not_exist.register"]))

    def test_invalid_explicit_import_path_shape_raises(self) -> None:
        registry = CommandRegistry()
        with pytest.raises(PluginLoadError, match="Invalid import path"):
            load_plugins(registry, _spec(explicit=["not-a-dotted-path"]))

    def test_plugin_exception_is_wrapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def bad_plugin(registry: CommandRegistry, spec: CliSpec) -> None:
            raise RuntimeError("boom")

        module = types.ModuleType("tests_plugin_bad")
        module.register = bad_plugin
        monkeypatch.setitem(sys.modules, module.__name__, module)

        registry = CommandRegistry()
        with pytest.raises(PluginLoadError, match="boom"):
            load_plugins(registry, _spec(explicit=[f"{module.__name__}.register"]))

    def test_entry_point_plugin_registers_commands(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeEntryPoint:
            def load(self):
                return _register_command

        monkeypatch.setattr(
            "cli_core_yo.plugins.entry_points",
            lambda **kwargs: [FakeEntryPoint()],
        )

        registry = CommandRegistry()
        load_plugins(registry, _spec(entry_points=["hello-plugin"]))

        command = registry.get_command(("hello",))
        assert command is not None

    def test_missing_entry_point_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("cli_core_yo.plugins.entry_points", lambda **kwargs: [])

        registry = CommandRegistry()
        with pytest.raises(PluginLoadError, match="No entry point 'missing-plugin'"):
            load_plugins(registry, _spec(entry_points=["missing-plugin"]))

    def test_entry_point_loader_exception_is_wrapped(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeEntryPoint:
            def load(self):
                raise RuntimeError("entry-point boom")

        monkeypatch.setattr(
            "cli_core_yo.plugins.entry_points",
            lambda **kwargs: [FakeEntryPoint()],
        )

        registry = CommandRegistry()
        with pytest.raises(PluginLoadError, match="entry-point boom"):
            load_plugins(registry, _spec(entry_points=["bad-plugin"]))

    def test_plugin_load_error_is_re_raised(self) -> None:
        registry = CommandRegistry()
        expected = PluginLoadError("demo", "already wrapped")

        def already_wrapped(_registry: CommandRegistry, _spec: CliSpec) -> None:
            raise expected

        with pytest.raises(PluginLoadError) as exc_info:
            _invoke_plugin(already_wrapped, "demo", registry, _spec())

        assert exc_info.value is expected
