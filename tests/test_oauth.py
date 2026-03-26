"""Tests for cli_core_yo.oauth — pure URI validation helpers."""

from __future__ import annotations

import pytest

from cli_core_yo.oauth import (
    default_port_for_scheme,
    is_local_oauth_uri,
    normalize_uri,
    runtime_oauth_host,
    uri_port,
    validate_cognito_app_client,
    validate_uri_list_ports,
)


# -- runtime_oauth_host -------------------------------------------------------


class TestRuntimeOAuthHost:
    def test_bind_all_ipv4_maps_to_localhost(self):
        assert runtime_oauth_host("0.0.0.0") == "localhost"

    def test_bind_all_ipv6_maps_to_localhost(self):
        assert runtime_oauth_host("::") == "localhost"

    def test_explicit_host_passes_through(self):
        assert runtime_oauth_host("example.com") == "example.com"

    def test_localhost_passes_through(self):
        assert runtime_oauth_host("localhost") == "localhost"


# -- default_port_for_scheme ---------------------------------------------------


class TestDefaultPortForScheme:
    def test_https(self):
        assert default_port_for_scheme("https") == 443

    def test_http(self):
        assert default_port_for_scheme("http") == 80

    def test_unknown_returns_none(self):
        assert default_port_for_scheme("ftp") is None
        assert default_port_for_scheme("") is None


# -- normalize_uri -------------------------------------------------------------


class TestNormalizeUri:
    def test_strips_trailing_slash(self):
        assert normalize_uri("https://host/path/") == "https://host/path"

    def test_strips_fragment(self):
        assert normalize_uri("https://host/path#frag") == "https://host/path"

    def test_strips_query(self):
        assert normalize_uri("https://host/path?q=1") == "https://host/path"

    def test_preserves_root_slash(self):
        assert normalize_uri("https://host/") == "https://host/"

    def test_strips_whitespace(self):
        assert normalize_uri("  https://host/path  ") == "https://host/path"


# -- uri_port ------------------------------------------------------------------


class TestUriPort:
    def test_explicit_port(self):
        assert uri_port("https://host:8912/path") == 8912

    def test_implicit_https(self):
        assert uri_port("https://host/path") == 443

    def test_implicit_http(self):
        assert uri_port("http://host/path") == 80

    def test_invalid_returns_none(self):
        assert uri_port("notaurl") is None

    def test_ftp_no_port(self):
        assert uri_port("ftp://host/path") is None


# -- is_local_oauth_uri --------------------------------------------------------


class TestIsLocalOAuthUri:
    def test_localhost(self):
        assert is_local_oauth_uri("https://localhost:8912/cb", "localhost") is True

    def test_loopback_ipv4(self):
        assert is_local_oauth_uri("https://127.0.0.1:8912/cb", "localhost") is True

    def test_bind_all(self):
        assert is_local_oauth_uri("https://0.0.0.0:8912/cb", "localhost") is True

    def test_remote(self):
        assert is_local_oauth_uri("https://example.com/cb", "localhost") is False

    def test_matches_runtime_host(self):
        assert is_local_oauth_uri("https://myhost:8912/cb", "myhost") is True


# -- validate_uri_list_ports ---------------------------------------------------


class TestValidateUriListPorts:
    def test_valid_local_uris_no_errors(self):
        errors = validate_uri_list_ports(
            uris=["https://localhost:8912/auth/callback"],
            label="CallbackURLs",
            expected_port=8912,
            runtime_host="localhost",
        )
        assert errors == []

    def test_invalid_uri_flagged(self):
        errors = validate_uri_list_ports(
            uris=["notaurl"], label="Test", expected_port=80, runtime_host="localhost"
        )
        assert any("invalid URI" in e for e in errors)

    def test_unsupported_scheme_flagged(self):
        errors = validate_uri_list_ports(
            uris=["ftp://localhost/path"], label="Test",
            expected_port=80, runtime_host="localhost",
        )


# -- validate_cognito_app_client -----------------------------------------------


def _make_app_client(
    name: str = "myapp",
    oauth_enabled: bool = True,
    callbacks: list[str] | None = None,
    logouts: list[str] | None = None,
    default_redirect: str = "",
) -> dict:
    return {
        "ClientName": name,
        "AllowedOAuthFlowsUserPoolClient": oauth_enabled,
        "CallbackURLs": ["https://localhost:8912/auth/callback"] if callbacks is None else callbacks,
        "LogoutURLs": ["https://localhost:8912/"] if logouts is None else logouts,
        "DefaultRedirectURI": default_redirect,
    }


class TestValidateCognitoAppClient:
    def test_valid_config_no_errors(self):
        errors = validate_cognito_app_client(
            app_client=_make_app_client(),
            expected_callback_url="https://localhost:8912/auth/callback",
            expected_logout_url="https://localhost:8912/",
            expected_port=8912,
            runtime_host="localhost",
            expected_client_name="myapp",
        )
        assert errors == []

    def test_name_mismatch(self):
        errors = validate_cognito_app_client(
            app_client=_make_app_client(name="wrong"),
            expected_callback_url="https://localhost:8912/auth/callback",
            expected_logout_url="https://localhost:8912/",
            expected_port=8912,
            runtime_host="localhost",
            expected_client_name="myapp",
        )
        assert any("name mismatch" in e for e in errors)

    def test_oauth_not_enabled(self):
        errors = validate_cognito_app_client(
            app_client=_make_app_client(oauth_enabled=False),
            expected_callback_url="https://localhost:8912/auth/callback",
            expected_logout_url="https://localhost:8912/",
            expected_port=8912,
            runtime_host="localhost",
            expected_client_name="myapp",
        )
        assert any("OAuth2 flows enabled" in e for e in errors)

    def test_missing_callback_url(self):
        errors = validate_cognito_app_client(
            app_client=_make_app_client(callbacks=["https://localhost:8912/other"]),
            expected_callback_url="https://localhost:8912/auth/callback",
            expected_logout_url="https://localhost:8912/",
            expected_port=8912,
            runtime_host="localhost",
            expected_client_name="myapp",
        )
        assert any("Expected callback URI" in e for e in errors)

    def test_missing_logout_url(self):
        errors = validate_cognito_app_client(
            app_client=_make_app_client(logouts=["https://localhost:8912/other"]),
            expected_callback_url="https://localhost:8912/auth/callback",
            expected_logout_url="https://localhost:8912/",
            expected_port=8912,
            runtime_host="localhost",
            expected_client_name="myapp",
        )
        assert any("Expected logout URI" in e for e in errors)

    def test_no_callbacks_at_all(self):
        errors = validate_cognito_app_client(
            app_client=_make_app_client(callbacks=[]),
            expected_callback_url="https://localhost:8912/auth/callback",
            expected_logout_url="https://localhost:8912/",
            expected_port=8912,
            runtime_host="localhost",
            expected_client_name="myapp",
        )
        assert any("no CallbackURLs configured" in e for e in errors)

    def test_port_mismatch_in_callbacks(self):
        errors = validate_cognito_app_client(
            app_client=_make_app_client(
                callbacks=["https://localhost:9999/auth/callback"]
            ),
            expected_callback_url="https://localhost:9999/auth/callback",
            expected_logout_url="https://localhost:8912/",
            expected_port=8912,
            runtime_host="localhost",
            expected_client_name="myapp",
        )
        assert any("port mismatch" in e for e in errors)

    def test_port_mismatch_flagged(self):
        errors = validate_uri_list_ports(
            uris=["https://localhost:9999/cb"], label="Test",
            expected_port=8912, runtime_host="localhost",
        )
        assert any("port mismatch" in e for e in errors)

    def test_remote_uri_skipped(self):
        errors = validate_uri_list_ports(
            uris=["https://example.com:9999/cb"], label="Test",
            expected_port=8912, runtime_host="localhost",
        )
        assert errors == []

