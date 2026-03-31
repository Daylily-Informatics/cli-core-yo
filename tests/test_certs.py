"""Tests for cli_core_yo.certs."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli_core_yo.certs import (
    CERT_FILENAME,
    KEY_FILENAME,
    ResolvedHttpsCerts,
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

    def test_legacy_env_used_when_generic_env_missing(self, tmp_path: Path):
        legacy_cert, legacy_key = _write_pair(tmp_path / "legacy")

        result = resolve_https_certs(
            env={
                "URSA_SSL_CERT_FILE": str(legacy_cert),
                "URSA_SSL_KEY_FILE": str(legacy_key),
            },
            legacy_cert_env_vars=("URSA_SSL_CERT_FILE",),
            legacy_key_env_vars=("URSA_SSL_KEY_FILE",),
        )

        assert result == ResolvedHttpsCerts(legacy_cert, legacy_key, source="legacy-env")

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

    def test_legacy_env_requires_both_paths(self, tmp_path: Path):
        cert_path, _ = _write_pair(tmp_path / "legacy")

        with pytest.raises(SystemExit, match="URSA_SSL_CERT_FILE"):
            resolve_https_certs(
                env={"URSA_SSL_CERT_FILE": str(cert_path)},
                legacy_cert_env_vars=("URSA_SSL_CERT_FILE",),
                legacy_key_env_vars=("URSA_SSL_KEY_FILE",),
            )

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
