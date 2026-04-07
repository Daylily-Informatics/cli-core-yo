"""Tests for cli_core_yo package initialization."""

from __future__ import annotations

import builtins
import importlib
import sys
import types

import cli_core_yo


def test_import_prefers_version_module(monkeypatch) -> None:
    version_module = types.ModuleType("cli_core_yo._version")
    version_module.__version__ = "9.9.9"
    monkeypatch.setitem(sys.modules, "cli_core_yo._version", version_module)

    reloaded = importlib.reload(cli_core_yo)

    assert reloaded.__version__ == "9.9.9"

    importlib.reload(cli_core_yo)


def test_import_falls_back_when_version_module_is_missing(monkeypatch) -> None:
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "cli_core_yo._version":
            raise ImportError("missing test version module")
        return original_import(name, globals, locals, fromlist, level)

    with monkeypatch.context() as context:
        context.delitem(sys.modules, "cli_core_yo._version", raising=False)
        context.setattr(builtins, "__import__", fake_import)

        reloaded = importlib.reload(cli_core_yo)

        assert reloaded.__version__ == "0.0.0.dev0"

    importlib.reload(cli_core_yo)
