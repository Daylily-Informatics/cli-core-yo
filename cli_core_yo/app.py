"""App factory and built-in commands (§3.3–3.5, §4.6, §4.7).

Public API:
    create_app(spec) -> typer.Typer
    run(spec, argv) -> int
"""

from __future__ import annotations

import importlib.resources
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import click
import typer

from cli_core_yo import output
from cli_core_yo.errors import CliCoreYoError
from cli_core_yo.plugins import load_plugins
from cli_core_yo.registry import CommandRegistry
from cli_core_yo.runtime import _reset, get_context, initialize
from cli_core_yo.spec import CliSpec, ConfigSpec, EnvSpec
from cli_core_yo.xdg import XdgPaths, resolve_paths


class _CliCoreRootGroup(typer.core.TyperGroup):
    """Root Typer group that bootstraps runtime for each invocation."""

    def invoke(self, ctx: click.Context):  # type: ignore[override]
        _reset()

        def _process_result(value):
            if self._result_callback is not None:
                value = ctx.invoke(self._result_callback, value, **ctx.params)
            return value

        if not ctx._protected_args:
            if self.invoke_without_command:
                with ctx:
                    rv = click.Command.invoke(self, ctx)
                    return _process_result([] if self.chain else rv)
            ctx.fail("Missing command.")

        args = [*ctx._protected_args, *ctx.args]
        ctx.args = []
        ctx._protected_args = []

        if not self.chain:
            with ctx:
                cmd_name, cmd, cmd_args = self.resolve_command(ctx, args)
                assert cmd is not None
                ctx.invoked_subcommand = cmd_name
                click.Command.invoke(self, ctx)
                _bootstrap_runtime(ctx, args)
                sub_ctx = cmd.make_context(cmd_name, cmd_args, parent=ctx)
                with sub_ctx:
                    return _process_result(sub_ctx.command.invoke(sub_ctx))

        with ctx:
            ctx.invoked_subcommand = "*" if args else None
            click.Command.invoke(self, ctx)
            _bootstrap_runtime(ctx, args)

            contexts = []
            while args:
                cmd_name, cmd, args = self.resolve_command(ctx, args)
                assert cmd is not None
                sub_ctx = cmd.make_context(
                    cmd_name,
                    args,
                    parent=ctx,
                    allow_extra_args=True,
                    allow_interspersed_args=False,
                )
                contexts.append(sub_ctx)
                args, sub_ctx.args = sub_ctx.args, []

            rv = []
            for sub_ctx in contexts:
                with sub_ctx:
                    rv.append(sub_ctx.command.invoke(sub_ctx))
            return _process_result(rv)


def create_app(spec: CliSpec) -> typer.Typer:
    """Create a fully-constructed Typer app from a CliSpec.

    Sequence (§3.5):
    1. Validate spec
    2. Construct root Typer app
    3. Register the root callback and invocation metadata
    4. Register built-in commands (version, info)
    5. Conditionally register config group
    6. Conditionally register env group
    7. Load plugins
    8. Freeze registry
    9. Apply registry to app
    """
    _validate_spec(spec)

    app = typer.Typer(
        name=spec.prog_name,
        cls=_CliCoreRootGroup,
        help=spec.root_help,
        add_completion=True,
        no_args_is_help=True,
        rich_markup_mode="rich",
        context_settings={"help_option_names": ["--help"]},
    )

    # Resolve XDG paths and default config location
    xdg_paths = resolve_paths(spec.xdg)
    default_config_path = _resolve_config_path(spec.config, xdg_paths)

    _register_root_callback(app, spec, xdg_paths, default_config_path)

    # Build reserved names from enabled optional groups
    reserved: set[str] = set()
    if spec.config is not None:
        reserved.add("config")
    if spec.env is not None:
        reserved.add("env")

    registry = CommandRegistry(reserved_names=frozenset(reserved))

    # Register built-in commands
    _register_version(registry, spec)
    _register_info(registry, spec, xdg_paths)

    # Register optional built-in groups
    if spec.config is not None:
        _register_config_group(registry, spec.config)
    if spec.env is not None:
        _register_env_group(registry, spec.env, xdg_paths)

    # Load plugins (explicit first, then entry-points)
    load_plugins(registry, spec)

    # Freeze and apply
    registry.freeze()
    registry.apply(app)

    # Store registry on app for run() to access
    app._cli_core_yo_registry = registry  # type: ignore[attr-defined]
    app._cli_core_yo_spec = spec  # type: ignore[attr-defined]
    app._cli_core_yo_xdg_paths = xdg_paths  # type: ignore[attr-defined]
    app._cli_core_yo_config_path = default_config_path  # type: ignore[attr-defined]

    return app


def run(spec: CliSpec, argv: list[str] | None = None) -> int:
    """Execute the CLI and return an exit code. MUST NOT call sys.exit()."""
    _reset()  # ensure clean context for this invocation

    try:
        app = create_app(spec)
        args = argv if argv is not None else sys.argv[1:]
        app(args, standalone_mode=False)
        return 0
    except click.exceptions.NoArgsIsHelpError:
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0
    except CliCoreYoError as exc:
        if os.environ.get("CLI_CORE_YO_DEBUG") == "1":
            traceback.print_exc(file=sys.stderr)
        output.error(str(exc))
        return exc.exit_code
    except Exception as exc:
        if os.environ.get("CLI_CORE_YO_DEBUG") == "1":
            traceback.print_exc(file=sys.stderr)
        output.error(f"Unexpected error: {exc}")
        return 1


# ── Validation ───────────────────────────────────────────────────────────────


def _validate_spec(spec: CliSpec) -> None:
    """Validate CliSpec required fields (§3.5 step 1)."""
    from cli_core_yo.errors import SpecValidationError
    from cli_core_yo.spec import NAME_RE

    if not spec.prog_name:
        raise SpecValidationError("prog_name must not be empty")
    if not NAME_RE.match(spec.prog_name):
        raise SpecValidationError(f"prog_name '{spec.prog_name}' is not a valid name")
    if not spec.app_display_name:
        raise SpecValidationError("app_display_name must not be empty")
    if not spec.dist_name:
        raise SpecValidationError("dist_name must not be empty")
    if not spec.root_help:
        raise SpecValidationError("root_help must not be empty")


def _register_root_callback(
    app: typer.Typer,
    spec: CliSpec,
    xdg_paths: XdgPaths,
    default_config_path: Path | None,
) -> None:
    """Register the root callback used for global options and invocation metadata."""

    if spec.config is None:

        @app.callback()
        def _root_callback_no_config(ctx: typer.Context) -> None:
            _store_invocation_metadata(ctx, spec, xdg_paths, default_config_path)

        return

    @app.callback()
    def _root_callback_with_config(
        ctx: typer.Context,
        config: str | None = typer.Option(
            None,
            "--config",
            metavar="PATH",
            help="Use this config file for this invocation only.",
        ),
    ) -> None:
        _store_invocation_metadata(ctx, spec, xdg_paths, default_config_path)


def _store_invocation_metadata(
    ctx: typer.Context,
    spec: CliSpec,
    xdg_paths: XdgPaths,
    default_config_path: Path | None,
) -> None:
    """Attach immutable invocation metadata to the root Click context."""
    ctx.meta["cli_core_yo_spec"] = spec
    ctx.meta["cli_core_yo_xdg_paths"] = xdg_paths
    ctx.meta["cli_core_yo_default_config_path"] = default_config_path


def _bootstrap_runtime(root_ctx: click.Context, raw_args: list[str]) -> None:
    """Initialize runtime once the root options and active command are known."""
    spec = root_ctx.meta["cli_core_yo_spec"]
    xdg_paths = root_ctx.meta["cli_core_yo_xdg_paths"]
    default_config_path = root_ctx.meta["cli_core_yo_default_config_path"]
    config_override = root_ctx.params.get("config")
    config_path = _resolve_invocation_config_path(default_config_path, config_override)
    initialize(
        spec,
        xdg_paths,
        config_path=config_path,
        json_mode=_argv_requests_json(raw_args),
        debug=os.environ.get("CLI_CORE_YO_DEBUG") == "1",
    )


# ── Built-in: version ────────────────────────────────────────────────────────


def _register_version(registry: CommandRegistry, spec: CliSpec) -> None:
    """Register the 'version' built-in command (§2.5)."""

    def _version_callback(
        json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
    ) -> None:
        version = _get_dist_version(spec.dist_name)
        if json:
            output.emit_json({"app": spec.app_display_name, "version": version})
        else:
            output.print_text(f"{spec.app_display_name} [cyan]{version}[/cyan]")

    registry._reserved.discard("version")
    registry.add_command(None, "version", _version_callback, help_text="Show version.", order=0)
    registry._reserved.add("version")


# ── Built-in: info ───────────────────────────────────────────────────────────


def _register_info(registry: CommandRegistry, spec: CliSpec, xdg_paths: XdgPaths) -> None:
    """Register the 'info' built-in command (§2.5, §6.3)."""

    def _info_callback(
        json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
    ) -> None:
        version = _get_dist_version(spec.dist_name)
        core_version = _get_dist_version("cli-core-yo")

        rows: list[tuple[str, str]] = [
            ("Version", version),
            ("Python", sys.version.split()[0]),
            ("Config Dir", str(xdg_paths.config)),
            ("Data Dir", str(xdg_paths.data)),
            ("State Dir", str(xdg_paths.state)),
            ("Cache Dir", str(xdg_paths.cache)),
            ("CLI Core", core_version),
        ]
        if spec.config is not None:
            config_path = get_context().config_path
            if config_path is not None:
                rows.append(("Config File", str(config_path)))

        # Extension hooks (§6.3)
        for hook in spec.info_hooks:
            rows.extend(hook())

        if json:
            output.emit_json({k: v for k, v in rows})
        else:
            output.heading(f"{spec.app_display_name} Info")
            max_key = max(len(k) for k, _ in rows)
            for key, val in rows:
                output.print_text(f"  {key:<{max_key}}  {val}")

    registry._reserved.discard("info")
    registry.add_command(None, "info", _info_callback, help_text="Show system info.", order=1)
    registry._reserved.add("info")


# ── Built-in: config group ───────────────────────────────────────────────────


def _register_config_group(
    registry: CommandRegistry, config_spec: ConfigSpec
) -> None:
    """Register built-in config subcommands (§4.6)."""
    registry._reserved.discard("config")
    registry.add_group("config", help_text="Configuration management.")
    registry._reserved.add("config")

    # config path
    def _config_path_callback() -> None:
        output.print_text(str(_active_config_path()))

    registry.add_command(
        "config",
        "path",
        _config_path_callback,
        help_text="Show config file path.",
    )

    # config init
    def _config_init_callback(
        force: bool = typer.Option(False, "--force", help="Overwrite existing file."),
    ) -> None:
        config_path = _active_config_path()
        if config_path.exists() and not force:
            output.error(f"Config file already exists: {config_path}")
            output.detail("Use --force to overwrite.")
            raise SystemExit(1)
        template = _resolve_template(config_spec)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_bytes(template)
        output.success(f"Config file created: {config_path}")

    registry.add_command(
        "config",
        "init",
        _config_init_callback,
        help_text="Create config from template.",
    )

    # config show
    def _config_show_callback() -> None:
        config_path = _active_config_path()
        if not config_path.exists():
            output.error(f"Config file not found: {config_path}")
            raise SystemExit(1)
        sys.stdout.write(config_path.read_text(encoding="utf-8"))

    registry.add_command(
        "config",
        "show",
        _config_show_callback,
        help_text="Show config file contents.",
    )

    # config validate
    def _config_validate_callback() -> None:
        if config_spec.validator is None:
            output.success("No validator configured — config is accepted.")
            return
        config_path = _active_config_path()
        if not config_path.exists():
            output.error(f"Config file not found: {config_path}")
            raise SystemExit(1)
        content = config_path.read_text(encoding="utf-8")
        errors = config_spec.validator(content)
        if errors:
            output.error("Config validation failed:")
            for err in errors:
                output.bullet(err)
            raise SystemExit(1)
        output.success("Config is valid.")

    registry.add_command(
        "config",
        "validate",
        _config_validate_callback,
        help_text="Validate config file.",
    )

    # config edit
    def _config_edit_callback() -> None:
        if not sys.stdin.isatty():
            output.error("Cannot edit config: not an interactive terminal.")
            raise SystemExit(1)
        config_path = _active_config_path()
        if not config_path.exists():
            output.error(f"Config file not found: {config_path}")
            raise SystemExit(1)
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
        result = subprocess.run([editor, str(config_path)])
        if result.returncode != 0:
            output.error(f"Editor exited with code {result.returncode}")
            raise SystemExit(1)

    registry.add_command(
        "config",
        "edit",
        _config_edit_callback,
        help_text="Edit config in editor.",
    )

    # config reset
    def _config_reset_callback(
        yes: bool = typer.Option(False, "--yes", help="Skip confirmation."),
    ) -> None:
        config_path = _active_config_path()
        if config_path.exists():
            if not yes:
                confirm = typer.confirm(
                    "Reset config to template? This will overwrite current config."
                )
                if not confirm:
                    output.action("Aborted.")
                    raise SystemExit(0)
            # Backup
            ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = config_path.with_suffix(f".{ts}.bak")
            shutil.copy2(str(config_path), str(backup))
            output.detail(f"Backup: {backup}")
        template = _resolve_template(config_spec)
        config_path.write_bytes(template)
        output.success(f"Config reset to template: {config_path}")

    registry.add_command(
        "config",
        "reset",
        _config_reset_callback,
        help_text="Reset config to template.",
    )


# ── Built-in: env group ──────────────────────────────────────────────────────


def _register_env_group(registry: CommandRegistry, env_spec: EnvSpec, xdg_paths: XdgPaths) -> None:
    """Register built-in env subcommands (§4.7)."""

    registry._reserved.discard("env")
    registry.add_group("env", help_text="Environment management.")
    registry._reserved.add("env")

    # env status
    def _env_status_callback() -> None:
        active_val = os.environ.get(env_spec.active_env_var, "")
        is_active = bool(active_val)
        project_root = os.environ.get(env_spec.project_root_env_var, "")

        if is_active:
            output.success("Environment is [bold]active[/bold]")
        else:
            output.warning("Environment is [bold]not active[/bold]")

        output.detail(f"Active env var: {env_spec.active_env_var}={active_val or '(unset)'}")
        output.detail(f"Project root:   {project_root or '(unset)'}")
        output.detail(f"Python path:    {sys.executable}")
        output.detail(f"Config dir:     {xdg_paths.config}")

    registry.add_command(
        "env",
        "status",
        _env_status_callback,
        help_text="Show environment status.",
    )

    # env activate
    def _env_activate_callback() -> None:
        output.print_text(f"source {env_spec.activate_script_name}")

    registry.add_command(
        "env",
        "activate",
        _env_activate_callback,
        help_text="Print activation command.",
    )

    # env deactivate
    def _env_deactivate_callback() -> None:
        output.print_text(f"source {env_spec.deactivate_script_name}")

    registry.add_command(
        "env", "deactivate", _env_deactivate_callback, help_text="Print deactivation command."
    )

    # env reset
    def _env_reset_callback() -> None:
        output.print_text(f"source {env_spec.deactivate_script_name}")
        output.print_text(f"source {env_spec.activate_script_name}")

    registry.add_command("env", "reset", _env_reset_callback, help_text="Print reset commands.")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_dist_version(dist_name: str) -> str:
    """Get installed version of a distribution package."""
    try:
        from importlib.metadata import version

        return version(dist_name)
    except Exception:
        return "unknown"


def _resolve_template(config_spec: ConfigSpec) -> bytes:
    """Resolve template content from bytes or resource."""
    if config_spec.template_bytes is not None:
        return config_spec.template_bytes
    if config_spec.template_resource is not None:
        pkg, resource_name = config_spec.template_resource
        ref = importlib.resources.files(pkg).joinpath(resource_name)
        return ref.read_bytes()
    raise ValueError("ConfigSpec has no template source")


def _resolve_config_path(config_spec: ConfigSpec | None, xdg_paths: XdgPaths) -> Path | None:
    """Resolve the single config file path for this invocation."""
    if config_spec is None:
        return None
    if config_spec.xdg_relative_path is not None:
        return xdg_paths.config / Path(config_spec.xdg_relative_path)
    if config_spec.absolute_path is not None:
        return Path(config_spec.absolute_path).expanduser()
    raise ValueError("ConfigSpec has no location source")


def _resolve_invocation_config_path(
    default_config_path: Path | None, config_override: str | None
) -> Path | None:
    """Resolve the effective config path for this invocation."""
    if config_override is None:
        return default_config_path

    override_path = Path(config_override).expanduser()
    if not override_path.is_absolute():
        override_path = Path.cwd() / override_path
    return override_path.resolve()


def _argv_requests_json(argv: list[str]) -> bool:
    """Return True if the raw argv contains a JSON output flag anywhere."""
    return "--json" in argv or "-j" in argv


def _active_config_path() -> Path:
    """Return the effective config path from runtime context."""
    config_path = get_context().config_path
    if config_path is None:
        raise RuntimeError("Config path is unavailable because the config group is disabled.")
    return config_path
