"""Runtime context initialized once per CLI invocation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

from cli_core_yo.errors import ContextNotInitializedError
from cli_core_yo.spec import CliSpec
from cli_core_yo.xdg import XdgPaths

_context: RuntimeContext | None = None


@dataclass(frozen=True)
class RuntimeContext:
    """Immutable context available to commands during one invocation."""

    spec: CliSpec
    xdg_paths: XdgPaths
    config_path: Path | None = None
    json_mode: bool = False
    debug: bool = False
    no_color: bool = False
    invocation: Mapping[str, Any] = field(default_factory=dict)
    backend_name: str | None = None
    backend_kind: str | None = None
    runtime_guard_mode: Literal["off", "advisory", "enforced"] = "off"
    runtime_check_skipped: bool = False
    dry_run: bool = False


def initialize(
    spec: CliSpec,
    xdg_paths: XdgPaths,
    config_path: Path | None = None,
    *,
    json_mode: bool = False,
    debug: bool = False,
    no_color: bool = False,
    invocation: Mapping[str, Any] | None = None,
    backend_name: str | None = None,
    backend_kind: str | None = None,
    runtime_guard_mode: Literal["off", "advisory", "enforced"] = "off",
    runtime_check_skipped: bool = False,
    dry_run: bool = False,
) -> RuntimeContext:
    """Initialize the runtime context for the current invocation."""
    global _context
    if _context is not None:
        raise RuntimeError("RuntimeContext is already initialized.")
    _context = RuntimeContext(
        spec=spec,
        xdg_paths=xdg_paths,
        config_path=config_path,
        json_mode=json_mode,
        debug=debug,
        no_color=no_color,
        invocation=dict(invocation or {}),
        backend_name=backend_name,
        backend_kind=backend_kind,
        runtime_guard_mode=runtime_guard_mode,
        runtime_check_skipped=runtime_check_skipped,
        dry_run=dry_run,
    )
    return _context


def get_context() -> RuntimeContext:
    """Return the current invocation context."""
    if _context is None:
        raise ContextNotInitializedError()
    return _context


def _reset() -> None:
    """Reset the singleton context for tests."""
    global _context
    _context = None
