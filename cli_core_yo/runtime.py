"""Runtime context — initialized once per CLI invocation (§3.2, §3.3)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cli_core_yo.errors import ContextNotInitializedError
from cli_core_yo.spec import CliSpec
from cli_core_yo.xdg import XdgPaths

# Module-level singleton
_context: RuntimeContext | None = None


@dataclass(frozen=True)
class RuntimeContext:
    """Immutable context available to all commands during a single invocation."""

    spec: CliSpec
    xdg_paths: XdgPaths
    config_path: Path | None = None
    json_mode: bool = False
    debug: bool = False


def initialize(
    spec: CliSpec,
    xdg_paths: XdgPaths,
    config_path: Path | None = None,
    json_mode: bool = False,
    debug: bool = False,
) -> RuntimeContext:
    """Initialize the runtime context. Must be called exactly once per invocation."""
    global _context
    if _context is not None:
        raise RuntimeError("RuntimeContext is already initialized.")
    _context = RuntimeContext(
        spec=spec,
        xdg_paths=xdg_paths,
        config_path=config_path,
        json_mode=json_mode,
        debug=debug,
    )
    return _context


def get_context() -> RuntimeContext:
    """Return the current invocation's context.

    Raises ContextNotInitializedError if called before initialize().
    """
    if _context is None:
        raise ContextNotInitializedError()
    return _context


def _reset() -> None:
    """Reset the context (test-only)."""
    global _context
    _context = None
