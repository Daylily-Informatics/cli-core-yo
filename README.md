# cli-core-yo

[![GitHub Release](https://img.shields.io/github/v/release/Daylily-Informatics/cli-core-yo?style=flat-square&label=release)](https://github.com/Daylily-Informatics/cli-core-yo/releases/latest)
[![GitHub Tag](https://img.shields.io/github/v/tag/Daylily-Informatics/cli-core-yo?style=flat-square&label=tag)](https://github.com/Daylily-Informatics/cli-core-yo/tags)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

`cli-core-yo` v2.0.0 is an opinionated enforcement layer for downstream Python CLIs. It keeps Typer, Click, and Rich as the implementation substrate, but the framework owns root parsing, output mode, dry-run mode, runtime validation, and command policy enforcement.

It is not a standalone service CLI. It is the shared kernel downstream repos embed into their own entrypoints.

Use `create_app(spec)` when you need the configured CLI object directly, or `run(spec, argv=None)` when you want process-style execution with an exit code.

## v2 Contract

The top-level configuration is an immutable `CliSpec`.

```python
from cli_core_yo.app import run
from cli_core_yo.spec import CliSpec, PolicySpec, XdgSpec

SPEC = CliSpec(
    prog_name="my-tool",
    app_display_name="My Tool",
    dist_name="my-tool",
    root_help="Unified CLI for My Tool.",
    xdg=XdgSpec(app_dir_name="my-tool"),
    policy=PolicySpec(),
)

raise SystemExit(run(SPEC))
```

`CliSpec` in v2 requires:

| Field | Purpose |
| --- | --- |
| `prog_name` | CLI program name |
| `app_display_name` | Human-facing app name |
| `dist_name` | Installed distribution name |
| `root_help` | Root help text |
| `xdg` | App-scoped XDG directory policy |
| `policy` | Framework policy profile |

Optional sections include `config`, `env`, `runtime`, `context`, `output`, `plugins`, `info_hooks`, and `deploy`.

## Root Behavior

The framework owns these root options:

- `--json`
- `--dry-run`
- `--no-color`
- `--debug`
- `--config PATH`
- `--runtime-backend BACKEND`
- `--skip-runtime-check`
- any `InvocationContextSpec` selectors

JSON is root-global. Downstream commands do not define their own `--json` flags. `--dry-run` is root-global too, and commands that do not support it fail before execution.

## Command Registration

Register downstream behavior through the policy-aware registry.

```python
from cli_core_yo import output
from cli_core_yo.registry import CommandRegistry
from cli_core_yo.spec import CliSpec, CommandPolicy


def greet() -> None:
    output.success("hello")


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    registry.add_command(
        None,
        "greet",
        greet,
        help_text="Say hello.",
        policy=CommandPolicy(),
    )
```

The supported registry surface is:

- `add_group(name, help_text="", order=None)`
- `add_command(group_path, name, callback, *, help_text="", policy, order=None)`

`add_typer_app()` is not part of the v2 contract.

## Built-Ins

The framework provides built-ins through the same registry and policy machinery:

- `version`
- `info`
- optional `config`
- optional `env`
- optional `runtime`

`runtime` is enabled only when `RuntimeSpec` is configured. When present, it includes `runtime status`, `runtime check`, and `runtime explain`.

## Runtime And Output

Use `get_context()` inside commands when you need invocation-scoped state.

```python
from cli_core_yo.runtime import get_context


def show_runtime() -> None:
    ctx = get_context()
    print(ctx.spec.prog_name)
    print(ctx.json_mode)
    print(ctx.dry_run)
    print(ctx.backend_name)
```

Output helpers live in `cli_core_yo.output`. Human output goes to stdout, diagnostics go to stderr, and JSON output is deterministic UTF-8 with sorted keys, `indent=2`, and a trailing newline.

Environment hooks that matter at the framework level:

- `NO_COLOR` disables ANSI styling
- `CLI_CORE_YO_DEBUG=1` enables traceback diagnostics
- `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME`, and `XDG_CACHE_HOME` override XDG resolution

## Conformance Helpers

Downstream repos can reuse `cli_core_yo.conformance` in pytest suites.

```python
from cli_core_yo.app import create_app
from cli_core_yo.conformance import assert_exit_code, assert_json_output, invoke
from cli_core_yo.spec import CliSpec, PolicySpec, XdgSpec

SPEC = CliSpec(
    prog_name="my-tool",
    app_display_name="My Tool",
    dist_name="my-tool",
    root_help="Unified CLI for My Tool.",
    xdg=XdgSpec(app_dir_name="my-tool"),
    policy=PolicySpec(),
)

app = create_app(SPEC)
result = invoke(app, ["--json", "version"])
assert_exit_code(result, 0)
data = assert_json_output(result)
assert "version" in data
```

The helper module is intentionally small and generic:

- `invoke(app, argv, ...)`
- `stdout_text(result)`
- `stderr_text(result)`
- `json_output(result)`
- `assert_exit_code(result, expected)`
- `assert_json_output(result, expected=None)`
- `assert_no_ansi(text)`
- `assert_stdout_only(result)`

## Development

Bootstrap a local environment from the repo root:

```console
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Validation commands used by this repo:

```console
python -m pytest tests/ -v --cov=cli_core_yo
ruff check cli_core_yo tests
ruff format --check cli_core_yo tests
mypy cli_core_yo --ignore-missing-imports
python -m build
twine check dist/*
```

## Guidance For AI Agents

- Treat this repository as the shared CLI framework layer, not as a downstream app.
- Define exactly one immutable `CliSpec` in downstream CLIs.
- Register commands through `CommandRegistry` with explicit `CommandPolicy` metadata.
- Keep JSON and dry-run ownership in the framework, not in downstream callbacks.
- Do not rely on `add_typer_app()` or legacy JSON flag behavior.
- Use `cli_core_yo.output` for user-facing output and `cli_core_yo.conformance` for pytest contract checks.

For the repo-specific agent policy, see [`AI_DIRECTIVE.md`](AI_DIRECTIVE.md).

## License

MIT. See [`LICENSE`](LICENSE).
