"""Tests for cli_core_yo.output."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from cli_core_yo import output
from cli_core_yo.runtime import initialize
from cli_core_yo.spec import CliSpec, XdgSpec
from cli_core_yo.xdg import XdgPaths


@pytest.fixture(autouse=True)
def _clean_console():
    """Reset the console singleton between tests."""
    output._reset_console()
    yield
    output._reset_console()


@pytest.fixture()
def _init_context(tmp_path: Path):
    """Initialize a runtime context for output tests."""
    spec = CliSpec(
        prog_name="test",
        app_display_name="Test",
        dist_name="test-app",
        root_help="Help.",
        xdg=XdgSpec(app_dir_name="test"),
    )
    paths = XdgPaths(
        config=tmp_path / "c",
        data=tmp_path / "d",
        state=tmp_path / "s",
        cache=tmp_path / "k",
    )
    initialize(spec, paths)


@pytest.fixture()
def _init_json_context(tmp_path: Path):
    """Initialize a runtime context in JSON mode."""
    spec = CliSpec(
        prog_name="test",
        app_display_name="Test",
        dist_name="test-app",
        root_help="Help.",
        xdg=XdgSpec(app_dir_name="test"),
    )
    paths = XdgPaths(
        config=tmp_path / "c",
        data=tmp_path / "d",
        state=tmp_path / "s",
        cache=tmp_path / "k",
    )
    initialize(spec, paths, json_mode=True)


class TestHumanPrimitives:
    @pytest.mark.usefixtures("_init_context")
    def test_success_contains_checkmark(self, capsys):
        output.success("done")
        out = capsys.readouterr().out
        assert "✓" in out
        assert "done" in out

    @pytest.mark.usefixtures("_init_context")
    def test_warning_contains_symbol(self, capsys):
        output.warning("careful")
        out = capsys.readouterr().out
        assert "⚠" in out

    @pytest.mark.usefixtures("_init_context")
    def test_error_contains_symbol(self, capsys):
        output.error("failed")
        out = capsys.readouterr().out
        assert "✗" in out

    @pytest.mark.usefixtures("_init_context")
    def test_action_contains_arrow(self, capsys):
        output.action("doing")
        out = capsys.readouterr().out
        assert "→" in out

    @pytest.mark.usefixtures("_init_context")
    def test_detail_indented(self, capsys):
        output.detail("info")
        out = capsys.readouterr().out
        assert out.startswith("   ")

    @pytest.mark.usefixtures("_init_context")
    def test_bullet_indented_with_bullet(self, capsys):
        output.bullet("item")
        out = capsys.readouterr().out
        assert "   •" in out


class TestJsonModeSuppression:
    @pytest.mark.usefixtures("_init_json_context")
    def test_success_suppressed(self, capsys):
        output.success("done")
        assert capsys.readouterr().out == ""

    @pytest.mark.usefixtures("_init_json_context")
    def test_heading_suppressed(self, capsys):
        output.heading("Title")
        assert capsys.readouterr().out == ""


class TestEmitJson:
    def test_valid_json(self, capsys):
        output.emit_json({"b": 2, "a": 1})
        raw = capsys.readouterr().out
        parsed = json.loads(raw)
        assert parsed == {"a": 1, "b": 2}

    def test_sorted_keys(self, capsys):
        output.emit_json({"z": 1, "a": 2})
        raw = capsys.readouterr().out
        assert raw.index('"a"') < raw.index('"z"')

    def test_indent_2(self, capsys):
        output.emit_json({"key": "val"})
        raw = capsys.readouterr().out
        assert '  "key"' in raw

    def test_trailing_newline(self, capsys):
        output.emit_json({})
        raw = capsys.readouterr().out
        assert raw.endswith("\n")

    def test_utf8_passthrough(self, capsys):
        output.emit_json({"emoji": "🎉"})
        raw = capsys.readouterr().out
        assert "🎉" in raw


class TestNoColor:
    @pytest.mark.usefixtures("_init_context")
    def test_no_color_env(self, capsys):
        output._reset_console()
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            output.success("done")
        out = capsys.readouterr().out
        # Should not contain ANSI escape sequences
        assert "\x1b[" not in out


class TestCliOutputObject:
    @pytest.mark.usefixtures("_init_context")
    def test_ccyo_out_info_alias_uses_detail_output(self, capsys):
        output.ccyo_out.info("hello")
        out = capsys.readouterr().out
        assert out.startswith("   ")
        assert "hello" in out

    @pytest.mark.usefixtures("_init_context")
    def test_ccyo_out_exposes_emit_json(self, capsys):
        output.ccyo_out.emit_json({"ok": True})
        out = capsys.readouterr().out
        assert json.loads(out) == {"ok": True}
