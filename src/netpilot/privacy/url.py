"""HTTP(S)-only citations with no credentials or sensitive URL parameters."""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .detectors import normalize_key, sensitive_key

QUERY_KEYS = {"key", "auth", "session", "sessionid", "session_id", "sid", "sig", "signature"}


def sanitize_url(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return "[REDACTED]"
        host = parsed.hostname
        if ":" in host:
            host = "[" + host + "]"
        netloc = host + (":" + str(parsed.port) if parsed.port else "")
        query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                 if not sensitive_key(k) and normalize_key(k) not in QUERY_KEYS]
        # Fragments can carry OAuth tokens and are unnecessary for diagnosis.
        return urlunsplit((parsed.scheme.lower(), netloc, parsed.path, urlencode(query), ""))
    except (ValueError, UnicodeError):
        return "[REDACTED]"
