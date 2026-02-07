"""Tests for cli_root_yo.registry."""

from __future__ import annotations

import pytest
import typer

from cli_root_yo.errors import RegistryConflictError, RegistryFrozenError
from cli_root_yo.registry import CommandRegistry


def _noop() -> None:
    """Dummy callback for command registration."""


class TestAddGroup:
    def test_add_group(self):
        reg = CommandRegistry()
        reg.add_group("tools", help_text="Tool commands.")
        assert "tools" in reg._roots

    def test_duplicate_group_same_help_merges(self):
        reg = CommandRegistry()
        reg.add_group("tools", help_text="Tool commands.")
        reg.add_group("tools", help_text="Tool commands.")  # no error
        assert "tools" in reg._roots

    def test_duplicate_group_empty_help_merges(self):
        reg = CommandRegistry()
        reg.add_group("tools", help_text="Tool commands.")
        reg.add_group("tools", help_text="")  # no error — empty help is allowed
        assert reg._roots["tools"].help_text == "Tool commands."

    def test_duplicate_group_fills_empty_help(self):
        reg = CommandRegistry()
        reg.add_group("tools")
        reg.add_group("tools", help_text="Now has help.")
        assert reg._roots["tools"].help_text == "Now has help."

    def test_duplicate_group_mismatched_help_raises(self):
        reg = CommandRegistry()
        reg.add_group("tools", help_text="Help A.")
        with pytest.raises(RegistryConflictError, match="mismatch"):
            reg.add_group("tools", help_text="Help B.")

    def test_group_over_command_raises(self):
        reg = CommandRegistry()
        reg.add_command(None, "tools", _noop)
        with pytest.raises(RegistryConflictError):
            reg.add_group("tools")


class TestAddCommand:
    def test_root_command(self):
        reg = CommandRegistry()
        reg.add_command(None, "greet", _noop, help_text="Say hello.")
        assert "greet" in reg._roots

    def test_command_under_group(self):
        reg = CommandRegistry()
        reg.add_group("tools")
        reg.add_command("tools", "run", _noop, help_text="Run a tool.")
        assert "run" in reg._roots["tools"].children

    def test_duplicate_command_raises(self):
        reg = CommandRegistry()
        reg.add_command(None, "greet", _noop)
        with pytest.raises(RegistryConflictError, match="already registered"):
            reg.add_command(None, "greet", _noop)

    def test_command_over_group_raises(self):
        """Registering a command where a group already exists must fail."""
        reg = CommandRegistry()
        reg.add_group("tools")
        with pytest.raises(RegistryConflictError):
            reg.add_command(None, "tools", _noop)

    def test_auto_creates_intermediate_groups(self):
        reg = CommandRegistry()
        reg.add_command("a/b", "leaf", _noop)
        assert "a" in reg._roots
        assert "b" in reg._roots["a"].children
        assert "leaf" in reg._roots["a"].children["b"].children


class TestAddTyperApp:
    def test_root_typer_app(self):
        sub = typer.Typer()
        reg = CommandRegistry()
        reg.add_typer_app(None, sub, "ext", help_text="External app.")
        assert "ext" in reg._roots

    def test_duplicate_typer_app_raises(self):
        sub = typer.Typer()
        reg = CommandRegistry()
        reg.add_typer_app(None, sub, "ext")
        with pytest.raises(RegistryConflictError):
            reg.add_typer_app(None, sub, "ext")


class TestFreeze:
    def test_freeze_blocks_add_group(self):
        reg = CommandRegistry()
        reg.freeze()
        with pytest.raises(RegistryFrozenError):
            reg.add_group("tools")

    def test_freeze_blocks_add_command(self):
        reg = CommandRegistry()
        reg.freeze()
        with pytest.raises(RegistryFrozenError):
            reg.add_command(None, "greet", _noop)

    def test_freeze_blocks_add_typer_app(self):
        reg = CommandRegistry()
        reg.freeze()
        with pytest.raises(RegistryFrozenError):
            reg.add_typer_app(None, typer.Typer(), "ext")

    def test_is_frozen_property(self):
        reg = CommandRegistry()
        assert not reg.is_frozen
        reg.freeze()
        assert reg.is_frozen


class TestNaming:
    def test_invalid_name_raises(self):
        reg = CommandRegistry()
        with pytest.raises(ValueError, match="Invalid command name"):
            reg.add_command(None, "UPPER", _noop)

    def test_reserved_name_raises(self):
        reg = CommandRegistry()
        with pytest.raises(RegistryConflictError, match="reserved"):
            reg.add_command(None, "version", _noop)

    def test_reserved_info_raises(self):
        reg = CommandRegistry()
        with pytest.raises(RegistryConflictError, match="reserved"):
            reg.add_group("info")

    def test_extra_reserved_names(self):
        reg = CommandRegistry(reserved_names=frozenset({"config", "env"}))
        with pytest.raises(RegistryConflictError, match="reserved"):
            reg.add_group("config")


class TestOrdering:
    def test_registration_order_preserved(self):
        reg = CommandRegistry()
        reg.add_command(None, "beta", _noop)
        reg.add_command(None, "alpha", _noop)
        reg.add_command(None, "gamma", _noop)
        ordered = sorted(reg._roots.values(), key=lambda n: n.order)
        assert [n.name for n in ordered] == ["beta", "alpha", "gamma"]

    def test_explicit_order_overrides(self):
        reg = CommandRegistry()
        reg.add_command(None, "second", _noop, order=20)
        reg.add_command(None, "first", _noop, order=10)
        ordered = sorted(reg._roots.values(), key=lambda n: n.order)
        assert [n.name for n in ordered] == ["first", "second"]

