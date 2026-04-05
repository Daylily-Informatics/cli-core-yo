# cli-core-yo

[![GitHub Release](https://img.shields.io/github/v/release/Daylily-Informatics/cli-core-yo?style=flat-square&label=release)](https://github.com/Daylily-Informatics/cli-core-yo/releases/latest)
[![GitHub Tag](https://img.shields.io/github/v/tag/Daylily-Informatics/cli-core-yo?style=flat-square&label=tag)](https://github.com/Daylily-Informatics/cli-core-yo/tags)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

Reusable CLI framework layer for downstream Python CLIs built on Typer and Rich.

## What This Library Is

`cli-core-yo` is the shared command-line kernel that downstream repositories embed into their own CLI entrypoints. It is responsible for consistent command-tree construction, built-in framework commands, output conventions, runtime context, plugin loading, and XDG path resolution.

It is not a standalone service CLI and it is not the place for downstream business logic. Downstream repos should define one immutable `CliSpec`, extend the command tree through the registry/plugin interfaces, and keep domain behavior outside this package.

## What You Get Out Of The Box

- A root app factory via `create_app(spec)` and an execution entrypoint via `run(spec, argv=None)`.
- Built-in root commands: `version` and `info`.
- Optional built-in groups: `config` and `env`.
- Deterministic plugin loading:
  explicit plugin callables first, entry-point plugins second.
- An immutable runtime context exposed through `get_context()`.
- Consistent human output primitives in `cli_core_yo.output`.
- Deterministic JSON emission for commands that explicitly expose `--json` / `-j`.
- XDG config/data/state/cache directory resolution with Linux and macOS defaults.
- `NO_COLOR` support for human output and `CLI_CORE_YO_DEBUG=1` traceback mode.
- Secondary helper modules for cert resolution, OAuth URI validation, server lifecycle helpers, and direct XDG path access.

## Quick Start

Install the package:

```console
pip install cli-core-yo
```

Define one `CliSpec` and route process exit through `run()`:

```python
from cli_core_yo.app import run
from cli_core_yo.spec import CliSpec, XdgSpec

SPEC = CliSpec(
    prog_name="my-tool",
    app_display_name="My Tool",
    dist_name="my-tool",
    root_help="Unified CLI for My Tool.",
    xdg=XdgSpec(app_dir_name="my-tool"),
)

raise SystemExit(run(SPEC))
```

That gives the downstream CLI a root Typer app with:

- `my-tool version`
- `my-tool info`
- Typer/Rich help output
- XDG path initialization
- runtime context initialization

If you need the Typer app object directly, use `create_app(spec)` instead of `run()`:

```python
from cli_core_yo.app import create_app

app = create_app(SPEC)
```

### Core API

| Symbol | Purpose |
| --- | --- |
| `create_app(spec)` | Build and return the configured Typer app. |
| `run(spec, argv=None)` | Execute the CLI and return an integer exit code without calling `sys.exit()`. |
| `CommandRegistry` | Register commands, groups, and Typer sub-apps in a deterministic tree. |
| `get_context()` | Access the current invocation's immutable runtime context. |
| `output.*` | Emit human output or deterministic JSON. |
| `resolve_paths()` / `XdgPaths` | Resolve app-scoped config/data/state/cache directories. |

### Spec Objects

`CliSpec` is the top-level immutable configuration passed into `create_app()` or `run()`.

| Dataclass | Current fields |
| --- | --- |
| `XdgSpec` | `app_dir_name` |
| `ConfigSpec` | `xdg_relative_path`, `absolute_path`, `template_bytes`, `template_resource`, `validator` |
| `EnvSpec` | `active_env_var`, `project_root_env_var`, `activate_script_name`, `deactivate_script_name` |
| `PluginSpec` | `explicit`, `entry_points` |
| `CliSpec` | `prog_name`, `app_display_name`, `dist_name`, `root_help`, `xdg`, `config`, `env`, `plugins`, `info_hooks` |

`ConfigSpec` requires exactly one location source:
`xdg_relative_path` or `absolute_path`.

`ConfigSpec` also requires exactly one template source:
`template_bytes` or `template_resource`.

## Extension Model

The supported extension path is:

1. define a `CliSpec`
2. register downstream commands through `CommandRegistry`
3. load that registration through explicit plugins or entry points

Do not mutate the root Typer app ad hoc in downstream repos when this library is the framework layer.

### Plugin Signature

Plugin callables must have this shape:

```python
from cli_core_yo.registry import CommandRegistry
from cli_core_yo.spec import CliSpec


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    ...
```

Example explicit plugin:

```python
from cli_core_yo import output
from cli_core_yo.registry import CommandRegistry
from cli_core_yo.spec import CliSpec


def greet() -> None:
    output.success("hello")


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    registry.add_command(None, "greet", greet, help_text="Say hello.")
```

Wire it into the spec:

```python
from cli_core_yo.spec import PluginSpec

SPEC = CliSpec(
    prog_name="my-tool",
    app_display_name="My Tool",
    dist_name="my-tool",
    root_help="Unified CLI for My Tool.",
    xdg=XdgSpec(app_dir_name="my-tool"),
    plugins=PluginSpec(explicit=["my_tool.plugin.register"]),
)
```

Or expose it as a package entry point:

```toml
[project.entry-points."cli_core_yo.plugins"]
my-tool = "my_tool.plugin:register"
```

### Load Order And Registry Rules

- `spec.plugins.explicit` loads first, in list order.
- `spec.plugins.entry_points` loads second, in list order.
- Entry-point group name is `cli_core_yo.plugins`.
- Root reserved names are `version` and `info`, plus `config` and `env` when those built-ins are enabled.
- Command and group names must match `^[a-z][a-z0-9-]*$`.
- `CommandRegistry` is frozen before application to the Typer tree; post-freeze mutation raises framework errors.

`CommandRegistry` supports:

- `add_group(name, help_text="", order=None)`
- `add_command(group_path, name, callback, help_text="", order=None)`
- `add_typer_app(group_path, typer_app, name, help_text="", order=None)`

Use `group_path=None` for root-level commands. Nested paths use slash-separated group paths such as `"admin/users"`.

## Optional Built-Ins

### `config`

Enable the config group by supplying a `ConfigSpec`:

```python
from cli_core_yo.spec import CliSpec, ConfigSpec, XdgSpec

SPEC = CliSpec(
    prog_name="my-tool",
    app_display_name="My Tool",
    dist_name="my-tool",
    root_help="Unified CLI for My Tool.",
    xdg=XdgSpec(app_dir_name="my-tool"),
    config=ConfigSpec(
        xdg_relative_path="config.json",
        template_bytes=b'{"env": "dev"}\n',
    ),
)
```

Built-in subcommands:

- `config path`
- `config init`
- `config show`
- `config validate`
- `config edit`
- `config reset`

Behavior notes:

- The config file path is resolved once per invocation from either `xdg_relative_path` or `absolute_path`.
- `config init` writes the configured template and supports `--force`.
- `config validate` calls `validator(content)` when provided; otherwise it accepts the config.
- `config edit` shells out to `VISUAL`, `EDITOR`, or `vi` and requires an interactive terminal.
- `config reset` backs up the current file to a UTC timestamped `.bak` before rewriting the template.
- Downstream commands and plugins can read the resolved file path from `get_context().config_path`.

### `env`

Enable the env group by supplying an `EnvSpec`:

```python
from cli_core_yo.spec import CliSpec, EnvSpec, XdgSpec

SPEC = CliSpec(
    prog_name="my-tool",
    app_display_name="My Tool",
    dist_name="my-tool",
    root_help="Unified CLI for My Tool.",
    xdg=XdgSpec(app_dir_name="my-tool"),
    env=EnvSpec(
        active_env_var="MY_TOOL_ACTIVE",
        project_root_env_var="MY_TOOL_ROOT",
        activate_script_name="activate.sh",
        deactivate_script_name="deactivate.sh",
    ),
)
```

Built-in subcommands:

- `env status`
- `env activate`
- `env deactivate`
- `env reset`

Behavior notes:

- `env status` reports environment status from the configured env vars.
- `env activate`, `env deactivate`, and `env reset` print shell commands; they do not mutate the caller's shell environment.

## Environment Variables

This library supports a small set of environment-variable hooks, but env vars are discouraged in most cases.
Treat them as escape hatches for process-scoped overrides, not the default configuration API between layers.

Prefer, in order:

1. explicit CLI arguments
2. `CliSpec` configuration in code
3. config files managed through the built-in `config` group
4. environment variables only for process-scoped overrides or integration boundaries

There is no generic env-to-`CliSpec` mapping layer in `cli-core-yo`.

Supported environment-variable behavior:

- `CLI_CORE_YO_DEBUG=1` enables traceback/debug mode in `run()`.
- `NO_COLOR=1` disables ANSI styling in human output.
- `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME`, `XDG_CACHE_HOME` override the resolved app directories.
- The built-in `env` group reads the downstream-defined names from `EnvSpec.active_env_var` and `EnvSpec.project_root_env_var`.
- `VISUAL` or `EDITOR` control the editor used by `config edit`, with `vi` as fallback.
- `resolve_https_certs()` supports `SSL_CERT_FILE` and `SSL_KEY_FILE`, plus caller-supplied legacy env-var names.
- `shared_dayhoff_certs_dir()` respects `XDG_STATE_HOME`.
- `source_env_file()` can load a simple `.env` file into `os.environ`, but only when downstream code calls it explicitly.

What this library does not do:

- it does not automatically populate `CliSpec` from env vars
- it does not automatically load `.env` files during startup
- it does not use env vars as the primary extension/configuration mechanism

## Runtime And Output Contract

Use `get_context()` inside commands and plugins when you need invocation-scoped state:

```python
from cli_core_yo.runtime import get_context


def show_runtime() -> None:
    ctx = get_context()
    print(ctx.spec.prog_name)
    print(ctx.config_path)
    print(ctx.xdg_paths.config)
    print(ctx.json_mode)
    print(ctx.debug)
```

`RuntimeContext` contains:

- `spec`
- `xdg_paths`
- `config_path`
- `json_mode`
- `debug`

For user-facing output, use `cli_core_yo.output` instead of raw ANSI formatting:

- `heading(title)`
- `success(msg)`
- `warning(msg)`
- `error(msg)`
- `action(msg)`
- `detail(msg)`
- `bullet(msg)`
- `print_text(msg)`
- `emit_json(data)`

Important behavior:

- Human primitives are automatically suppressed when runtime JSON mode is enabled.
- `emit_json()` writes deterministic JSON:
  sorted keys, `indent=2`, UTF-8 passthrough, trailing newline, and no ANSI.
- `NO_COLOR=1` disables ANSI styling in human output.
- `CLI_CORE_YO_DEBUG=1` enables traceback printing for framework exceptions.
- `run()` returns exit codes instead of raising `SystemExit` itself.

JSON support is command-specific, not universal. In the core library, `version` and `info` expose `--json` / `-j`. Commands that do not declare JSON flags will treat `--json` as a usage error.

Practical exit code expectations:

- `0` for success
- `1` for framework/domain failures
- `2` for Typer/Click usage errors such as unknown commands or invalid options

## Secondary Helper Modules

These modules are public and useful, but they are secondary to the CLI-kernel story.

### `cli_core_yo.xdg`

Use this when you need direct access to resolved app directories outside normal command execution.

- `resolve_paths(xdg_spec)` returns `XdgPaths(config, data, state, cache)`.
- Directories are created automatically.
- Linux defaults use `~/.config`, `~/.local/share`, `~/.local/state`, and `~/.cache`.
- macOS defaults use `~/.config`, `~/Library/Application Support`, `~/Library/Logs`, and `~/Library/Caches`.

### `cli_core_yo.certs`

Use this for local HTTPS cert management in downstream service CLIs.

- `ensure_certs(certs_dir)` ensures `cert.pem` and `key.pem`, generating them with `mkcert` when needed.
- `resolve_https_certs(...)` resolves cert/key paths by precedence:
  explicit paths, generic SSL env vars, caller-supplied legacy env vars, shared dir, fallback dir, then optional generation.
- `shared_dayhoff_certs_dir(deploy_name)` resolves the Dayhoff shared cert directory under XDG state.
- `cert_status(certs_dir)` reports readiness and mkcert/CA status.

### `cli_core_yo.oauth`

Use this for pure URI validation logic around local OAuth/Cognito flows.

- No I/O
- No AWS calls
- Port-alignment and expected-URL validation helpers for app-client configuration

### `cli_core_yo.server`

Use this for service-style CLIs that need small process-management helpers.

- PID file helpers
- timestamped log-file helpers
- process stop helpers
- `.env` sourcing
- user-facing host display normalization

## Development

Bootstrap a local development environment from the repo root:

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

The package requires Python 3.10+.

## Reference

Use [`SPEC.md`](SPEC.md) as the formal contract for framework behavior.

Use the tests in [`tests/`](tests/) as the executable compatibility surface. When documentation and assumptions diverge, the code and tests win.

## License

MIT. See [`LICENSE`](LICENSE).

## Guidance For AI Agents

If you are modifying this repository with an AI coding agent, treat `cli-core-yo` as a shared CLI framework layer, not as a standalone service CLI.

- Prefer framework extension points over ad-hoc Typer wiring.
- Define exactly one immutable `CliSpec` in downstream CLIs and route execution through `run(spec, argv=None)`.
- Add downstream behavior through `CommandRegistry` and plugins, not by mutating the root app directly.
- Respect reserved root names: `version`, `info`, and optional built-ins `config` and `env`.
- Use `get_context()` for invocation-scoped runtime state.
- Use `cli_core_yo.output` for human output and `emit_json()` for machine output instead of custom ANSI or JSON formatting.
- Keep behavior aligned with [`SPEC.md`](SPEC.md) and the tests in [`tests/`](tests/).
- Run the repo validation commands before handing work back:
  `python -m pytest tests/ -v --cov=cli_core_yo`,
  `ruff check cli_core_yo tests`,
  `ruff format --check cli_core_yo tests`,
  `mypy cli_core_yo --ignore-missing-imports`,
  `python -m build`,
  `twine check dist/*`.

For the repo-specific agent policy, see [`AI_DIRECTIVE.md`](AI_DIRECTIVE.md).
