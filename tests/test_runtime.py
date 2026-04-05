"""Tests for cli_core_yo.runtime."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli_core_yo.errors import ContextNotInitializedError
from cli_core_yo.runtime import RuntimeContext, _reset, get_context, initialize
from cli_core_yo.spec import CliSpec, XdgSpec
from cli_core_yo.xdg import XdgPaths


@pytest.fixture()
def dummy_spec():
    return CliSpec(
        prog_name="test",
        app_display_name="Test",
        dist_name="test-app",
        root_help="Test app.",
        xdg=XdgSpec(app_dir_name="test"),
    )


@pytest.fixture()
def dummy_paths(tmp_path: Path):
    return XdgPaths(
        config=tmp_path / "cfg",
        data=tmp_path / "data",
        state=tmp_path / "state",
        cache=tmp_path / "cache",
    )


class TestInitialize:
    def test_init_and_get(self, dummy_spec, dummy_paths):
        ctx = initialize(dummy_spec, dummy_paths)
        assert isinstance(ctx, RuntimeContext)
        assert get_context() is ctx
        assert ctx.spec is dummy_spec
        assert ctx.config_path is None
        assert ctx.json_mode is False
        assert ctx.debug is False

    def test_init_with_flags(self, dummy_spec, dummy_paths):
        ctx = initialize(dummy_spec, dummy_paths, json_mode=True, debug=True)
        assert ctx.json_mode is True
        assert ctx.debug is True

    def test_init_with_config_path(self, dummy_spec, dummy_paths, tmp_path: Path):
        config_path = tmp_path / "config.json"
        ctx = initialize(dummy_spec, dummy_paths, config_path=config_path)
        assert ctx.config_path == config_path

    def test_double_init_raises(self, dummy_spec, dummy_paths):
        initialize(dummy_spec, dummy_paths)
        with pytest.raises(RuntimeError, match="already initialized"):
            initialize(dummy_spec, dummy_paths)


class TestGetContext:
    def test_before_init_raises(self):
        with pytest.raises(ContextNotInitializedError):
            get_context()


class TestReset:
    def test_reset_allows_reinit(self, dummy_spec, dummy_paths):
        initialize(dummy_spec, dummy_paths)
        _reset()
        ctx2 = initialize(dummy_spec, dummy_paths)
        assert get_context() is ctx2
