"""Tests for cli_core_yo.certs."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from cli_core_yo.certs import (
    CERT_FILENAME,
    KEY_FILENAME,
    ResolvedHttpsCerts,
    ca_installed,
    ca_root_path,
    cert_status,
    ensure_certs,
    install_ca,
    mkcert_available,
    resolve_https_certs,
    shared_dayhoff_certs_dir,
)


def _write_pair(certs_dir: Path) -> tuple[Path, Path]:
    cert_path = certs_dir / CERT_FILENAME
    key_path = certs_dir / KEY_FILENAME
    certs_dir.mkdir(parents=True, exist_ok=True)
    cert_path.write_text("cert", encoding="utf-8")
    key_path.write_text("key", encoding="utf-8")
    return cert_path, key_path


class TestSharedDayhoffCertsDir:
    def test_uses_xdg_state_home_when_present(self, tmp_path: Path):
        result = shared_dayhoff_certs_dir(
            "jemtest",
            env={"XDG_STATE_HOME": str(tmp_path / "state")},
        )
        assert result == tmp_path / "state" / "dayhoff" / "jemtest" / "certs"

    def test_falls_back_to_home_local_state(self, tmp_path: Path):
        result = shared_dayhoff_certs_dir("jemtest", env={}, home=tmp_path / "home")
        assert result == tmp_path / "home" / ".local" / "state" / "dayhoff" / "jemtest" / "certs"

    def test_empty_deploy_name_rejected(self):
        with pytest.raises(ValueError, match="deploy_name"):
            shared_dayhoff_certs_dir("  ")


class TestResolveHttpsCerts:
    def test_cli_paths_take_precedence_over_env(self, tmp_path: Path):
        cli_cert, cli_key = _write_pair(tmp_path / "cli")
        env_cert, env_key = _write_pair(tmp_path / "env")

        result = resolve_https_certs(
            cert_path=cli_cert,
            key_path=cli_key,
            env={
                "SSL_CERT_FILE": str(env_cert),
                "SSL_KEY_FILE": str(env_key),
            },
        )

        assert result == ResolvedHttpsCerts(cli_cert, cli_key, source="cli")

    def test_generic_env_used_when_cli_missing(self, tmp_path: Path):
        env_cert, env_key = _write_pair(tmp_path / "env")

        result = resolve_https_certs(
            env={
                "SSL_CERT_FILE": str(env_cert),
                "SSL_KEY_FILE": str(env_key),
            },
        )

        assert result == ResolvedHttpsCerts(env_cert, env_key, source="env")

    def test_shared_dir_beats_fallback_dir(self, tmp_path: Path):
        shared_cert, shared_key = _write_pair(tmp_path / "shared")
        _write_pair(tmp_path / "fallback")

        result = resolve_https_certs(
            shared_certs_dir=tmp_path / "shared",
            fallback_certs_dir=tmp_path / "fallback",
            generate_if_missing=False,
        )

        assert result == ResolvedHttpsCerts(shared_cert, shared_key, source="shared-dir")

    def test_fallback_dir_used_when_shared_missing(self, tmp_path: Path):
        fallback_cert, fallback_key = _write_pair(tmp_path / "fallback")

        result = resolve_https_certs(
            shared_certs_dir=tmp_path / "shared",
            fallback_certs_dir=tmp_path / "fallback",
            generate_if_missing=False,
        )

        assert result == ResolvedHttpsCerts(fallback_cert, fallback_key, source="fallback-dir")

    def test_generates_into_shared_dir_when_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        expected_cert = tmp_path / "shared" / CERT_FILENAME
        expected_key = tmp_path / "shared" / KEY_FILENAME

        def fake_ensure(
            certs_dir: Path,
            *,
            hosts: tuple[str, ...],
            force: bool = False,
        ) -> tuple[Path, Path]:
            assert certs_dir == tmp_path / "shared"
            assert hosts == ("localhost", "127.0.0.1", "::1")
            assert force is False
            return expected_cert, expected_key

        monkeypatch.setattr("cli_core_yo.certs.ensure_certs", fake_ensure)

        result = resolve_https_certs(shared_certs_dir=tmp_path / "shared")

        assert result == ResolvedHttpsCerts(expected_cert, expected_key, source="generated")

    def test_generation_uses_fallback_dir_when_shared_not_configured(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        expected_cert = tmp_path / "fallback" / CERT_FILENAME
        expected_key = tmp_path / "fallback" / KEY_FILENAME

        def fake_ensure(
            certs_dir: Path,
            *,
            hosts: tuple[str, ...],
            force: bool = False,
        ) -> tuple[Path, Path]:
            assert certs_dir == tmp_path / "fallback"
            return expected_cert, expected_key

        monkeypatch.setattr("cli_core_yo.certs.ensure_certs", fake_ensure)

        result = resolve_https_certs(fallback_certs_dir=tmp_path / "fallback")

        assert result == ResolvedHttpsCerts(expected_cert, expected_key, source="generated")

    def test_cli_requires_both_paths(self, tmp_path: Path):
        cert_path, _ = _write_pair(tmp_path / "cli")

        with pytest.raises(SystemExit, match="both cert and key"):
            resolve_https_certs(cert_path=cert_path)

    def test_generic_env_requires_both_paths(self, tmp_path: Path):
        cert_path, _ = _write_pair(tmp_path / "env")

        with pytest.raises(SystemExit, match="SSL_CERT_FILE"):
            resolve_https_certs(env={"SSL_CERT_FILE": str(cert_path)})

    def test_missing_explicit_cert_fails_clearly(self, tmp_path: Path):
        key_path = tmp_path / "missing-key.pem"
        key_path.write_text("key", encoding="utf-8")

        with pytest.raises(SystemExit, match="does not exist"):
            resolve_https_certs(
                cert_path=tmp_path / "missing-cert.pem",
                key_path=key_path,
            )

    def test_missing_sources_fail_without_generation(self, tmp_path: Path):
        with pytest.raises(SystemExit, match="HTTPS certificates were not found"):
            resolve_https_certs(
                shared_certs_dir=tmp_path / "shared",
                generate_if_missing=False,
            )

    def test_generation_without_configured_directory_fails_clearly(self):
        with pytest.raises(SystemExit, match="no certificate source was configured"):
            resolve_https_certs(generate_if_missing=True)

    def test_missing_explicit_key_fails_clearly(self, tmp_path: Path):
        cert_path = tmp_path / "cert.pem"
        cert_path.write_text("cert", encoding="utf-8")

        with pytest.raises(SystemExit, match="key file does not exist"):
            resolve_https_certs(
                cert_path=cert_path,
                key_path=tmp_path / "missing-key.pem",
            )


class TestMkcertHelpers:
    def test_mkcert_available_true_when_binary_found(self):
        with patch("cli_core_yo.certs.shutil.which", return_value="/usr/bin/mkcert"):
            assert mkcert_available() is True

    def test_mkcert_available_false_when_missing(self):
        with patch("cli_core_yo.certs.shutil.which", return_value=None):
            assert mkcert_available() is False

    def test_ca_installed_true_when_root_ca_exists(self, tmp_path: Path):
        ca_root = tmp_path / "ca-root"
        ca_root.mkdir()
        (ca_root / "rootCA.pem").write_text("pem", encoding="utf-8")

        completed = subprocess.CompletedProcess(
            args=["mkcert", "-CAROOT"],
            returncode=0,
            stdout=f"{ca_root}\n",
            stderr="",
        )
        with patch("cli_core_yo.certs.subprocess.run", return_value=completed):
            assert ca_installed() is True

    def test_ca_installed_false_on_nonzero_return(self):
        completed = subprocess.CompletedProcess(
            args=["mkcert", "-CAROOT"],
            returncode=1,
            stdout="",
            stderr="bad",
        )
        with patch("cli_core_yo.certs.subprocess.run", return_value=completed):
            assert ca_installed() is False

    def test_ca_installed_false_when_mkcert_missing(self):
        with patch("cli_core_yo.certs.subprocess.run", side_effect=FileNotFoundError):
            assert ca_installed() is False

    def test_ca_root_path_returns_path_on_success(self, tmp_path: Path):
        ca_root = tmp_path / "ca-root"
        completed = subprocess.CompletedProcess(
            args=["mkcert", "-CAROOT"],
            returncode=0,
            stdout=f"{ca_root}\n",
            stderr="",
        )
        with patch("cli_core_yo.certs.subprocess.run", return_value=completed):
            assert ca_root_path() == ca_root

    def test_ca_root_path_returns_none_on_failure(self):
        completed = subprocess.CompletedProcess(
            args=["mkcert", "-CAROOT"],
            returncode=1,
            stdout="",
            stderr="bad",
        )
        with patch("cli_core_yo.certs.subprocess.run", return_value=completed):
            assert ca_root_path() is None

    def test_install_ca_false_when_binary_missing(self):
        with patch("cli_core_yo.certs.shutil.which", return_value=None):
            assert install_ca() is False

    def test_install_ca_true_on_zero_exit(self):
        completed = subprocess.CompletedProcess(args=["mkcert", "-install"], returncode=0)
        with (
            patch("cli_core_yo.certs.shutil.which", return_value="/usr/bin/mkcert"),
            patch("cli_core_yo.certs.subprocess.run", return_value=completed),
        ):
            assert install_ca() is True


class TestEnsureCerts:
    def test_returns_existing_pair_without_generation(self, tmp_path: Path):
        cert_path, key_path = _write_pair(tmp_path / "certs")

        with patch("cli_core_yo.certs.shutil.which") as mock_which:
            result = ensure_certs(tmp_path / "certs")

        assert result == (cert_path, key_path)
        mock_which.assert_not_called()

    def test_raises_when_mkcert_missing(self, tmp_path: Path):
        with patch("cli_core_yo.certs.shutil.which", return_value=None):
            with pytest.raises(SystemExit, match="mkcert is required"):
                ensure_certs(tmp_path / "certs")

    def test_raises_when_mkcert_generation_fails(self, tmp_path: Path):
        install_result = subprocess.CompletedProcess(args=["mkcert", "-install"], returncode=0)
        generation_error = subprocess.CalledProcessError(
            1,
            ["mkcert"],
            stderr="generation failed",
        )

        with (
            patch("cli_core_yo.certs.shutil.which", return_value="/usr/bin/mkcert"),
            patch(
                "cli_core_yo.certs.subprocess.run",
                side_effect=[install_result, generation_error],
            ),
        ):
            with pytest.raises(SystemExit, match="generation failed"):
                ensure_certs(tmp_path / "certs")

    def test_raises_when_mkcert_does_not_create_files(self, tmp_path: Path):
        install_result = subprocess.CompletedProcess(args=["mkcert", "-install"], returncode=0)
        generation_result = subprocess.CompletedProcess(args=["mkcert"], returncode=0)

        with (
            patch("cli_core_yo.certs.shutil.which", return_value="/usr/bin/mkcert"),
            patch(
                "cli_core_yo.certs.subprocess.run",
                side_effect=[install_result, generation_result],
            ),
        ):
            with pytest.raises(SystemExit, match="did not produce"):
                ensure_certs(tmp_path / "certs")

    def test_generates_and_returns_cert_pair(self, tmp_path: Path):
        certs_dir = tmp_path / "certs"
        cert_path = certs_dir / CERT_FILENAME
        key_path = certs_dir / KEY_FILENAME

        def fake_run(args, **kwargs):
            if "-cert-file" in args and "-key-file" in args:
                cert_path.write_text("cert", encoding="utf-8")
                key_path.write_text("key", encoding="utf-8")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        with (
            patch("cli_core_yo.certs.shutil.which", return_value="/usr/bin/mkcert"),
            patch("cli_core_yo.certs.subprocess.run", side_effect=fake_run),
        ):
            result = ensure_certs(certs_dir)

        assert result == (cert_path, key_path)
        assert cert_path.exists()
        assert key_path.exists()


class TestCertStatus:
    def test_reports_readiness_and_paths(self, tmp_path: Path):
        certs_dir = tmp_path / "certs"
        cert_path, key_path = _write_pair(certs_dir)

        with (
            patch("cli_core_yo.certs.mkcert_available", return_value=True),
            patch("cli_core_yo.certs.ca_installed", return_value=False),
            patch("cli_core_yo.certs.ca_root_path", return_value=tmp_path / "ca-root"),
        ):
            status = cert_status(certs_dir)

        assert status == {
            "mkcert_installed": True,
            "ca_installed": False,
            "ca_root": str(tmp_path / "ca-root"),
            "cert_exists": True,
            "key_exists": True,
            "cert_path": str(cert_path),
            "key_path": str(key_path),
        }
