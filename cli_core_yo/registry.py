"""Policy-aware command registry for cli-core-yo v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable

import typer

from cli_core_yo.errors import RegistryConflictError, RegistryFrozenError
from cli_core_yo.spec import NAME_RE, CommandPolicy

_ALWAYS_RESERVED: frozenset[str] = frozenset()


class _NodeKind(Enum):
    GROUP = auto()
    COMMAND = auto()


@dataclass(frozen=True)
class GroupMetadata:
    """Reserved extension point for help categorization and ordering."""

    category: str | None = None


@dataclass(frozen=True)
class CommandRegistration:
    """Immutable view of a registered command."""

    path: tuple[str, ...]
    name: str
    callback: Callable[..., Any]
    help_text: str
    order: int
    policy: CommandPolicy


@dataclass
class _Node:
    kind: _NodeKind
    name: str
    help_text: str
    order: int
    path: tuple[str, ...]
    callback: Callable[..., Any] | None = None
    policy: CommandPolicy | None = None
    metadata: GroupMetadata | None = None
    children: dict[str, _Node] = field(default_factory=dict)


class CommandRegistry:
    """Accumulate and freeze CLI command registrations before app construction."""

    def __init__(self, *, reserved_names: frozenset[str] | None = None) -> None:
        self._roots: dict[str, _Node] = {}
        self._reserved = set(_ALWAYS_RESERVED | (reserved_names or frozenset()))
        self._counter = 0
        self._frozen = False
        self._commands: dict[tuple[str, ...], CommandRegistration] = {}

    def add_group(
        self,
        name: str,
        *,
        help_text: str = "",
        order: int | None = None,
        metadata: GroupMetadata | None = None,
    ) -> None:
        self._check_frozen()
        self._validate_name(name)
        ord_val = self._next_order(order)

        if name in self._roots:
            existing = self._roots[name]
            if existing.kind != _NodeKind.GROUP:
                raise RegistryConflictError(name, "exists as a command")
            if help_text and existing.help_text and existing.help_text != help_text:
                raise RegistryConflictError(name, "group help mismatch")
            if help_text and not existing.help_text:
                existing.help_text = help_text
            return

        self._roots[name] = _Node(
            kind=_NodeKind.GROUP,
            name=name,
            help_text=help_text,
            order=ord_val,
            path=(name,),
            metadata=metadata,
        )

    def add_command(
        self,
        group_path: str | None,
        name: str,
        callback: Callable[..., Any],
        *,
        help_text: str = "",
        policy: CommandPolicy,
        order: int | None = None,
    ) -> None:
        self._check_frozen()
        self._validate_name(name)
        if policy is None:
            raise TypeError("policy is required")
        ord_val = self._next_order(order)
        parent = self._resolve_parent(group_path)
        siblings = self._roots if parent is None else parent.children
        path = (*(() if parent is None else parent.path), name)
        if name in siblings:
            raise RegistryConflictError("/".join(path), "already registered")
        node = _Node(
            kind=_NodeKind.COMMAND,
            name=name,
            help_text=help_text,
            order=ord_val,
            path=path,
            callback=callback,
            policy=policy,
        )
        siblings[name] = node
        self._commands[path] = CommandRegistration(
            path=path,
            name=name,
            callback=callback,
            help_text=help_text,
            order=ord_val,
            policy=policy,
        )

    def freeze(self) -> None:
        self._frozen = True

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    def get_command(self, path: str | tuple[str, ...]) -> CommandRegistration | None:
        key = tuple(path.split("/")) if isinstance(path, str) else path
        return self._commands.get(key)

    def resolve_command_args(self, argv: list[str]) -> CommandRegistration | None:
        node_dict = self._roots
        matched: tuple[str, ...] = ()
        node: _Node | None = None
        for token in argv:
            if token.startswith("-"):
                break
            node = node_dict.get(token)
            if node is None:
                break
            matched = (*matched, token)
            if node.kind == _NodeKind.COMMAND:
                return self._commands.get(matched)
            node_dict = node.children
        return None

    def apply(self, app: typer.Typer) -> None:
        for node in sorted(self._roots.values(), key=lambda item: item.order):
            self._apply_node(app, node)

    def _apply_node(self, parent: typer.Typer, node: _Node) -> None:
        if node.kind == _NodeKind.COMMAND:
            assert node.callback is not None
            parent.command(name=node.name, help=node.help_text)(node.callback)
            return
        sub = typer.Typer(
            name=node.name,
            help=node.help_text,
            no_args_is_help=True,
            rich_markup_mode="rich",
        )
        for child in sorted(node.children.values(), key=lambda item: item.order):
            self._apply_node(sub, child)
        parent.add_typer(sub, name=node.name, help=node.help_text)

    def _resolve_parent(self, group_path: str | None) -> _Node | None:
        if group_path is None:
            return None
        current_dict = self._roots
        node: _Node | None = None
        parts = tuple(part for part in group_path.split("/") if part)
        for index, part in enumerate(parts):
            self._validate_name(part)
            if part not in current_dict:
                ord_val = self._next_order(None)
                current_dict[part] = _Node(
                    kind=_NodeKind.GROUP,
                    name=part,
                    help_text="",
                    order=ord_val,
                    path=parts[: index + 1],
                )
            node = current_dict[part]
            if node.kind != _NodeKind.GROUP:
                raise RegistryConflictError("/".join(node.path), "expected group")
            current_dict = node.children
        return node

    def _check_frozen(self) -> None:
        if self._frozen:
            raise RegistryFrozenError()

    def _validate_name(self, name: str) -> None:
        if not NAME_RE.match(name):
            raise ValueError(f"Invalid command name '{name}': must match {NAME_RE.pattern}")
        if name in self._reserved:
            raise RegistryConflictError(name, "is a reserved name")

    def _next_order(self, explicit: int | None) -> int:
        if explicit is not None:
            return explicit
        self._counter += 1
        return self._counter
