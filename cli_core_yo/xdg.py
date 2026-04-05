"""XDG Base Directory path resolution.

Resolves config, data, state, and cache directories per the XDG spec,
with macOS-specific paths for Library/Application Support.
"""

from __future__ import annotations

import os
import platform

from dataclasses import dataclass
from pathlib import Path

from cli_core_yo.spec import XdgSpec


@dataclass(frozen=True)
class XdgPaths:
    """Resolved XDG directory paths."""

    config: Path
    data: Path
    state: Path
    cache: Path


def _is_macos() -> bool:
    return platform.system() == "Darwin"


def resolve_paths(xdg_spec: XdgSpec) -> XdgPaths:
    """Resolve XDG directories for the given app, creating them if needed.

    Rules (§6.4):
    - Config: XDG_CONFIG_HOME or ~/.config
    - Data: XDG_DATA_HOME or ~/.local/share (Linux) / ~/Library/Application Support (macOS)
    - State: XDG_STATE_HOME or ~/.local/state (Linux) / ~/Library/Logs (macOS)
    - Cache: XDG_CACHE_HOME or ~/.cache (Linux) / ~/Library/Caches (macOS)
    """
    home = Path.home()
    macos = _is_macos()

    xdg_config = os.environ.get("XDG_CONFIG_HOME", "").strip()
    config_base = Path(xdg_config) if xdg_config else home / ".config"
    config_dir = config_base / xdg_spec.app_dir_name

    xdg_data = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg_data:
        data_base = Path(xdg_data)
    elif macos:
        data_base = home / "Library" / "Application Support"
    else:
        data_base = home / ".local" / "share"
    data_dir = data_base / xdg_spec.app_dir_name

    xdg_state = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg_state:
        state_base = Path(xdg_state)
    elif macos:
        state_base = home / "Library" / "Logs"
    else:
        state_base = home / ".local" / "state"
    state_dir = state_base / xdg_spec.app_dir_name

    xdg_cache = os.environ.get("XDG_CACHE_HOME", "").strip()
    if xdg_cache:
        cache_base = Path(xdg_cache)
    elif macos:
        cache_base = home / "Library" / "Caches"
    else:
        cache_base = home / ".cache"
    cache_dir = cache_base / xdg_spec.app_dir_name

    # Create directories (§6.4: parents=True, exist_ok=True)
    for d in (config_dir, data_dir, state_dir, cache_dir):
        d.mkdir(parents=True, exist_ok=True)

    return XdgPaths(config=config_dir, data=data_dir, state=state_dir, cache=cache_dir)
