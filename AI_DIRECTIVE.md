# AI Directive: cli-core-yo

## Operational Policy
Use this repository as the shared CLI framework layer.
When a downstream CLI uses `cli-core-yo`, implement behavior through `CliSpec`, `CommandRegistry`, and plugins.
Do not bypass framework contracts with ad-hoc command trees or direct one-off CLI wiring when this library is the designated path.

This repository is a Python library, not an operational service CLI by itself.

## Environment Bootstrap
From repo root, use:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Required Integration Pattern (Downstream Repos)
Define exactly one immutable `CliSpec` and use `cli_core_yo.app.run(spec, argv=None)` as the execution path.

```python
from cli_core_yo.app import run
from cli_core_yo.spec import CliSpec, XdgSpec

SPEC = CliSpec(
    prog_name="my-tool",
    app_display_name="My Tool",
    dist_name="my-tool",
    root_help="My CLI.",
    xdg=XdgSpec(app_dir_name="my-tool"),
)

raise SystemExit(run(SPEC))
```

If optional built-ins are needed:
- `ConfigSpec`: provide exactly one of `xdg_relative_path` or `absolute_path`, and exactly one of `template_bytes` or `template_resource`.
- `EnvSpec`: provide `active_env_var`, `project_root_env_var`, `activate_script_name`, `deactivate_script_name`.

When `ConfigSpec` is enabled, the root CLI also supports `--config PATH` as a one-invocation override.
That override must appear before the subcommand.
Relative override paths resolve from the current working directory.

## Plugin and Registry Rules
Register downstream commands via plugins with signature:
`(registry: CommandRegistry, spec: CliSpec) -> None`

Supported loading order:
1. `spec.plugins.explicit` (in list order)
2. `spec.plugins.entry_points` (in list order, group `cli_core_yo.plugins`)

Root reserved names:
- `version`
- `info`
- `config` (when enabled)
- `env` (when enabled)

Command/group names must match:
`^[a-z][a-z0-9-]*$`

## Built-in Commands Provided by This Library
Always present:
- `version`
- `info`

Optional groups (only when configured):
- `config`: `path`, `init`, `show`, `validate`, `edit`, `reset`
- `env`: `status`, `activate`, `deactivate`, `reset`

## Output and JSON Contract
For user-facing output, prefer `cli_core_yo.output` primitives:
- `heading`, `success`, `warning`, `error`, `action`, `detail`, `bullet`, `print_text`
- `emit_json` for machine output

Behavior guarantees:
- `--json` / `-j` mode suppresses human primitives automatically
- `emit_json` is deterministic (`indent=2`, sorted keys, trailing newline)
- `NO_COLOR` disables ANSI styling

## Runtime and Error Handling
Use `cli_core_yo.runtime.get_context()` inside commands/plugins for invocation state, including the effective `config_path` after any root `--config PATH` override when config is enabled.
Do not manually initialize runtime outside framework startup.

`run()` returns exit codes and does not call `sys.exit()`.
Framework errors map to non-zero exits; usage errors come from Typer/Click.

## Guardrails for Agents
- Prefer framework extension points over direct Typer mutation.
- Do not register reserved names or duplicate command paths.
- Do not mutate frozen spec dataclasses.
- Keep plugin imports deterministic and explicit.
- Avoid ad-hoc ANSI/styled output outside `cli_core_yo.output`.
- For changes in this repo, keep behavior aligned with tests and `SPEC.md`.

## Verification Commands (This Repo)
```sh
python -m pytest tests/ -v --cov=cli_core_yo
ruff check cli_core_yo tests
ruff format --check cli_core_yo tests
mypy cli_core_yo --ignore-missing-imports
python -m build
twine check dist/*
```
