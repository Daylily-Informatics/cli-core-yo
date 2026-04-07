# AI Directive: cli-core-yo

## Operational Policy
`cli-core-yo` v2 is a strict CLI framework layer.
Downstream repos must implement behavior through `CliSpec`, `CommandRegistry`, plugins, and the framework output/runtime helpers.
Do not bypass framework contracts with ad-hoc command trees, manual root parsing, or direct Typer mutation.

This repository is a Python library, not an operational service CLI by itself.

## Environment Bootstrap
From repo root, use:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Required Downstream Pattern
Define exactly one immutable `CliSpec` and execute through `cli_core_yo.app.run(spec, argv=None)`.

```python
from cli_core_yo.app import run
from cli_core_yo.spec import CliSpec, PolicySpec, XdgSpec

SPEC = CliSpec(
    prog_name="my-tool",
    app_display_name="My Tool",
    dist_name="my-tool",
    root_help="My CLI.",
    xdg=XdgSpec(app_dir_name="my-tool"),
    policy=PolicySpec(),
)

raise SystemExit(run(SPEC))
```

If optional sections are needed:
- `ConfigSpec`: provide exactly one location source and exactly one template source.
- `EnvSpec`: provide `active_env_var`, `project_root_env_var`, `activate_script_name`, `deactivate_script_name`.
- `RuntimeSpec`: declare backend and prereq policy; the framework owns runtime enforcement.
- `InvocationContextSpec`: declare root selectors through structured option metadata.

## Plugin And Registry Rules
Register downstream commands via plugins with signature:
`(registry: CommandRegistry, spec: CliSpec) -> None`

Loading order:
1. `spec.plugins.explicit`
2. `spec.plugins.entry_points` in group `cli_core_yo.plugins`

Root reserved names and root-owned behavior:
- `version`
- `info`
- optional `config`
- optional `env`
- optional `runtime`
- root-global `--json`, `--dry-run`, `--no-color`, `--debug`, `--config`, `--runtime-backend`, and `--skip-runtime-check`

Command and group names must match `^[a-z][a-z0-9-]*$`.
Every command registration must include `CommandPolicy`.
`add_typer_app()` is out of contract.

## Output And Runtime Contract
Use `cli_core_yo.output` for user-facing output:
- `heading`, `success`, `warning`, `error`, `action`, `detail`, `bullet`, `print_text`
- `emit_json`, `emit_error_json`, `emit_prereq_report`

Behavior guarantees:
- JSON mode is root-global and framework-owned.
- Dry-run mode is root-global and framework-owned.
- Human output is suppressed automatically in JSON mode.
- Diagnostics, debug output, and tracebacks go to stderr.
- `NO_COLOR` disables ANSI styling.

Use `cli_core_yo.runtime.get_context()` inside commands and plugins for invocation state.
Do not manually initialize runtime outside framework startup.

## Guardrails For Agents
- Prefer framework extension points over direct Typer mutation.
- Do not register reserved names or duplicate command paths.
- Do not mutate frozen spec dataclasses.
- Keep plugin imports deterministic and explicit.
- Avoid ad-hoc ANSI/styled output outside `cli_core_yo.output`.
- Use `cli_core_yo.conformance` for downstream pytest contract checks.
- Do not preserve legacy JSON flags, `add_typer_app()`, or compatibility shims.

## Verification Commands
```sh
python -m pytest tests/ -v --cov=cli_core_yo
ruff check cli_core_yo tests
ruff format --check cli_core_yo tests
mypy cli_core_yo --ignore-missing-imports
python -m build
twine check dist/*
```
