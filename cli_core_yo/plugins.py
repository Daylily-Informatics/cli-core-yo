"""Deterministic plugin discovery and loading for cli-core-yo v2."""

from __future__ import annotations

import importlib
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Callable

from cli_core_yo.errors import PluginLoadError

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

_EP_GROUP = "cli_core_yo.plugins"


def load_plugins(registry: "CommandRegistry", spec: "CliSpec") -> None:
    """Load explicit plugins first, then named entry-point plugins."""
    for import_path in spec.plugins.explicit:
        _load_explicit(import_path, registry, spec)
    for entry_point_name in spec.plugins.entry_points:
        _load_entry_point(entry_point_name, registry, spec)


def _load_explicit(import_path: str, registry: "CommandRegistry", spec: "CliSpec") -> None:
    try:
        module_path, _, attr_name = import_path.rpartition(".")
        if not module_path or not attr_name:
            raise ImportError(f"Invalid import path '{import_path}'")
        module = importlib.import_module(module_path)
        plugin = getattr(module, attr_name)
    except Exception as exc:  # pragma: no cover - exact import failures vary by runtime
        raise PluginLoadError(import_path, str(exc)) from exc
    _invoke_plugin(plugin, import_path, registry, spec)


def _load_entry_point(
    entry_point_name: str,
    registry: "CommandRegistry",
    spec: "CliSpec",
) -> None:
    try:
        matches = list(entry_points(group=_EP_GROUP, name=entry_point_name))
        if not matches:
            raise ImportError(f"No entry point '{entry_point_name}' in group '{_EP_GROUP}'")
        plugin = matches[0].load()
    except Exception as exc:  # pragma: no cover - exact import failures vary by runtime
        raise PluginLoadError(entry_point_name, str(exc)) from exc
    _invoke_plugin(plugin, entry_point_name, registry, spec)


def _invoke_plugin(
    plugin: Callable[["CommandRegistry", "CliSpec"], None],
    plugin_name: str,
    registry: "CommandRegistry",
    spec: "CliSpec",
) -> None:
    try:
        plugin(registry, spec)
    except PluginLoadError:
        raise
    except Exception as exc:
        raise PluginLoadError(plugin_name, str(exc)) from exc
