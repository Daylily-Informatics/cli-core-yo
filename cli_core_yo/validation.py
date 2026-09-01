"""Opt-in validation for downstream ``cli-core-yo`` command surfaces.

This module deliberately does not participate in app construction or runtime
execution. Downstream test suites and CI jobs call :func:`validate_cli`
explicitly with a declared :class:`CliSyntaxValidationConfig`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from cli_core_yo.app import root_option_flags
from cli_core_yo.registry import CommandRegistry
from cli_core_yo.spec import NAME_RE, CliSpec, CommandPolicy

CommandPath = tuple[str, ...]
CommandPathInput = str | Sequence[str]

_ALLOWED_RUNTIME_GUARDS = {"required", "exempt", "advisory"}
_ALLOWED_MODES = {"warn", "fail"}


def _normalize_path(value: CommandPathInput, field_name: str) -> CommandPath:
    if isinstance(value, str):
        path = tuple(value.split("/"))
    elif isinstance(value, Sequence):
        path = tuple(value)
    else:
        raise ValueError(f"{field_name} entries must be slash-delimited strings or sequences.")
    if not path or any(not isinstance(part, str) or not NAME_RE.fullmatch(part) for part in path):
        raise ValueError(f"{field_name} entries must be non-empty valid command paths.")
    return path


def _normalize_paths(
    values: tuple[CommandPathInput, ...], field_name: str
) -> tuple[CommandPath, ...]:
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple.")
    paths = tuple(_normalize_path(value, field_name) for value in values)
    if len(paths) != len(set(paths)):
        raise ValueError(f"{field_name} entries must be unique.")
    return paths


def _normalize_root_flags(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple of long option flags.")
    if any(
        not isinstance(flag, str) or not flag.startswith("--") or len(flag) == 2 for flag in values
    ):
        raise ValueError(f"{field_name} entries must be non-empty long option flags.")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} entries must be unique.")
    return tuple(sorted(values))


def _path_display(path: CommandPath | None) -> str | None:
    return None if path is None else "/".join(path)


def _is_valid_path(path: CommandPath) -> bool:
    return bool(path) and all(isinstance(part, str) and NAME_RE.fullmatch(part) for part in path)


@dataclass(frozen=True)
class CommandPolicyExpectation:
    """Optional policy values expected for one command path."""

    mutates_state: bool | None = None
    supports_json: bool | None = None
    supports_dry_run: bool | None = None
    runtime_guard: Literal["required", "exempt", "advisory"] | None = None
    interactive: bool | None = None
    long_running: bool | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "mutates_state",
            "supports_json",
            "supports_dry_run",
            "interactive",
            "long_running",
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"{field_name} must be a bool or None.")
        if self.runtime_guard is not None and self.runtime_guard not in _ALLOWED_RUNTIME_GUARDS:
            raise ValueError("runtime_guard must be 'required', 'exempt', 'advisory', or None.")


@dataclass(frozen=True)
class FindingAllowance:
    """Allow one declared validation finding during an intentional migration."""

    code: str
    path: CommandPathInput | None = None
    root_flag: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("code must be a non-empty string.")
        if self.path is not None and self.root_flag is not None:
            raise ValueError("path and root_flag cannot both be set.")
        if self.path is not None:
            object.__setattr__(self, "path", _normalize_path(self.path, "path"))
        if self.root_flag is not None:
            if not self.root_flag.startswith("--") or len(self.root_flag) == 2:
                raise ValueError("root_flag must be a non-empty long option flag.")


@dataclass(frozen=True)
class CliSyntaxValidationConfig:
    """Declared expectations for a downstream CLI surface.

    ``mode='fail'`` is suitable for CI gating. ``mode='warn'`` preserves the
    same findings but gives a zero exit code so a migration can be observed
    before it is enforced.
    """

    required_root_flags: tuple[str, ...] = ()
    forbidden_root_flags: tuple[str, ...] = ()
    required_commands: tuple[CommandPathInput, ...] = ()
    forbidden_commands: tuple[CommandPathInput, ...] = ()
    required_groups: tuple[CommandPathInput, ...] = ()
    forbidden_groups: tuple[CommandPathInput, ...] = ()
    policy_expectations: Mapping[CommandPathInput, CommandPolicyExpectation] = field(
        default_factory=dict
    )
    allowlisted_findings: tuple[FindingAllowance, ...] = ()
    mode: Literal["warn", "fail"] = "fail"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "required_root_flags",
            _normalize_root_flags(self.required_root_flags, "required_root_flags"),
        )
        object.__setattr__(
            self,
            "forbidden_root_flags",
            _normalize_root_flags(self.forbidden_root_flags, "forbidden_root_flags"),
        )
        object.__setattr__(
            self,
            "required_commands",
            _normalize_paths(self.required_commands, "required_commands"),
        )
        object.__setattr__(
            self,
            "forbidden_commands",
            _normalize_paths(self.forbidden_commands, "forbidden_commands"),
        )
        object.__setattr__(
            self,
            "required_groups",
            _normalize_paths(self.required_groups, "required_groups"),
        )
        object.__setattr__(
            self,
            "forbidden_groups",
            _normalize_paths(self.forbidden_groups, "forbidden_groups"),
        )
        if not isinstance(self.policy_expectations, Mapping):
            raise ValueError("policy_expectations must be a mapping.")
        normalized_expectations: dict[CommandPath, CommandPolicyExpectation] = {}
        for path, expectation in self.policy_expectations.items():
            normalized_path = _normalize_path(path, "policy_expectations")
            if normalized_path in normalized_expectations:
                raise ValueError("policy_expectations entries must be unique.")
            if not isinstance(expectation, CommandPolicyExpectation):
                raise ValueError("policy_expectations values must be CommandPolicyExpectation.")
            normalized_expectations[normalized_path] = expectation
        object.__setattr__(self, "policy_expectations", normalized_expectations)
        if not isinstance(self.allowlisted_findings, tuple):
            raise ValueError("allowlisted_findings must be a tuple.")
        if any(not isinstance(entry, FindingAllowance) for entry in self.allowlisted_findings):
            raise ValueError("allowlisted_findings entries must be FindingAllowance.")
        if self.mode not in _ALLOWED_MODES:
            raise ValueError("mode must be 'warn' or 'fail'.")


@dataclass(frozen=True)
class CommandPolicySurface:
    """Serializable snapshot of framework-owned command policy."""

    mutates_state: bool
    supports_json: bool
    supports_dry_run: bool
    runtime_guard: str
    interactive: bool
    long_running: bool
    prereq_tags: tuple[str, ...]

    @classmethod
    def from_policy(cls, policy: CommandPolicy) -> "CommandPolicySurface":
        return cls(
            mutates_state=policy.mutates_state,
            supports_json=policy.supports_json,
            supports_dry_run=policy.supports_dry_run,
            runtime_guard=policy.runtime_guard,
            interactive=policy.interactive,
            long_running=policy.long_running,
            prereq_tags=tuple(sorted(policy.prereq_tags)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutates_state": self.mutates_state,
            "supports_json": self.supports_json,
            "supports_dry_run": self.supports_dry_run,
            "runtime_guard": self.runtime_guard,
            "interactive": self.interactive,
            "long_running": self.long_running,
            "prereq_tags": list(self.prereq_tags),
        }


@dataclass(frozen=True)
class CommandSurface:
    """One normalized command path and its framework policy."""

    path: CommandPath
    policy: CommandPolicySurface

    def to_dict(self) -> dict[str, Any]:
        return {"path": _path_display(self.path), "policy": self.policy.to_dict()}


@dataclass(frozen=True)
class CliSurface:
    """Normalized command tree and root option surface for validation."""

    root_flags: tuple[str, ...]
    groups: tuple[CommandPath, ...]
    commands: tuple[CommandSurface, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_flags": list(self.root_flags),
            "groups": [_path_display(path) for path in self.groups],
            "commands": [command.to_dict() for command in self.commands],
        }


@dataclass(frozen=True)
class ValidationFinding:
    """One structured syntax-drift finding."""

    code: str
    message: str
    path: CommandPath | None = None
    root_flag: str | None = None
    expected: bool | str | None = None
    actual: bool | str | None = None
    allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "path": _path_display(self.path),
            "root_flag": self.root_flag,
            "expected": self.expected,
            "actual": self.actual,
            "allowed": self.allowed,
        }


@dataclass(frozen=True)
class ValidationReport:
    """Structured result for human inspection and machine-readable CI gating."""

    surface: CliSurface
    findings: tuple[ValidationFinding, ...]
    mode: Literal["warn", "fail"]

    @property
    def is_valid(self) -> bool:
        """Whether the observed surface has no unallowlisted drift."""

        return not any(not finding.allowed for finding in self.findings)

    @property
    def exit_code(self) -> int:
        """Return the CI-friendly result for the configured validation mode."""

        return 0 if self.mode == "warn" or self.is_valid else 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "valid": self.is_valid,
            "exit_code": self.exit_code,
            "surface": self.surface.to_dict(),
            "findings": [finding.to_dict() for finding in self.findings],
        }


def normalize_cli(app: Any) -> CliSurface:
    """Return a deterministic surface snapshot for a core-created Typer app."""

    registry = getattr(app, "_cli_core_yo_registry", None)
    spec = getattr(app, "_cli_core_yo_spec", None)
    if not isinstance(registry, CommandRegistry) or not isinstance(spec, CliSpec):
        raise TypeError("app must be created by cli_core_yo.app.create_app().")
    commands = tuple(
        CommandSurface(path=command.path, policy=CommandPolicySurface.from_policy(command.policy))
        for command in registry.command_registrations()
    )
    return CliSurface(
        root_flags=root_option_flags(spec),
        groups=registry.group_paths(),
        commands=commands,
    )


def validate_cli(app: Any, config: CliSyntaxValidationConfig) -> ValidationReport:
    """Validate a core-created app only when a caller explicitly requests it."""

    return validate_surface(normalize_cli(app), config)


def validate_surface(surface: CliSurface, config: CliSyntaxValidationConfig) -> ValidationReport:
    """Validate an already-normalized CLI surface against declared expectations."""

    if not isinstance(surface, CliSurface):
        raise TypeError("surface must be a CliSurface instance.")
    if not isinstance(config, CliSyntaxValidationConfig):
        raise TypeError("config must be a CliSyntaxValidationConfig instance.")

    findings: list[ValidationFinding] = []

    for flag in surface.root_flags:
        if not isinstance(flag, str) or not flag.startswith("--") or len(flag) == 2:
            findings.append(
                ValidationFinding(
                    code="invalid_root_flag",
                    root_flag=str(flag),
                    message=f"Observed root flag {flag!r} is not a valid long option flag.",
                )
            )

    group_paths = set(surface.groups)
    command_by_path: dict[CommandPath, CommandSurface] = {}
    for group_path in surface.groups:
        if not _is_valid_path(group_path):
            findings.append(
                ValidationFinding(
                    code="invalid_group_path",
                    path=group_path,
                    message=(
                        f"Observed group path {_path_display(group_path)!r} has invalid syntax."
                    ),
                )
            )
    for command in surface.commands:
        if not _is_valid_path(command.path):
            display_path = _path_display(command.path)
            findings.append(
                ValidationFinding(
                    code="invalid_command_path",
                    path=command.path,
                    message=f"Observed command path {display_path!r} has invalid syntax.",
                )
            )
            continue
        if command.path in command_by_path:
            display_path = _path_display(command.path)
            findings.append(
                ValidationFinding(
                    code="duplicate_command_path",
                    path=command.path,
                    message=f"Observed command path {display_path!r} more than once.",
                )
            )
            continue
        command_by_path[command.path] = command

    root_flags = set(surface.root_flags)
    for flag in config.required_root_flags:
        if flag not in root_flags:
            findings.append(
                ValidationFinding(
                    code="missing_root_flag",
                    root_flag=flag,
                    message=f"Required root flag {flag!r} is missing.",
                )
            )
    for flag in config.forbidden_root_flags:
        if flag in root_flags:
            findings.append(
                ValidationFinding(
                    code="forbidden_root_flag",
                    root_flag=flag,
                    message=f"Forbidden root flag {flag!r} is present.",
                )
            )
    for configured_path in config.required_groups:
        path = _normalize_path(configured_path, "required_groups")
        if path not in group_paths:
            findings.append(
                ValidationFinding(
                    code="missing_group",
                    path=path,
                    message=f"Required group {_path_display(path)!r} is missing.",
                )
            )
    for configured_path in config.forbidden_groups:
        path = _normalize_path(configured_path, "forbidden_groups")
        if path in group_paths:
            findings.append(
                ValidationFinding(
                    code="forbidden_group",
                    path=path,
                    message=f"Forbidden group {_path_display(path)!r} is present.",
                )
            )
    for configured_path in config.required_commands:
        path = _normalize_path(configured_path, "required_commands")
        if path not in command_by_path:
            findings.append(
                ValidationFinding(
                    code="missing_command",
                    path=path,
                    message=f"Required command {_path_display(path)!r} is missing.",
                )
            )
    for configured_path in config.forbidden_commands:
        path = _normalize_path(configured_path, "forbidden_commands")
        if path in command_by_path:
            findings.append(
                ValidationFinding(
                    code="forbidden_command",
                    path=path,
                    message=f"Forbidden command {_path_display(path)!r} is present.",
                )
            )
    for configured_path, expected_policy in config.policy_expectations.items():
        path = _normalize_path(configured_path, "policy_expectations")
        registered_command = command_by_path.get(path)
        if registered_command is None:
            continue
        findings.extend(_policy_findings(registered_command, expected_policy))

    allowed_findings = tuple(
        _mark_allowed(finding, config.allowlisted_findings) for finding in findings
    )
    return ValidationReport(surface=surface, findings=allowed_findings, mode=config.mode)


def _policy_findings(
    command: CommandSurface,
    expected_policy: CommandPolicyExpectation,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for field_name in (
        "mutates_state",
        "supports_json",
        "supports_dry_run",
        "runtime_guard",
        "interactive",
        "long_running",
    ):
        expected = getattr(expected_policy, field_name)
        if expected is None:
            continue
        actual = getattr(command.policy, field_name)
        if actual != expected:
            findings.append(
                ValidationFinding(
                    code="policy_mismatch",
                    path=command.path,
                    expected=expected,
                    actual=actual,
                    message=(
                        f"Command {_path_display(command.path)!r} policy {field_name!r} "
                        f"is {actual!r}, expected {expected!r}."
                    ),
                )
            )
    return findings


def _mark_allowed(
    finding: ValidationFinding,
    allowlist: tuple[FindingAllowance, ...],
) -> ValidationFinding:
    for allowance in allowlist:
        if allowance.code != finding.code:
            continue
        if allowance.path is not None and allowance.path != finding.path:
            continue
        if allowance.root_flag is not None and allowance.root_flag != finding.root_flag:
            continue
        return replace(finding, allowed=True)
    return finding


__all__ = [
    "CliSurface",
    "CliSyntaxValidationConfig",
    "CommandPolicyExpectation",
    "CommandPolicySurface",
    "CommandSurface",
    "FindingAllowance",
    "ValidationFinding",
    "ValidationReport",
    "normalize_cli",
    "validate_cli",
    "validate_surface",
]
