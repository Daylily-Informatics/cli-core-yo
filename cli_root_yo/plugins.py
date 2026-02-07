"""Deterministic plugin discovery and loading (§4.4).

Plugin callable signature: (registry: CommandRegistry, spec: CliSpec) -> None

Loading order:
1. spec.plugins.explicit — import paths loaded in list order
2. spec.plugins.entry_points — entry-point names loaded in list order

Entry point group: cli_root_yo.plugins
"""

from __future__ import annotations

import importlib
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from cli_root_yo import output
from cli_root_yo.errors import PluginLoadError

if TYPE_CHECKING:
    from cli_root_yo.registry import CommandRegistry
    from cli_root_yo.spec import CliSpec, PluginSpec

# Entry-point group name (§4.4)
_EP_GROUP = "cli_root_yo.plugins"


def load_plugins(
    registry: CommandRegistry,
    spec: CliSpec,
) -> None:
    """Load all plugins defined in spec.plugins, in deterministic order.

    Explicit plugins first, then entry-point plugins.
    Raises PluginLoadError on import failure or registration exception.
    """
    plugin_spec = spec.plugins

    # Phase 1: explicit plugins (import-path strings)
    for import_path in plugin_spec.explicit:
        _load_explicit(import_path, registry, spec)

    # Phase 2: entry-point plugins
    for ep_name in plugin_spec.entry_points:
        _load_entry_point(ep_name, registry, spec)


def _load_explicit(
    import_path: str,
    registry: CommandRegistry,
    spec: CliSpec,
) -> None:
    """Import and invoke a single explicit plugin callable."""
    try:
        module_path, _, attr_name = import_path.rpartition(".")
        if not module_path:
            raise ImportError(f"Invalid import path: '{import_path}' (no module component)")
        module = importlib.import_module(module_path)
        callable_ = getattr(module, attr_name)
    except Exception as exc:
        output.error(f"Plugin '{import_path}': {exc}")
        raise PluginLoadError(import_path, str(exc)) from exc

    try:
        callable_(registry, spec)
    except PluginLoadError:
        raise
    except Exception as exc:
        output.error(f"Plugin '{import_path}' raised: {exc}")
        raise PluginLoadError(import_path, str(exc)) from exc


def _load_entry_point(
    ep_name: str,
    registry: CommandRegistry,
    spec: CliSpec,
) -> None:
    """Discover and invoke a single entry-point plugin by name."""
    try:
        eps = entry_points(group=_EP_GROUP, name=ep_name)
        matches = list(eps)
        if not matches:
            raise ImportError(f"No entry point '{ep_name}' in group '{_EP_GROUP}'")
        # Use the first match (deterministic: name is unique per dist)
        callable_ = matches[0].load()
    except Exception as exc:
        output.error(f"Entry-point plugin '{ep_name}': {exc}")
        raise PluginLoadError(ep_name, str(exc)) from exc

    try:
        callable_(registry, spec)
    except PluginLoadError:
        raise
    except Exception as exc:
        output.error(f"Entry-point plugin '{ep_name}' raised: {exc}")
        raise PluginLoadError(ep_name, str(exc)) from exc

