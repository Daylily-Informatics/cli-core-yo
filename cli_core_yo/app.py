"""App factory and invocation flow for cli-core-yo v2."""

from __future__ import annotations

import importlib.resources
import inspect
import os
import shutil
import subprocess
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click
import typer

from cli_core_yo import output
from cli_core_yo.errors import (
    CliCoreYoError,
    ContractViolationError,
    RuntimeValidationError,
    SpecValidationError,
)
from cli_core_yo.plugins import load_plugins
from cli_core_yo.registry import CommandRegistration, CommandRegistry
from cli_core_yo.runtime import _reset, get_context, initialize
from cli_core_yo.runtime_checks import (
    BackendResolution,
    evaluate_backend_validation,
    evaluate_prereqs,
    prereq_report_payload,
    resolve_backend,
    summarize_prereq_results,
)
from cli_core_yo.spec import CliSpec, CommandPolicy, ConfigSpec, ContextOptionSpec, OutputSpec
from cli_core_yo.xdg import XdgPaths, resolve_paths


@dataclass(frozen=True)
class _PreflightState:
    command: CommandRegistration | None
    backend: BackendResolution | None
    effective_guard_mode: str
    runtime_check_skipped: bool
    backend_results: list[Any]
    prereq_results: list[Any]
    root_params: dict[str, Any]
    config_path: Path | None
    invocation: dict[str, Any]


class _CliCoreRootGroup(typer.core.TyperGroup):
    """Root Typer group that bootstraps runtime before command invocation."""

    def invoke(self, ctx: click.Context):  # type: ignore[override]
        _reset()

        def _process_result(value: Any) -> Any:
            if self._result_callback is not None:
                value = ctx.invoke(self._result_callback, value, **ctx.params)
            return value

        try:
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
                    preflight = _bootstrap_runtime(ctx, args)
                    sub_ctx = cmd.make_context(cmd_name, cmd_args, parent=ctx)
                    ctx.meta["cli_core_yo_preflight"] = preflight
                    with sub_ctx:
                        return _process_result(sub_ctx.command.invoke(sub_ctx))

            with ctx:
                ctx.invoked_subcommand = "*" if args else None
                click.Command.invoke(self, ctx)
                preflight = _bootstrap_runtime(ctx, args)
                ctx.meta["cli_core_yo_preflight"] = preflight

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
        except CliCoreYoError as exc:
            _emit_framework_error(exc)
            raise SystemExit(exc.exit_code) from exc
        except KeyboardInterrupt as exc:
            raise SystemExit(130) from exc


def create_app(spec: CliSpec) -> typer.Typer:
    """Create a fully-constructed Typer app from a CliSpec."""
    _validate_spec(spec)
    xdg_paths = resolve_paths(spec.xdg)
    default_config_path = _resolve_config_path(spec.config, xdg_paths)

    app = typer.Typer(
        name=spec.prog_name,
        cls=_CliCoreRootGroup,
        help=spec.root_help,
        add_completion=True,
        no_args_is_help=True,
        rich_markup_mode="rich",
        context_settings={"help_option_names": ["--help"]},
    )

    registry = CommandRegistry()
    _register_root_callback(app, spec, xdg_paths, default_config_path, registry)

    _register_version(registry, spec)
    _register_info(registry, spec, xdg_paths)
    if spec.config is not None:
        _register_config_group(registry, spec.config)
    if spec.env is not None:
        _register_env_group(registry, spec.env, xdg_paths)
    if spec.runtime is not None:
        _register_runtime_group(registry)
    load_plugins(registry, spec)
    registry.freeze()
    registry.apply(app)

    app._cli_core_yo_registry = registry  # type: ignore[attr-defined]
    app._cli_core_yo_spec = spec  # type: ignore[attr-defined]
    app._cli_core_yo_xdg_paths = xdg_paths  # type: ignore[attr-defined]
    app._cli_core_yo_default_config_path = default_config_path  # type: ignore[attr-defined]
    return app


def run(spec: CliSpec, argv: list[str] | None = None) -> int:
    """Execute the CLI and return an exit code."""
    _reset()
    args = list(argv if argv is not None else sys.argv[1:])
    try:
        app = create_app(spec)
        app(args, standalone_mode=False)
        return 0
    except click.exceptions.NoArgsIsHelpError:
        return 0
    except click.ClickException as exc:
        exc.show(file=sys.stderr)
        return exc.exit_code
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0
    except CliCoreYoError as exc:
        _emit_framework_error(exc)
        return exc.exit_code
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # pragma: no cover - exercised only on unexpected failures
        if os.environ.get("CLI_CORE_YO_DEBUG") == "1":
            traceback.print_exc(file=sys.stderr)
        output.error(f"Unexpected error: {exc}")
        return 1


def _validate_spec(spec: CliSpec) -> None:
    if spec.policy.profile != "platform-v2":
        raise SpecValidationError("policy.profile must be 'platform-v2'")

    output_spec = _effective_output_spec(spec)
    reserved_flags = _reserved_option_flags(spec, output_spec)
    reserved_names = {
        "json",
        "dry_run",
        "no_color",
        "debug",
        "config",
        "runtime_backend",
        "skip_runtime_check",
    }

    if spec.context is not None:
        seen_names: set[str] = set()
        seen_flags: set[str] = set()
        for option in spec.context.options:
            if option.name in reserved_names:
                raise SpecValidationError(f"context option name '{option.name}' is reserved")
            if option.name in seen_names:
                raise SpecValidationError(f"duplicate context option name '{option.name}'")
            seen_names.add(option.name)
            for flag in option.option_flags:
                if flag in reserved_flags:
                    raise SpecValidationError(f"context option flag '{flag}' is reserved")
                if flag in seen_flags:
                    raise SpecValidationError(f"duplicate context option flag '{flag}'")
                seen_flags.add(flag)

    if spec.runtime is not None:
        backends = spec.runtime.supported_backends
        if not backends:
            raise SpecValidationError("runtime.supported_backends must not be empty")
        backend_names = [backend.name for backend in backends]
        if len(backend_names) != len(set(backend_names)):
            raise SpecValidationError(
                "runtime.supported_backends contains duplicate backend names"
            )
        if (
            spec.runtime.default_backend is not None
            and spec.runtime.default_backend not in backend_names
        ):
            raise SpecValidationError(
                "runtime.default_backend must be declared in supported_backends"
            )
        prereq_keys = [prereq.key for prereq in spec.runtime.prereqs]
        if len(prereq_keys) != len(set(prereq_keys)):
            raise SpecValidationError("runtime.prereqs contains duplicate prereq keys")


def _register_root_callback(
    app: typer.Typer,
    spec: CliSpec,
    xdg_paths: XdgPaths,
    default_config_path: Path | None,
    registry: CommandRegistry,
) -> None:
    def _root_callback(ctx: typer.Context, **_kwargs: Any) -> None:
        ctx.meta["cli_core_yo_spec"] = spec
        ctx.meta["cli_core_yo_xdg_paths"] = xdg_paths
        ctx.meta["cli_core_yo_default_config_path"] = default_config_path
        ctx.meta["cli_core_yo_registry"] = registry

    _root_callback.__signature__ = _root_callback_signature(spec)  # type: ignore[attr-defined]
    app.callback()(_root_callback)


def _root_callback_signature(spec: CliSpec) -> inspect.Signature:
    output_spec = _effective_output_spec(spec)
    params = [
        inspect.Parameter(
            "ctx",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=typer.Context,
        )
    ]

    if output_spec.support_json:
        params.append(
            inspect.Parameter(
                "json",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=bool,
                default=typer.Option(False, "--json", help="Emit machine-readable JSON."),
            )
        )
    params.append(
        inspect.Parameter(
            "dry_run",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=bool,
            default=typer.Option(
                False,
                "--dry-run",
                help="Plan the command without making persistent changes.",
            ),
        )
    )
    if output_spec.support_no_color_flag:
        params.append(
            inspect.Parameter(
                "no_color",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=bool,
                default=typer.Option(False, "--no-color", help="Disable ANSI styling."),
            )
        )
    params.append(
        inspect.Parameter(
            "debug",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=bool,
            default=typer.Option(False, "--debug", help="Enable debug diagnostics."),
        )
    )
    if spec.config is not None:
        params.append(
            inspect.Parameter(
                "config",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=str | None,
                default=typer.Option(
                    None,
                    "--config",
                    metavar="PATH",
                    help="Use this config file for this invocation only.",
                ),
            )
        )
    if spec.runtime is not None and len(spec.runtime.supported_backends) > 1:
        params.append(
            inspect.Parameter(
                "runtime_backend",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=str | None,
                default=typer.Option(
                    None,
                    "--runtime-backend",
                    metavar="BACKEND",
                    help="Select the execution backend.",
                    click_type=click.Choice(
                        [backend.name for backend in spec.runtime.supported_backends]
                    ),
                ),
            )
        )
    if spec.runtime is not None and spec.runtime.allow_skip_check:
        params.append(
            inspect.Parameter(
                "skip_runtime_check",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=bool,
                default=typer.Option(
                    False,
                    "--skip-runtime-check",
                    help="Skip runtime validation for this invocation.",
                ),
            )
        )
    if spec.context is not None:
        for option in spec.context.options:
            params.append(_context_signature_parameter(option))
    return inspect.Signature(params)


def _context_signature_parameter(option: ContextOptionSpec) -> inspect.Parameter:
    option_kwargs: dict[str, Any] = {
        "help": option.help,
        "show_default": option.default is not None,
    }
    annotation: Any
    if option.value_type == "bool":
        annotation = bool
        default = typer.Option(bool(option.default), *option.option_flags, **option_kwargs)
    elif option.value_type == "int":
        annotation = int | None
        default = typer.Option(option.default, *option.option_flags, **option_kwargs)
    elif option.value_type == "choice":
        annotation = str | None
        default = typer.Option(
            option.default,
            *option.option_flags,
            click_type=click.Choice(list(option.choices)),
            **option_kwargs,
        )
    else:
        annotation = str | None
        default = typer.Option(option.default, *option.option_flags, **option_kwargs)

    return inspect.Parameter(
        option.name,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        annotation=annotation,
        default=default,
    )


def _bootstrap_runtime(root_ctx: click.Context, raw_args: list[str]) -> _PreflightState:
    spec: CliSpec = root_ctx.meta["cli_core_yo_spec"]
    xdg_paths: XdgPaths = root_ctx.meta["cli_core_yo_xdg_paths"]
    default_config_path: Path | None = root_ctx.meta["cli_core_yo_default_config_path"]
    registry: CommandRegistry = root_ctx.meta["cli_core_yo_registry"]

    root_params = dict(root_ctx.params)
    command = registry.resolve_command_args(raw_args)
    command_policy = (
        command.policy
        if command is not None
        else CommandPolicy(runtime_guard="exempt")
    )
    json_mode = bool(root_params.get("json", False))
    dry_run = bool(root_params.get("dry_run", False))
    debug = bool(
        root_params.get("debug", False)
        or os.environ.get("CLI_CORE_YO_DEBUG") == "1"
    )
    no_color = bool(root_params.get("no_color", False) or "NO_COLOR" in os.environ)
    config_path = _resolve_invocation_config_path(
        default_config_path,
        root_params.get("config"),
    )
    invocation = _invocation_values(spec, root_params)

    if json_mode and not command_policy.supports_json:
        raise ContractViolationError(
            "JSON mode is not supported for this command.",
            details={"command": _command_path(command)},
            json_mode=True,
        )
    if dry_run and not command_policy.supports_dry_run:
        raise ContractViolationError(
            "Dry-run mode is not supported for this command.",
            details={"command": _command_path(command)},
            json_mode=json_mode,
        )

    backend: BackendResolution | None = None
    effective_guard_mode = "off"
    runtime_check_skipped = False
    backend_results: list[Any] = []
    prereq_results: list[Any] = []

    if spec.runtime is not None:
        backend = resolve_backend(
            spec.runtime,
            backend_override=root_params.get("runtime_backend"),
        )
        if backend.selected_by == "unresolved":
            raise ContractViolationError(
                backend.detail or "Unsupported runtime backend.",
                details={"requested_backend": root_params.get("runtime_backend")},
                json_mode=json_mode,
            )

        effective_guard_mode = _effective_runtime_guard(spec, command_policy)
        runtime_check_skipped = bool(root_params.get("skip_runtime_check", False))
        if effective_guard_mode != "off" and not runtime_check_skipped:
            backend_results = evaluate_backend_validation(
                backend.backend_spec,
                cwd=Path.cwd(),
            )
            prereq_results = evaluate_prereqs(
                spec.runtime.prereqs,
                backend_name=backend.backend_name,
                command_tags=command_policy.prereq_tags,
                cwd=Path.cwd(),
            )
            if effective_guard_mode == "enforced":
                combined = [*backend_results, *prereq_results]
                summary = summarize_prereq_results(combined)
                if summary["blocking_failures"] > 0:
                    raise RuntimeValidationError(
                        "Runtime validation failed.",
                        details=prereq_report_payload(combined),
                        json_mode=json_mode,
                    )
        elif effective_guard_mode == "off":
            runtime_check_skipped = False

    initialize(
        spec,
        xdg_paths,
        config_path=config_path,
        json_mode=json_mode,
        debug=debug,
        no_color=no_color,
        invocation=invocation,
        backend_name=None if backend is None else backend.backend_name,
        backend_kind=None if backend is None else backend.backend_kind,
        runtime_guard_mode=effective_guard_mode,  # type: ignore[arg-type]
        runtime_check_skipped=runtime_check_skipped,
        dry_run=dry_run,
    )
    return _PreflightState(
        command=command,
        backend=backend,
        effective_guard_mode=effective_guard_mode,
        runtime_check_skipped=runtime_check_skipped,
        backend_results=backend_results,
        prereq_results=prereq_results,
        root_params=root_params,
        config_path=config_path,
        invocation=invocation,
    )


def _register_version(registry: CommandRegistry, spec: CliSpec) -> None:
    def _version_callback() -> None:
        version = _get_dist_version(spec.dist_name)
        if get_context().json_mode:
            output.emit_json({"app": spec.app_display_name, "version": version})
            return
        output.print_rich(f"{spec.app_display_name} [cyan]{version}[/cyan]")

    registry.add_command(
        None,
        "version",
        _version_callback,
        help_text="Show version.",
        policy=CommandPolicy(supports_json=True, runtime_guard="exempt"),
        order=0,
    )


def _register_info(registry: CommandRegistry, spec: CliSpec, xdg_paths: XdgPaths) -> None:
    def _info_callback() -> None:
        ctx = get_context()
        rows: list[tuple[str, str]] = [
            ("Version", _get_dist_version(spec.dist_name)),
            ("Python", sys.version.split()[0]),
            ("Config Dir", str(xdg_paths.config)),
            ("Data Dir", str(xdg_paths.data)),
            ("State Dir", str(xdg_paths.state)),
            ("Cache Dir", str(xdg_paths.cache)),
            ("CLI Core", _get_dist_version("cli-core-yo")),
        ]
        if ctx.config_path is not None:
            rows.append(("Config File", str(ctx.config_path)))
        if ctx.backend_name is not None:
            rows.append(("Runtime Backend", ctx.backend_name))
        for hook in spec.info_hooks:
            rows.extend(hook())

        if ctx.json_mode:
            output.emit_json({key: value for key, value in rows})
            return

        output.heading(f"{spec.app_display_name} Info")
        width = max(len(key) for key, _ in rows)
        for key, value in rows:
            output.print_text(f"  {key:<{width}}  {value}")

    registry.add_command(
        None,
        "info",
        _info_callback,
        help_text="Show system info.",
        policy=CommandPolicy(supports_json=True, runtime_guard="exempt"),
        order=1,
    )


def _register_config_group(registry: CommandRegistry, config_spec: ConfigSpec) -> None:
    registry.add_group("config", help_text="Configuration management.")

    def _config_path_callback() -> None:
        config_path = _active_config_path()
        if get_context().json_mode:
            output.emit_json({"config_path": str(config_path)})
            return
        output.print_text(str(config_path))

    registry.add_command(
        "config",
        "path",
        _config_path_callback,
        help_text="Show config file path.",
        policy=CommandPolicy(supports_json=True, runtime_guard="exempt"),
    )

    def _config_init_callback(
        force: bool = typer.Option(
            False,
            "--force",
            help="Overwrite existing file.",
        )
    ) -> None:
        config_path = _active_config_path()
        if config_path.exists() and not force:
            raise click.ClickException(f"Config file already exists: {config_path}")
        if get_context().dry_run:
            output.heading("Dry-run plan")
            output.detail(f"Would write config template to {config_path}")
            if force and config_path.exists():
                output.detail("Existing config would be overwritten.")
            return
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_bytes(_resolve_template(config_spec))
        output.success(f"Config file created: {config_path}")

    registry.add_command(
        "config",
        "init",
        _config_init_callback,
        help_text="Create config from template.",
        policy=CommandPolicy(
            mutates_state=True,
            supports_dry_run=True,
            runtime_guard="exempt",
        ),
    )

    def _config_show_callback() -> None:
        config_path = _active_config_path()
        if not config_path.exists():
            raise click.ClickException(f"Config file not found: {config_path}")
        contents = config_path.read_text(encoding="utf-8")
        if get_context().json_mode:
            output.emit_json({"config_path": str(config_path), "contents": contents})
            return
        output.print_text(contents)

    registry.add_command(
        "config",
        "show",
        _config_show_callback,
        help_text="Show config file contents.",
        policy=CommandPolicy(supports_json=True, runtime_guard="exempt"),
    )

    def _config_validate_callback() -> None:
        config_path = _active_config_path()
        if not config_path.exists():
            raise click.ClickException(f"Config file not found: {config_path}")
        if config_spec.validator is None:
            payload = {"config_path": str(config_path), "ok": True, "errors": []}
            if get_context().json_mode:
                output.emit_json(payload)
            else:
                output.success("No validator configured; config is accepted.")
            return
        errors = config_spec.validator(config_path.read_text(encoding="utf-8"))
        payload = {"config_path": str(config_path), "ok": not errors, "errors": errors}
        if get_context().json_mode:
            output.emit_json(payload)
            if errors:
                raise SystemExit(1)
            return
        if errors:
            output.error("Config validation failed.")
            for err in errors:
                output.warning(err)
            raise SystemExit(1)
        output.success("Config is valid.")

    registry.add_command(
        "config",
        "validate",
        _config_validate_callback,
        help_text="Validate config file.",
        policy=CommandPolicy(supports_json=True, runtime_guard="exempt"),
    )

    def _config_edit_callback() -> None:
        config_path = _active_config_path()
        if not sys.stdin.isatty():
            raise click.ClickException("Cannot edit config: not an interactive terminal.")
        if not config_path.exists():
            raise click.ClickException(f"Config file not found: {config_path}")
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
        result = subprocess.run([editor, str(config_path)], check=False)
        if result.returncode != 0:
            raise click.ClickException(f"Editor exited with code {result.returncode}")

    registry.add_command(
        "config",
        "edit",
        _config_edit_callback,
        help_text="Edit config in an editor.",
        policy=CommandPolicy(mutates_state=True, interactive=True, runtime_guard="exempt"),
    )

    def _config_reset_callback(
        yes: bool = typer.Option(False, "--yes", help="Skip confirmation.")
    ) -> None:
        config_path = _active_config_path()
        exists = config_path.exists()
        if get_context().dry_run:
            output.heading("Dry-run plan")
            if exists:
                output.detail(f"Would back up {config_path} before rewriting from template.")
            else:
                output.detail(f"Would create {config_path} from the configured template.")
            return
        if exists and not yes:
            if not typer.confirm("Reset config to template? This overwrites the current file."):
                output.action("Aborted.")
                raise SystemExit(0)
        if exists:
            ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = config_path.with_suffix(f".{ts}.bak")
            shutil.copy2(str(config_path), str(backup))
            output.detail(f"Backup: {backup}")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_bytes(_resolve_template(config_spec))
        output.success(f"Config reset to template: {config_path}")

    registry.add_command(
        "config",
        "reset",
        _config_reset_callback,
        help_text="Reset config to template.",
        policy=CommandPolicy(
            mutates_state=True,
            supports_dry_run=True,
            interactive=True,
            runtime_guard="exempt",
        ),
    )


def _register_env_group(registry: CommandRegistry, env_spec: Any, xdg_paths: XdgPaths) -> None:
    registry.add_group("env", help_text="Environment guidance.")

    def _env_status_callback() -> None:
        rows = {
            "active": bool(os.environ.get(env_spec.active_env_var)),
            "active_env_var": env_spec.active_env_var,
            "active_env_value": os.environ.get(env_spec.active_env_var),
            "project_root_env_var": env_spec.project_root_env_var,
            "project_root": os.environ.get(env_spec.project_root_env_var),
            "python": sys.executable,
            "config_dir": str(xdg_paths.config),
            "preferred_backend": env_spec.preferred_backend,
            "status_fields": {field: os.environ.get(field) for field in env_spec.status_fields},
        }
        if get_context().json_mode:
            output.emit_json(rows)
            return
        if rows["active"]:
            output.success("Environment is active.")
        else:
            output.warning("Environment is not active.")
        output.detail(f"{env_spec.active_env_var}={rows['active_env_value'] or '(unset)'}")
        output.detail(f"{env_spec.project_root_env_var}={rows['project_root'] or '(unset)'}")
        output.detail(f"Python path: {rows['python']}")
        output.detail(f"Config dir: {rows['config_dir']}")
        if env_spec.preferred_backend:
            output.detail(f"Preferred backend: {env_spec.preferred_backend}")
        for field in env_spec.status_fields:
            output.detail(f"{field}: {rows['status_fields'][field] or '(unset)'}")

    registry.add_command(
        "env",
        "status",
        _env_status_callback,
        help_text="Show environment status.",
        policy=CommandPolicy(supports_json=True, runtime_guard="exempt"),
    )

    def _env_activate_callback() -> None:
        output.print_text(f"source {env_spec.activate_script_name}")

    registry.add_command(
        "env",
        "activate",
        _env_activate_callback,
        help_text="Print activation guidance.",
        policy=CommandPolicy(runtime_guard="exempt"),
    )

    def _env_deactivate_callback() -> None:
        output.print_text(f"source {env_spec.deactivate_script_name}")

    registry.add_command(
        "env",
        "deactivate",
        _env_deactivate_callback,
        help_text="Print deactivation guidance.",
        policy=CommandPolicy(runtime_guard="exempt"),
    )

    if env_spec.allow_reset:
        def _env_reset_callback() -> None:
            output.print_text(f"source {env_spec.deactivate_script_name}")
            output.print_text(f"source {env_spec.activate_script_name}")

        registry.add_command(
            "env",
            "reset",
            _env_reset_callback,
            help_text="Print environment reset guidance.",
            policy=CommandPolicy(runtime_guard="exempt"),
        )


def _register_runtime_group(registry: CommandRegistry) -> None:
    registry.add_group("runtime", help_text="Runtime inspection.")

    def _runtime_status_callback() -> None:
        ctx = get_context()
        report = _runtime_report(run_checks=True)
        backend_name = report.backend.backend_name if report.backend else None
        backend_kind = report.backend.backend_kind if report.backend else None
        config_path = None if ctx.config_path is None else str(ctx.config_path)
        summary = summarize_prereq_results([*report.backend_results, *report.prereq_results])
        payload = {
            "backend_name": backend_name,
            "backend_kind": backend_kind,
            "config_path": config_path,
            "runtime_guard_mode": ctx.runtime_guard_mode,
            "runtime_check_skipped": ctx.runtime_check_skipped,
            "prereq_summary": summary,
        }
        if ctx.json_mode:
            output.emit_json(payload)
            return
        output.heading("Runtime status")
        output.detail(f"Backend: {backend_name or '(none)'}")
        output.detail(f"Backend kind: {backend_kind or '(none)'}")
        output.detail(f"Config path: {config_path or '(none)'}")
        output.detail(f"Guard mode: {ctx.runtime_guard_mode}")
        output.detail(f"Skip check: {ctx.runtime_check_skipped}")
        output.detail(
            "Prereqs: "
            f"{summary['pass']} pass, {summary['warn']} warn, "
            f"{summary['fail']} fail, {summary['skip']} skip"
        )

    def _runtime_check_callback() -> None:
        report = _runtime_report(run_checks=True)
        results = [*report.backend_results, *report.prereq_results]
        if get_context().json_mode:
            output.emit_json(
                {
                    "backend_name": report.backend.backend_name if report.backend else None,
                    "backend_kind": report.backend.backend_kind if report.backend else None,
                    **prereq_report_payload(results),
                }
            )
            return
        output.emit_prereq_report(results, heading_text="Runtime check")

    def _runtime_explain_callback() -> None:
        report = _runtime_report(run_checks=True)
        backend = report.backend
        payload = {
            "backend_name": backend.backend_name if backend else None,
            "backend_kind": backend.backend_kind if backend else None,
            "entry_guidance": None
            if backend is None or backend.backend_spec is None
            else backend.backend_spec.entry_guidance,
            "results": prereq_report_payload([*report.backend_results, *report.prereq_results]),
        }
        if get_context().json_mode:
            output.emit_json(payload)
            return
        output.heading("Runtime explain")
        if payload["backend_name"] is not None:
            output.detail(f"Backend: {payload['backend_name']} ({payload['backend_kind']})")
        if payload["entry_guidance"]:
            output.detail(str(payload["entry_guidance"]))
        output.emit_prereq_report(
            [*report.backend_results, *report.prereq_results],
            heading_text="Applicable checks",
        )

    policy = CommandPolicy(supports_json=True, runtime_guard="exempt")
    registry.add_command(
        "runtime",
        "status",
        _runtime_status_callback,
        help_text="Show runtime status.",
        policy=policy,
    )
    registry.add_command(
        "runtime",
        "check",
        _runtime_check_callback,
        help_text="Run runtime checks.",
        policy=policy,
    )
    registry.add_command(
        "runtime",
        "explain",
        _runtime_explain_callback,
        help_text="Explain runtime requirements.",
        policy=policy,
    )


def _runtime_report(*, run_checks: bool) -> _PreflightState:
    ctx = get_context()
    spec = ctx.spec
    backend = (
        None
        if spec.runtime is None
        else resolve_backend(spec.runtime, backend_override=ctx.backend_name)
    )
    if spec.runtime is None:
        return _PreflightState(
            command=None,
            backend=None,
            effective_guard_mode="off",
            runtime_check_skipped=False,
            backend_results=[],
            prereq_results=[],
            root_params={},
            config_path=ctx.config_path,
            invocation=dict(ctx.invocation),
        )
    assert backend is not None
    backend_results = (
        evaluate_backend_validation(backend.backend_spec, cwd=Path.cwd())
        if run_checks
        else []
    )
    prereq_results = (
        evaluate_prereqs(
            spec.runtime.prereqs,
            backend_name=backend.backend_name,
            cwd=Path.cwd(),
        )
        if run_checks
        else []
    )
    return _PreflightState(
        command=None,
        backend=backend,
        effective_guard_mode=ctx.runtime_guard_mode,
        runtime_check_skipped=ctx.runtime_check_skipped,
        backend_results=backend_results,
        prereq_results=prereq_results,
        root_params={},
        config_path=ctx.config_path,
        invocation=dict(ctx.invocation),
    )


def _effective_output_spec(spec: CliSpec) -> OutputSpec:
    return spec.output or OutputSpec()


def _effective_runtime_guard(spec: CliSpec, policy: CommandPolicy) -> str:
    if spec.runtime is None:
        return "off"
    if policy.runtime_guard == "exempt":
        return "off"
    if policy.runtime_guard == "advisory":
        return "advisory"
    return spec.runtime.guard_mode


def _invocation_values(spec: CliSpec, root_params: dict[str, Any]) -> dict[str, Any]:
    if spec.context is None:
        return {}
    invocation: dict[str, Any] = {}
    for option in spec.context.options:
        if option.include_in_runtime_context:
            invocation[option.name] = root_params.get(option.name)
    return invocation


def _reserved_option_flags(spec: CliSpec, output_spec: OutputSpec) -> set[str]:
    flags = {"--help", "--debug", "--dry-run"}
    if output_spec.support_json:
        flags.add("--json")
    if output_spec.support_no_color_flag:
        flags.add("--no-color")
    if spec.config is not None:
        flags.add("--config")
    if spec.runtime is not None and len(spec.runtime.supported_backends) > 1:
        flags.add("--runtime-backend")
    if spec.runtime is not None and spec.runtime.allow_skip_check:
        flags.add("--skip-runtime-check")
    return flags


def _emit_framework_error(exc: CliCoreYoError) -> None:
    json_mode = bool(getattr(exc, "json_mode", False))
    if json_mode:
        output.emit_error_json(
            getattr(exc, "error_code", "cli_core_yo_error"),
            str(exc),
            getattr(exc, "details", None),
        )
        return
    if getattr(exc, "details", None) and isinstance(exc, RuntimeValidationError):
        output.error(str(exc))
        results = getattr(exc, "details", {}).get("results", [])
        if results:
            output.emit_prereq_report(results, heading_text="Runtime validation")
        return
    output.error(str(exc))


def _get_dist_version(dist_name: str) -> str:
    try:
        from importlib.metadata import version

        return version(dist_name)
    except Exception:
        return "unknown"


def _resolve_template(config_spec: ConfigSpec) -> bytes:
    if config_spec.template_bytes is not None:
        return config_spec.template_bytes
    if config_spec.template_resource is not None:
        pkg, resource_name = config_spec.template_resource
        ref = importlib.resources.files(pkg).joinpath(resource_name)
        return ref.read_bytes()
    raise ValueError("ConfigSpec has no template source")


def _resolve_config_path(config_spec: ConfigSpec | None, xdg_paths: XdgPaths) -> Path | None:
    if config_spec is None:
        return None
    if config_spec.xdg_relative_path is not None:
        return xdg_paths.config / Path(config_spec.xdg_relative_path)
    if config_spec.absolute_path is not None:
        return Path(config_spec.absolute_path).expanduser()
    raise ValueError("ConfigSpec has no location source")


def _resolve_invocation_config_path(
    default_config_path: Path | None,
    config_override: str | None,
) -> Path | None:
    if config_override is None:
        return default_config_path
    override_path = Path(config_override).expanduser()
    if not override_path.is_absolute():
        override_path = Path.cwd() / override_path
    return override_path.resolve()


def _active_config_path() -> Path:
    config_path = get_context().config_path
    if config_path is None:
        raise RuntimeError("Config path is unavailable because the config group is disabled.")
    return config_path


def _command_path(command: CommandRegistration | None) -> str | None:
    if command is None:
        return None
    return "/".join(command.path)
