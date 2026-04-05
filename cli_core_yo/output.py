"""UX output primitives and JSON emitter (§6.1, §6.2, §2.8).

All human output goes through Rich Console.
JSON output bypasses Rich entirely.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from rich.console import Console

# Module-level console — lazy-initialized to respect NO_COLOR at call time.
_console: Console | None = None


def _get_console() -> Console:
    """Return a Console that writes to the *current* sys.stdout.

    A fresh Console is created each call so that test harnesses (e.g.
    Typer's CliRunner) that temporarily replace sys.stdout always
    receive the output.
    """
    no_color = "NO_COLOR" in os.environ
    return Console(
        file=sys.stdout,
        highlight=False,
        no_color=no_color,
        stderr=False,
    )


def _reset_console() -> None:
    """Reset the console (test-only)."""
    global _console
    _console = None


def _is_json_mode() -> bool:
    """Check if the current invocation is in JSON mode."""
    try:
        from cli_core_yo.runtime import get_context

        return get_context().json_mode
    except Exception:
        return False


# ── Human output primitives (§6.2) ──────────────────────────────────────────


def heading(title: str) -> None:
    """Print a section heading: blank line, bold cyan title, blank line."""
    if _is_json_mode():
        return
    con = _get_console()
    con.print()
    con.print(f"[bold cyan]{title}[/bold cyan]")
    con.print()


def success(msg: str) -> None:
    """Print a success line: ✓ prefix in green."""
    if _is_json_mode():
        return
    _get_console().print(f"[green]✓[/green] {msg}")


def warning(msg: str) -> None:
    """Print a warning line: ⚠ prefix in yellow."""
    if _is_json_mode():
        return
    _get_console().print(f"[yellow]⚠[/yellow] {msg}")


def error(msg: str) -> None:
    """Print an error line: ✗ prefix in red."""
    if _is_json_mode():
        return
    _get_console().print(f"[red]✗[/red] {msg}")


def action(msg: str) -> None:
    """Print an action line: → prefix in cyan."""
    if _is_json_mode():
        return
    _get_console().print(f"[cyan]→[/cyan] {msg}")


def detail(msg: str) -> None:
    """Print an indented detail line (3-space indent)."""
    if _is_json_mode():
        return
    _get_console().print(f"   {msg}")


def bullet(msg: str) -> None:
    """Print a bullet detail line (3-space indent + •)."""
    if _is_json_mode():
        return
    _get_console().print(f"   • {msg}")


def print_text(msg: Any) -> None:
    """Print arbitrary text or Rich renderable through the console (respects NO_COLOR)."""
    if _is_json_mode():
        return
    _get_console().print(msg)


# ── JSON emitter (§2.8) ─────────────────────────────────────────────────────


def emit_json(data: Any) -> None:
    """Write deterministic JSON to stdout, bypassing Rich.

    - indent=2, sort_keys=True, ensure_ascii=False
    - Trailing newline
    - No ANSI codes
    """
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


# ── Singleton output object ───────────────────────────────────────────────────


class CliOutput:
    """Collision-safe wrapper around the output module functions.

    Usage::

        from cli_core_yo import ccyo_out
        ccyo_out.info("hello")
        ccyo_out.error("oops")
    """

    heading = staticmethod(heading)
    success = staticmethod(success)
    warning = staticmethod(warning)
    error = staticmethod(error)
    action = staticmethod(action)
    detail = staticmethod(detail)
    bullet = staticmethod(bullet)
    print_text = staticmethod(print_text)
    emit_json = staticmethod(emit_json)
    info = staticmethod(detail)  # alias


ccyo_out = CliOutput()
