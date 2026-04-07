"""Tests for the v2 command registry."""

from __future__ import annotations

import pytest

from cli_core_yo.errors import RegistryConflictError, RegistryFrozenError
from cli_core_yo.registry import CommandRegistry
from cli_core_yo.spec import CommandPolicy


def _callback() -> None:
    return None


class TestCommandRegistry:
    def test_add_command_requires_policy(self) -> None:
        registry = CommandRegistry()
        with pytest.raises(TypeError):
            registry.add_command(None, "demo", _callback)  # type: ignore[call-arg]

    def test_add_typer_app_is_not_supported(self) -> None:
        registry = CommandRegistry()
        assert not hasattr(registry, "add_typer_app")

    def test_freeze_blocks_mutation(self) -> None:
        registry = CommandRegistry()
        registry.freeze()
        with pytest.raises(RegistryFrozenError):
            registry.add_group("admin")
        with pytest.raises(RegistryFrozenError):
            registry.add_command(None, "demo", _callback, policy=CommandPolicy())

    def test_duplicate_command_path_rejected(self) -> None:
        registry = CommandRegistry()
        registry.add_command(None, "demo", _callback, policy=CommandPolicy())
        with pytest.raises(RegistryConflictError):
            registry.add_command(None, "demo", _callback, policy=CommandPolicy())

    def test_resolve_nested_command_path(self) -> None:
        registry = CommandRegistry()
        policy = CommandPolicy(supports_json=True)
        registry.add_command("admin/users", "list", _callback, policy=policy)

        command = registry.resolve_command_args(["admin", "users", "list", "--json"])

        assert command is not None
        assert command.path == ("admin", "users", "list")
        assert command.policy is policy

    def test_invalid_name_rejected(self) -> None:
        registry = CommandRegistry()
        with pytest.raises(ValueError, match="Invalid command name"):
            registry.add_command(None, "BadName", _callback, policy=CommandPolicy())

    def test_group_path_conflict_rejected(self) -> None:
        registry = CommandRegistry()
        registry.add_command(None, "admin", _callback, policy=CommandPolicy())

        with pytest.raises(RegistryConflictError, match="expected group"):
            registry.add_command("admin/users", "list", _callback, policy=CommandPolicy())
