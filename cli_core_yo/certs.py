"""Shared TLS certificate management utilities for CLI services.

Provides reusable helpers for mkcert-based localhost certificate
generation using the standardized ``cert.pem`` / ``key.pem`` naming.
"""

from __future__ import annotations

import shutil
import subprocess
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
            "mkcert is required to generate localhost HTTPS certificates. "
            "Install it and retry."
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
                "-cert-file", str(cert_file),
                "-key-file", str(key_file),
                *hosts,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise SystemExit(
            f"Failed to generate HTTPS certificates with mkcert: {stderr}"
        )

    if not (cert_file.exists() and key_file.exists()):
        raise SystemExit(
            f"mkcert did not produce {CERT_FILENAME}/{KEY_FILENAME} in {certs_dir}"
        )
    return cert_file, key_file


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
