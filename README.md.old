# cli-core-yo

[![GitHub Release](https://img.shields.io/github/v/release/Daylily-Informatics/cli-core-yo?style=flat-square&label=release)](https://github.com/Daylily-Informatics/cli-core-yo/releases/latest)
[![GitHub Tag](https://img.shields.io/github/v/tag/Daylily-Informatics/cli-core-yo?style=flat-square&label=tag)](https://github.com/Daylily-Informatics/cli-core-yo/tags)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

Reusable CLI kernel for building unified command-line interfaces with consistent behavior, output style, help, and extension semantics. Built on [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/).

## What It Does

`cli-core-yo` provides the shared foundation that downstream CLI tools build on:

- **Root app factory** — `create_app()` builds a fully configured Typer app from a declarative spec
- **Built-in commands** — `version`, `info`, and optional `config`/`env` groups
- **Plugin system** — explicit callables + `cli_core_yo.plugins` entry-point discovery
- **XDG paths** — platform-aware config/data/state/cache directory resolution (macOS + Linux)
- **Output primitives** — `heading`, `success`, `warning`, `error`, `action`, `detail`, `bullet`, `emit_json`
- **Runtime context** — immutable singleton accessible to all commands during invocation
- **JSON mode** — `--json`/`-j` flag with deterministic output (indent=2, sorted keys, no ANSI)
- **NO_COLOR** — respects the [NO_COLOR](https://no-color.org/) convention
- **Debug mode** — `CLI_CORE_YO_DEBUG=1` prints tracebacks to STDERR

## Prerequisites

- Python 3.10+
- pip

## Installation

```bash
pip install cli-core-yo
```

For development:

```bash
git clone https://github.com/Daylily-Informatics/cli-core-yo.git
cd cli-core-yo
pip install -e ".[dev]"
```

## Quick Start

```python
from cli_core_yo.spec import CliSpec, XdgSpec
from cli_core_yo.app import run

spec = CliSpec(
    prog_name="my-tool",
    app_display_name="My Tool",
    dist_name="my-tool",
    root_help="A CLI built with cli-core-yo.",
    xdg=XdgSpec(vendor="my-tool"),
)

exit_code = run(spec)
```

This gives you `my-tool version`, `my-tool info`, `my-tool --help`, `--json` support, and all the standard behaviors out of the box.

## Adding Commands via Plugin

```python
# my_tool/plugin.py
def register(registry, spec):
    registry.add_command(None, "greet", greet_cmd, help_text="Say hello.")

def greet_cmd():
    from cli_core_yo import output
    output.success("Hello, world!")
```

Register it in your spec:

```python
from cli_core_yo.spec import PluginSpec

spec = CliSpec(
    ...,
    plugins=PluginSpec(explicit=["my_tool.plugin.register"]),
)
```

Or via entry points in `pyproject.toml`:

```toml
[project.entry-points."cli_core_yo.plugins"]
my-tool = "my_tool.plugin:register"
```

## Config & Env Groups

Enable optional built-in command groups by providing specs:

```python
from cli_core_yo.spec import ConfigSpec, EnvSpec

spec = CliSpec(
    ...,
    config=ConfigSpec(
        primary_filename="config.json",
        template_bytes=b'{"key": "value"}\n',
    ),
    env=EnvSpec(
        env_dir_name=".venv",
        activate_script_rel="bin/activate",
    ),
)
```

This adds `config path|init|show|validate|edit|reset` and `env status|activate|deactivate|reset`.

## Public API

| Symbol | Module | Description |
|--------|--------|-------------|
| `create_app(spec)` | `cli_core_yo.app` | Build a Typer app from a CliSpec |
| `run(spec, argv)` | `cli_core_yo.app` | Execute CLI, return exit code (never calls `sys.exit()`) |
| `CommandRegistry` | `cli_core_yo.registry` | Register commands/groups with ordering and conflict detection |
| `get_context()` | `cli_core_yo.runtime` | Access the current invocation's RuntimeContext |
| `CliSpec`, `ConfigSpec`, `EnvSpec`, `PluginSpec`, `XdgSpec` | `cli_core_yo.spec` | Frozen dataclass specs |
| `output.*` | `cli_core_yo.output` | UX primitives + `emit_json()` |

## HTTPS Certificate Resolution

`cli_core_yo.certs` now supports a shared HTTPS resolution contract for downstream
services. The `resolve_https_certs()` helper applies this precedence order:

1. explicit CLI-provided cert and key paths
2. generic `SSL_CERT_FILE` / `SSL_KEY_FILE`
3. service-specific legacy env vars supplied by the caller
4. an existing shared certificate directory
5. an existing repo-local fallback certificate directory
6. optional `mkcert` generation, preferring the shared directory

For Dayhoff-managed local deployments, `shared_dayhoff_certs_dir(deploy_name)`
resolves the canonical shared directory under XDG state:

```text
~/.local/state/dayhoff/<deploy-name>/certs/
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Domain/runtime failure |
| 2 | Usage error (bad args, unknown command) |
| 130 | SIGINT |

## Build / Test / Lint

```bash
# Run tests
python -m pytest tests/ -v --cov=cli_core_yo

# Lint + format check
ruff check cli_core_yo tests
ruff format --check cli_core_yo tests

# Type check
mypy cli_core_yo --ignore-missing-imports

# Build distribution
python -m build
twine check dist/*
```

## License

MIT — see [LICENSE](LICENSE).
