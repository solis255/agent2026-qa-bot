"""Privacy-minimal environment context; never a live network measurement."""

from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


OSFamily = Literal["windows", "macos", "linux", "android", "ios", "unknown"]
ClientMode = Literal["server_local", "remote_browser", "mock", "unknown"]
NetworkAccess = Literal["campus_wifi", "campus_wired", "off_campus", "mobile_hotspot", "unknown"]
AffectedScope = Literal["all_network", "web_only", "single_service", "internal_resource", "unknown"]
EnvironmentSource = Literal["browser", "user", "snapshot", "server", "mock", "inferred"]
PRECEDENCE = {"inferred": 0, "server": 1, "browser": 2, "mock": 3, "snapshot": 4, "user": 5}
BROWSER_FIELDS = frozenset({"os_family", "browser_online", "browser_language", "effective_type", "estimated_rtt_ms", "estimated_downlink_mbps"})
USER_FIELDS = frozenset({"os_family", "os_version", "network_access", "vpn_enabled", "proxy_enabled", "affected_scope", "affected_service"})


class EnvironmentFieldSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: EnvironmentSource
    confidence: Literal["high", "medium", "low"]


class BrowserEnvironmentValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    os_family: OSFamily = "unknown"
    browser_online: bool | None = Field(default=None, strict=True)
    browser_language: str | None = Field(default=None, max_length=35)
    effective_type: Literal["slow-2g", "2g", "3g", "4g"] | None = None
    estimated_rtt_ms: int | None = Field(default=None, ge=0, le=60_000, strict=True)
    estimated_downlink_mbps: float | None = Field(default=None, ge=0, le=100_000, allow_inf_nan=False, strict=True)

    @field_validator("browser_language")
    @classmethod
    def language_tag_only(cls, value):
        if value is not None and not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", value):
            raise ValueError("browser_language must be a normalized language tag")
        return value


class EnvironmentUpdate(BaseModel):
    """Only explicitly supplied fields are merged; None is not False."""
    model_config = ConfigDict(extra="forbid")
    os_family: OSFamily = "unknown"
    os_version: str | None = Field(default=None, max_length=24)
    network_access: NetworkAccess = "unknown"
    vpn_enabled: bool | None = Field(default=None, strict=True)
    proxy_enabled: bool | None = Field(default=None, strict=True)
    affected_scope: AffectedScope = "unknown"
    affected_service: str | None = Field(default=None, max_length=80)

    @field_validator("os_version")
    @classmethod
    def numeric_version_only(cls, value):
        if value is not None and not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", value):
            raise ValueError("os_version must be an explicitly supplied numeric version")
        return value

    @field_validator("affected_service")
    @classmethod
    def service_label_only(cls, value):
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not re.fullmatch(r"[A-Za-z0-9\u4e00-\u9fff ._()+（）-]{1,80}", value):
            raise ValueError("use only a service name or hostname, not a URL or credential")
        if re.search(r"(?i)\b(?:cookie|token|password|ssid|bssid|user-agent|mac)\b|密码|口令|密钥|公网IP", value):
            raise ValueError("sensitive environment identifiers are not accepted")
        if re.search(r"\b(?:[0-9a-fA-F]{2}[-:]){5}[0-9a-fA-F]{2}\b", value):
            raise ValueError("hardware identifiers are not accepted")
        for candidate in re.findall(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", value):
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                continue
            raise ValueError("IP addresses do not belong in the environment profile")
        return value


class EnvironmentProfile(EnvironmentUpdate):
    client_mode: ClientMode = "unknown"
    browser_online: bool | None = Field(default=None, strict=True)
    browser_language: str | None = Field(default=None, max_length=35)
    effective_type: Literal["slow-2g", "2g", "3g", "4g"] | None = None
    estimated_rtt_ms: int | None = Field(default=None, ge=0, le=60_000, strict=True)
    estimated_downlink_mbps: float | None = Field(default=None, ge=0, le=100_000, allow_inf_nan=False, strict=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    field_sources: dict[str, EnvironmentFieldSource] = Field(default_factory=dict)

    @field_validator("browser_language")
    @classmethod
    def validate_language(cls, value):
        return BrowserEnvironmentValues.language_tag_only(value)

    @field_validator("field_sources")
    @classmethod
    def known_fields_only(cls, value):
        if set(value) - (BROWSER_FIELDS | USER_FIELDS | {"client_mode"}):
            raise ValueError("unknown environment provenance field")
        return value


def initial_environment(client_mode: ClientMode = "unknown") -> EnvironmentProfile:
    profile = EnvironmentProfile()
    if client_mode != "unknown":
        return merge_environment(profile, {"client_mode": client_mode}, source="mock" if client_mode == "mock" else "server")
    return profile


def legacy_environment() -> EnvironmentProfile:
    # Stable unknown defaults, not inferred from old answers or the server's OS.
    return EnvironmentProfile(updated_at=datetime(1970, 1, 1, tzinfo=timezone.utc))


def merge_environment(profile: EnvironmentProfile, values: dict, *, source: EnvironmentSource) -> EnvironmentProfile:
    if source not in PRECEDENCE:
        raise ValueError("unknown environment source")
    allowed = {"os_family", "os_version"} if source == "snapshot" else BROWSER_FIELDS if source == "browser" else USER_FIELDS if source == "user" else BROWSER_FIELDS | USER_FIELDS | {"client_mode"}
    if set(values) - allowed:
        raise ValueError("environment update contains fields not allowed for its source")
    data = profile.model_dump()
    changed = False
    for name, value in values.items():
        old = profile.field_sources.get(name)
        if old is not None and PRECEDENCE[old.source] > PRECEDENCE[source]:
            continue
        if source == "browser" and name == "os_family" and value == "unknown":
            continue
        confidence = "high" if source in {"user", "mock", "snapshot"} else "low" if source == "inferred" or name in {"effective_type", "estimated_rtt_ms", "estimated_downlink_mbps"} else "medium"
        provenance = {"source": source, "confidence": confidence}
        if data[name] != value or data["field_sources"].get(name) != provenance:
            data[name] = value
            data["field_sources"][name] = provenance
            changed = True
        # A changed OS must not keep a version explicitly supplied for another OS.
        if name == "os_family" and profile.os_family != value and "os_version" not in values:
            data["os_version"] = None
            data["field_sources"].pop("os_version", None)
    if changed:
        data["updated_at"] = datetime.now(timezone.utc)
    return EnvironmentProfile.model_validate(data)


def extract_environment_updates(message: str) -> EnvironmentUpdate:
    """Conservative explicit statements only; no independent LLM classification."""
    values = {}
    # Do not borrow the omitted subject from a quotation/third-party scenario.
    if re.search(r'如果|假如|假设|比如|例如|他说|同学|有人|["“”‘’]', message):
        return EnvironmentUpdate()
    clauses = re.split(r"[，,。；;\n]", message[:4000].casefold())
    statements = [text for text in clauses if not re.search(r"[?？吗\"“”‘’]|如果|假如|假设|比如|例如|是否|怎么|如何|怎样|能否|会不会|什么|可能|好像|也许|不确定|不知道|请|建议|他说|同学|有人|打算|准备|计划|想|需要|不要", text)]
    for text in statements:
        negated_connection = bool(re.search(r"(?:没(?:有)?|未|不|尚未)(?:连|接|用|使用|通过|在)", text))
        if not negated_connection and re.search(r"我(?:现在|目前|其实)?(?:是|用|使用|在用)|我的|(?:设备|系统|电脑|手机)(?:是|为|用)", text):
            for pattern, family in [(r"windows|win(?:10|11)\b", "windows"), (r"macos|mac os|macbook|苹果电脑", "macos"), (r"linux|ubuntu|debian", "linux"), (r"android|安卓", "android"), (r"ios|iphone|ipad|苹果手机", "ios")]:
                if re.search(pattern, text):
                    values["os_family"] = family
        if not negated_connection and re.search(r"(?:连(?:接)?|接入|用|通过).{0,8}(?:校园|校内|天津大学|天大)\s*(?:wi-?fi|无线|wlan)", text):
            values["network_access"] = "campus_wifi"
        if not negated_connection and re.search(r"(?:连(?:接)?|接入|用|通过).{0,8}(?:校园|校内)\s*(?:有线|网线)", text):
            values["network_access"] = "campus_wired"
        if not negated_connection and re.search(r"我(?:现在|目前)?(?:在|用|连接).{0,5}(?:校外|家里|校外网络)", text):
            values["network_access"] = "off_campus"
        if not negated_connection and re.search(r"(?:连(?:接)?|使用|用的是|用着).{0,6}(?:手机|移动)热点", text):
            values["network_access"] = "mobile_hotspot"
        for word, field in [("vpn", "vpn_enabled"), ("proxy|代理", "proxy_enabled")]:
            if re.search(rf"(?:没(?:有)?|未)(?:开(?:启)?|启用|打开|使用)\s*(?:{word})|(?:已关闭|关闭了|关了|停用了)\s*(?:{word})|(?:{word})\s*(?:未开启|没开|已关闭|关闭|未启用)", text):
                values[field] = False
            elif re.search(rf"(?:已开启|开启了|启用了|打开了|开着|开了)\s*(?:{word})|我(?:现在|目前)?(?:开启|打开|启用)\s*(?:{word})|(?:{word})\s*(?:已开启|开启中|开着|已启用)", text):
                values[field] = True
        if re.search(r"(?:全部网络|所有网络|所有应用).{0,5}(?:不通|断开|不能上网|无法联网)", text):
            values["affected_scope"] = "all_network"
        if re.search(r"(?:只有|仅|只是)(?:网页|浏览器).{0,5}(?:打不开|无法访问|异常)", text):
            values["affected_scope"] = "web_only"
        if re.search(r"(?:只有|仅)(?:校内|校园网内部)资源\s*(?:打不开|无法访问|不通)", text):
            values["affected_scope"] = "internal_resource"
        service = re.search(r"(?:只有|仅)\s*([a-z0-9][a-z0-9.-]{0,79})\s*(?:这个服务)?(?:打不开|无法访问|连不上)", text)
        if service:
            values["affected_scope"] = "single_service"
            try:
                values["affected_service"] = EnvironmentUpdate(affected_service=service.group(1)).affected_service
            except ValueError:
                pass  # Never copy an IP/identifier into the profile from chat.
    explicit_text = "，".join(statements)
    if re.search(r"(?:微信|qq|聊天软件)\s*(?:仍然|仍|依然)?\s*正常", explicit_text) and re.search(r"(?:网页|浏览器)\s*(?:却|但|都|还是|仍然|仍)?\s*(?:打不开|无法访问)", explicit_text):
        values["affected_scope"] = "web_only"
    return EnvironmentUpdate(**values)


OS_LABELS = {"windows":"Windows", "macos":"macOS", "linux":"Linux", "android":"Android", "ios":"iOS", "unknown":"未知"}
ACCESS_LABELS = {"campus_wifi":"校园 WiFi", "campus_wired":"校园有线", "off_campus":"校外网络", "mobile_hotspot":"手机热点", "unknown":"未知"}
SCOPE_LABELS = {"all_network":"全部网络", "web_only":"仅网页", "single_service":"单一服务", "internal_resource":"仅校内资源", "unknown":"未知"}


def bool_label(value: bool | None) -> str:
    return "未知" if value is None else "开启" if value else "关闭"


def environment_summary(profile: EnvironmentProfile) -> str:
    return f"{OS_LABELS[profile.os_family]} · {ACCESS_LABELS[profile.network_access]} · VPN {bool_label(profile.vpn_enabled)} · Proxy {bool_label(profile.proxy_enabled)} · {SCOPE_LABELS[profile.affected_scope]}"


def environment_context(profile: EnvironmentProfile) -> str:
    labels = {"client_mode":"Client mode", "os_family":"OS", "os_version":"OS version", "network_access":"Network access", "vpn_enabled":"VPN", "proxy_enabled":"Proxy", "affected_scope":"Affected scope", "affected_service":"Affected service", "browser_online":"Browser online", "browser_language":"Browser language", "effective_type":"Estimated effective type", "estimated_rtt_ms":"Estimated RTT ms", "estimated_downlink_mbps":"Estimated downlink Mbps"}
    lines = []
    for field, label in labels.items():
        value = getattr(profile, field)
        text = "unknown" if value is None else str(value).lower() if isinstance(value, bool) else str(value)
        provenance = profile.field_sources.get(field)
        suffix = " (user confirmed)" if provenance and provenance.source == "user" else " (browser context only)" if provenance and provenance.source == "browser" else ""
        lines.append(f"- {label}: {text}{suffix}")
    return "ENVIRONMENT PROFILE\n" + "\n".join(lines) + (
        "\nEnvironment context is not live Tool Evidence. Unknown is not false. "
        "Browser online does not prove Internet health; effective type 4g does not imply cellular access. "
        "For remote_browser, Local Tools measure only the NetPilot server, not the user's device."
    )
