"""UX output primitives for v2 stdout/stderr and JSON contracts."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

from rich.console import Console

_console: Console | None = None


def _reset_console() -> None:
    """Reset cached console state for tests."""
    global _console
    _console = None


def _current_context() -> Any | None:
    try:
        from cli_core_yo.runtime import get_context

        return get_context()
    except Exception:
        return None


def _is_json_mode() -> bool:
    ctx = _current_context()
    return bool(getattr(ctx, "json_mode", False)) if ctx is not None else False


def _no_color_enabled() -> bool:
    ctx = _current_context()
    if ctx is not None and getattr(ctx, "no_color", False):
        return True
    return "NO_COLOR" in os.environ


def _console_for(stream: Any) -> Console:
    return Console(
        file=stream,
        highlight=False,
        no_color=_no_color_enabled(),
        stderr=stream is sys.stderr,
    )


def _write_stdout(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def _write_stderr(text: str) -> None:
    sys.stderr.write(text)
    sys.stderr.flush()


def _render_console(stream: Any, renderable: Any) -> None:
    _console_for(stream).print(renderable)


def _json_dump(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)


def _json_ready(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(key): _json_ready(value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [_json_ready(value) for value in data]
    if isinstance(data, set):
        return sorted(_json_ready(value) for value in data)
    if isinstance(data, Path):
        return str(data)
    if data is None or isinstance(data, (str, int, float, bool)):
        return data
    if hasattr(data, "__dict__") and not isinstance(data, type):
        return {
            str(key): _json_ready(value)
            for key, value in vars(data).items()
            if not str(key).startswith("_")
        }
    return str(data)


def heading(title: str) -> None:
    if _is_json_mode():
        return
    _render_console(sys.stdout, f"\n[bold cyan]{title}[/bold cyan]\n")


def success(msg: str) -> None:
    if _is_json_mode():
        return
    _render_console(sys.stdout, f"[green]✓[/green] {msg}")


def warning(msg: str) -> None:
    _render_console(sys.stderr, f"[yellow]⚠[/yellow] {msg}")


def error(msg: str) -> None:
    _render_console(sys.stderr, f"[red]✗[/red] {msg}")


def action(msg: str) -> None:
    if _is_json_mode():
        return
    _render_console(sys.stdout, f"[cyan]→[/cyan] {msg}")


def detail(msg: str) -> None:
    if _is_json_mode():
        return
    _render_console(sys.stdout, f"   {msg}")


def bullet(msg: str) -> None:
    if _is_json_mode():
        return
    _render_console(sys.stdout, f"   • {msg}")


def print_text(msg: Any) -> None:
    if _is_json_mode():
        return
    text = str(msg)
    _write_stdout(text if text.endswith("\n") else f"{text}\n")


def print_rich(renderable: Any) -> None:
    if _is_json_mode():
        return
    _render_console(sys.stdout, renderable)


def debug(msg: str) -> None:
    ctx = _current_context()
    if ctx is None and "CLI_CORE_YO_DEBUG" not in os.environ:
        return
    if ctx is not None and not getattr(ctx, "debug", False):
        return
    _render_console(sys.stderr, f"[dim]debug[/dim] {msg}")


def emit_json(data: Any) -> None:
    _write_stdout(_json_dump(_json_ready(data)) + "\n")


def emit_error_json(code: str, message: str, details: Any | None = None) -> None:
    payload = {
        "error": {
            "code": code,
            "details": _json_ready(details),
            "message": message,
        }
    }
    emit_json(payload)


def emit_prereq_report(
    results: Iterable[Any],
    *,
    heading_text: str = "Prerequisite report",
) -> None:
    results_list = list(results)
    from cli_core_yo.runtime_checks import (
        prereq_report_payload,
        prereq_result_as_dict,
        summarize_prereq_results,
    )

    if _is_json_mode():
        emit_json(prereq_report_payload(results_list))
        return

    summary = summarize_prereq_results(results_list)
    heading(heading_text)
    detail(
        "Summary: "
        f"{summary['pass']} pass, {summary['warn']} warn, "
        f"{summary['fail']} fail, {summary['skip']} skip"
    )
    for result in results_list:
        row = prereq_result_as_dict(result)
        status = str(row["status"] or "skip")
        line = f"{row['key']}: {row['summary']}"
        if row["detail"]:
            line = f"{line} ({row['detail']})"
        if status == "pass":
            success(line)
        elif status == "skip":
            detail(line)
        else:
            warning(line)


class CliOutput:
    """Wrapper exposing the module-level output helpers."""

    heading = staticmethod(heading)
    success = staticmethod(success)
    warning = staticmethod(warning)
    error = staticmethod(error)
    action = staticmethod(action)
    detail = staticmethod(detail)
    bullet = staticmethod(bullet)
    print_text = staticmethod(print_text)
    print_rich = staticmethod(print_rich)
    emit_json = staticmethod(emit_json)
    emit_error_json = staticmethod(emit_error_json)
    emit_prereq_report = staticmethod(emit_prereq_report)
    debug = staticmethod(debug)
    info = staticmethod(detail)


ccyo_out = CliOutput()
