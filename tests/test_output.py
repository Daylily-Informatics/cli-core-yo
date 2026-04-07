"""Tests for cli_core_yo.output."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cli_core_yo import output, runtime_checks
from cli_core_yo.runtime import _reset, initialize
from cli_core_yo.xdg import XdgPaths


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    output._reset_console()
    _reset()
    yield
    output._reset_console()
    _reset()


def _init_context(
    tmp_path: Path,
    *,
    json_mode: bool = False,
    debug: bool = False,
    no_color: bool = False,
) -> None:
    initialize(
        SimpleNamespace(name="test-spec"),
        XdgPaths(
            config=tmp_path / "config",
            data=tmp_path / "data",
            state=tmp_path / "state",
            cache=tmp_path / "cache",
        ),
        json_mode=json_mode,
        debug=debug,
        no_color=no_color,
    )


class TestHumanOutput:
    def test_stdout_helpers_write_stdout(self, capsys, tmp_path: Path) -> None:
        _init_context(tmp_path)
        output.heading("Title")
        output.success("done")
        output.action("working")
        output.detail("detail")
        output.bullet("item")
        output.print_text("literal")
        output.print_rich("[cyan]styled[/cyan]")

        captured = capsys.readouterr()
        assert "Title" in captured.out
        assert "done" in captured.out
        assert "working" in captured.out
        assert "detail" in captured.out
        assert "item" in captured.out
        assert "literal" in captured.out
        assert "styled" in captured.out
        assert captured.err == ""

    def test_diagnostics_write_stderr(self, capsys, tmp_path: Path) -> None:
        _init_context(tmp_path)
        output.warning("careful")
        output.error("failed")

        captured = capsys.readouterr()
        assert "careful" in captured.err
        assert "failed" in captured.err
        assert captured.out == ""


class TestJsonMode:
    def test_human_helpers_suppress_stdout(self, capsys, tmp_path: Path) -> None:
        _init_context(tmp_path, json_mode=True)
        output.success("done")
        output.heading("Title")
        output.action("working")
        output.detail("detail")
        output.bullet("item")
        output.print_text("literal")
        output.print_rich("[cyan]styled[/cyan]")
        output.warning("careful")

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "careful" in captured.err

    def test_debug_emits_only_when_enabled(self, capsys, tmp_path: Path) -> None:
        _init_context(tmp_path, debug=True)
        output.debug("diagnostic")
        captured = capsys.readouterr()
        assert "diagnostic" in captured.err

    def test_debug_is_silent_when_disabled(self, capsys, tmp_path: Path) -> None:
        _init_context(tmp_path, debug=False)
        output.debug("diagnostic")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_debug_uses_environment_flag_without_runtime_context(
        self, capsys, monkeypatch
    ) -> None:
        monkeypatch.setenv("CLI_CORE_YO_DEBUG", "1")
        output.debug("env diagnostic")

        captured = capsys.readouterr()

        assert captured.out == ""
        assert "env diagnostic" in captured.err


class TestJsonEmitters:
    def test_emit_json_is_deterministic(self, capsys) -> None:
        output.emit_json({"b": 2, "a": 1})
        raw = capsys.readouterr().out
        assert json.loads(raw) == {"a": 1, "b": 2}
        assert raw.endswith("\n")
        assert raw.index('"a"') < raw.index('"b"')

    def test_emit_json_handles_paths_and_nested_objects(self, capsys, tmp_path: Path) -> None:
        payload = {
            "path": tmp_path / "config.json",
            "nested": SimpleNamespace(value=1),
        }
        output.emit_json(payload)
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["path"] == str(tmp_path / "config.json")
        assert parsed["nested"]["value"] == 1

    def test_emit_json_handles_sets_and_string_fallbacks(self, capsys) -> None:
        class SlotOnly:
            __slots__ = ()

            def __str__(self) -> str:
                return "slot-only"

        output.emit_json({"tags": {"beta", "alpha"}, "value": SlotOnly()})

        parsed = json.loads(capsys.readouterr().out)

        assert parsed["tags"] == ["alpha", "beta"]
        assert parsed["value"] == "slot-only"

    def test_emit_error_json(self, capsys) -> None:
        output.emit_error_json("3", "runtime failed", {"detail": "missing"})
        parsed = json.loads(capsys.readouterr().out)
        assert parsed == {
            "error": {
                "code": "3",
                "details": {"detail": "missing"},
                "message": "runtime failed",
            }
        }

    def test_emit_prereq_report_json(self, capsys, tmp_path: Path) -> None:
        _init_context(tmp_path, json_mode=True)
        result = runtime_checks.PrereqResult(
            key="binary-ok",
            status="pass",
            severity="error",
            summary="Executable available",
            detail="/usr/bin/demo",
        )
        output.emit_prereq_report([result])
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["summary"]["pass"] == 1
        assert parsed["results"][0]["key"] == "binary-ok"

    def test_emit_prereq_report_human_mode_routes_rows_by_status(
        self, capsys, tmp_path: Path
    ) -> None:
        _init_context(tmp_path, json_mode=False)
        results = [
            runtime_checks.PrereqResult(
                key="ok",
                status="pass",
                severity="error",
                summary="All good",
                detail="/tmp/demo",
            ),
            runtime_checks.PrereqResult(
                key="skip",
                status="skip",
                severity="info",
                summary="Skipped",
                detail=None,
            ),
            runtime_checks.PrereqResult(
                key="warn",
                status="warn",
                severity="warn",
                summary="Needs attention",
                detail="check config",
            ),
        ]

        output.emit_prereq_report(results, heading_text="Runtime check")

        captured = capsys.readouterr()

        assert "Runtime check" in captured.out
        assert "Summary:" in captured.out
        assert "ok: All good" in captured.out
        assert "skip: Skipped" in captured.out
        assert "warn: Needs attention" in captured.err


class TestNoColor:
    def test_no_color_context_suppresses_ansi(self, capsys, tmp_path: Path) -> None:
        _init_context(tmp_path, no_color=True)
        output.success("done")
        captured = capsys.readouterr()
        assert "\x1b[" not in captured.out
        assert "\x1b[" not in captured.err

    def test_write_stderr_writes_directly(self, capsys) -> None:
        output._write_stderr("problem\n")

        captured = capsys.readouterr()

        assert captured.out == ""
        assert captured.err == "problem\n"
