"""Deterministic backend and prerequisite helpers for v2 runtime enforcement."""

from __future__ import annotations

import importlib
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Literal, Mapping, cast

from cli_core_yo.spec import PrereqResult

Severity = Literal["error", "warn", "info"]
Status = Literal["pass", "warn", "fail", "skip"]


@dataclass(frozen=True)
class BackendResolution:
    """Resolved backend metadata for the current invocation."""

    backend_name: str | None
    backend_kind: str | None
    backend_spec: Any | None
    selected_by: Literal["override", "default", "single", "heuristic", "unresolved"]
    detected: bool = False
    detail: str | None = None


def supported_backends(runtime_spec: Any) -> list[Any]:
    """Return the declared backend specs in deterministic order."""
    return list(getattr(runtime_spec, "supported_backends", []) or [])


def backend_spec_by_name(runtime_spec: Any, backend_name: str | None) -> Any | None:
    """Return a backend spec by name, or ``None`` when not found."""
    if backend_name is None:
        return None
    for backend in supported_backends(runtime_spec):
        if getattr(backend, "name", None) == backend_name:
            return backend
    return None


def detect_backend_active(kind: str | None, *, env: Mapping[str, str] | None = None) -> bool:
    """Return ``True`` when the runtime heuristics suggest an active backend."""
    env_map = env or os.environ
    if kind == "conda":
        return bool(env_map.get("CONDA_PREFIX"))
    if kind == "venv":
        return bool(env_map.get("VIRTUAL_ENV")) or sys.prefix != sys.base_prefix
    if kind == "system":
        return not env_map.get("CONDA_PREFIX") and not env_map.get("VIRTUAL_ENV") and (
            sys.prefix == sys.base_prefix
        )
    if kind in {"docker", "podman", "apptainer"}:
        return bool(
            env_map.get("container")
            or env_map.get("DOCKER_CONTAINER")
            or env_map.get("PODMAN_CONTAINER")
            or env_map.get("APPTAINER_CONTAINER")
        )
    return False


def resolve_backend(
    runtime_spec: Any,
    *,
    backend_override: str | None = None,
    env: Mapping[str, str] | None = None,
) -> BackendResolution:
    """Resolve the effective backend for the current invocation."""
    backends = supported_backends(runtime_spec)
    if not backends:
        return BackendResolution(
            backend_name=None,
            backend_kind=None,
            backend_spec=None,
            selected_by="unresolved",
            detected=False,
            detail="No backends were declared.",
        )

    if backend_override is not None:
        backend = backend_spec_by_name(runtime_spec, backend_override)
        if backend is None:
            return BackendResolution(
                backend_name=backend_override,
                backend_kind=None,
                backend_spec=None,
                selected_by="unresolved",
                detected=False,
                detail=f"Unknown backend '{backend_override}'.",
            )
        return BackendResolution(
            backend_name=getattr(backend, "name", None),
            backend_kind=getattr(backend, "kind", None),
            backend_spec=backend,
            selected_by="override",
            detected=detect_backend_active(getattr(backend, "kind", None), env=env),
        )

    default_backend = getattr(runtime_spec, "default_backend", None)
    if default_backend is not None:
        backend = backend_spec_by_name(runtime_spec, default_backend)
        if backend is not None:
            return BackendResolution(
                backend_name=getattr(backend, "name", None),
                backend_kind=getattr(backend, "kind", None),
                backend_spec=backend,
                selected_by="default",
                detected=detect_backend_active(getattr(backend, "kind", None), env=env),
            )

    if len(backends) == 1:
        backend = backends[0]
        return BackendResolution(
            backend_name=getattr(backend, "name", None),
            backend_kind=getattr(backend, "kind", None),
            backend_spec=backend,
            selected_by="single",
            detected=detect_backend_active(getattr(backend, "kind", None), env=env),
        )

    active_backends = [
        backend
        for backend in backends
        if detect_backend_active(getattr(backend, "kind", None), env=env)
    ]
    if active_backends:
        backend = active_backends[0]
        detail = None
        if len(active_backends) > 1:
            detail = "Multiple backends matched; using the first supported backend."
        return BackendResolution(
            backend_name=getattr(backend, "name", None),
            backend_kind=getattr(backend, "kind", None),
            backend_spec=backend,
            selected_by="heuristic",
            detected=True,
            detail=detail,
        )

    backend = backends[0]
    return BackendResolution(
        backend_name=getattr(backend, "name", None),
        backend_kind=getattr(backend, "kind", None),
        backend_spec=backend,
        selected_by="heuristic",
        detected=False,
        detail="No active backend was detected; falling back to declaration order.",
    )


def prereq_applies(
    prereq: Any,
    *,
    backend_name: str | None = None,
    command_tags: Iterable[str] | None = None,
) -> bool:
    """Return ``True`` when a prereq should be evaluated for this invocation."""
    backend_filters = set(getattr(prereq, "applies_to_backends", set()) or set())
    if backend_filters and backend_name not in backend_filters:
        return False

    prereq_tags = set(getattr(prereq, "tags", set()) or set())
    command_tags_set = set(command_tags or ())
    if not prereq_tags:
        return True
    if not command_tags_set:
        return False
    return not prereq_tags.isdisjoint(command_tags_set)


def evaluate_backend_validation(
    backend_spec: Any | None,
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> list[PrereqResult]:
    """Evaluate a backend's validation hints as prereq-like checks."""
    if backend_spec is None:
        return []

    validation = getattr(backend_spec, "validation", None)
    if validation is None:
        return []

    prereqs: list[SimpleNamespace] = []
    backend_name = getattr(backend_spec, "name", "backend")
    for item in getattr(validation, "env_vars", ()) or ():
        prereqs.append(
            SimpleNamespace(
                key=f"{backend_name}:env:{item}",
                kind="env_var",
                value=item,
                severity="error",
                success_message=f"Backend env var present: {item}",
                failure_message=f"Backend env var missing: {item}",
            )
        )
    for item in getattr(validation, "binaries", ()) or ():
        prereqs.append(
            SimpleNamespace(
                key=f"{backend_name}:binary:{item}",
                kind="binary",
                value=item,
                severity="error",
                success_message=f"Backend executable available: {item}",
                failure_message=f"Backend executable not found: {item}",
            )
        )
    for item in getattr(validation, "files", ()) or ():
        kind = "directory" if str(item).endswith(("/", os.sep)) else "file"
        prereqs.append(
            SimpleNamespace(
                key=f"{backend_name}:{kind}:{item}",
                kind=kind,
                value=str(item).rstrip("/"),
                severity="error",
                success_message=f"Backend path exists: {item}",
                failure_message=f"Backend path missing: {item}",
            )
        )
    if getattr(validation, "command_probe", ()) or ():
        prereqs.append(
            SimpleNamespace(
                key=f"{backend_name}:probe",
                kind="command_probe",
                value=tuple(getattr(validation, "command_probe", ()) or ()),
                severity="error",
                success_message=f"Backend probe passed for {backend_name}",
                failure_message=f"Backend probe failed for {backend_name}",
            )
        )

    return [evaluate_prereq(prereq, env=env, cwd=cwd) for prereq in prereqs]


def evaluate_prereq(
    prereq: Any,
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> PrereqResult:
    """Evaluate one prereq spec and return a deterministic result."""
    kind = getattr(prereq, "kind", None)
    value = getattr(prereq, "value", None)
    severity = _coerce_severity(getattr(prereq, "severity", "error"))
    key = getattr(prereq, "key", "unknown")
    success_message = getattr(prereq, "success_message", None)
    failure_message = getattr(prereq, "failure_message", None)

    if kind == "binary":
        command = str(value)
        path_value = None if env is None else env.get("PATH")
        found = shutil.which(command, path=path_value)
        if found:
            return _make_prereq_result(
                key=key,
                status="pass",
                severity=severity,
                summary=success_message or f"Executable available: {command}",
                detail=found,
            )
        return _fail_result(
            key=key,
            severity=severity,
            summary=failure_message or f"Executable not found: {command}",
            detail="Not on PATH",
        )

    if kind == "python_import":
        module_name = str(value)
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            return _fail_result(
                key=key,
                severity=severity,
                summary=failure_message or f"Python import failed: {module_name}",
                detail=str(exc),
            )
        return _make_prereq_result(
            key=key,
            status="pass",
            severity=severity,
            summary=success_message or f"Python import available: {module_name}",
            detail=None,
        )

    env_map = env or os.environ
    if kind == "env_var":
        env_name = str(value)
        if env_name in env_map and env_map.get(env_name):
            return _make_prereq_result(
                key=key,
                status="pass",
                severity=severity,
                summary=success_message or f"Environment variable present: {env_name}",
                detail=env_map.get(env_name),
            )
        return _fail_result(
            key=key,
            severity=severity,
            summary=failure_message or f"Environment variable missing: {env_name}",
            detail=None,
        )

    if kind == "file":
        path = Path(str(value)).expanduser()
        if path.exists() and path.is_file():
            return _make_prereq_result(
                key=key,
                status="pass",
                severity=severity,
                summary=success_message or f"File exists: {path}",
                detail=str(path),
            )
        return _fail_result(
            key=key,
            severity=severity,
            summary=failure_message or f"File missing: {path}",
            detail=str(path),
        )

    if kind == "directory":
        path = Path(str(value)).expanduser()
        if path.exists() and path.is_dir():
            return _make_prereq_result(
                key=key,
                status="pass",
                severity=severity,
                summary=success_message or f"Directory exists: {path}",
                detail=str(path),
            )
        return _fail_result(
            key=key,
            severity=severity,
            summary=failure_message or f"Directory missing: {path}",
            detail=str(path),
        )

    if kind == "command_probe":
        command_argv = _coerce_command(value)
        try:
            completed = subprocess.run(
                command_argv,
                cwd=cwd,
                env=dict(env_map),
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            return _fail_result(
                key=key,
                severity=severity,
                summary=failure_message or f"Command probe failed: {' '.join(command_argv)}",
                detail=str(exc),
            )

        if completed.returncode == 0:
            detail = (completed.stdout or "").strip() or None
            return _make_prereq_result(
                key=key,
                status="pass",
                severity=severity,
                summary=success_message or f"Command probe passed: {' '.join(command_argv)}",
                detail=detail,
            )

        detail = _join_probe_output(completed.stdout, completed.stderr)
        return _fail_result(
            key=key,
            severity=severity,
            summary=failure_message or f"Command probe failed: {' '.join(command_argv)}",
            detail=detail,
        )

    return _fail_result(
        key=key,
        severity=severity,
        summary=failure_message or f"Unsupported prereq kind: {kind}",
        detail=None,
    )


def evaluate_prereqs(
    prereqs: Iterable[Any],
    *,
    backend_name: str | None = None,
    command_tags: Iterable[str] | None = None,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> list[PrereqResult]:
    """Evaluate all prereqs that apply to this invocation."""
    results: list[PrereqResult] = []
    for prereq in prereqs:
        if prereq_applies(prereq, backend_name=backend_name, command_tags=command_tags):
            results.append(evaluate_prereq(prereq, env=env, cwd=cwd))
            continue
        results.append(
            _make_prereq_result(
                key=getattr(prereq, "key", "unknown"),
                status="skip",
                severity=_coerce_severity(getattr(prereq, "severity", "error")),
                summary="Skipped by backend/tag filter.",
                detail=None,
            )
        )
    return results


def summarize_prereq_results(results: Iterable[Any]) -> dict[str, int]:
    """Return deterministic prereq counts for reporting."""
    counts = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
    for result in results:
        status = _result_field(result, "status")
        if status in counts:
            counts[status] += 1
    counts["total"] = sum(counts.values())
    counts["blocking_failures"] = sum(
        1
        for result in results
        if _result_field(result, "status") == "fail"
        and _result_field(result, "severity") == "error"
    )
    return counts


def prereq_report_payload(results: Iterable[Any]) -> dict[str, Any]:
    """Return a JSON-ready prereq report payload."""
    results_list = [prereq_result_as_dict(result) for result in results]
    return {
        "results": results_list,
        "summary": summarize_prereq_results(results_list),
    }


def prereq_result_as_dict(result: Any) -> dict[str, Any]:
    """Convert a prereq result-like object into a JSON-safe mapping."""
    return {
        "key": _result_field(result, "key"),
        "status": _result_field(result, "status"),
        "severity": _result_field(result, "severity"),
        "summary": _result_field(result, "summary"),
        "detail": _result_field(result, "detail"),
    }


def _coerce_command(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    if isinstance(value, str):
        return shlex.split(value)
    return [str(value)]


def _join_probe_output(stdout: str | None, stderr: str | None) -> str | None:
    text = "\n".join(
        part.strip() for part in (stdout or "", stderr or "") if part and part.strip()
    )
    return text or None


def _result_field(result: Any, name: str) -> Any:
    if isinstance(result, dict):
        return result.get(name)
    return getattr(result, name, None)


def _make_prereq_result(
    *,
    key: str,
    status: Status,
    severity: Severity,
    summary: str,
    detail: str | None,
) -> PrereqResult:
    return PrereqResult(
        key=key,
        status=status,
        severity=severity,
        summary=summary,
        detail=detail,
    )


def _fail_result(
    *,
    key: str,
    severity: Severity,
    summary: str,
    detail: str | None,
) -> PrereqResult:
    status: Status = "fail" if severity == "error" else "warn"
    return _make_prereq_result(
        key=key,
        status=status,
        severity=severity,
        summary=summary,
        detail=detail,
    )


def _coerce_severity(value: Any) -> Severity:
    if value in {"error", "warn", "info"}:
        return cast(Severity, value)
    return "error"
