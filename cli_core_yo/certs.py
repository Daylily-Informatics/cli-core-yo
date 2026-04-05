"""Shared TLS certificate management utilities for CLI services.

Provides reusable helpers for mkcert-based localhost certificate
generation using the standardized ``cert.pem`` / ``key.pem`` naming.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

# Standardized certificate file names (ecosystem-wide convention).
CERT_FILENAME = "cert.pem"
KEY_FILENAME = "key.pem"


# -- mkcert checks --------------------------------------------------------------


def mkcert_available() -> bool:
    """Return True if ``mkcert`` is on PATH."""
    return shutil.which("mkcert") is not None


def ca_installed() -> bool:
    """Return True if the mkcert local CA root certificate exists."""
    try:
        result = subprocess.run(
            ["mkcert", "-CAROOT"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        ca_root = Path(result.stdout.strip())
        return (ca_root / "rootCA.pem").exists()
    except FileNotFoundError:
        return False


def ca_root_path() -> Path | None:
    """Return the CA root directory, or None if unavailable."""
    try:
        result = subprocess.run(
            ["mkcert", "-CAROOT"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except FileNotFoundError:
        pass
    return None


# -- Certificate lifecycle -------------------------------------------------------


def install_ca() -> bool:
    """Install the mkcert local CA (idempotent). Returns success."""
    mkcert_bin = shutil.which("mkcert")
    if not mkcert_bin:
        return False
    result = subprocess.run([mkcert_bin, "-install"])
    return result.returncode == 0


def ensure_certs(
    certs_dir: Path,
    *,
    hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "::1"),
    force: bool = False,
) -> tuple[Path, Path]:
    """Ensure ``cert.pem`` and ``key.pem`` exist in *certs_dir*.

    Auto-generates them via ``mkcert`` if missing (or if *force* is True).
    Raises ``SystemExit(1)`` on failure.

    Returns ``(cert_path, key_path)``.
    """
    certs_dir.mkdir(parents=True, exist_ok=True)
    cert_file = certs_dir / CERT_FILENAME
    key_file = certs_dir / KEY_FILENAME

    if cert_file.exists() and key_file.exists() and not force:
        return cert_file, key_file

    mkcert_bin = shutil.which("mkcert")
    if not mkcert_bin:
        raise SystemExit(
            "mkcert is required to generate localhost HTTPS certificates. Install it and retry."
        )

    # Install local CA (idempotent)
    subprocess.run(
        [mkcert_bin, "-install"],
        check=False,
        capture_output=True,
        text=True,
    )

    try:
        subprocess.run(
            [
                mkcert_bin,
                "-cert-file",
                str(cert_file),
                "-key-file",
                str(key_file),
                *hosts,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise SystemExit(f"Failed to generate HTTPS certificates with mkcert: {stderr}")

    if not (cert_file.exists() and key_file.exists()):
        raise SystemExit(f"mkcert did not produce {CERT_FILENAME}/{KEY_FILENAME} in {certs_dir}")
    return cert_file, key_file


@dataclass(frozen=True)
class ResolvedHttpsCerts:
    """Resolved HTTPS certificate paths and their source."""

    cert_path: Path
    key_path: Path
    source: str


def shared_dayhoff_certs_dir(
    deploy_name: str,
    *,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the shared Dayhoff deployment-scoped certificate directory."""
    if not deploy_name.strip():
        raise ValueError("deploy_name must not be empty")
    env_map = os.environ if env is None else env
    if state_home := env_map.get("XDG_STATE_HOME", "").strip():
        state_base = Path(state_home)
    else:
        state_base = (Path.home() if home is None else home) / ".local" / "state"
    return state_base / "dayhoff" / deploy_name / "certs"


def resolve_https_certs(
    *,
    cert_path: str | Path | None = None,
    key_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    shared_certs_dir: str | Path | None = None,
    fallback_certs_dir: str | Path | None = None,
    hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "::1"),
    generate_if_missing: bool = True,
) -> ResolvedHttpsCerts:
    """Resolve HTTPS cert/key paths using the shared precedence contract.

    Resolution order:
    1. Explicit ``cert_path`` / ``key_path``
    2. Generic env ``SSL_CERT_FILE`` / ``SSL_KEY_FILE``
    3. Existing files in ``shared_certs_dir``
    4. Existing files in ``fallback_certs_dir``
    5. Optional mkcert generation, preferring ``shared_certs_dir``
    """
    env_map = os.environ if env is None else env
    resolved = _resolve_explicit_pair(cert_path, key_path, source="CLI flags")
    if resolved is not None:
        return _validated_paths(*resolved, source="cli")

    resolved = _resolve_env_pair(
        env_map,
        cert_env_vars=("SSL_CERT_FILE",),
        key_env_vars=("SSL_KEY_FILE",),
        source="generic SSL env",
    )
    if resolved is not None:
        return _validated_paths(*resolved, source="env")

    shared_dir = Path(shared_certs_dir).expanduser() if shared_certs_dir else None
    if shared_dir is not None:
        existing = _existing_cert_pair(shared_dir)
        if existing is not None:
            return ResolvedHttpsCerts(*existing, source="shared-dir")

    fallback_dir = Path(fallback_certs_dir).expanduser() if fallback_certs_dir else None
    if fallback_dir is not None:
        existing = _existing_cert_pair(fallback_dir)
        if existing is not None:
            return ResolvedHttpsCerts(*existing, source="fallback-dir")

    if generate_if_missing:
        generation_dir = shared_dir or fallback_dir
        if generation_dir is None:
            raise SystemExit(
                "HTTPS is enabled but no certificate source was configured. "
                "Provide --cert/--key, set SSL_CERT_FILE and SSL_KEY_FILE, "
                "or configure a shared certificate directory."
            )
        cert_file, key_file = ensure_certs(generation_dir, hosts=hosts)
        return ResolvedHttpsCerts(cert_file, key_file, source="generated")

    raise SystemExit(
        "HTTPS certificates were not found. Provide --cert/--key, "
        "set SSL_CERT_FILE and SSL_KEY_FILE, or place cert.pem/key.pem "
        f"in {shared_dir or fallback_dir}."
    )


def _resolve_explicit_pair(
    cert_path: str | Path | None,
    key_path: str | Path | None,
    *,
    source: str,
) -> tuple[Path, Path] | None:
    if cert_path is None and key_path is None:
        return None
    if cert_path is None or key_path is None:
        raise SystemExit(f"{source} must provide both cert and key paths.")
    return Path(cert_path).expanduser(), Path(key_path).expanduser()


def _resolve_env_pair(
    env: Mapping[str, str],
    *,
    cert_env_vars: tuple[str, ...],
    key_env_vars: tuple[str, ...],
    source: str,
) -> tuple[Path, Path] | None:
    cert_value = _first_env_value(env, cert_env_vars)
    key_value = _first_env_value(env, key_env_vars)
    if cert_value is None and key_value is None:
        return None
    if cert_value is None or key_value is None:
        cert_names = ", ".join(cert_env_vars) or "<none>"
        key_names = ", ".join(key_env_vars) or "<none>"
        raise SystemExit(
            f"{source} must provide both a cert path ({cert_names}) and a key path ({key_names})."
        )
    return Path(cert_value).expanduser(), Path(key_value).expanduser()


def _first_env_value(env: Mapping[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        value = env.get(name, "").strip()
        if value:
            return value
    return None


def _existing_cert_pair(certs_dir: Path) -> tuple[Path, Path] | None:
    cert_file = certs_dir / CERT_FILENAME
    key_file = certs_dir / KEY_FILENAME
    if cert_file.exists() and key_file.exists():
        return cert_file, key_file
    return None


def _validated_paths(cert_path: Path, key_path: Path, *, source: str) -> ResolvedHttpsCerts:
    if not cert_path.exists():
        raise SystemExit(f"HTTPS cert file does not exist: {cert_path}")
    if not key_path.exists():
        raise SystemExit(f"HTTPS key file does not exist: {key_path}")
    return ResolvedHttpsCerts(cert_path, key_path, source=source)


def cert_status(certs_dir: Path) -> dict[str, bool | str | None]:
    """Return a dict describing certificate readiness.

    Keys: ``mkcert_installed``, ``ca_installed``, ``ca_root``,
    ``cert_exists``, ``key_exists``, ``cert_path``, ``key_path``.
    """
    cert_file = certs_dir / CERT_FILENAME
    key_file = certs_dir / KEY_FILENAME
    ca = ca_root_path()
    return {
        "mkcert_installed": mkcert_available(),
        "ca_installed": ca_installed(),
        "ca_root": str(ca) if ca else None,
        "cert_exists": cert_file.exists(),
        "key_exists": key_file.exists(),
        "cert_path": str(cert_file),
        "key_path": str(key_file),
    }
