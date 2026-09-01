"""Tests for opt-in downstream CLI syntax validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli_core_yo.app import create_app
from cli_core_yo.conformance import invoke, json_output
from cli_core_yo.spec import CliSpec, CommandPolicy, ConfigSpec, PolicySpec, XdgSpec
from cli_core_yo.validation import (
    CliSurface,
    CliSyntaxValidationConfig,
    CommandPolicyExpectation,
    CommandPolicySurface,
    CommandSurface,
    FindingAllowance,
    normalize_cli,
    validate_cli,
    validate_surface,
)


@pytest.fixture(autouse=True)
def _xdg_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config-home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data-home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state-home"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache-home"))


def _base_spec(**kwargs: object) -> CliSpec:
    return CliSpec(
        prog_name="demo",
        app_display_name="Demo",
        dist_name="demo",
        root_help="Demo CLI.",
        xdg=XdgSpec(app_dir_name="demo"),
        policy=PolicySpec(),
        **kwargs,
    )


def _policy_surface() -> CommandPolicySurface:
    return CommandPolicySurface.from_policy(CommandPolicy())


class TestNormalizeCli:
    def test_existing_cli_spec_is_unchanged_when_validation_is_not_requested(self) -> None:
        app = create_app(_base_spec())

        surface_before = normalize_cli(app)
        version_before = invoke(app, ["--json", "version"])

        assert surface_before.root_flags == (
            "--debug",
            "--dry-run",
            "--help",
            "--json",
            "--no-color",
        )
        assert surface_before.groups == ()
        assert [command.path for command in surface_before.commands] == [("info",), ("version",)]
        assert version_before.exit_code == 0
        assert json_output(version_before)["app"] == "Demo"
        assert normalize_cli(app) == surface_before

    def test_validation_is_observational_and_does_not_change_invocation_behavior(self) -> None:
        app = create_app(_base_spec())
        surface_before = normalize_cli(app)
        before = invoke(app, ["--json", "version"])

        report = validate_cli(
            app,
            CliSyntaxValidationConfig(
                required_root_flags=("--json", "--dry-run"),
                required_commands=("version", "info"),
                policy_expectations={
                    "version": CommandPolicyExpectation(
                        supports_json=True,
                        runtime_guard="exempt",
                    )
                },
            ),
        )
        after = invoke(app, ["--json", "version"])

        assert report.is_valid
        assert report.exit_code == 0
        assert normalize_cli(app) == surface_before
        assert json_output(after) == json_output(before)

    def test_normalize_cli_requires_a_core_created_app(self) -> None:
        with pytest.raises(TypeError, match="created by cli_core_yo.app.create_app"):
            normalize_cli(object())


class TestValidateCli:
    def test_reports_root_group_command_and_policy_drift(self) -> None:
        app = create_app(
            _base_spec(
                config=ConfigSpec(
                    xdg_relative_path="demo.json",
                    template_bytes=b"{}\n",
                )
            )
        )

        report = validate_cli(
            app,
            CliSyntaxValidationConfig(
                required_root_flags=("--config", "--json"),
                forbidden_root_flags=("--debug",),
                required_groups=("config", "deploy"),
                forbidden_groups=("config",),
                required_commands=("version", "deploy/apply"),
                forbidden_commands=("info",),
                policy_expectations={
                    "version": CommandPolicyExpectation(
                        supports_json=False,
                        runtime_guard="required",
                    )
                },
            ),
        )

        assert report.exit_code == 1
        assert not report.is_valid
        assert [finding.code for finding in report.findings] == [
            "forbidden_root_flag",
            "missing_group",
            "forbidden_group",
            "missing_command",
            "forbidden_command",
            "policy_mismatch",
            "policy_mismatch",
        ]
        assert report.to_dict()["findings"][0]["root_flag"] == "--debug"
        assert report.to_dict()["findings"][3]["path"] == "deploy/apply"

    def test_allowlisted_finding_is_reported_without_failing(self) -> None:
        app = create_app(_base_spec())

        report = validate_cli(
            app,
            CliSyntaxValidationConfig(
                required_commands=("deploy/apply",),
                allowlisted_findings=(
                    FindingAllowance(code="missing_command", path="deploy/apply"),
                ),
            ),
        )

        assert report.is_valid
        assert report.exit_code == 0
        assert report.findings[0].allowed

    def test_warn_mode_preserves_findings_without_a_nonzero_exit_code(self) -> None:
        app = create_app(_base_spec())

        report = validate_cli(
            app,
            CliSyntaxValidationConfig(required_commands=("deploy/apply",), mode="warn"),
        )

        assert not report.is_valid
        assert report.exit_code == 0
        assert report.to_dict()["mode"] == "warn"

    def test_invalid_observed_command_syntax_is_reported(self) -> None:
        surface = CliSurface(
            root_flags=("--json",),
            groups=(),
            commands=(CommandSurface(path=("BadName",), policy=_policy_surface()),),
        )

        report = validate_surface(surface, CliSyntaxValidationConfig())

        assert not report.is_valid
        assert report.findings[0].code == "invalid_command_path"
        assert report.findings[0].path == ("BadName",)

    def test_config_rejects_invalid_declared_path(self) -> None:
        with pytest.raises(ValueError, match="valid command paths"):
            CliSyntaxValidationConfig(required_commands=("BadName",))
