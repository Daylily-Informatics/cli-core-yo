"""Pytest-friendly conformance helpers for downstream v2 CLIs.

These helpers are intentionally small and composable so downstream repos can
assert the framework contract without reimplementing Click/Typer boilerplate.
"""

from __future__ import annotations

import inspect
import json
import re
from typing import Any, Mapping, Sequence

from click.testing import Result
from typer.testing import CliRunner

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def build_runner(*, mix_stderr: bool = False) -> CliRunner:
    """Return a Click runner configured for conformance assertions."""
    if "mix_stderr" in inspect.signature(CliRunner).parameters:
        return CliRunner(mix_stderr=mix_stderr)  # type: ignore[call-arg]
    return CliRunner()


def invoke(
    app: Any,
    argv: Sequence[str],
    *,
    input: str | bytes | None = None,
    env: Mapping[str, str] | None = None,
    prog_name: str | None = None,
    mix_stderr: bool = False,
) -> Result:
    """Invoke a CLI app and return the Click result object."""

    runner = build_runner(mix_stderr=mix_stderr)
    return runner.invoke(
        app,
        list(argv),
        input=input,
        env=None if env is None else dict(env),
        prog_name=prog_name,
    )


def stdout_text(result: Result) -> str:
    """Return captured stdout text, falling back to Click's combined output."""

    stdout = getattr(result, "stdout", None)
    if isinstance(stdout, str):
        return stdout
    output = getattr(result, "output", None)
    return output if isinstance(output, str) else ""


def stderr_text(result: Result) -> str:
    """Return captured stderr text when the runner separates streams."""

    stderr = getattr(result, "stderr", None)
    return stderr or ""


def combined_output(result: Result) -> str:
    """Return all captured output as a single string."""

    output = getattr(result, "output", None)
    if isinstance(output, str):
        return output
    return stdout_text(result) + stderr_text(result)


def json_output(result: Result) -> Any:
    """Parse stdout as JSON and return the decoded payload."""

    return json.loads(stdout_text(result))


def assert_exit_code(result: Result, expected: int) -> Result:
    """Assert the exit code matches and return the original result."""

    if result.exit_code != expected:
        raise AssertionError(
            f"expected exit code {expected}, got {result.exit_code}\n{combined_output(result)}"
        )
    return result


def assert_json_output(result: Result, expected: Any | None = None) -> Any:
    """Assert stdout is valid JSON and optionally compare it to ``expected``."""

    data = json_output(result)
    if expected is not None and data != expected:
        raise AssertionError(f"expected JSON {expected!r}, got {data!r}")
    return data


def assert_no_ansi(text: str) -> None:
    """Fail if the supplied text contains ANSI escape sequences."""

    if _ANSI_RE.search(text):
        raise AssertionError(f"ANSI escape codes found in output: {text!r}")


def assert_stdout_only(result: Result) -> None:
    """Assert stderr is empty for invocations that must be stdout-only."""

    if stderr_text(result).strip():
        raise AssertionError(f"unexpected stderr output: {stderr_text(result)!r}")
