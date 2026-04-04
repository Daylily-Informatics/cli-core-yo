"""Pure OAuth/Cognito URI validation helpers.

No I/O, no AWS calls — just URL parsing and port-alignment checks.
Service CLIs use these to validate Cognito app-client configuration
at startup without duplicating validation logic.
"""

from __future__ import annotations

from urllib.parse import urlparse

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "::"}


def runtime_oauth_host(host: str) -> str:
    """Resolve runtime callback host for browser-facing URLs.

    Bind-all addresses (``0.0.0.0``, ``::``) become ``localhost``.
    """
    if host in ("0.0.0.0", "::"):
        return "localhost"
    return host


def default_port_for_scheme(scheme: str) -> int | None:
    """Return implicit port for known URI schemes."""
    if scheme == "https":
        return 443
    if scheme == "http":
        return 80
    return None


def normalize_uri(uri: str) -> str:
    """Normalize URI for reliable comparison (strip trailing slash, params, query, fragment)."""
    parsed = urlparse(uri.strip())
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    normalized = parsed._replace(path=path, params="", query="", fragment="")
    return normalized.geturl()


def uri_port(uri: str) -> int | None:
    """Resolve explicit or implicit URI port."""
    parsed = urlparse(uri.strip())
    if not parsed.scheme or not parsed.netloc:
        return None
    return parsed.port or default_port_for_scheme(parsed.scheme.lower())


def is_local_oauth_uri(uri: str, runtime_host: str) -> bool:
    """Return True when URI points to a local/loopback host."""
    parsed = urlparse(uri.strip())
    hostname = (parsed.hostname or "").lower()
    return hostname in _LOCAL_HOSTS or hostname == runtime_host.lower()


def validate_uri_list_ports(
    *,
    uris: list[str],
    label: str,
    expected_port: int,
    runtime_host: str,
) -> list[str]:
    """Validate URI structure and port alignment for local endpoints.

    Returns a list of error strings (empty = OK).
    """
    errors: list[str] = []
    for raw_uri in uris:
        uri = raw_uri.strip()
        parsed = urlparse(uri)
        if not parsed.scheme or not parsed.netloc:
            errors.append(f"{label} contains invalid URI: {uri}")
            continue
        if parsed.scheme not in {"http", "https"}:
            errors.append(f"{label} contains unsupported URI scheme: {uri}")
            continue
        if is_local_oauth_uri(uri, runtime_host):
            actual_port = uri_port(uri)
            if actual_port != expected_port:
                errors.append(
                    f"{label} URI port mismatch for local endpoint: {uri} "
                    f"(expected port {expected_port})"
                )
    return errors


def validate_cognito_app_client(
    *,
    app_client: dict,
    expected_callback_url: str,
    expected_logout_url: str,
    expected_port: int,
    runtime_host: str,
    expected_client_name: str,
) -> list[str]:
    """Validate Cognito app-client OAuth URLs against runtime expectations.

    *app_client* is the dict from ``describe_user_pool_client`` response.
    Returns a list of error strings (empty = OK).
    """
    errors: list[str] = []
    actual_client_name = str(app_client.get("ClientName") or "").strip()
    callback_urls = [str(u) for u in (app_client.get("CallbackURLs") or []) if u]
    logout_urls = [str(u) for u in (app_client.get("LogoutURLs") or []) if u]
    default_redirect_uri = str(app_client.get("DefaultRedirectURI") or "").strip()

    if not actual_client_name:
        errors.append("Cognito app client has no ClientName configured")
    elif actual_client_name != expected_client_name:
        errors.append(
            f"Cognito app client name mismatch: "
            f"found '{actual_client_name}', expected '{expected_client_name}'"
        )
    if not app_client.get("AllowedOAuthFlowsUserPoolClient", False):
        errors.append("Cognito app client does not have OAuth2 flows enabled")
    if not callback_urls:
        errors.append("Cognito app client has no CallbackURLs configured")
    if not logout_urls:
        errors.append("Cognito app client has no LogoutURLs configured")

    errors.extend(
        validate_uri_list_ports(
            uris=callback_urls,
            label="CallbackURLs",
            expected_port=expected_port,
            runtime_host=runtime_host,
        )
    )
    errors.extend(
        validate_uri_list_ports(
            uris=logout_urls,
            label="LogoutURLs",
            expected_port=expected_port,
            runtime_host=runtime_host,
        )
    )
    if default_redirect_uri:
        errors.extend(
            validate_uri_list_ports(
                uris=[default_redirect_uri],
                label="DefaultRedirectURI",
                expected_port=expected_port,
                runtime_host=runtime_host,
            )
        )

    normalized_callbacks = {normalize_uri(u) for u in callback_urls}
    normalized_logouts = {normalize_uri(u) for u in logout_urls}
    normalized_expected_callback = normalize_uri(expected_callback_url)
    normalized_expected_logout = normalize_uri(expected_logout_url)

    if normalized_expected_callback not in normalized_callbacks:
        errors.append(
            "Expected callback URI is not configured in Cognito app client: "
            f"{expected_callback_url}"
        )
    if normalized_expected_logout not in normalized_logouts:
        errors.append(
            f"Expected logout URI is not configured in Cognito app client: {expected_logout_url}"
        )

    return errors
