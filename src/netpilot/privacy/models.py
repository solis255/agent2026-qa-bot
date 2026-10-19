"""Value-free privacy contracts shared by ingestion, storage and exports."""
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

PRIVACY_POLICY_VERSION = "1"
RedactionCategory = Literal["credential", "hostname", "mac", "ssid", "public_client_ip", "identity",
                            "url", "private_ip", "email", "phone", "length_limit", "depth_limit"]


class RedactionResult(BaseModel):
    value: Any
    changed: bool
    redacted_categories: list[RedactionCategory] = Field(default_factory=list)
    redacted_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class RedactionMetadata(BaseModel):
    applied: bool = True
    policy_version: Literal["1"] = PRIVACY_POLICY_VERSION
    categories: list[RedactionCategory] = Field(default_factory=list)
    redacted_count: int = Field(default=0, ge=0)
    private_ip_masked: bool = False
    hostname_redacted: bool = False
    sensitive_values_removed: bool = False


class PrivacyAuditEvent(BaseModel):
    event_type: Literal["redaction_applied", "sensitive_upload_rejected"]
    categories: list[str] = Field(default_factory=list)
    count: int = 0
    context: Literal["persistence", "presentation", "export", "snapshot", "logging"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
