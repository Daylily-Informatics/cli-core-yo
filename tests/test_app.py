"""High-signal v2 app contract tests."""

from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from typer.testing import CliRunner

import cli_core_yo.app as app_module
from cli_core_yo import output
from cli_core_yo.app import create_app, run
from cli_core_yo.errors import ContractViolationError, RuntimeValidationError, SpecValidationError
from cli_core_yo.registry import CommandRegistry
from cli_core_yo.runtime import _reset, get_context, initialize
from cli_core_yo.spec import (
    BackendDetectSpec,
    BackendValidationSpec,
    CliSpec,
    CommandPolicy,
    ConfigSpec,
    ContextOptionSpec,
    EnvSpec,
    ExecutionBackendSpec,
    InvocationContextSpec,
    PluginSpec,
    PolicySpec,
    PrereqSpec,
    RuntimeSpec,
    XdgSpec,
)
from cli_core_yo.xdg import XdgPaths


@pytest.fixture(autouse=True)
def _xdg_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config-home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data-home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state-home"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache-home"))


def _register_module(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    register,
) -> str:
    module = types.ModuleType(name)
    module.register = register
    monkeypatch.setitem(sys.modules, name, module)
    return f"{name}.register"


def _base_spec(**kwargs) -> CliSpec:
    return CliSpec(
        prog_name="demo",
        app_display_name="Demo",
        dist_name="demo",
        root_help="Demo CLI.",
        xdg=XdgSpec(app_dir_name="demo"),
        policy=PolicySpec(),
        **kwargs,
    )


def _system_runtime(*, failing_prereq: bool = False) -> RuntimeSpec:
    prereqs = []
    if failing_prereq:
        prereqs.append(PrereqSpec(key="missing", kind="file", value="/definitely/missing"))
    return RuntimeSpec(
        supported_backends=[
            ExecutionBackendSpec(
                name="system",
                kind="system",
                entry_guidance="Use the system interpreter.",
                detect=BackendDetectSpec(binaries=("python",)),
                validation=BackendValidationSpec(env_vars=("PATH",)),
            )
        ],
        prereqs=prereqs,
    )


def _multi_backend_runtime(*, allow_skip_check: bool = False) -> RuntimeSpec:
    return RuntimeSpec(
        supported_backends=[
            ExecutionBackendSpec(
                name="system",
                kind="system",
                entry_guidance="Use the system interpreter.",
                detect=BackendDetectSpec(binaries=("python",)),
                validation=BackendValidationSpec(env_vars=("PATH",)),
            ),
            ExecutionBackendSpec(
                name="conda",
                kind="conda",
                entry_guidance="Activate the conda environment first.",
                detect=BackendDetectSpec(env_vars=("CONDA_PREFIX",)),
                validation=BackendValidationSpec(env_vars=("CONDA_PREFIX",)),
            ),
        ],
        allow_skip_check=allow_skip_check,
    )


def _runtime_paths(tmp_path: Path) -> XdgPaths:
    return XdgPaths(
        config=tmp_path / "config",
        data=tmp_path / "data",
        state=tmp_path / "state",
        cache=tmp_path / "cache",
    )


@pytest.fixture(autouse=True)
def _reset_runtime_state() -> None:
    output._reset_console()
    _reset()
    yield
    output._reset_console()
    _reset()


class TestRootContract:
    def test_root_json_is_global_for_version(self) -> None:
        result = CliRunner().invoke(create_app(_base_spec()), ["--json", "version"])

        assert result.exit_code == 0
        assert json.loads(result.stdout)["app"] == "Demo"
        assert result.stderr == ""

    def test_json_rejected_for_unsupported_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def nojson() -> None:
            output.print_text("hello")

        def register(registry: CommandRegistry, spec: CliSpec) -> None:
            registry.add_command(
                None,
                "nojson",
                nojson,
                policy=CommandPolicy(runtime_guard="exempt"),
            )

        plugin = _register_module(monkeypatch, "tests_plugin_nojson", register)
        app = create_app(_base_spec(plugins=PluginSpec(explicit=[plugin])))

        result = CliRunner().invoke(app, ["--json", "nojson"])

        assert result.exit_code == 2
        payload = json.loads(result.stdout)
        assert payload["error"]["code"] == "contract_violation"
        assert payload["error"]["details"]["command"] == "nojson"
        assert result.stderr == ""

    def test_dry_run_rejected_for_unsupported_command(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def nojson() -> None:
            output.print_text("hello")

        def register(registry: CommandRegistry, spec: CliSpec) -> None:
            registry.add_command(
                None,
                "nojson",
                nojson,
                policy=CommandPolicy(runtime_guard="exempt"),
            )

        plugin = _register_module(monkeypatch, "tests_plugin_dryrun", register)
        app = create_app(_base_spec(plugins=PluginSpec(explicit=[plugin])))

        result = CliRunner().invoke(app, ["--dry-run", "nojson"])

        assert result.exit_code == 2
        assert result.stdout == ""
        assert "Dry-run mode is not supported" in result.stderr

    def test_invocation_selectors_populate_runtime_context(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def report() -> None:
            ctx = get_context()
            output.emit_json(
                {
                    "invocation": dict(ctx.invocation),
                    "dry_run": ctx.dry_run,
                }
            )

        def register(registry: CommandRegistry, spec: CliSpec) -> None:
            registry.add_command(
                None,
                "report",
                report,
                policy=CommandPolicy(supports_json=True, runtime_guard="exempt"),
            )

        plugin = _register_module(monkeypatch, "tests_plugin_context", register)
        app = create_app(
            _base_spec(
                plugins=PluginSpec(explicit=[plugin]),
                context=InvocationContextSpec(
                    options=[
                        ContextOptionSpec(
                            name="target_env",
                            option_flags=("--target-env",),
                            value_type="choice",
                            choices=("dev", "prod"),
                            default="dev",
                        )
                    ]
                ),
            )
        )

        result = CliRunner().invoke(app, ["--json", "--target-env", "prod", "report"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["invocation"] == {"target_env": "prod"}
        assert payload["dry_run"] is False


class TestRuntimeContract:
    def test_runtime_required_failure_returns_exit_3_json(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def guarded() -> None:
            output.emit_json({"guarded": True})

        def register(registry: CommandRegistry, spec: CliSpec) -> None:
            registry.add_command(
                None,
                "guarded",
                guarded,
                policy=CommandPolicy(supports_json=True, runtime_guard="required"),
            )

        plugin = _register_module(monkeypatch, "tests_plugin_guarded", register)
        app = create_app(
            _base_spec(
                plugins=PluginSpec(explicit=[plugin]),
                runtime=_system_runtime(failing_prereq=True),
            )
        )

        result = CliRunner().invoke(app, ["--json", "guarded"])

        assert result.exit_code == 3
        payload = json.loads(result.stdout)
        assert payload["error"]["code"] == "runtime_validation_failed"
        assert payload["error"]["details"]["summary"]["blocking_failures"] == 1
        assert result.stderr == ""

    def test_runtime_exempt_command_bypasses_runtime_guard(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def hello() -> None:
            ctx = get_context()
            output.emit_json({"backend": ctx.backend_name, "ok": True})

        def register(registry: CommandRegistry, spec: CliSpec) -> None:
            registry.add_command(
                None,
                "hello",
                hello,
                policy=CommandPolicy(supports_json=True, runtime_guard="exempt"),
            )

        plugin = _register_module(monkeypatch, "tests_plugin_runtime_exempt", register)
        app = create_app(
            _base_spec(
                plugins=PluginSpec(explicit=[plugin]),
                runtime=_system_runtime(failing_prereq=True),
            )
        )

        result = CliRunner().invoke(app, ["--json", "hello"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {"backend": "system", "ok": True}

    def test_runtime_group_status_and_check_emit_json(self) -> None:
        app = create_app(_base_spec(runtime=_system_runtime(failing_prereq=True)))
        runner = CliRunner()

        status = runner.invoke(app, ["--json", "runtime", "status"])
        check = runner.invoke(app, ["--json", "runtime", "check"])

        assert status.exit_code == 0
        assert json.loads(status.stdout)["backend_name"] == "system"
        assert check.exit_code == 0
        payload = json.loads(check.stdout)
        assert payload["summary"]["fail"] == 1
        assert payload["results"][0]["key"].startswith("system:")


class TestConfigAndEnvBuiltins:
    def test_config_path_supports_json(self) -> None:
        app = create_app(
            _base_spec(config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n"))
        )

        result = CliRunner().invoke(app, ["--json", "config", "path"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["config_path"].endswith("/demo/config.json")

    def test_config_init_dry_run_emits_plan_without_writing(self, tmp_path: Path) -> None:
        app = create_app(
            _base_spec(config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n"))
        )
        config_file = tmp_path / "config-home" / "demo" / "config.json"

        result = CliRunner().invoke(app, ["--dry-run", "config", "init"])

        assert result.exit_code == 0
        assert "Dry-run plan" in result.stdout
        assert not config_file.exists()

    def test_env_reset_is_suppressed_when_disallowed(self) -> None:
        app = create_app(
            _base_spec(
                env=EnvSpec(
                    active_env_var="ACTIVE_ENV",
                    project_root_env_var="ROOT_ENV",
                    activate_script_name="activate.sh",
                    deactivate_script_name="deactivate.sh",
                    allow_reset=False,
                )
            )
        )

        result = CliRunner().invoke(app, ["env", "--help"])

        assert result.exit_code == 0
        assert "reset" not in result.stdout

    def test_human_version_output(self) -> None:
        result = CliRunner().invoke(create_app(_base_spec()), ["version"])

        assert result.exit_code == 0
        assert "Demo" in result.stdout
        assert "unknown" in result.stdout or "." in result.stdout

    def test_human_info_includes_runtime_config_and_hooks(self) -> None:
        app = create_app(
            _base_spec(
                config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n"),
                runtime=_system_runtime(),
                info_hooks=[lambda: [("Extra", "Value")]],
            )
        )

        result = CliRunner().invoke(app, ["info"])

        assert result.exit_code == 0
        assert "Demo Info" in result.stdout
        assert "Config File" in result.stdout
        assert "Runtime Backend" in result.stdout
        assert "Extra" in result.stdout

    def test_config_path_human_output(self) -> None:
        app = create_app(
            _base_spec(config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n"))
        )

        result = CliRunner().invoke(app, ["config", "path"])

        assert result.exit_code == 0
        assert result.stdout.strip().endswith("/demo/config.json")

    def test_config_init_writes_template(self, tmp_path: Path) -> None:
        app = create_app(
            _base_spec(
                config=ConfigSpec(
                    xdg_relative_path="config.json", template_bytes=b'{\n  "ok": true\n}\n'
                )
            )
        )
        config_file = tmp_path / "config-home" / "demo" / "config.json"

        result = CliRunner().invoke(app, ["config", "init"])

        assert result.exit_code == 0
        assert config_file.read_text(encoding="utf-8") == '{\n  "ok": true\n}\n'
        assert "Config file created" in result.stdout

    def test_config_init_existing_file_requires_force(self, tmp_path: Path) -> None:
        app = create_app(
            _base_spec(config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n"))
        )
        config_file = tmp_path / "config-home" / "demo" / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("old\n", encoding="utf-8")

        result = CliRunner().invoke(app, ["config", "init"])

        assert result.exit_code == 1
        assert "Config file already exists" in result.output

    def test_config_init_dry_run_force_reports_overwrite(self, tmp_path: Path) -> None:
        app = create_app(
            _base_spec(config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n"))
        )
        config_file = tmp_path / "config-home" / "demo" / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("old\n", encoding="utf-8")

        result = CliRunner().invoke(app, ["--dry-run", "config", "init", "--force"])

        assert result.exit_code == 0
        assert "Existing config would be overwritten." in result.stdout

    def test_config_show_missing_file_errors(self) -> None:
        app = create_app(
            _base_spec(config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n"))
        )

        result = CliRunner().invoke(app, ["config", "show"])

        assert result.exit_code == 1
        assert "Config file not found" in result.output

    def test_config_show_human_output(self, tmp_path: Path) -> None:
        app = create_app(
            _base_spec(config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n"))
        )
        config_file = tmp_path / "config-home" / "demo" / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text('{"hello": "world"}\n', encoding="utf-8")

        result = CliRunner().invoke(app, ["config", "show"])

        assert result.exit_code == 0
        assert result.stdout == '{"hello": "world"}\n'

    def test_config_validate_missing_file_errors(self) -> None:
        app = create_app(
            _base_spec(
                config=ConfigSpec(
                    xdg_relative_path="config.json",
                    template_bytes=b"{}\n",
                    validator=lambda text: [],
                )
            )
        )

        result = CliRunner().invoke(app, ["config", "validate"])

        assert result.exit_code == 1
        assert "Config file not found" in result.output

    def test_config_validate_without_validator_accepts_human_output(self, tmp_path: Path) -> None:
        app = create_app(
            _base_spec(config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n"))
        )
        config_file = tmp_path / "config-home" / "demo" / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("{}\n", encoding="utf-8")

        result = CliRunner().invoke(app, ["config", "validate"])

        assert result.exit_code == 0
        assert "No validator configured; config is accepted." in result.stdout

    def test_config_validate_failure_human_output(self, tmp_path: Path) -> None:
        app = create_app(
            _base_spec(
                config=ConfigSpec(
                    xdg_relative_path="config.json",
                    template_bytes=b"{}\n",
                    validator=lambda text: ["missing field"],
                )
            )
        )
        config_file = tmp_path / "config-home" / "demo" / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("{}\n", encoding="utf-8")

        result = CliRunner().invoke(app, ["config", "validate"])

        assert result.exit_code == 1
        assert "Config validation failed." in result.output
        assert "missing field" in result.output

    def test_config_validate_failure_json_output(self, tmp_path: Path) -> None:
        app = create_app(
            _base_spec(
                config=ConfigSpec(
                    xdg_relative_path="config.json",
                    template_bytes=b"{}\n",
                    validator=lambda text: ["missing field"],
                )
            )
        )
        config_file = tmp_path / "config-home" / "demo" / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("{}\n", encoding="utf-8")

        result = CliRunner().invoke(app, ["--json", "config", "validate"])

        assert result.exit_code == 1
        assert json.loads(result.stdout)["errors"] == ["missing field"]

    def test_config_validate_success_human_output(self, tmp_path: Path) -> None:
        app = create_app(
            _base_spec(
                config=ConfigSpec(
                    xdg_relative_path="config.json",
                    template_bytes=b"{}\n",
                    validator=lambda text: [],
                )
            )
        )
        config_file = tmp_path / "config-home" / "demo" / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("{}\n", encoding="utf-8")

        result = CliRunner().invoke(app, ["config", "validate"])

        assert result.exit_code == 0
        assert "Config is valid." in result.stdout

    def test_config_edit_requires_interactive_terminal(self) -> None:
        app = create_app(
            _base_spec(config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n"))
        )

        result = CliRunner().invoke(app, ["config", "edit"])

        assert result.exit_code == 1
        assert "not an interactive terminal" in result.output

    def test_config_edit_requires_existing_file_when_interactive(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        app = create_app(
            _base_spec(config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n"))
        )
        registry = app._cli_core_yo_registry  # type: ignore[attr-defined]
        command = registry.get_command(("config", "edit"))
        assert command is not None

        initialize(
            _base_spec(config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n")),
            _runtime_paths(tmp_path),
            config_path=tmp_path / "config-home" / "demo" / "config.json",
        )
        monkeypatch.setattr(app_module.sys, "stdin", SimpleNamespace(isatty=lambda: True))

        with pytest.raises(click.ClickException, match="Config file not found"):
            command.callback()

    def test_config_edit_reports_editor_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        app = create_app(
            _base_spec(config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n"))
        )
        registry = app._cli_core_yo_registry  # type: ignore[attr-defined]
        command = registry.get_command(("config", "edit"))
        assert command is not None
        config_file = tmp_path / "config-home" / "demo" / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("{}\n", encoding="utf-8")
        initialize(
            _base_spec(config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n")),
            _runtime_paths(tmp_path),
            config_path=config_file,
        )
        monkeypatch.setattr(app_module.sys, "stdin", SimpleNamespace(isatty=lambda: True))
        monkeypatch.setenv("VISUAL", "fake-editor")
        monkeypatch.setattr(
            app_module.subprocess,
            "run",
            lambda command, check=False: subprocess.CompletedProcess(command, 1),
        )

        with pytest.raises(click.ClickException, match="Editor exited with code 1"):
            command.callback()

    def test_config_reset_dry_run_existing_file_reports_backup(self, tmp_path: Path) -> None:
        app = create_app(
            _base_spec(config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n"))
        )
        config_file = tmp_path / "config-home" / "demo" / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("old\n", encoding="utf-8")

        result = CliRunner().invoke(app, ["--dry-run", "config", "reset"])

        assert result.exit_code == 0
        assert "Would back up" in result.stdout

    def test_config_reset_abort_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        app = create_app(
            _base_spec(config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n"))
        )
        config_file = tmp_path / "config-home" / "demo" / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("old\n", encoding="utf-8")
        monkeypatch.setattr(app_module.typer, "confirm", lambda message: False)

        result = CliRunner().invoke(app, ["config", "reset"])

        assert result.exit_code == 0
        assert "Aborted." in result.stdout
        assert config_file.read_text(encoding="utf-8") == "old\n"

    def test_config_reset_creates_backup_and_rewrites_file(self, tmp_path: Path) -> None:
        app = create_app(
            _base_spec(config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"new\n"))
        )
        config_file = tmp_path / "config-home" / "demo" / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("old\n", encoding="utf-8")

        result = CliRunner().invoke(app, ["config", "reset", "--yes"])

        backups = list(config_file.parent.glob("config.*.bak"))

        assert result.exit_code == 0
        assert config_file.read_text(encoding="utf-8") == "new\n"
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == "old\n"
        assert "Config reset to template" in result.stdout

    def test_env_status_human_output_when_active(self, monkeypatch: pytest.MonkeyPatch) -> None:
        app = create_app(
            _base_spec(
                env=EnvSpec(
                    active_env_var="ACTIVE_ENV",
                    project_root_env_var="ROOT_ENV",
                    activate_script_name="activate.sh",
                    deactivate_script_name="deactivate.sh",
                    status_fields=["EXTRA_STATUS"],
                    preferred_backend="system",
                )
            )
        )
        monkeypatch.setenv("ACTIVE_ENV", "demo")
        monkeypatch.setenv("ROOT_ENV", "/workspace")
        monkeypatch.setenv("EXTRA_STATUS", "ready")

        result = CliRunner().invoke(app, ["env", "status"])

        assert result.exit_code == 0
        assert "Environment is active." in result.stdout
        assert "Preferred backend: system" in result.stdout
        assert "EXTRA_STATUS: ready" in result.stdout

    def test_env_status_human_output_when_inactive(self) -> None:
        app = create_app(
            _base_spec(
                env=EnvSpec(
                    active_env_var="ACTIVE_ENV",
                    project_root_env_var="ROOT_ENV",
                    activate_script_name="activate.sh",
                    deactivate_script_name="deactivate.sh",
                )
            )
        )

        result = CliRunner().invoke(app, ["env", "status"])

        assert result.exit_code == 0
        assert "Environment is not active." in result.output

    def test_env_activate_deactivate_and_reset_guidance(self) -> None:
        app = create_app(
            _base_spec(
                env=EnvSpec(
                    active_env_var="ACTIVE_ENV",
                    project_root_env_var="ROOT_ENV",
                    activate_script_name="activate.sh",
                    deactivate_script_name="deactivate.sh",
                    allow_reset=True,
                )
            )
        )
        runner = CliRunner()

        activate = runner.invoke(app, ["env", "activate"])
        deactivate = runner.invoke(app, ["env", "deactivate"])
        reset = runner.invoke(app, ["env", "reset"])

        assert activate.stdout == "source activate.sh\n"
        assert deactivate.stdout == "source deactivate.sh\n"
        assert reset.stdout == "source deactivate.sh\nsource activate.sh\n"

    def test_runtime_status_check_and_explain_human_output(self) -> None:
        app = create_app(_base_spec(runtime=_system_runtime(failing_prereq=True)))
        runner = CliRunner()

        status = runner.invoke(app, ["runtime", "status"])
        check = runner.invoke(app, ["runtime", "check"])
        explain = runner.invoke(app, ["runtime", "explain"])

        assert status.exit_code == 0
        assert "Runtime status" in status.stdout
        assert "Backend: system" in status.stdout
        assert check.exit_code == 0
        assert "Runtime check" in check.stdout
        assert explain.exit_code == 0
        assert "Runtime explain" in explain.stdout
        assert "Use the system interpreter." in explain.stdout

    def test_runtime_explain_json_output(self) -> None:
        app = create_app(_base_spec(runtime=_system_runtime(failing_prereq=True)))

        result = CliRunner().invoke(app, ["--json", "runtime", "explain"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["backend_name"] == "system"
        assert payload["entry_guidance"] == "Use the system interpreter."


class TestAppHelpers:
    def test_root_callback_signature_includes_framework_and_context_options(self) -> None:
        spec = _base_spec(
            config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}\n"),
            runtime=_multi_backend_runtime(allow_skip_check=True),
            context=InvocationContextSpec(
                options=[
                    ContextOptionSpec(
                        name="enabled", option_flags=("--enabled",), value_type="bool"
                    ),
                    ContextOptionSpec(name="count", option_flags=("--count",), value_type="int"),
                    ContextOptionSpec(
                        name="target_env",
                        option_flags=("--target-env",),
                        value_type="choice",
                        choices=("dev", "prod"),
                    ),
                    ContextOptionSpec(name="label", option_flags=("--label",), value_type="str"),
                ]
            ),
        )

        params = app_module._root_callback_signature(spec).parameters

        assert list(params) == [
            "ctx",
            "json",
            "dry_run",
            "no_color",
            "debug",
            "config",
            "runtime_backend",
            "skip_runtime_check",
            "enabled",
            "count",
            "target_env",
            "label",
        ]
        assert params["enabled"].annotation is bool
        assert params["count"].annotation == int | None
        assert params["target_env"].annotation == str | None
        assert params["label"].annotation == str | None

    def test_reserved_option_flags_include_runtime_specific_flags(self) -> None:
        flags = app_module._reserved_option_flags(
            _base_spec(runtime=_multi_backend_runtime(allow_skip_check=True)),
            app_module.OutputSpec(),
        )

        assert "--runtime-backend" in flags
        assert "--skip-runtime-check" in flags

    def test_validate_spec_rejects_invalid_profile(self) -> None:
        spec = CliSpec(
            prog_name="demo",
            app_display_name="Demo",
            dist_name="demo",
            root_help="Demo CLI.",
            xdg=XdgSpec(app_dir_name="demo"),
            policy=PolicySpec(profile="legacy"),  # type: ignore[arg-type]
        )

        with pytest.raises(SpecValidationError, match="policy.profile must be 'platform-v2'"):
            app_module._validate_spec(spec)

    def test_validate_spec_rejects_reserved_context_name(self) -> None:
        spec = _base_spec(
            context=InvocationContextSpec(
                options=[
                    ContextOptionSpec(name="json", option_flags=("--json-mode",), value_type="str")
                ]
            )
        )

        with pytest.raises(SpecValidationError, match="context option name 'json' is reserved"):
            app_module._validate_spec(spec)

    def test_validate_spec_rejects_remaining_cross_object_conflicts(self) -> None:
        duplicate_backends = RuntimeSpec(
            supported_backends=[
                ExecutionBackendSpec(
                    name="system",
                    kind="system",
                    entry_guidance="Use system",
                    detect=BackendDetectSpec(binaries=("python",)),
                    validation=BackendValidationSpec(env_vars=("PATH",)),
                ),
                ExecutionBackendSpec(
                    name="system",
                    kind="conda",
                    entry_guidance="Use conda",
                    detect=BackendDetectSpec(env_vars=("CONDA_PREFIX",)),
                    validation=BackendValidationSpec(env_vars=("CONDA_PREFIX",)),
                ),
            ]
        )
        duplicate_prereqs = RuntimeSpec(
            supported_backends=[
                ExecutionBackendSpec(
                    name="system",
                    kind="system",
                    entry_guidance="Use system",
                    detect=BackendDetectSpec(binaries=("python",)),
                    validation=BackendValidationSpec(env_vars=("PATH",)),
                )
            ],
            prereqs=[
                PrereqSpec(key="dup", kind="binary", value="python"),
                PrereqSpec(key="dup", kind="file", value="/tmp/missing"),
            ],
        )

        cases = [
            (
                _base_spec(
                    context=InvocationContextSpec(
                        options=[
                            ContextOptionSpec(
                                name="env1", option_flags=("--json",), value_type="str"
                            )
                        ]
                    )
                ),
                "context option flag '--json' is reserved",
            ),
            (
                _base_spec(
                    context=InvocationContextSpec(
                        options=[
                            ContextOptionSpec(
                                name="env1", option_flags=("--env",), value_type="str"
                            ),
                            ContextOptionSpec(
                                name="env1", option_flags=("--other",), value_type="str"
                            ),
                        ]
                    )
                ),
                "duplicate context option name 'env1'",
            ),
            (
                _base_spec(
                    context=InvocationContextSpec(
                        options=[
                            ContextOptionSpec(
                                name="env1", option_flags=("--env",), value_type="str"
                            ),
                            ContextOptionSpec(
                                name="env2", option_flags=("--env",), value_type="str"
                            ),
                        ]
                    )
                ),
                "duplicate context option flag '--env'",
            ),
            (
                _base_spec(runtime=RuntimeSpec(supported_backends=[])),
                "runtime.supported_backends must not be empty",
            ),
            (_base_spec(runtime=duplicate_backends), "duplicate backend names"),
            (
                _base_spec(
                    runtime=RuntimeSpec(
                        supported_backends=duplicate_backends.supported_backends[:1],
                        default_backend="conda",
                    )
                ),
                "runtime.default_backend must be declared",
            ),
            (
                _base_spec(runtime=duplicate_prereqs),
                "runtime.prereqs contains duplicate prereq keys",
            ),
        ]

        for spec, message in cases:
            with pytest.raises(SpecValidationError, match=message):
                app_module._validate_spec(spec)

    def test_runtime_report_without_runtime_returns_off(self, tmp_path: Path) -> None:
        ctx = initialize(_base_spec(), _runtime_paths(tmp_path))

        report = app_module._runtime_report(run_checks=True)

        assert report.backend is None
        assert report.effective_guard_mode == "off"
        assert report.config_path == ctx.config_path

    def test_effective_runtime_guard_handles_all_modes(self) -> None:
        runtime_spec = _base_spec(runtime=_system_runtime()).runtime
        assert runtime_spec is not None
        assert app_module._effective_runtime_guard(_base_spec(), CommandPolicy()) == "off"
        assert (
            app_module._effective_runtime_guard(
                _base_spec(runtime=runtime_spec), CommandPolicy(runtime_guard="exempt")
            )
            == "off"
        )
        assert (
            app_module._effective_runtime_guard(
                _base_spec(runtime=runtime_spec), CommandPolicy(runtime_guard="advisory")
            )
            == "advisory"
        )

    def test_emit_framework_error_human_runtime_validation_outputs_report(self, capsys) -> None:
        exc = RuntimeValidationError(
            "Runtime validation failed.",
            details={
                "results": [
                    {
                        "key": "missing",
                        "status": "fail",
                        "severity": "error",
                        "summary": "Missing dependency",
                        "detail": None,
                    }
                ]
            },
        )

        app_module._emit_framework_error(exc)

        captured = capsys.readouterr()

        assert "Runtime validation failed." in captured.err
        assert "Runtime validation" in captured.out

    def test_resolve_template_and_config_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_spec = ConfigSpec(
            absolute_path=Path("/tmp/demo.json"),
            template_resource=("cli_core_yo", "__init__.py"),
        )

        template = app_module._resolve_template(config_spec)
        path = app_module._resolve_config_path(config_spec, _runtime_paths(tmp_path))

        monkeypatch.chdir(tmp_path)
        override = app_module._resolve_invocation_config_path(None, "demo.json")

        assert b"cli-core-yo" in template
        assert path == Path("/tmp/demo.json")
        assert override == (tmp_path / "demo.json").resolve()

    def test_resolve_template_and_config_path_require_sources(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="no template source"):
            app_module._resolve_template(
                SimpleNamespace(template_bytes=None, template_resource=None)
            )  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="no location source"):
            app_module._resolve_config_path(
                SimpleNamespace(xdg_relative_path=None, absolute_path=None),  # type: ignore[arg-type]
                _runtime_paths(tmp_path),
            )

    def test_active_config_path_requires_enabled_config(self, tmp_path: Path) -> None:
        initialize(_base_spec(), _runtime_paths(tmp_path), config_path=None)

        with pytest.raises(RuntimeError, match="config group is disabled"):
            app_module._active_config_path()

    def test_command_path_none_returns_none(self) -> None:
        assert app_module._command_path(None) is None

    def test_run_maps_framework_exceptions_to_exit_codes(
        self, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        class RaisingApp:
            def __init__(self, exc: BaseException) -> None:
                self.exc = exc

            def __call__(self, args: list[str], standalone_mode: bool = False) -> None:
                raise self.exc

        ctx = click.Context(click.Command("demo"))
        cases = [
            (click.exceptions.NoArgsIsHelpError(ctx), 0),
            (click.ClickException("bad click"), 1),
            (SystemExit(7), 7),
            (ContractViolationError("bad contract"), 2),
            (KeyboardInterrupt(), 130),
        ]

        for exc, expected in cases:
            monkeypatch.setattr(app_module, "create_app", lambda spec, exc=exc: RaisingApp(exc))
            assert run(_base_spec(), []) == expected

        captured = capsys.readouterr()
        assert "bad click" in captured.err
        assert "bad contract" in captured.err
