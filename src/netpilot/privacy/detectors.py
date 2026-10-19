"""Precompiled, high-confidence identifiers. Ordinary diagnostic prose is retained."""
import re

REDACTED = "[REDACTED]"
MAC = "[REDACTED_MAC]"
HOSTNAME = "[REDACTED_HOSTNAME]"
SSID = "[REDACTED_SSID]"
SECRET_NAMES = ("password", "passwd", "pwd", "cookie", "set_cookie", "authorization",
                "proxy_authorization", "auth_token", "token", "access_token", "refresh_token",
                "api_key", "apikey", "x_api_key", "secret", "client_secret", "credential",
                "credentials", "session_token", "private_key", "密码", "口令", "密钥")
HOST_KEYS = {"hostname", "host_name", "computername", "computer_name", "主机名", "设备名"}
MAC_KEYS = {"mac", "mac_address", "macaddress", "bssid"}
SSID_KEYS = {"ssid"}


def normalize_key(key):
    return re.sub(r"[^\w]", "_", re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key))).lower().strip("_")


def sensitive_key(key):
    key = normalize_key(key)
    return any(key == name or key.endswith("_" + name) for name in SECRET_NAMES)


_NAMES = r"(?:proxy[-_ ]authorization|authorization|set[-_ ]cookie|cookie|password|passwd|pwd|(?:x[-_ ])?api[-_ ]?key|(?:auth|access|refresh|session)[-_ ]?token|token|client[-_ ]secret|secret|credentials?|private[-_ ]key|密码|口令|密钥)"
ASSIGNMENT = re.compile(r'''(?i)(?<![\w])(["']?''' + _NAMES + r'''["']?\s*[:=：]\s*)(\[REDACTED\]|"[^"\n]*"|'[^'\n]*'|[^\s,，;；}\]\)<>]+)''')
HEADER = re.compile(r"(?im)\b(?:proxy-authorization|authorization|set-cookie|cookie)\s*[:：][^\r\n]+")
AUTH = re.compile(r"(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+")
PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----[\s\S]*?(?:-----END (?:[A-Z]+ )*PRIVATE KEY-----|$)")
OPAQUE = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b")
MAC_PATTERN = re.compile(r"(?i)(?<![\w:])(?:(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}|(?:[0-9a-f]{4}\.){2}[0-9a-f]{4})(?![\w:])")
HOST_PATTERN = re.compile(r"(?i)\b(?:DESKTOP|LAPTOP|WIN|PC)-[A-Z0-9_-]+\b")
IDENTIFIER = re.compile(r'''(?i)(?<![\w])(["']?(?:hostname|host_name|computername|ssid|bssid|mac(?:_address)?|主机名|设备名)["']?(?:\s*[:=：]\s*|\s+))(\[REDACTED(?:_HOSTNAME|_MAC|_SSID)?\]|"[^"\n]*"|'[^'\n]*'|[^\s,，;；}\]\)<>]+)''')
URL = re.compile(r'''(?i)\b(?:https?://|javascript:|data:|file:)[^\s<>"'\)`]+''')
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE = re.compile(r"(?<![\w.])(?:\+?86[- ]?)?1[3-9]\d{9}(?![\w.])")
USER_AGENT = re.compile(r"(?im)\b(?:User-Agent\s*[:：]\s*|Mozilla/)[^\n]+")
LOCATION = re.compile(r"(?<![\d.])-?\d{1,3}\.\d{4,}\s*[,，]\s*-?\d{1,3}\.\d{4,}(?![\d.])")
