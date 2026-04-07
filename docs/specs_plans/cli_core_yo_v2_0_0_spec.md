# cli-core-yo v2.0.0 Refactor / Expansion Spec

Status: implementation spec  
Audience: Codex IDE working in `daylily/cli-core-yo` first, then downstream repos  
Date: 2026-04-06

## 0. Executive decision

`cli-core-yo` v2.0.0 will stop being a light CLI scaffold plus repo-local conventions and become an opinionated enforcement layer for platform CLI behavior.

This version is intentionally **not backward compatible**.

Do not spend effort on shims, legacy adapters, compatibility wrappers, or preserving old per-repo callback patterns. Downstream repos will be migrated to the new contract after `cli-core-yo` lands.

## 1. Why this exists

The current state already has real drift across repos:

- root option behavior differs by repo
- JSON behavior differs by repo
- runtime / conda guard behavior is duplicated repo-locally
- `EnvSpec` is used inconsistently
- some repos still bypass framework parsing with manual root callbacks or argv surgery
- some repos still bridge large legacy Typer apps instead of registering policy-aware commands

v2 exists to make those differences explicit and enforceable at the framework layer.

## 2. Hard design choices

These are decisions, not open questions.

### 2.1 JSON model

Adopt **framework-owned root-global JSON mode**.

- `--json` is a reserved root option.
- Downstream repos do **not** define per-command `--json` flags.
- A command either declares that it supports JSON or the framework rejects JSON mode for that command before execution.
- All JSON output must be valid UTF-8 JSON with:
  - `indent=2`
  - `sort_keys=True`
  - trailing newline
  - no ANSI

### 2.2 Dry-run model

Adopt one dry-run meaning:

- `--dry-run` means **no persistent mutation and no external side effects**.
- Commands may still:
  - parse inputs
  - resolve config
  - inspect local state
  - build and emit a plan
- Commands may **not**:
  - write files unless explicitly designated ephemeral report output and documented as such
  - mutate databases
  - call external APIs that change state
  - trigger deploys / launches / deletes / writes / side-effecting jobs

### 2.3 Runtime / environment model

Split runtime concerns into two separate concepts:

- `RuntimeSpec`: what execution backends and prerequisite checks are required to run commands
- `EnvSpec`: user-facing activation / status / reset guidance only

`EnvSpec` is not the enforcement model.

### 2.4 Root callback ownership

The framework owns root parsing.

Downstream repos may not define custom root callbacks that parse or reserve root flags.

Repo-specific root selectors must be declared in a structured spec and installed by the framework.

### 2.5 Deployment scope

Do **not** turn `cli-core-yo` into a deploy engine in v2.

Bounded deployment support is allowed only at the metadata / rendering / dry-run-plan layer, and only after the output + runtime contracts are stable.

### 2.6 Legacy Typer bridges

`add_typer_app()` style registration is out of contract for v2-compliant CLIs.

The v2 registry must register commands and groups with policy metadata. Giant opaque Typer subtrees are not acceptable for compliant mode because the framework cannot enforce JSON / dry-run / runtime policy through them.

## 3. Non-goals

v2 must not:

- own repo domain logic
- own app-specific config schemas
- synthesize activation scripts
- silently modify the caller shell
- become a cloud control plane
- preserve legacy repo-local root callbacks
- preserve legacy per-command JSON semantics
- preserve backward compatibility with v1 API shapes where that blocks a clean contract

## 4. New v2 public model

## 4.1 `CliSpec`

Replace the current minimal `CliSpec` with a richer top-level declaration.

Required fields:

- `prog_name: str`
- `app_display_name: str`
- `dist_name: str`
- `root_help: str`
- `xdg: XdgSpec`
- `policy: PolicySpec`

Optional fields:

- `config: ConfigSpec | None = None`
- `env: EnvSpec | None = None`
- `runtime: RuntimeSpec | None = None`
- `context: InvocationContextSpec | None = None`
- `output: OutputSpec | None = None`
- `plugins: PluginSpec = PluginSpec()`
- `info_hooks: list[Callable[[], list[tuple[str, str]]]] = []`
- `deploy: DeploySpec | None = None`

### 4.2 `PolicySpec`

```python
@dataclass(frozen=True)
class PolicySpec:
    profile: Literal["platform-v2"] = "platform-v2"
```

Notes:
- No legacy profile in v2.
- No migration / compatibility profile in this implementation.
- v2 code should assume the new contract everywhere.

### 4.3 `OutputSpec`

```python
@dataclass(frozen=True)
class OutputSpec:
    support_json: bool = True
    support_no_color_flag: bool = True
    log_stream: Literal["stderr"] = "stderr"
    human_stream: Literal["stdout"] = "stdout"
```

Notes:
- `--json` is root-global only.
- `--output json` is not added in v2.
- `--no-color` is a reserved root option.
- `NO_COLOR` must still be honored.

### 4.4 `RuntimeSpec`

```python
@dataclass(frozen=True)
class RuntimeSpec:
    supported_backends: list[ExecutionBackendSpec]
    default_backend: str | None = None
    guard_mode: Literal["off", "advisory", "enforced"] = "enforced"
    allow_skip_check: bool = False
    prereqs: list[PrereqSpec] = field(default_factory=list)
```

Notes:
- `guard_mode` governs backend + prereq enforcement.
- If `allow_skip_check=False`, reserved root option `--skip-runtime-check` must not appear in help or parse.

### 4.5 `ExecutionBackendSpec`

```python
@dataclass(frozen=True)
class ExecutionBackendSpec:
    name: str
    kind: Literal["system", "venv", "conda", "docker", "podman", "apptainer"]
    entry_guidance: str
    detect: BackendDetectSpec
    validation: BackendValidationSpec
```

Required v2 implementation scope:

- fully support `conda`
- support basic `venv`
- support basic `system`
- keep container support minimal but structurally ready
- do not implement remote / SSH / cluster backends in v2

### 4.6 `EnvSpec`

```python
@dataclass(frozen=True)
class EnvSpec:
    active_env_var: str
    project_root_env_var: str
    activate_script_name: str
    deactivate_script_name: str
    status_fields: list[str] = field(default_factory=list)
    allow_reset: bool = True
    preferred_backend: str | None = None
```

Notes:
- This is for human-facing commands like env status / activate guidance / deactivate guidance.
- This does not define runtime enforcement.

### 4.7 `InvocationContextSpec`

This replaces repo-local custom root callbacks.

```python
@dataclass(frozen=True)
class InvocationContextSpec:
    options: list[ContextOptionSpec] = field(default_factory=list)
```

```python
@dataclass(frozen=True)
class ContextOptionSpec:
    name: str
    option_flags: tuple[str, ...]
    value_type: Literal["str", "int", "bool", "choice"]
    default: Any = None
    help: str = ""
    choices: tuple[str, ...] = ()
    include_in_runtime_context: bool = True
```

Notes:
- Typical examples: deploy name, target env, AWS profile, auth-disable toggle.
- These are parsed by the framework and surfaced in `RuntimeContext.invocation`.

### 4.8 `DeploySpec`

Keep this minimal and optional.

```python
@dataclass(frozen=True)
class DeploySpec:
    capabilities: set[Literal["plan", "apply", "status", "resume", "logs"]]
    require_confirmation_for_apply: bool = True
    emit_plan_json: bool = True
```

Notes:
- v2 should define this spec and basic rendering helpers only.
- v2 should not ship a framework-owned built-in `deploy` group.

### 4.9 `CommandPolicy`

This is mandatory for every registered command.

```python
@dataclass(frozen=True)
class CommandPolicy:
    mutates_state: bool = False
    supports_json: bool = False
    supports_dry_run: bool = False
    runtime_guard: Literal["required", "exempt", "advisory"] = "required"
    interactive: bool = False
    long_running: bool = False
    prereq_tags: set[str] = field(default_factory=set)
```

Interpretation:

- `supports_json=False` + root `--json` on that command => fail before execution with exit code `2`
- `supports_dry_run=True` is only valid when the command meaningfully mutates or would mutate state
- `runtime_guard="required"` => backend / prereqs enforced according to `RuntimeSpec.guard_mode`
- `runtime_guard="exempt"` => command may run without backend / prereq enforcement
- `prereq_tags` let commands opt into only the relevant subset of declared prereqs

## 5. New v2 prerequisite validator

Yes, add this. It is a good feature if kept bounded.

It belongs in v2 because it is the same class of problem as runtime guard drift: repos currently hand-roll environment assumptions. Those assumptions should be declarative, testable, and reusable.

### 5.1 Purpose

Allow downstream repos to declare system prerequisites once and use them in two places:

1. human-facing inspection commands
2. pre-execution runtime validation

### 5.2 Scope boundaries

The prerequisite validator must stay **local and deterministic** by default.

Allowed first-wave checks:

- executable exists on `PATH`
- file exists
- directory exists
- environment variable present
- Python import succeeds
- command probe succeeds locally
- optional version probe with local parsing

Not allowed in v2 first wave:

- network reachability probes by default
- cloud account / auth checks as generic framework behavior
- service-specific external health checks in the core library
- mutating checks

Repos may still add domain-specific commands for those checks.

### 5.3 `PrereqSpec`

```python
@dataclass(frozen=True)
class PrereqSpec:
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
```

### 5.4 Result model

```python
@dataclass(frozen=True)
class PrereqResult:
    key: str
    status: Literal["pass", "warn", "fail", "skip"]
    severity: Literal["error", "warn", "info"]
    summary: str
    detail: str | None = None
```

### 5.5 Enforcement rules

- prereqs are filtered by active backend and command `prereq_tags`
- `severity="error"` contributes to hard failure when runtime guard is enforced
- `severity="warn"` never hard-fails by itself
- `severity="info"` is reporting only
- when `guard_mode="advisory"`, all prereq failures are logged / emitted but do not block execution
- when `guard_mode="off"`, prereq checks run only through explicit inspection commands

### 5.6 Built-in command surface

If `RuntimeSpec` is enabled, add a built-in `runtime` group with:

- `runtime status`
- `runtime check`
- `runtime explain`

Behavior:

- `runtime status` shows detected backend, effective config path, runtime guard mode, skip-check state, and prereq summary
- `runtime check` runs all applicable backend + prerequisite checks
- `runtime explain` prints human guidance for how to enter a valid backend or satisfy failed prereqs

`runtime check` must support root-global `--json`.

### 5.7 Runtime context integration

`RuntimeContext` must include:

```python
@dataclass(frozen=True)
class RuntimeContext:
    spec: CliSpec
    xdg_paths: XdgPaths
    config_path: Path | None
    json_mode: bool
    debug: bool
    no_color: bool
    invocation: Mapping[str, Any]
    backend_name: str | None
    backend_kind: str | None
    runtime_guard_mode: Literal["off", "advisory", "enforced"]
    runtime_check_skipped: bool
    dry_run: bool
```

Notes:
- `dry_run` should be derived from framework parsing, not from repo-local flag logic.
- `invocation` holds values from `InvocationContextSpec`.

## 6. Registry redesign

The registry must become policy-aware.

### 6.1 Keep

Keep the idea of deterministic command registration and freeze semantics.

### 6.2 Change

Every registered command must include a `CommandPolicy`.

New API:

```python
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
    ...
```

### 6.3 Remove

Remove `add_typer_app()` from the supported v2 public API.

If existing internal code still references it during development, delete those callsites in downstream repos rather than preserving the API.

### 6.4 Group metadata

Groups do not need full command policy but should be able to declare optional metadata for help ordering / category labeling later. Do not overbuild this now.

## 7. App factory redesign

## 7.1 Root reserved options

The framework must own these root options:

- `--help`
- `--json`
- `--no-color`
- `--debug`
- `--config PATH` when config is enabled
- `--runtime-backend BACKEND` when multiple backends are supported
- `--skip-runtime-check` only when runtime spec allows it
- repo-declared `InvocationContextSpec` options

### 7.2 Root bootstrap order

For every invocation:

1. parse reserved root options
2. parse repo-declared invocation selectors
3. resolve target command
4. resolve effective config path
5. detect backend
6. determine active command policy
7. determine JSON mode and dry-run mode
8. run runtime / prereq validation if applicable
9. initialize `RuntimeContext`
10. invoke command

### 7.3 Important behavioral changes

- JSON mode is determined by root parsing only, not by scanning raw argv for `--json` anywhere
- dry-run mode is determined by framework parsing only
- no repo-local argv surgery
- no repo-local root callback parsing

## 8. Output layer redesign

The output module must separate user output from diagnostics cleanly.

### 8.1 Streams

- human-friendly CLI output: `stdout`
- machine-readable JSON output: `stdout`
- diagnostics, debug, prereq failures, tracebacks: `stderr`

### 8.2 JSON mode behavior

When JSON mode is active:

- human output helpers must emit nothing to `stdout`
- diagnostics may still go to `stderr`
- framework-level contract failures must be rendered as structured JSON to `stdout` when appropriate, while full debug details may go to `stderr`

### 8.3 New helper requirements

Add helpers for:

- `emit_json(data)`
- `emit_error_json(code, message, details=None)`
- `emit_prereq_report(results)`
- `debug(msg)` to `stderr`

## 9. Built-in commands in v2

## 9.1 Keep built-ins

Keep built-ins:

- `version`
- `info`
- optional `config`
- optional `env`
- optional `runtime`

## 9.2 Built-in command contract

Built-ins must be registered through the same registry and have explicit `CommandPolicy`.

Examples:

- `version`: `supports_json=True`, `runtime_guard="exempt"`
- `info`: `supports_json=True`, `runtime_guard="exempt"`
- `config path`: likely `supports_json=True`, `runtime_guard="exempt"`
- `runtime check`: `supports_json=True`, `runtime_guard="exempt"`

## 10. Validation / enforcement behavior

## 10.1 Exit codes

Use these exit codes consistently:

- `0`: success
- `1`: command/domain failure
- `2`: usage error or contract violation before command execution
- `3`: runtime/backend/prereq validation failure
- `130`: interrupted by user

## 10.2 Construction-time enforcement

App construction must fail if:

- a command is registered without `CommandPolicy`
- reserved root options are redeclared downstream
- `RuntimeSpec.default_backend` is not in `supported_backends`
- duplicate prereq keys exist
- invalid context option declarations exist

## 10.3 Invocation-time enforcement

Before command execution, the framework must:

- reject JSON mode for commands with `supports_json=False`
- reject dry-run for commands with `supports_dry_run=False`
- reject unsupported backend selection
- enforce runtime/backend/prereq checks for `runtime_guard="required"`
- skip enforcement for `runtime_guard="exempt"`
- emit deterministic error structure in JSON mode

## 11. v2 file-level implementation plan inside `cli-core-yo`

This section is intentionally concrete.

### 11.1 `cli_core_yo/spec.py`

Rewrite to define:

- `XdgSpec`
- `ConfigSpec`
- `EnvSpec`
- `PolicySpec`
- `OutputSpec`
- `RuntimeSpec`
- `ExecutionBackendSpec`
- `BackendDetectSpec`
- `BackendValidationSpec`
- `InvocationContextSpec`
- `ContextOptionSpec`
- `DeploySpec`
- `PrereqSpec`
- `CommandPolicy`
- `CliSpec`

Keep the dataclasses frozen.

### 11.2 `cli_core_yo/runtime.py`

Rewrite `RuntimeContext` and initialization logic to support:

- root-global JSON mode
- framework-owned dry-run state
- resolved backend metadata
- invocation selector values
- runtime guard status

### 11.3 `cli_core_yo/registry.py`

Rewrite registry APIs to require command policy metadata.

Remove supported use of `add_typer_app()`.

### 11.4 `cli_core_yo/app.py`

Rewrite app construction and invocation flow around the v2 root contract.

Must include:

- reserved root option parsing
- invocation selector parsing
- backend detection
- prereq execution
- command policy enforcement
- initialization of runtime context before command invocation

### 11.5 `cli_core_yo/output.py`

Rewrite output helpers to separate `stdout` and `stderr` cleanly and add structured error JSON support.

### 11.6 New module: `cli_core_yo/runtime_checks.py`

Create runtime checking helpers for:

- backend detection
- backend validation
- prereq execution
- result summarization

### 11.7 New module: `cli_core_yo/conformance.py`

Create pytest-friendly conformance helpers for downstream repos.

Must include helpers to test:

- root `--help`
- root `--json`
- JSON rejection for unsupported commands
- dry-run rejection for unsupported commands
- runtime guard exemption behavior
- runtime failure behavior
- built-in command contracts

### 11.8 README and examples

Rewrite README to describe v2 only.

Do not document or preserve v1 behavior.

## 12. Tests required in `cli-core-yo`

Add or rewrite tests to cover at least:

### 12.1 Root contract

- root `--json` is accepted and sets global JSON mode
- per-command `--json` is not part of framework examples or built-ins
- root `--no-color` disables color
- root `--debug` enables debug diagnostics
- root invocation selectors populate runtime context

### 12.2 Output contract

- JSON output is deterministic
- no ANSI in JSON mode
- human output suppressed in JSON mode
- diagnostics go to `stderr`

### 12.3 Runtime contract

- backend detection for `system`, `venv`, `conda`
- backend selection override behavior
- enforced vs advisory vs off modes
- skip-runtime-check behavior when enabled

### 12.4 Prereq validator

- pass / warn / fail / skip states
- tag filtering by command
- backend filtering by prereq
- JSON report output
- enforced error prereqs cause exit code `3`
- advisory mode does not block

### 12.5 Command policy

- missing policy fails at construction time
- unsupported JSON rejected with exit code `2`
- unsupported dry-run rejected with exit code `2`
- exempt commands bypass runtime guard

## 13. Acceptance criteria for v2.0.0

`cli-core-yo` v2.0.0 is done when all of the following are true:

1. The public API and README describe only the v2 contract.
2. JSON mode is root-global and framework-owned.
3. Runtime/backend checks are framework-owned.
4. System prerequisite validation exists and is reusable by both runtime preflight and human-facing commands.
5. Every command registration requires policy metadata.
6. Built-ins use the same enforcement machinery as downstream commands.
7. There is no supported `add_typer_app()` escape hatch in the public contract.
8. The conformance test helpers exist for downstream repos.
9. The package version is bumped to `2.0.0`.

## 14. Follow-on downstream repo order

After `cli-core-yo` lands, normalize repos in this order:

1. `lsmc-atlas`
2. `dewey`
3. `zebra_day`
4. `daylily-ursa`
5. `lsmc/kahlo`
6. `daylily-cognito`
7. `daylily-tapdb`

Rationale:

- Atlas and Dewey are the cleanest reference shapes
- Zebra forces the root-global JSON decision through a real outlier
- Ursa tests env/runtime overlap
- Kahlo is a secondary operator-oriented shape
- Daycog is a thinner library/CLI hybrid
- TapDB is the highest-blast-radius partial migration and should come last

## 15. Explicit instructions to Codex IDE

Implement this in `cli-core-yo` only first.

Do not edit downstream repos in the same change.

Do not preserve backward compatibility.

Do not add legacy fallback paths.

Do not leave old APIs in place “just in case.”

Favor deletion over shims.

Prefer a smaller, harder contract over a more flexible but fuzzy one.

When an existing implementation detail conflicts with this spec, change the implementation to match the spec.
