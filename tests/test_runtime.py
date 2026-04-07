"""Tests for cli_core_yo.runtime and runtime_checks."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cli_core_yo import runtime_checks
from cli_core_yo.errors import ContextNotInitializedError
from cli_core_yo.runtime import RuntimeContext, _reset, get_context, initialize
from cli_core_yo.xdg import XdgPaths


def _spec() -> SimpleNamespace:
    return SimpleNamespace(name="test-spec")


def _paths(tmp_path: Path) -> XdgPaths:
    return XdgPaths(
        config=tmp_path / "config",
        data=tmp_path / "data",
        state=tmp_path / "state",
        cache=tmp_path / "cache",
    )


def _backend(name: str, kind: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        kind=kind,
        entry_guidance=f"use {name}",
        detect={},
        validation={},
    )


def _runtime_spec(
    backends: list[SimpleNamespace],
    *,
    default_backend: str | None = None,
    guard_mode: str = "enforced",
    allow_skip_check: bool = False,
    prereqs: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        supported_backends=backends,
        default_backend=default_backend,
        guard_mode=guard_mode,
        allow_skip_check=allow_skip_check,
        prereqs=list(prereqs or []),
    )


def _prereq(
    key: str,
    kind: str,
    value: object,
    *,
    severity: str = "error",
    applies_to_backends: set[str] | None = None,
    tags: set[str] | None = None,
    success_message: str | None = None,
    failure_message: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        key=key,
        kind=kind,
        value=value,
        severity=severity,
        applies_to_backends=set(applies_to_backends or set()),
        tags=set(tags or set()),
        success_message=success_message,
        failure_message=failure_message,
    )


class TestRuntimeContext:
    def teardown_method(self) -> None:
        _reset()

    def test_initialize_full_context(self, tmp_path: Path) -> None:
        ctx = initialize(
            _spec(),
            _paths(tmp_path),
            config_path=tmp_path / "config.json",
            json_mode=True,
            debug=True,
            no_color=True,
            invocation={"env": "dev", "profile": "local"},
            backend_name="conda",
            backend_kind="conda",
            runtime_guard_mode="advisory",
            runtime_check_skipped=True,
            dry_run=True,
        )

        assert isinstance(ctx, RuntimeContext)
        assert get_context() is ctx
        assert ctx.config_path == tmp_path / "config.json"
        assert ctx.json_mode is True
        assert ctx.debug is True
        assert ctx.no_color is True
        assert ctx.invocation == {"env": "dev", "profile": "local"}
        assert ctx.backend_name == "conda"
        assert ctx.backend_kind == "conda"
        assert ctx.runtime_guard_mode == "advisory"
        assert ctx.runtime_check_skipped is True
        assert ctx.dry_run is True

    def test_double_initialize_raises(self, tmp_path: Path) -> None:
        initialize(_spec(), _paths(tmp_path))
        with pytest.raises(RuntimeError, match="already initialized"):
            initialize(_spec(), _paths(tmp_path))

    def test_get_context_before_init_raises(self) -> None:
        with pytest.raises(ContextNotInitializedError):
            get_context()

    def test_reset_allows_reinit(self, tmp_path: Path) -> None:
        initialize(_spec(), _paths(tmp_path))
        _reset()
        ctx = initialize(_spec(), _paths(tmp_path))
        assert get_context() is ctx


class TestBackendDetection:
    def test_system_detection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "prefix", "/usr")
        monkeypatch.setattr(sys, "base_prefix", "/usr")
        monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)
        monkeypatch.delenv("CONDA_PREFIX", raising=False)
        assert runtime_checks.detect_backend_active("system")

    def test_venv_detection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "prefix", "/tmp/venv")
        monkeypatch.setattr(sys, "base_prefix", "/usr")
        monkeypatch.delenv("CONDA_PREFIX", raising=False)
        assert runtime_checks.detect_backend_active("venv")

    def test_conda_detection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CONDA_PREFIX", "/tmp/conda")
        assert runtime_checks.detect_backend_active("conda")

    @pytest.mark.parametrize(
        "kind, env_key",
        [
            ("docker", "container"),
            ("podman", "PODMAN_CONTAINER"),
            ("apptainer", "APPTAINER_CONTAINER"),
        ],
    )
    def test_container_detection(self, kind: str, env_key: str) -> None:
        assert runtime_checks.detect_backend_active(kind, env={env_key: "1"}) is True

    def test_unknown_backend_detection_is_false(self) -> None:
        assert runtime_checks.detect_backend_active("missing") is False


class TestBackendResolution:
    def test_supported_backends_returns_declared_backends(self) -> None:
        backends = [_backend("system", "system")]
        assert runtime_checks.supported_backends(_runtime_spec(backends)) == backends

    def test_backend_spec_by_name_none_returns_none(self) -> None:
        assert runtime_checks.backend_spec_by_name(_runtime_spec([]), None) is None

    def test_override_takes_precedence(self) -> None:
        spec = _runtime_spec([_backend("system", "system"), _backend("conda", "conda")])
        resolution = runtime_checks.resolve_backend(spec, backend_override="conda")
        assert resolution.backend_name == "conda"
        assert resolution.backend_kind == "conda"
        assert resolution.selected_by == "override"

    def test_default_backend_is_used(self) -> None:
        spec = _runtime_spec(
            [_backend("system", "system"), _backend("conda", "conda")],
            default_backend="conda",
        )
        resolution = runtime_checks.resolve_backend(spec)
        assert resolution.backend_name == "conda"
        assert resolution.selected_by == "default"

    def test_unknown_override_is_unresolved(self) -> None:
        spec = _runtime_spec([_backend("system", "system")])
        resolution = runtime_checks.resolve_backend(spec, backend_override="missing")
        assert resolution.selected_by == "unresolved"
        assert resolution.detail == "Unknown backend 'missing'."

    def test_no_backends_is_unresolved(self) -> None:
        resolution = runtime_checks.resolve_backend(_runtime_spec([]))
        assert resolution.selected_by == "unresolved"
        assert resolution.detail == "No backends were declared."

    def test_single_backend_is_used(self) -> None:
        resolution = runtime_checks.resolve_backend(_runtime_spec([_backend("system", "system")]))
        assert resolution.selected_by == "single"
        assert resolution.backend_name == "system"

    def test_heuristic_prefers_first_active_backend(self) -> None:
        spec = _runtime_spec([_backend("venv", "venv"), _backend("conda", "conda")])
        resolution = runtime_checks.resolve_backend(
            spec,
            env={"VIRTUAL_ENV": "/tmp/venv", "CONDA_PREFIX": "/tmp/conda"},
        )
        assert resolution.selected_by == "heuristic"
        assert resolution.backend_name == "venv"
        assert resolution.detected is True
        assert "Multiple backends matched" in str(resolution.detail)

    def test_heuristic_falls_back_when_nothing_is_detected(self) -> None:
        spec = _runtime_spec([_backend("conda", "conda"), _backend("docker", "docker")])
        resolution = runtime_checks.resolve_backend(spec, env={"UNUSED": "1"})
        assert resolution.selected_by == "heuristic"
        assert resolution.backend_name == "conda"
        assert resolution.detected is False
        assert "falling back to declaration order" in str(resolution.detail)


class TestPrereqs:
    def test_prereq_applies_respects_backend_and_tags(self) -> None:
        prereq = _prereq(
            "backend-tagged", "binary", "demo", applies_to_backends={"conda"}, tags={"runtime"}
        )

        assert (
            runtime_checks.prereq_applies(prereq, backend_name="conda", command_tags={"runtime"})
            is True
        )
        assert (
            runtime_checks.prereq_applies(prereq, backend_name="system", command_tags={"runtime"})
            is False
        )
        assert (
            runtime_checks.prereq_applies(prereq, backend_name="conda", command_tags={"other"})
            is False
        )
        assert (
            runtime_checks.prereq_applies(prereq, backend_name="conda", command_tags=None) is False
        )

    def test_evaluate_backend_validation_handles_none_and_missing_validation(self) -> None:
        assert runtime_checks.evaluate_backend_validation(None) == []
        assert (
            runtime_checks.evaluate_backend_validation(
                SimpleNamespace(name="system", validation=None)
            )
            == []
        )

    def test_evaluate_backend_validation_builds_checks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        backend_root = tmp_path / "backend"
        backend_root.mkdir()
        marker = backend_root / "marker.txt"
        marker.write_text("x", encoding="utf-8")

        monkeypatch.setenv("BACKEND_ENV", "1")
        monkeypatch.setattr(
            runtime_checks.shutil, "which", lambda command, path=None: f"/usr/bin/{command}"
        )
        monkeypatch.setattr(
            runtime_checks.subprocess,
            "run",
            lambda command, **kwargs: subprocess.CompletedProcess(
                command, 0, stdout="ok\n", stderr=""
            ),
        )

        backend = SimpleNamespace(
            name="system",
            validation=SimpleNamespace(
                env_vars=("BACKEND_ENV",),
                binaries=("python",),
                files=(str(marker), f"{backend_root}{os.sep}"),
                command_probe=("python", "--version"),
            ),
        )

        results = runtime_checks.evaluate_backend_validation(backend, cwd=tmp_path)

        assert [result.status for result in results] == ["pass", "pass", "pass", "pass", "pass"]
        assert results[2].key == f"system:file:{marker}"
        assert results[3].key.startswith("system:directory:")

    def test_prereq_filtering_and_results(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            runtime_checks.shutil,
            "which",
            lambda command, path=None: "/usr/bin/demo" if command == "demo" else None,
        )

        def fake_run(command, **kwargs):
            if command == ["probe-ok"]:
                return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="probe failed\n")

        monkeypatch.setattr(runtime_checks.subprocess, "run", fake_run)

        prereqs = [
            _prereq("binary-ok", "binary", "demo", tags={"runtime"}),
            _prereq("env-ok", "env_var", "DEMO_TOKEN", severity="warn"),
            _prereq("file-missing", "file", tmp_path / "missing.txt"),
            _prereq("skip-backend", "directory", tmp_path, applies_to_backends={"conda"}),
            _prereq("probe-ok", "command_probe", ("probe-ok",)),
            _prereq("import-ok", "python_import", "json"),
        ]

        monkeypatch.setenv("DEMO_TOKEN", "present")
        results = runtime_checks.evaluate_prereqs(
            prereqs,
            backend_name="system",
            command_tags={"runtime"},
            cwd=tmp_path,
        )

        by_key = {result.key: result for result in results}
        assert by_key["binary-ok"].status == "pass"
        assert by_key["env-ok"].status == "pass"
        assert by_key["file-missing"].status == "fail"
        assert by_key["skip-backend"].status == "skip"
        assert by_key["probe-ok"].status == "pass"
        assert by_key["import-ok"].status == "pass"

        summary = runtime_checks.summarize_prereq_results(results)
        assert summary["pass"] == 4
        assert summary["skip"] == 1
        assert summary["fail"] == 1
        assert summary["blocking_failures"] == 1

    def test_warn_severity_does_not_fail_hard(self, tmp_path: Path) -> None:
        prereq = _prereq("missing-optional", "file", tmp_path / "missing.txt", severity="warn")
        result = runtime_checks.evaluate_prereq(prereq, cwd=tmp_path)
        assert result.status == "warn"
        assert result.severity == "warn"

    def test_python_import_failure_returns_failed_result(self) -> None:
        result = runtime_checks.evaluate_prereq(
            _prereq("missing-import", "python_import", "definitely_missing_module")
        )
        assert result.status == "fail"
        assert "Python import failed" in result.summary

    def test_command_probe_failure_joins_stdout_and_stderr(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            runtime_checks.subprocess,
            "run",
            lambda command, **kwargs: subprocess.CompletedProcess(
                command, 1, stdout="out\n", stderr="err\n"
            ),
        )

        result = runtime_checks.evaluate_prereq(
            _prereq("probe-fail", "command_probe", ("demo", "--check")),
            cwd=tmp_path,
        )

        assert result.status == "fail"
        assert result.detail == "out\nerr"

    def test_command_probe_exception_is_reported(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        def raise_error(command, **kwargs):
            raise OSError("probe exploded")

        monkeypatch.setattr(runtime_checks.subprocess, "run", raise_error)

        result = runtime_checks.evaluate_prereq(
            _prereq("probe-error", "command_probe", ("demo",)),
            cwd=tmp_path,
        )

        assert result.status == "fail"
        assert result.detail == "probe exploded"

    def test_unsupported_prereq_kind_fails(self) -> None:
        prereq = SimpleNamespace(key="weird", kind="unknown", value="x", severity="error")
        result = runtime_checks.evaluate_prereq(prereq)
        assert result.status == "fail"
        assert "Unsupported prereq kind" in result.summary

    def test_prereq_report_payload_is_json_ready(self, tmp_path: Path) -> None:
        result = runtime_checks.PrereqResult(
            key="binary-ok",
            status="pass",
            severity="error",
            summary="Executable available",
            detail="/usr/bin/demo",
        )
        payload = runtime_checks.prereq_report_payload([result])
        assert payload["summary"]["pass"] == 1
        assert payload["results"][0]["key"] == "binary-ok"

    def test_prereq_report_helpers_cover_internal_conversion(self) -> None:
        result = runtime_checks.PrereqResult(
            key="optional",
            status="warn",
            severity="info",
            summary="Optional check missing",
            detail="not configured",
        )

        assert runtime_checks.prereq_result_as_dict(result)["key"] == "optional"
        assert runtime_checks._result_field({"key": "dict-key"}, "key") == "dict-key"
        assert runtime_checks._coerce_command("python -V") == ["python", "-V"]
        assert runtime_checks._coerce_command(42) == ["42"]
        assert runtime_checks._join_probe_output("out\n", "err\n") == "out\nerr"
        assert runtime_checks._join_probe_output("", "") is None
        assert runtime_checks._coerce_severity("not-valid") == "error"
