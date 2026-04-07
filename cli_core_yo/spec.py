"""Immutable configuration dataclasses for cli-core-yo v2.

All spec objects are frozen dataclasses. Validation is limited to
field-local invariants inside each dataclass; cross-object validation
belongs to the app layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any, Callable, Literal

NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")

_ALLOWED_BACKEND_KINDS = {
    "system",
    "venv",
    "conda",
    "docker",
    "podman",
    "apptainer",
}
_ALLOWED_OUTPUT_STREAMS = {"stdout", "stderr"}
_ALLOWED_RUNTIME_GUARDS = {"off", "advisory", "enforced"}
_ALLOWED_COMMAND_GUARDS = {"required", "exempt", "advisory"}
_ALLOWED_PREREQ_KINDS = {
    "binary",
    "python_import",
    "env_var",
    "file",
    "directory",
    "command_probe",
}
_ALLOWED_CONTEXT_VALUE_TYPES = {"str", "int", "bool", "choice"}
_ALLOWED_DEPLOY_CAPABILITIES = {"plan", "apply", "status", "resume", "logs"}


def _require_str(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty.")


def _require_name(value: str, field_name: str) -> None:
    _require_str(value, field_name)
    if not NAME_RE.match(value):
        raise ValueError(f"{field_name} '{value}' is not a valid name.")


def _require_tuple_of_strs(value: tuple[str, ...], field_name: str) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{field_name} must be a tuple of strings.")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} entries must be non-empty strings.")
    if len(value) != len(set(value)):
        raise ValueError(f"{field_name} entries must be unique.")


@dataclass(frozen=True)
class XdgSpec:
    """XDG Base Directory configuration."""

    app_dir_name: str

    def __post_init__(self) -> None:
        _require_str(self.app_dir_name, "app_dir_name")
        if any(sep in self.app_dir_name for sep in ("/", "\\")):
            raise ValueError("app_dir_name must be a single path segment.")


@dataclass(frozen=True)
class ConfigSpec:
    """Built-in config group configuration."""

    xdg_relative_path: str | None = None
    absolute_path: str | Path | None = None
    template_bytes: bytes | None = None
    template_resource: tuple[str, str] | None = None
    validator: Callable[[str], list[str]] | None = None

    def __post_init__(self) -> None:
        has_relative = self.xdg_relative_path is not None
        has_absolute = self.absolute_path is not None
        has_bytes = self.template_bytes is not None
        has_resource = self.template_resource is not None

        if has_relative == has_absolute:
            raise ValueError(
                "Exactly one of xdg_relative_path or absolute_path must be non-null."
            )

        if self.xdg_relative_path is not None:
            _require_str(self.xdg_relative_path, "xdg_relative_path")
            xdg_path = PurePath(self.xdg_relative_path)
            if xdg_path.is_absolute():
                raise ValueError("xdg_relative_path must be relative.")
            if any(part == ".." for part in xdg_path.parts):
                raise ValueError("xdg_relative_path must not contain '..'.")

        if self.absolute_path is not None:
            _require_str(str(self.absolute_path), "absolute_path")
            if not Path(self.absolute_path).expanduser().is_absolute():
                raise ValueError("absolute_path must be absolute.")

        if has_bytes == has_resource:
            raise ValueError(
                "Exactly one of template_bytes or template_resource must be non-null."
            )

        if self.template_resource is not None:
            if len(self.template_resource) != 2:
                raise ValueError("template_resource must be a (package, resource) pair.")
            pkg, resource = self.template_resource
            _require_str(pkg, "template_resource[0]")
            _require_str(resource, "template_resource[1]")
        if self.validator is not None and not callable(self.validator):
            raise ValueError("validator must be callable.")


@dataclass(frozen=True)
class BackendDetectSpec:
    """Local detection hints for a backend."""

    env_vars: tuple[str, ...] = ()
    binaries: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    command_probe: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not any((self.env_vars, self.binaries, self.files, self.command_probe)):
            raise ValueError("BackendDetectSpec requires at least one detection hint.")
        _require_tuple_of_strs(self.env_vars, "env_vars")
        _require_tuple_of_strs(self.binaries, "binaries")
        _require_tuple_of_strs(self.files, "files")
        _require_tuple_of_strs(self.command_probe, "command_probe")


@dataclass(frozen=True)
class BackendValidationSpec:
    """Local validation hints for a backend."""

    env_vars: tuple[str, ...] = ()
    binaries: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    command_probe: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not any((self.env_vars, self.binaries, self.files, self.command_probe)):
            raise ValueError("BackendValidationSpec requires at least one validation hint.")
        _require_tuple_of_strs(self.env_vars, "env_vars")
        _require_tuple_of_strs(self.binaries, "binaries")
        _require_tuple_of_strs(self.files, "files")
        _require_tuple_of_strs(self.command_probe, "command_probe")


@dataclass(frozen=True)
class ExecutionBackendSpec:
    """Execution backend declaration."""

    name: str
    kind: Literal["system", "venv", "conda", "docker", "podman", "apptainer"]
    entry_guidance: str
    detect: BackendDetectSpec
    validation: BackendValidationSpec

    def __post_init__(self) -> None:
        _require_str(self.name, "name")
        _require_str(self.entry_guidance, "entry_guidance")
        if self.kind not in _ALLOWED_BACKEND_KINDS:
            raise ValueError(f"kind '{self.kind}' is not a supported backend kind.")
        if not isinstance(self.detect, BackendDetectSpec):
            raise ValueError("detect must be a BackendDetectSpec instance.")
        if not isinstance(self.validation, BackendValidationSpec):
            raise ValueError("validation must be a BackendValidationSpec instance.")


@dataclass(frozen=True)
class EnvSpec:
    """Built-in env group configuration."""

    active_env_var: str
    project_root_env_var: str
    activate_script_name: str
    deactivate_script_name: str
    status_fields: list[str] = field(default_factory=list)
    allow_reset: bool = True
    preferred_backend: str | None = None

    def __post_init__(self) -> None:
        _require_str(self.active_env_var, "active_env_var")
        _require_str(self.project_root_env_var, "project_root_env_var")
        _require_str(self.activate_script_name, "activate_script_name")
        _require_str(self.deactivate_script_name, "deactivate_script_name")
        if self.preferred_backend is not None:
            _require_str(self.preferred_backend, "preferred_backend")
        if not isinstance(self.status_fields, list):
            raise ValueError("status_fields must be a list of strings.")
        if any(not isinstance(item, str) or not item.strip() for item in self.status_fields):
            raise ValueError("status_fields entries must be non-empty strings.")


@dataclass(frozen=True)
class PolicySpec:
    """Top-level policy profile declaration."""

    profile: Literal["platform-v2"] = "platform-v2"


@dataclass(frozen=True)
class OutputSpec:
    """Output policy owned by the framework."""

    support_json: bool = True
    support_no_color_flag: bool = True
    log_stream: Literal["stderr"] = "stderr"
    human_stream: Literal["stdout"] = "stdout"

    def __post_init__(self) -> None:
        if self.log_stream not in _ALLOWED_OUTPUT_STREAMS:
            raise ValueError("log_stream must be 'stdout' or 'stderr'.")
        if self.human_stream not in _ALLOWED_OUTPUT_STREAMS:
            raise ValueError("human_stream must be 'stdout' or 'stderr'.")


@dataclass(frozen=True)
class RuntimeSpec:
    """Runtime backend and prerequisite requirements."""

    supported_backends: list[ExecutionBackendSpec]
    default_backend: str | None = None
    guard_mode: Literal["off", "advisory", "enforced"] = "enforced"
    allow_skip_check: bool = False
    prereqs: list["PrereqSpec"] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.guard_mode not in _ALLOWED_RUNTIME_GUARDS:
            raise ValueError("guard_mode must be 'off', 'advisory', or 'enforced'.")
        if self.default_backend is not None:
            _require_str(self.default_backend, "default_backend")
        if not isinstance(self.supported_backends, list):
            raise ValueError("supported_backends must be a list of ExecutionBackendSpec.")
        if not isinstance(self.prereqs, list):
            raise ValueError("prereqs must be a list of PrereqSpec.")
        if any(
            not isinstance(backend, ExecutionBackendSpec)
            for backend in self.supported_backends
        ):
            raise ValueError("supported_backends entries must be ExecutionBackendSpec instances.")
        if any(not isinstance(prereq, PrereqSpec) for prereq in self.prereqs):
            raise ValueError("prereqs entries must be PrereqSpec instances.")


@dataclass(frozen=True)
class InvocationContextSpec:
    """Repository-defined invocation selector options."""

    options: list["ContextOptionSpec"] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.options, list):
            raise ValueError("options must be a list of ContextOptionSpec.")
        if any(not isinstance(option, ContextOptionSpec) for option in self.options):
            raise ValueError("options entries must be ContextOptionSpec instances.")


@dataclass(frozen=True)
class ContextOptionSpec:
    """A framework-parsed invocation selector option."""

    name: str
    option_flags: tuple[str, ...]
    value_type: Literal["str", "int", "bool", "choice"]
    default: Any = None
    help: str = ""
    choices: tuple[str, ...] = ()
    include_in_runtime_context: bool = True

    def __post_init__(self) -> None:
        _require_str(self.name, "name")
        _require_tuple_of_strs(self.option_flags, "option_flags")
        if not self.option_flags:
            raise ValueError("option_flags must not be empty.")
        if any(not flag.startswith("-") for flag in self.option_flags):
            raise ValueError("option_flags must be CLI flag names like '--env'.")
        if len(self.option_flags) != len(set(self.option_flags)):
            raise ValueError("option_flags entries must be unique.")
        if self.value_type not in _ALLOWED_CONTEXT_VALUE_TYPES:
            raise ValueError("value_type is not supported.")
        if self.value_type == "choice":
            _require_tuple_of_strs(self.choices, "choices")
            if not self.choices:
                raise ValueError("choices must not be empty when value_type is 'choice'.")
            if self.default is not None and self.default not in self.choices:
                raise ValueError("default must be one of choices when value_type is 'choice'.")
        elif self.choices:
            raise ValueError("choices are only valid when value_type is 'choice'.")

        if (
            self.value_type == "int"
            and self.default is not None
            and type(self.default) is not int
        ):
            raise ValueError("default must be an int when value_type is 'int'.")
        if (
            self.value_type == "bool"
            and self.default is not None
            and type(self.default) is not bool
        ):
            raise ValueError("default must be a bool when value_type is 'bool'.")
        if (
            self.value_type == "str"
            and self.default is not None
            and not isinstance(self.default, str)
        ):
            raise ValueError("default must be a string when value_type is 'str'.")


@dataclass(frozen=True)
class DeploySpec:
    """Minimal deployment metadata."""

    capabilities: set[Literal["plan", "apply", "status", "resume", "logs"]]
    require_confirmation_for_apply: bool = True
    emit_plan_json: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.capabilities, set):
            raise ValueError("capabilities must be a set of deployment capabilities.")
        if any(cap not in _ALLOWED_DEPLOY_CAPABILITIES for cap in self.capabilities):
            raise ValueError("capabilities contains an unsupported entry.")


@dataclass(frozen=True)
class PrereqSpec:
    """A local deterministic prerequisite declaration."""

    key: str
    kind: Literal[
        "binary",
        "python_import",
        "env_var",
        "file",
        "directory",
        "command_probe",
    ]
    value: str | tuple[str, ...]
    help: str = ""
    severity: Literal["error", "warn", "info"] = "error"
    applies_to_backends: set[str] = field(default_factory=set)
    tags: set[str] = field(default_factory=set)
    success_message: str | None = None
    failure_message: str | None = None

    def __post_init__(self) -> None:
        _require_str(self.key, "key")
        if self.kind not in _ALLOWED_PREREQ_KINDS:
            raise ValueError("kind is not a supported prerequisite kind.")
        if self.severity not in {"error", "warn", "info"}:
            raise ValueError("severity must be 'error', 'warn', or 'info'.")
        if self.kind == "command_probe":
            if not isinstance(self.value, tuple) or not self.value:
                raise ValueError("value must be a non-empty tuple for command_probe.")
            _require_tuple_of_strs(self.value, "value")
        else:
            _require_str(self.value, "value")
        if not isinstance(self.applies_to_backends, set):
            raise ValueError("applies_to_backends must be a set of backend names.")
        if not isinstance(self.tags, set):
            raise ValueError("tags must be a set of strings.")
        if any(not isinstance(item, str) or not item.strip() for item in self.applies_to_backends):
            raise ValueError("applies_to_backends entries must be non-empty strings.")
        if any(not isinstance(item, str) or not item.strip() for item in self.tags):
            raise ValueError("tags entries must be non-empty strings.")


@dataclass(frozen=True)
class PrereqResult:
    """Result of evaluating a prerequisite."""

    key: str
    status: Literal["pass", "warn", "fail", "skip"]
    severity: Literal["error", "warn", "info"]
    summary: str
    detail: str | None = None


@dataclass(frozen=True)
class CommandPolicy:
    """Per-command enforcement policy."""

    mutates_state: bool = False
    supports_json: bool = False
    supports_dry_run: bool = False
    runtime_guard: Literal["required", "exempt", "advisory"] = "required"
    interactive: bool = False
    long_running: bool = False
    prereq_tags: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.runtime_guard not in _ALLOWED_COMMAND_GUARDS:
            raise ValueError("runtime_guard must be 'required', 'exempt', or 'advisory'.")
        if self.supports_dry_run and not self.mutates_state:
            raise ValueError("supports_dry_run=True is only valid when mutates_state=True.")
        if not isinstance(self.prereq_tags, set):
            raise ValueError("prereq_tags must be a set of strings.")
        if any(not isinstance(tag, str) or not tag.strip() for tag in self.prereq_tags):
            raise ValueError("prereq_tags entries must be non-empty strings.")


@dataclass(frozen=True)
class CliSpec:
    """Top-level immutable specification for a CLI application."""

    prog_name: str
    app_display_name: str
    dist_name: str
    root_help: str
    xdg: XdgSpec
    policy: PolicySpec
    config: ConfigSpec | None = None
    env: EnvSpec | None = None
    runtime: RuntimeSpec | None = None
    context: InvocationContextSpec | None = None
    output: OutputSpec | None = None
    plugins: PluginSpec = field(default_factory=lambda: PluginSpec())
    info_hooks: list[Callable[[], list[tuple[str, str]]]] = field(default_factory=list)
    deploy: DeploySpec | None = None

    def __post_init__(self) -> None:
        _require_name(self.prog_name, "prog_name")
        _require_str(self.app_display_name, "app_display_name")
        _require_str(self.dist_name, "dist_name")
        _require_str(self.root_help, "root_help")
        if not isinstance(self.xdg, XdgSpec):
            raise ValueError("xdg must be an XdgSpec instance.")
        if not isinstance(self.policy, PolicySpec):
            raise ValueError("policy must be a PolicySpec instance.")
        if self.config is not None and not isinstance(self.config, ConfigSpec):
            raise ValueError("config must be a ConfigSpec instance.")
        if self.env is not None and not isinstance(self.env, EnvSpec):
            raise ValueError("env must be an EnvSpec instance.")
        if self.runtime is not None and not isinstance(self.runtime, RuntimeSpec):
            raise ValueError("runtime must be a RuntimeSpec instance.")
        if self.context is not None and not isinstance(self.context, InvocationContextSpec):
            raise ValueError("context must be an InvocationContextSpec instance.")
        if self.output is not None and not isinstance(self.output, OutputSpec):
            raise ValueError("output must be an OutputSpec instance.")
        if not isinstance(self.plugins, PluginSpec):
            raise ValueError("plugins must be a PluginSpec instance.")
        if not isinstance(self.info_hooks, list):
            raise ValueError("info_hooks must be a list of callables.")
        if any(not callable(hook) for hook in self.info_hooks):
            raise ValueError("info_hooks entries must be callable.")
        if self.deploy is not None and not isinstance(self.deploy, DeploySpec):
            raise ValueError("deploy must be a DeploySpec instance.")


@dataclass(frozen=True)
class PluginSpec:
    """Plugin loading configuration."""

    explicit: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.explicit, list) or not isinstance(self.entry_points, list):
            raise ValueError("explicit and entry_points must be lists of strings.")
        if any(not isinstance(item, str) or not item.strip() for item in self.explicit):
            raise ValueError("explicit entries must be non-empty strings.")
        if any(not isinstance(item, str) or not item.strip() for item in self.entry_points):
            raise ValueError("entry_points entries must be non-empty strings.")


__all__ = [
    "BackendDetectSpec",
    "BackendValidationSpec",
    "CliSpec",
    "CommandPolicy",
    "ConfigSpec",
    "ContextOptionSpec",
    "DeploySpec",
    "EnvSpec",
    "ExecutionBackendSpec",
    "InvocationContextSpec",
    "NAME_RE",
    "OutputSpec",
    "PluginSpec",
    "PolicySpec",
    "PrereqResult",
    "PrereqSpec",
    "RuntimeSpec",
    "XdgSpec",
]
