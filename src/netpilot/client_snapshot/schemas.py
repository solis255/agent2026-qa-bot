"""Strict, bounded Windows diagnostic snapshot v1 and privacy-minimal summary."""

from datetime import datetime, timezone
from ipaddress import ip_address
import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

Text = Annotated[str, Field(max_length=1024)]
Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]
def _address(value: str) -> str:
    ip_address(value)
    if "%" in value and not re.fullmatch(r"\d{1,6}", value.split("%", 1)[1]):
        raise ValueError("only numeric IPv6 interface scopes are permitted")
    return value


Address = Annotated[str, Field(max_length=64), AfterValidator(_address)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ClientIdentitySummary(StrictModel):
    client_instance_id: Text
    hostname: Text | None = None

    @field_validator("client_instance_id")
    @classmethod
    def random_uuid(cls, value):
        if UUID(value).version != 4:
            raise ValueError("a per-run UUID4 is required")
        return value


class ClientOSInfo(StrictModel):
    family: Literal["windows"] = "windows"
    version: Annotated[str, Field(max_length=24, pattern=r"^\d+(?:\.\d+)*$")] | None = None
    build: Annotated[str, Field(max_length=24, pattern=r"^\d+$")] | None = None
    architecture: Literal["x64", "x86", "arm64", "unknown"] | None = None


class ClientAdapter(StrictModel):
    adapter_id: Identifier
    name: Text
    interface_alias: Text | None = None
    status: Literal["up", "down", "unknown"]
    interface_type: Literal["ethernet", "wifi", "virtual", "loopback", "other"]
    ipv4_addresses: list[Address] = Field(default_factory=list, max_length=16)
    ipv6_addresses: list[Address] = Field(default_factory=list, max_length=16)
    has_default_gateway: bool | None = None

    @model_validator(mode="after")
    def addresses(self):
        for version, values in [(4, self.ipv4_addresses), (6, self.ipv6_addresses)]:
            if any(ip_address(value).version != version for value in values):
                raise ValueError("incorrect IP address family")
        return self


class ClientConnectionProfile(StrictModel):
    network_category: Literal["public", "private", "domain", "unknown"]
    ipv4_connectivity: Literal["Disconnected", "NoTraffic", "Subnet", "LocalNetwork", "Internet", "Unknown"] | None = None
    ipv6_connectivity: Literal["Disconnected", "NoTraffic", "Subnet", "LocalNetwork", "Internet", "Unknown"] | None = None


class ClientProxySummary(StrictModel):
    winhttp_proxy_enabled: bool | None = None
    winhttp_proxy: Text | None = None

    @field_validator("winhttp_proxy")
    @classmethod
    def endpoints_only(cls, value):
        if value is not None and ("@" in value or not re.fullmatch(r"[A-Za-z0-9.\[\]:;= /_-]+", value)):
            raise ValueError("proxy credentials or non-endpoint text are not accepted")
        return value


class ClientRouteSummary(StrictModel):
    destination: Literal["0.0.0.0/0", "::/0"]
    next_hop: Address | None = None
    interface_id: Identifier | None = None
    metric: int | None = Field(default=None, ge=0, le=2_147_483_647)


class ClientCheckData(StrictModel):
    """Only typed diagnostic facts, never arbitrary JSON or ErrorRecord text."""
    addresses: list[Address] = Field(default_factory=list, max_length=16)
    reachable: bool | None = None
    port: Literal[443] | None = None
    error_code: Literal["dns_query_failed", "probe_failed", "cmdlet_unavailable", "collection_error", "gateway_unknown"] | None = None


class ClientCheckResult(StrictModel):
    check_id: Identifier
    type: Literal["dns", "gateway_reachability", "tcp_connectivity"]
    target: Annotated[str, Field(min_length=1, max_length=253)]
    status: Literal["normal", "abnormal", "unsupported", "error"]
    latency_ms: float | None = Field(default=None, ge=0, le=300_000, allow_inf_nan=False)
    result: ClientCheckData = Field(default_factory=ClientCheckData)

    @model_validator(mode="after")
    def fixed_probe_contract(self):
        for address in self.result.addresses:
            ip_address(address)
        if self.type == "dns":
            if self.target not in {"www.tju.edu.cn", "www.baidu.com"} or self.result.port is not None or self.result.reachable is not None:
                raise ValueError("unsupported DNS probe")
            if self.status == "normal" and not self.result.addresses:
                raise ValueError("normal DNS requires answers")
            if self.status != "normal" and self.result.addresses:
                raise ValueError("failed DNS cannot contain successful answers")
        elif self.type == "tcp_connectivity":
            if self.target != "1.1.1.1" or self.result.port != 443 or self.result.addresses:
                raise ValueError("unsupported TCP probe")
        else:
            if self.target != "unknown":
                ip_address(self.target)
            if self.result.port is not None or self.result.addresses:
                raise ValueError("unsupported gateway probe")
        if self.type != "dns":
            if self.status == "normal" and self.result.reachable is not True:
                raise ValueError("normal probe must succeed")
            if self.status == "abnormal" and self.result.reachable is not False:
                raise ValueError("abnormal probe must fail")
        if self.status in {"unsupported", "error"} and self.result.reachable is not None:
            raise ValueError("unknown result must not imply reachability")
        return self


class ClientRedactionMetadata(StrictModel):
    hostname_redacted: bool
    mac_removed: bool
    ssid_removed: bool
    secrets_removed: bool


class ClientDiagnosticSnapshot(StrictModel):
    schema_version: Literal[1]
    collection_status: dict[Literal["os", "adapters", "ip_configuration", "dns_servers", "routes", "connection_profile", "proxy"], Literal["normal", "unsupported", "error", "unknown"]] = Field(default_factory=dict, max_length=7)
    generated_at: datetime
    client: ClientIdentitySummary
    os: ClientOSInfo
    adapters: list[ClientAdapter] = Field(max_length=32)
    active_adapter_id: Identifier | None
    default_gateway: Address | None
    dns_servers: list[Address] = Field(max_length=16)
    dns_servers_scope: Literal["active_adapter", "up_adapters", "unknown"] = "unknown"
    connection_profile: ClientConnectionProfile | None
    proxy: ClientProxySummary
    route_summary: list[ClientRouteSummary] = Field(max_length=16)
    checks: list[ClientCheckResult] = Field(max_length=32)
    redaction: ClientRedactionMetadata

    @model_validator(mode="after")
    def consistent(self):
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at requires timezone")
        ids = [item.adapter_id for item in self.adapters]
        if len(set(ids)) != len(ids) or (self.active_adapter_id is not None and self.active_adapter_id not in ids):
            raise ValueError("invalid adapter references")
        if self.dns_servers_scope == "active_adapter" and self.active_adapter_id is None:
            raise ValueError("active DNS scope needs an active adapter")
        for value in [*self.dns_servers, *([self.default_gateway] if self.default_gateway else [])]:
            ip_address(value)
        if self.default_gateway and ip_address(self.default_gateway).version != 4:
            raise ValueError("default_gateway is IPv4")
        for route in self.route_summary:
            if route.interface_id is not None and route.interface_id not in ids:
                raise ValueError("invalid route interface")
            if route.next_hop and ip_address(route.next_hop).version != (4 if route.destination == "0.0.0.0/0" else 6):
                raise ValueError("incorrect route family")
        check_ids = [item.check_id for item in self.checks]
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("duplicate checks")
        for check in self.checks:
            if check.type == "gateway_reachability" and check.target != (self.default_gateway or "unknown"):
                raise ValueError("gateway probe must match the captured gateway")
            if check.target == "unknown" and check.status not in {"error", "unsupported"}:
                raise ValueError("missing gateway is unknown, not a failed probe")
        return self


class ClientSnapshotSummary(BaseModel):
    privacy_policy_version: str = "1"
    model_config = ConfigDict(extra="forbid")
    snapshot_id: str
    snapshot_digest: str
    snapshot_sequence: int = Field(ge=1)
    generated_at: datetime
    ingested_at: datetime
    expires_at: datetime
    stale: bool = False
    clock_skew_suspected: bool = False
    os: ClientOSInfo
    active_interface_type: str | None = None
    evidence_count: int = Field(ge=1)
    target_version: int = Field(ge=1)
    task_version: int = Field(ge=1)
    applicable: bool = True
    redaction: ClientRedactionMetadata


def refresh_summary(summary: ClientSnapshotSummary | None, now: datetime | None = None):
    if summary is None:
        return None
    return summary.model_copy(update={"stale": (now or datetime.now(timezone.utc)) > summary.expires_at})
