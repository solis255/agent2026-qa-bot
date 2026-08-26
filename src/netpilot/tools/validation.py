"""Security-focused validation shared by mock and local tools."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit


_DOMAIN_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_BLOCKED_METADATA_HOSTS = {
    "metadata.google.internal",
    "metadata.azure.internal",
}


class UnsafeTargetError(ValueError):
    """Raised when a URL target violates the local HTTP safety boundary."""


def normalize_host(value: str) -> str:
    """Validate and normalize an IP address or DNS hostname."""

    normalized = value.strip()
    if not normalized:
        raise ValueError("host must not be empty")
    if normalized != value or any(character.isspace() for character in normalized):
        raise ValueError("host must not contain whitespace")
    if len(normalized) > 253:
        raise ValueError("host is too long")
    if normalized.startswith("-"):
        raise ValueError("host must not start with an option prefix")

    try:
        return str(ipaddress.ip_address(normalized))
    except ValueError:
        pass

    try:
        ascii_host = normalized.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("host contains invalid international characters") from exc

    if not ascii_host or len(ascii_host) > 253:
        raise ValueError("host is too long")
    if any(not _DOMAIN_LABEL.fullmatch(label) for label in ascii_host.split(".")):
        raise ValueError("host is not a valid IP address or DNS name")
    return ascii_host


def validate_http_url(value: str) -> str:
    """Validate HTTP syntax and reject directly identifiable unsafe targets."""

    normalized = value.strip()
    if normalized != value or any(ord(character) < 32 for character in normalized):
        raise ValueError("URL contains whitespace or control characters")

    parsed = urlsplit(normalized)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("URL scheme must be http or https")
    if not parsed.hostname:
        raise ValueError("URL must contain a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL must not contain user information")
    if parsed.fragment:
        raise ValueError("URL must not contain a fragment")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL contains an invalid port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("URL contains an invalid port")

    host = normalize_host(parsed.hostname)
    assert_safe_direct_http_host(host)

    if ":" in host:
        netloc_host = f"[{host}]"
    else:
        netloc_host = host
    netloc = f"{netloc_host}:{port}" if port is not None else netloc_host
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def assert_safe_direct_http_host(host: str) -> None:
    """Reject localhost, metadata names, and direct non-global IP targets."""

    normalized = host.rstrip(".").lower()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        raise UnsafeTargetError("localhost HTTP targets are blocked")
    if normalized in _BLOCKED_METADATA_HOSTS or normalized.endswith(".internal"):
        raise UnsafeTargetError("metadata and internal HTTP targets are blocked")

    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return
    assert_public_ip(address)


def assert_public_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """Require an Internet-routable address for HTTP checks."""

    if not address.is_global:
        raise UnsafeTargetError("non-public HTTP target addresses are blocked")
