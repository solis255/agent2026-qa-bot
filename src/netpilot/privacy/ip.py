"""Semantic client IP removal and optional private subnet preservation."""
import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

IP_PATTERN = re.compile(r"(?i)(?<![\w.:])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])|(?<![\w:])[0-9a-f]*:[0-9a-f:]+(?![\w:])")
CLIENT_PUBLIC_KEYS = {"client_public_ip", "public_client_ip", "observed_public_ip", "external_ip", "public_ip", "wan_ip", "client_observed_public_ip"}


def mask_address(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return value
    if not address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified:
        return value
    if address.version == 4:
        return value.rsplit(".", 1)[0] + ".xxx"
    return ":".join(address.exploded.split(":")[:4]) + ":xxxx:xxxx:xxxx:xxxx"


def mask_url_address(value):
    """Keep IPv6 URLs valid and clickable while zeroing the host portion."""
    try:
        parsed = urlsplit(value)
        address = ipaddress.ip_address(parsed.hostname or "")
        if not address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified:
            return value
        host = mask_address(str(address)) if address.version == 4 else "[" + str(ipaddress.ip_network(f"{address}/64", strict=False).network_address) + "]"
        netloc = host + (":" + str(parsed.port) if parsed.port else "")
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    except ValueError:
        return value
