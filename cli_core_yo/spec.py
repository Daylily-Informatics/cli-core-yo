"""Immutable configuration dataclasses for cli-core-yo.

All spec objects are frozen dataclasses — no runtime logic, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

# Regex for valid command/group names (§2.2)
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")


@dataclass(frozen=True)
class XdgSpec:
    """XDG Base Directory configuration."""

    app_dir_name: str


@dataclass(frozen=True)
class ConfigSpec:
    """Built-in config group configuration (§4.6)."""

    primary_filename: str
    template_bytes: bytes | None = None
    template_resource: tuple[str, str] | None = None
    validator: Callable[[str], list[str]] | None = None

    def __post_init__(self) -> None:
        has_bytes = self.template_bytes is not None
        has_resource = self.template_resource is not None
        if has_bytes == has_resource:
            raise ValueError(
                "Exactly one of template_bytes or template_resource must be non-null."
            )


@dataclass(frozen=True)
class EnvSpec:
    """Built-in env group configuration (§4.7)."""

    active_env_var: str
    project_root_env_var: str
    activate_script_name: str
    deactivate_script_name: str


@dataclass(frozen=True)
class PluginSpec:
    """Plugin loading configuration (§4.4)."""

    explicit: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CliSpec:
    """Top-level immutable specification for a CLI application.

    Downstream repos create exactly one instance and pass it to
    ``cli_core_yo.app.create_app()`` or ``cli_core_yo.app.run()``.
    """

    prog_name: str
    app_display_name: str
    dist_name: str
    root_help: str
    xdg: XdgSpec
    config: ConfigSpec | None = None
    env: EnvSpec | None = None
    plugins: PluginSpec = field(default_factory=PluginSpec)
    info_hooks: list[Callable[[], list[tuple[str, str]]]] = field(default_factory=list)
