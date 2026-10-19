"""Conservative removal across every exported free-text field; no raw payloads."""
import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from netpilot.escalation.models import EscalationPrivacyPolicy

REDACTED_FIELDS = ("hostname", "MAC", "BSSID", "SSID", "password", "cookie", "authorization",
                   "API key", "token", "secret", "credential", "user-agent", "precise_location")
_KEY = r"(?:password|passwd|pwd|cookie|set-cookie|authorization|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|token|secret|credential|bssid|ssid|user[-_ ]?agent|hostname|computername|host_name|mac(?:_address)?|location|latitude|longitude|密码|口令|密钥|主机名|设备名|精确位置|经纬度)"
_ASSIGN = re.compile(r'(?i)([\"\']?' + _KEY + r'[\"\']?\s*[:=：]\s*)(?:"[^"\n]*"|\'[^\'\n]*\'|[^\n,，;；}]+)')


def _url(match):
    try:
        parsed = urlsplit(match.group())
        # Drop userinfo, fragment, and sensitive query names (including variants).
        host = parsed.hostname or ""
        if ":" in host: host = "[" + host + "]"
        netloc = host + (":" + str(parsed.port) if parsed.port else "")
        query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                 if not re.search(_KEY + r"|session|auth|signature|sig$|key$", k, re.I)]
        return urlunsplit((parsed.scheme, netloc, parsed.path, urlencode(query), ""))
    except ValueError:
        return "[URL removed]"


def redact(value: str | None, policy: EscalationPrivacyPolicy | None = None) -> str | None:
    if value is None: return None
    policy = policy or EscalationPrivacyPolicy()
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    value = re.sub(r"https?://[^\s<>\"']+", _url, value, flags=re.I)
    value = re.sub(r"(?im)\b(?:Cookie|Set-Cookie|Authorization|User-Agent)\s*[:：][^\n]+", "[sensitive header redacted]", value)
    value = _ASSIGN.sub(lambda m: m[1] + "[redacted]", value)
    value = re.sub(r"(?i)\b(?:SSID|BSSID|hostname|computername)\s+(?!redacted\b)[^\s,，;；]+", "[identifier redacted]", value)
    value = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "[redacted]", value)
    value = re.sub(r"(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b|\b(?:[0-9a-f]{4}\.){2}[0-9a-f]{4}\b", "[redacted]", value)
    value = re.sub(r"(?i)\b(?:DESKTOP|LAPTOP|WIN|PC)-[A-Z0-9_-]+\b", "[hostname redacted]", value)
    # Unlabelled API keys / JWTs, user-agent strings and GPS coordinates.
    value = re.sub(r"\b(?:sk-[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b", "[redacted]", value)
    value = re.sub(r"(?im)\bMozilla/[^\n]+", "[user-agent redacted]", value)
    value = re.sub(r"(?<![\d.])-?\d{1,3}\.\d{4,}\s*[,，]\s*-?\d{1,3}\.\d{4,}(?![\d.])", "[location redacted]", value)
    if policy.mask_private_ip:
        def mask(m):
            try:
                address = ipaddress.ip_address(m.group())
                return m.group().rsplit(".", 1)[0] + ".xxx" if address.is_private else m.group()
            except ValueError: return m.group()
        value = re.sub(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", mask, value)
        def mask6(m):
            try:
                address = ipaddress.ip_address(m.group())
                return "[private IPv6 masked]" if address.is_private else m.group()
            except ValueError: return m.group()
        value = re.sub(r"(?i)(?<![\w:])[0-9a-f]*:[0-9a-f:]+(?![\w:])", mask6, value)
    return value[:4000]
