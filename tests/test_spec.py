"""Tests for cli_core_yo.spec."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from cli_core_yo.spec import (
    NAME_RE,
    BackendDetectSpec,
    BackendValidationSpec,
    CliSpec,
    CommandPolicy,
    ConfigSpec,
    ContextOptionSpec,
    DeploySpec,
    EnvSpec,
    ExecutionBackendSpec,
    InvocationContextSpec,
    OutputSpec,
    PluginSpec,
    PolicySpec,
    PrereqResult,
    PrereqSpec,
    RuntimeSpec,
    XdgSpec,
)


class TestNameRegex:
    @pytest.mark.parametrize(
        "name",
        ["version", "info", "my-command", "a1", "config", "env-status", "x"],
    )
    def test_valid_names(self, name: str) -> None:
        assert NAME_RE.match(name)

    @pytest.mark.parametrize(
        "name",
        ["", "1start", "-dash", "UPPER", "camelCase", "under_score", "has space", "a.b"],
    )
    def test_invalid_names(self, name: str) -> None:
        assert not NAME_RE.match(name)


class TestXdgSpec:
    def test_minimal(self) -> None:
        spec = XdgSpec(app_dir_name="myapp")
        assert spec.app_dir_name == "myapp"

    def test_rejects_path_separators(self) -> None:
        with pytest.raises(ValueError, match="single path segment"):
            XdgSpec(app_dir_name="my/app")

    def test_frozen(self) -> None:
        spec = XdgSpec(app_dir_name="myapp")
        with pytest.raises(FrozenInstanceError):
            spec.app_dir_name = "other"  # type: ignore[misc]


class TestConfigSpec:
    def test_with_xdg_relative_path_and_template_bytes(self) -> None:
        spec = ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}")
        assert spec.xdg_relative_path == "config.json"
        assert spec.absolute_path is None
        assert spec.template_bytes == b"{}"
        assert spec.template_resource is None

    def test_with_nested_xdg_relative_path_and_template_bytes(self) -> None:
        spec = ConfigSpec(xdg_relative_path="profiles/dev/config.json", template_bytes=b"{}")
        assert spec.xdg_relative_path == "profiles/dev/config.json"
        assert spec.absolute_path is None

    def test_with_absolute_path_and_template_resource(self) -> None:
        spec = ConfigSpec(
            absolute_path=Path("/tmp/config.json"),
            template_resource=("my_pkg", "default.json"),
        )
        assert spec.absolute_path == Path("/tmp/config.json")
        assert spec.xdg_relative_path is None
        assert spec.template_resource == ("my_pkg", "default.json")
        assert spec.template_bytes is None

    def test_location_both_null_raises(self) -> None:
        with pytest.raises(ValueError, match="Exactly one of xdg_relative_path or absolute_path"):
            ConfigSpec(template_bytes=b"{}")

    def test_location_both_set_raises(self) -> None:
        with pytest.raises(ValueError, match="Exactly one of xdg_relative_path or absolute_path"):
            ConfigSpec(
                xdg_relative_path="config.json",
                absolute_path="/tmp/config.json",
                template_bytes=b"{}",
            )

    def test_template_both_null_raises(self) -> None:
        with pytest.raises(ValueError, match="Exactly one"):
            ConfigSpec(xdg_relative_path="config.json")

    def test_template_both_set_raises(self) -> None:
        with pytest.raises(ValueError, match="Exactly one"):
            ConfigSpec(
                xdg_relative_path="config.json",
                template_bytes=b"{}",
                template_resource=("pkg", "res"),
            )

    def test_xdg_relative_path_must_be_relative(self) -> None:
        with pytest.raises(ValueError, match="xdg_relative_path must be relative"):
            ConfigSpec(xdg_relative_path="/tmp/config.json", template_bytes=b"{}")

    def test_xdg_relative_path_must_not_be_empty(self) -> None:
        with pytest.raises(ValueError, match="xdg_relative_path must not be empty"):
            ConfigSpec(xdg_relative_path="   ", template_bytes=b"{}")

    def test_xdg_relative_path_rejects_parent_traversal(self) -> None:
        with pytest.raises(ValueError, match="must not contain '..'"):
            ConfigSpec(xdg_relative_path="../config.json", template_bytes=b"{}")

    def test_absolute_path_must_be_absolute(self) -> None:
        with pytest.raises(ValueError, match="absolute_path must be absolute"):
            ConfigSpec(absolute_path="config.json", template_bytes=b"{}")

    def test_absolute_path_must_not_be_empty(self) -> None:
        with pytest.raises(ValueError, match="absolute_path must not be empty"):
            ConfigSpec(absolute_path="   ", template_bytes=b"{}")

    def test_template_resource_requires_pair(self) -> None:
        with pytest.raises(ValueError, match="template_resource must be a"):
            ConfigSpec(xdg_relative_path="config.json", template_resource=("pkg",))

    def test_validator_must_be_callable(self) -> None:
        with pytest.raises(ValueError, match="validator must be callable"):
            ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}", validator="nope")

    def test_frozen(self) -> None:
        spec = ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}")
        with pytest.raises(FrozenInstanceError):
            spec.xdg_relative_path = "other"  # type: ignore[misc]


class TestBackendSpecs:
    def test_detect_spec(self) -> None:
        spec = BackendDetectSpec(env_vars=("CONDA_PREFIX",))
        assert spec.env_vars == ("CONDA_PREFIX",)

    def test_detect_spec_requires_hint(self) -> None:
        with pytest.raises(ValueError, match="requires at least one detection hint"):
            BackendDetectSpec()

    def test_detect_spec_requires_tuples_of_unique_non_empty_strings(self) -> None:
        with pytest.raises(ValueError, match="must be a tuple of strings"):
            BackendDetectSpec(env_vars=["CONDA_PREFIX"])  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="entries must be non-empty strings"):
            BackendDetectSpec(env_vars=("CONDA_PREFIX", ""))
        with pytest.raises(ValueError, match="entries must be unique"):
            BackendDetectSpec(env_vars=("CONDA_PREFIX", "CONDA_PREFIX"))

    def test_validation_spec(self) -> None:
        spec = BackendValidationSpec(command_probe=("python", "--version"))
        assert spec.command_probe == ("python", "--version")

    def test_validation_spec_requires_hint(self) -> None:
        with pytest.raises(ValueError, match="requires at least one validation hint"):
            BackendValidationSpec()

    def test_validation_spec_requires_tuple_inputs(self) -> None:
        with pytest.raises(ValueError, match="must be a tuple of strings"):
            BackendValidationSpec(command_probe=["python", "--version"])  # type: ignore[arg-type]


class TestExecutionBackendSpec:
    def test_valid_spec(self) -> None:
        spec = ExecutionBackendSpec(
            name="conda",
            kind="conda",
            entry_guidance="Run `conda activate <env>` first.",
            detect=BackendDetectSpec(env_vars=("CONDA_PREFIX",)),
            validation=BackendValidationSpec(command_probe=("conda", "--version")),
        )
        assert spec.name == "conda"
        assert spec.kind == "conda"

    def test_rejects_invalid_kind(self) -> None:
        with pytest.raises(ValueError, match="supported backend kind"):
            ExecutionBackendSpec(
                name="unknown",
                kind="unknown",  # type: ignore[arg-type]
                entry_guidance="Use it.",
                detect=BackendDetectSpec(env_vars=("X",)),
                validation=BackendValidationSpec(env_vars=("X",)),
            )

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="name must not be empty"):
            ExecutionBackendSpec(
                name="   ",
                kind="system",
                entry_guidance="Use it.",
                detect=BackendDetectSpec(env_vars=("X",)),
                validation=BackendValidationSpec(env_vars=("X",)),
            )

    def test_requires_backend_detect_and_validation_instances(self) -> None:
        with pytest.raises(ValueError, match="detect must be a BackendDetectSpec instance"):
            ExecutionBackendSpec(  # type: ignore[arg-type]
                name="system",
                kind="system",
                entry_guidance="Use it.",
                detect="bad",
                validation=BackendValidationSpec(env_vars=("PATH",)),
            )
        with pytest.raises(
            ValueError, match="validation must be a BackendValidationSpec instance"
        ):
            ExecutionBackendSpec(  # type: ignore[arg-type]
                name="system",
                kind="system",
                entry_guidance="Use it.",
                detect=BackendDetectSpec(env_vars=("PATH",)),
                validation="bad",
            )

    def test_frozen(self) -> None:
        spec = ExecutionBackendSpec(
            name="system",
            kind="system",
            entry_guidance="Use it.",
            detect=BackendDetectSpec(env_vars=("PATH",)),
            validation=BackendValidationSpec(env_vars=("PATH",)),
        )
        with pytest.raises(FrozenInstanceError):
            spec.name = "other"  # type: ignore[misc]


class TestEnvSpec:
    def test_fields_and_defaults(self) -> None:
        spec = EnvSpec(
            active_env_var="MY_ACTIVE",
            project_root_env_var="MY_ROOT",
            activate_script_name="activate.sh",
            deactivate_script_name="deactivate.sh",
        )
        assert spec.active_env_var == "MY_ACTIVE"
        assert spec.deactivate_script_name == "deactivate.sh"
        assert spec.status_fields == []
        assert spec.allow_reset is True
        assert spec.preferred_backend is None

    def test_preferred_backend_validated(self) -> None:
        spec = EnvSpec(
            active_env_var="MY_ACTIVE",
            project_root_env_var="MY_ROOT",
            activate_script_name="activate.sh",
            deactivate_script_name="deactivate.sh",
            preferred_backend="conda",
        )
        assert spec.preferred_backend == "conda"

    def test_status_fields_must_be_a_list_of_non_empty_strings(self) -> None:
        with pytest.raises(ValueError, match="status_fields must be a list of strings"):
            EnvSpec(  # type: ignore[arg-type]
                active_env_var="MY_ACTIVE",
                project_root_env_var="MY_ROOT",
                activate_script_name="activate.sh",
                deactivate_script_name="deactivate.sh",
                status_fields=("state",),
            )
        with pytest.raises(ValueError, match="status_fields entries must be non-empty strings"):
            EnvSpec(
                active_env_var="MY_ACTIVE",
                project_root_env_var="MY_ROOT",
                activate_script_name="activate.sh",
                deactivate_script_name="deactivate.sh",
                status_fields=[""],
            )


class TestPolicySpec:
    def test_default_profile(self) -> None:
        spec = PolicySpec()
        assert spec.profile == "platform-v2"


class TestOutputSpec:
    def test_defaults(self) -> None:
        spec = OutputSpec()
        assert spec.support_json is True
        assert spec.support_no_color_flag is True
        assert spec.log_stream == "stderr"
        assert spec.human_stream == "stdout"

    def test_invalid_stream_rejected(self) -> None:
        with pytest.raises(ValueError, match="human_stream must be"):
            OutputSpec(log_stream="stderr", human_stream="bogus")  # type: ignore[arg-type]


class TestRuntimeSpec:
    def test_defaults(self) -> None:
        backend = ExecutionBackendSpec(
            name="system",
            kind="system",
            entry_guidance="Use the system interpreter.",
            detect=BackendDetectSpec(binaries=("python",)),
            validation=BackendValidationSpec(command_probe=("python", "--version")),
        )
        spec = RuntimeSpec(supported_backends=[backend])
        assert spec.supported_backends == [backend]
        assert spec.default_backend is None
        assert spec.guard_mode == "enforced"
        assert spec.allow_skip_check is False
        assert spec.prereqs == []

    def test_invalid_guard_mode_rejected(self) -> None:
        backend = ExecutionBackendSpec(
            name="system",
            kind="system",
            entry_guidance="Use the system interpreter.",
            detect=BackendDetectSpec(binaries=("python",)),
            validation=BackendValidationSpec(command_probe=("python", "--version")),
        )
        with pytest.raises(ValueError, match="guard_mode must be"):
            RuntimeSpec(supported_backends=[backend], guard_mode="other")  # type: ignore[arg-type]

    def test_runtime_spec_validates_collection_types(self) -> None:
        backend = ExecutionBackendSpec(
            name="system",
            kind="system",
            entry_guidance="Use the system interpreter.",
            detect=BackendDetectSpec(binaries=("python",)),
            validation=BackendValidationSpec(command_probe=("python", "--version")),
        )
        with pytest.raises(ValueError, match="supported_backends must be a list"):
            RuntimeSpec(supported_backends=(backend,))  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="prereqs must be a list"):
            RuntimeSpec(supported_backends=[backend], prereqs=tuple())  # type: ignore[arg-type]
        with pytest.raises(
            ValueError, match="supported_backends entries must be ExecutionBackendSpec"
        ):
            RuntimeSpec(supported_backends=["bad"])  # type: ignore[list-item]
        with pytest.raises(ValueError, match="prereqs entries must be PrereqSpec"):
            RuntimeSpec(supported_backends=[backend], prereqs=["bad"])  # type: ignore[list-item]


class TestInvocationContextSpec:
    def test_defaults(self) -> None:
        spec = InvocationContextSpec()
        assert spec.options == []

    def test_with_option(self) -> None:
        option = ContextOptionSpec(
            name="target_env",
            option_flags=("--target-env",),
            value_type="choice",
            choices=("dev", "prod"),
            default="dev",
            help="Target environment.",
        )
        spec = InvocationContextSpec(options=[option])
        assert spec.options == [option]

    def test_options_must_be_a_list_of_context_options(self) -> None:
        with pytest.raises(ValueError, match="options must be a list"):
            InvocationContextSpec(options=("bad",))  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="options entries must be ContextOptionSpec"):
            InvocationContextSpec(options=["bad"])  # type: ignore[list-item]


class TestContextOptionSpec:
    def test_valid_choice_option(self) -> None:
        spec = ContextOptionSpec(
            name="target_env",
            option_flags=("--target-env", "--env"),
            value_type="choice",
            choices=("dev", "prod"),
            default="prod",
            help="Target environment.",
        )
        assert spec.name == "target_env"
        assert spec.option_flags == ("--target-env", "--env")

    def test_rejects_invalid_flags(self) -> None:
        with pytest.raises(ValueError, match="option_flags must be CLI flag names"):
            ContextOptionSpec(name="env", option_flags=("env",), value_type="str")

    def test_rejects_bad_choice_default(self) -> None:
        with pytest.raises(ValueError, match="default must be one of choices"):
            ContextOptionSpec(
                name="target_env",
                option_flags=("--target-env",),
                value_type="choice",
                choices=("dev", "prod"),
                default="qa",
            )

    def test_rejects_non_choice_default_types(self) -> None:
        with pytest.raises(ValueError, match="default must be an int"):
            ContextOptionSpec(
                name="count",
                option_flags=("--count",),
                value_type="int",
                default="1",
            )

    def test_rejects_invalid_bool_default(self) -> None:
        with pytest.raises(ValueError, match="default must be a bool"):
            ContextOptionSpec(
                name="enabled",
                option_flags=("--enabled",),
                value_type="bool",
                default="yes",
            )

    def test_rejects_invalid_value_type_and_choice_usage(self) -> None:
        with pytest.raises(ValueError, match="value_type is not supported"):
            ContextOptionSpec(  # type: ignore[arg-type]
                name="env",
                option_flags=("--env",),
                value_type="float",
            )
        with pytest.raises(ValueError, match="choices are only valid"):
            ContextOptionSpec(
                name="env",
                option_flags=("--env",),
                value_type="str",
                choices=("dev", "prod"),
            )
        with pytest.raises(ValueError, match="choices must not be empty"):
            ContextOptionSpec(
                name="env",
                option_flags=("--env",),
                value_type="choice",
            )
        with pytest.raises(ValueError, match="option_flags must not be empty"):
            ContextOptionSpec(name="env", option_flags=(), value_type="str")
        with pytest.raises(ValueError, match="entries must be unique"):
            ContextOptionSpec(
                name="env",
                option_flags=("--env", "--env"),
                value_type="str",
            )

    def test_frozen(self) -> None:
        spec = ContextOptionSpec(name="env", option_flags=("--env",), value_type="str")
        with pytest.raises(FrozenInstanceError):
            spec.name = "other"  # type: ignore[misc]


class TestDeploySpec:
    def test_defaults(self) -> None:
        spec = DeploySpec(capabilities={"plan"})
        assert spec.capabilities == {"plan"}
        assert spec.require_confirmation_for_apply is True
        assert spec.emit_plan_json is True

    def test_invalid_capability_rejected(self) -> None:
        with pytest.raises(ValueError, match="unsupported entry"):
            DeploySpec(capabilities={"destroy"})  # type: ignore[arg-type]

    def test_capabilities_must_be_a_set(self) -> None:
        with pytest.raises(ValueError, match="capabilities must be a set"):
            DeploySpec(capabilities=["plan"])  # type: ignore[arg-type]


class TestPrereqSpec:
    def test_binary_prereq(self) -> None:
        spec = PrereqSpec(key="python", kind="binary", value="python")
        assert spec.key == "python"
        assert spec.severity == "error"

    def test_command_probe_prereq(self) -> None:
        spec = PrereqSpec(
            key="git-version",
            kind="command_probe",
            value=("git", "--version"),
            severity="warn",
        )
        assert spec.value == ("git", "--version")
        assert spec.severity == "warn"

    def test_rejects_bad_kind(self) -> None:
        with pytest.raises(ValueError, match="supported prerequisite kind"):
            PrereqSpec(key="x", kind="unknown", value="x")  # type: ignore[arg-type]

    def test_rejects_command_probe_value_shape(self) -> None:
        with pytest.raises(ValueError, match="non-empty tuple for command_probe"):
            PrereqSpec(key="x", kind="command_probe", value="git")  # type: ignore[arg-type]

    def test_rejects_invalid_severity_and_collection_shapes(self) -> None:
        with pytest.raises(ValueError, match="severity must be"):
            PrereqSpec(  # type: ignore[arg-type]
                key="x",
                kind="binary",
                value="python",
                severity="fatal",
            )
        with pytest.raises(ValueError, match="applies_to_backends must be a set"):
            PrereqSpec(  # type: ignore[arg-type]
                key="x",
                kind="binary",
                value="python",
                applies_to_backends=["system"],
            )
        with pytest.raises(ValueError, match="tags must be a set"):
            PrereqSpec(  # type: ignore[arg-type]
                key="x",
                kind="binary",
                value="python",
                tags=["runtime"],
            )
        with pytest.raises(
            ValueError, match="applies_to_backends entries must be non-empty strings"
        ):
            PrereqSpec(
                key="x",
                kind="binary",
                value="python",
                applies_to_backends={""},
            )
        with pytest.raises(ValueError, match="tags entries must be non-empty strings"):
            PrereqSpec(
                key="x",
                kind="binary",
                value="python",
                tags={""},
            )

    def test_frozen(self) -> None:
        spec = PrereqSpec(key="python", kind="binary", value="python")
        with pytest.raises(FrozenInstanceError):
            spec.key = "other"  # type: ignore[misc]


class TestPrereqResult:
    def test_fields(self) -> None:
        result = PrereqResult(
            key="python",
            status="pass",
            severity="error",
            summary="python found",
            detail="python is on PATH",
        )
        assert result.detail == "python is on PATH"


class TestCommandPolicy:
    def test_defaults(self) -> None:
        policy = CommandPolicy()
        assert policy.mutates_state is False
        assert policy.supports_json is False
        assert policy.supports_dry_run is False
        assert policy.runtime_guard == "required"
        assert policy.prereq_tags == set()

    def test_supports_dry_run_requires_mutation(self) -> None:
        with pytest.raises(ValueError, match="supports_dry_run=True is only valid"):
            CommandPolicy(supports_dry_run=True)

    def test_invalid_runtime_guard_and_prereq_tags_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="runtime_guard must be"):
            CommandPolicy(runtime_guard="off")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="prereq_tags must be a set"):
            CommandPolicy(prereq_tags=["runtime"])  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="prereq_tags entries must be non-empty strings"):
            CommandPolicy(prereq_tags={""})

    def test_frozen(self) -> None:
        policy = CommandPolicy(mutates_state=True, supports_dry_run=True)
        with pytest.raises(FrozenInstanceError):
            policy.mutates_state = False  # type: ignore[misc]


class TestPluginSpec:
    def test_defaults(self) -> None:
        spec = PluginSpec()
        assert spec.explicit == []
        assert spec.entry_points == []

    def test_rejects_invalid_plugin_lists(self) -> None:
        with pytest.raises(ValueError, match="must be lists of strings"):
            PluginSpec(explicit="pkg.register")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="explicit entries must be non-empty strings"):
            PluginSpec(explicit=[""])
        with pytest.raises(ValueError, match="entry_points entries must be non-empty strings"):
            PluginSpec(entry_points=[""])


class TestCliSpec:
    def _backend(self) -> ExecutionBackendSpec:
        return ExecutionBackendSpec(
            name="system",
            kind="system",
            entry_guidance="Use the system interpreter.",
            detect=BackendDetectSpec(binaries=("python",)),
            validation=BackendValidationSpec(command_probe=("python", "--version")),
        )

    def test_minimal(self) -> None:
        spec = CliSpec(
            prog_name="myapp",
            app_display_name="My App",
            dist_name="my-app",
            root_help="My application.",
            xdg=XdgSpec(app_dir_name="myapp"),
            policy=PolicySpec(),
        )
        assert spec.prog_name == "myapp"
        assert spec.policy == PolicySpec()
        assert spec.config is None
        assert spec.env is None
        assert spec.runtime is None
        assert spec.context is None
        assert spec.output is None
        assert spec.plugins == PluginSpec()
        assert spec.info_hooks == []
        assert spec.deploy is None

    def test_with_optional_sections(self) -> None:
        backend = self._backend()
        spec = CliSpec(
            prog_name="myapp",
            app_display_name="My App",
            dist_name="my-app",
            root_help="My application.",
            xdg=XdgSpec(app_dir_name="myapp"),
            policy=PolicySpec(),
            config=ConfigSpec(xdg_relative_path="config.json", template_bytes=b"{}"),
            env=EnvSpec(
                active_env_var="A",
                project_root_env_var="B",
                activate_script_name="a.sh",
                deactivate_script_name="d.sh",
                status_fields=["state", "backend"],
                preferred_backend="system",
            ),
            runtime=RuntimeSpec(
                supported_backends=[backend],
                prereqs=[PrereqSpec(key="python", kind="binary", value="python")],
            ),
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
            output=OutputSpec(),
            plugins=PluginSpec(explicit=["pkg.register"]),
            info_hooks=[lambda: [("Extra", "Value")]],
            deploy=DeploySpec(capabilities={"plan"}),
        )
        assert spec.runtime is not None
        assert spec.runtime.supported_backends == [backend]
        assert spec.context is not None
        assert spec.output == OutputSpec()
        assert spec.deploy == DeploySpec(capabilities={"plan"})

    def test_requires_policy(self) -> None:
        with pytest.raises(TypeError):
            CliSpec(  # type: ignore[call-arg]
                prog_name="myapp",
                app_display_name="My App",
                dist_name="my-app",
                root_help="Help.",
                xdg=XdgSpec(app_dir_name="myapp"),
            )

    def test_validates_optional_section_types(self) -> None:
        base = dict(
            prog_name="myapp",
            app_display_name="My App",
            dist_name="my-app",
            root_help="Help.",
            xdg=XdgSpec(app_dir_name="myapp"),
            policy=PolicySpec(),
        )

        with pytest.raises(ValueError, match="config must be a ConfigSpec instance"):
            CliSpec(**base, config="bad")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="env must be an EnvSpec instance"):
            CliSpec(**base, env="bad")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="runtime must be a RuntimeSpec instance"):
            CliSpec(**base, runtime="bad")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="context must be an InvocationContextSpec instance"):
            CliSpec(**base, context="bad")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="output must be an OutputSpec instance"):
            CliSpec(**base, output="bad")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="plugins must be a PluginSpec instance"):
            CliSpec(**base, plugins="bad")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="info_hooks must be a list of callables"):
            CliSpec(**base, info_hooks="bad")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="info_hooks entries must be callable"):
            CliSpec(**base, info_hooks=["bad"])  # type: ignore[list-item]
        with pytest.raises(ValueError, match="deploy must be a DeploySpec instance"):
            CliSpec(**base, deploy="bad")  # type: ignore[arg-type]

    def test_frozen(self) -> None:
        spec = CliSpec(
            prog_name="myapp",
            app_display_name="My App",
            dist_name="my-app",
            root_help="Help.",
            xdg=XdgSpec(app_dir_name="myapp"),
            policy=PolicySpec(),
        )
        with pytest.raises(FrozenInstanceError):
            spec.prog_name = "other"  # type: ignore[misc]
