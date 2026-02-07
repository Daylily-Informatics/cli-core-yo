"""Command registry — the only supported mutation mechanism for the CLI tree (§3.2, §4.2–4.3).

Enforces naming rules, conflict rules, deterministic ordering, and freeze semantics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable

import typer

from cli_root_yo.errors import RegistryConflictError, RegistryFrozenError
from cli_root_yo.spec import NAME_RE

# Reserved root-level names (§4.2)
_ALWAYS_RESERVED = frozenset({"version", "info"})


class _NodeKind(Enum):
    GROUP = auto()
    COMMAND = auto()
    TYPER_APP = auto()


@dataclass
class _Node:
    kind: _NodeKind
    name: str
    help_text: str
    order: int
    callback: Callable[..., Any] | None = None
    typer_app: typer.Typer | None = None
    children: dict[str, _Node] = field(default_factory=dict)


class CommandRegistry:
    """Accumulates command/group registrations and applies them to a Typer app."""

    def __init__(self, *, reserved_names: frozenset[str] | None = None) -> None:
        self._roots: dict[str, _Node] = {}
        self._frozen = False
        self._counter = 0
        self._reserved = _ALWAYS_RESERVED | (reserved_names or frozenset())

    # ── Public registration API ──────────────────────────────────────────

    def add_group(self, name: str, help_text: str = "", order: int | None = None) -> None:
        """Register a command group at root level."""
        self._check_frozen()
        self._validate_name(name)
        ord_val = self._next_order(order)

        if name in self._roots:
            existing = self._roots[name]
            if existing.kind != _NodeKind.GROUP:
                raise RegistryConflictError(name, "exists as a command, cannot re-register as group")
            if help_text and existing.help_text and help_text != existing.help_text:
                raise RegistryConflictError(
                    name, f"group help mismatch: '{existing.help_text}' vs '{help_text}'"
                )
            # Merge: keep existing, update help if new is non-empty and old is empty
            if help_text and not existing.help_text:
                existing.help_text = help_text
            return

        self._roots[name] = _Node(
            kind=_NodeKind.GROUP, name=name, help_text=help_text, order=ord_val
        )

    def add_command(
        self,
        group_path: str | None,
        name: str,
        callback: Callable[..., Any],
        help_text: str = "",
        order: int | None = None,
    ) -> None:
        """Register a leaf command, optionally under a group path."""
        self._check_frozen()
        self._validate_name(name)
        ord_val = self._next_order(order)

        parent_node = self._resolve_parent(group_path)
        siblings = parent_node.children if parent_node is not None else self._roots

        if name in siblings:
            existing = siblings[name]
            raise RegistryConflictError(
                f"{group_path + '/' if group_path else ''}{name}",
                f"already registered as {existing.kind.name.lower()}",
            )

        siblings[name] = _Node(
            kind=_NodeKind.COMMAND, name=name, help_text=help_text,
            order=ord_val, callback=callback,
        )

    def add_typer_app(
        self,
        group_path: str | None,
        typer_app: typer.Typer,
        name: str,
        help_text: str = "",
        order: int | None = None,
    ) -> None:
        """Register a full Typer sub-app."""
        self._check_frozen()
        self._validate_name(name)
        ord_val = self._next_order(order)

        parent_node = self._resolve_parent(group_path)
        siblings = parent_node.children if parent_node is not None else self._roots

        if name in siblings:
            path_str = f"{group_path + '/' if group_path else ''}{name}"
            raise RegistryConflictError(path_str, "already registered")

        siblings[name] = _Node(
            kind=_NodeKind.TYPER_APP, name=name, help_text=help_text,
            order=ord_val, typer_app=typer_app,
        )

    def freeze(self) -> None:
        """Freeze the registry — no further mutations allowed."""
        self._frozen = True

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    # ── Apply to Typer ───────────────────────────────────────────────────

    def apply(self, app: typer.Typer) -> None:
        """Materialize all registrations onto the Typer app in order."""
        for node in sorted(self._roots.values(), key=lambda n: n.order):
            self._apply_node(app, node)

    # ── Internals ────────────────────────────────────────────────────────

    def _apply_node(self, parent: typer.Typer, node: _Node) -> None:
        if node.kind == _NodeKind.COMMAND:
            parent.command(name=node.name, help=node.help_text)(node.callback)
        elif node.kind == _NodeKind.TYPER_APP:
            parent.add_typer(node.typer_app, name=node.name, help=node.help_text)
        elif node.kind == _NodeKind.GROUP:
            sub = typer.Typer(name=node.name, help=node.help_text, no_args_is_help=True)
            for child in sorted(node.children.values(), key=lambda n: n.order):
                self._apply_node(sub, child)
            parent.add_typer(sub, name=node.name, help=node.help_text)

    def _check_frozen(self) -> None:
        """Raise RegistryFrozenError if the registry is frozen."""
        if self._frozen:
            raise RegistryFrozenError()

    def _validate_name(self, name: str) -> None:
        """Validate a command/group name against the naming regex and reserved list."""
        if not NAME_RE.match(name):
            raise ValueError(f"Invalid command name '{name}': must match {NAME_RE.pattern}")
        if name in self._reserved:
            raise RegistryConflictError(name, "is a reserved name")

    def _next_order(self, explicit: int | None) -> int:
        """Return the explicit order if given, otherwise auto-increment."""
        if explicit is not None:
            return explicit
        self._counter += 1
        return self._counter

    def _resolve_parent(self, group_path: str | None) -> _Node | None:
        """Walk the group path and return the leaf _Node, or None for root.

        Auto-creates intermediate groups as needed.
        """
        if group_path is None:
            return None

        parts = group_path.split("/")
        current_dict = self._roots

        node: _Node | None = None
        for i, part in enumerate(parts):
            if part not in current_dict:
                # Auto-create intermediate group
                ord_val = self._next_order(None)
                current_dict[part] = _Node(
                    kind=_NodeKind.GROUP, name=part, help_text="", order=ord_val
                )
            node = current_dict[part]
            if node.kind != _NodeKind.GROUP:
                path_so_far = "/".join(parts[: i + 1])
                raise RegistryConflictError(
                    path_so_far,
                    f"expected group but found {node.kind.name.lower()}",
                )
            current_dict = node.children

        return node

