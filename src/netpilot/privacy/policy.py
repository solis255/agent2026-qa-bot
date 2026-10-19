"""Immutable policy; credential protection cannot be disabled."""
from contextvars import ContextVar
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import PRIVACY_POLICY_VERSION


class PrivacyPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    redact_passwords: Literal[True] = True
    redact_tokens: Literal[True] = True
    redact_cookies: Literal[True] = True
    redact_authorization: Literal[True] = True
    strip_url_credentials: Literal[True] = True
    strip_sensitive_query_params: Literal[True] = True
    redact_mac: bool = True
    redact_bssid: bool = True
    redact_ssid: bool = True
    redact_hostname: bool = True
    mask_private_ip: bool = False
    remove_public_ip: bool = True
    redact_email: bool = False
    redact_phone: bool = False
    max_free_text_length: int = Field(default=4096, ge=64, le=1_000_000)
    max_depth: int = Field(default=24, ge=1, le=64)
    policy_version: Literal["1"] = PRIVACY_POLICY_VERSION

    @classmethod
    def from_settings(cls, settings):
        return cls(mask_private_ip=settings.privacy_mask_private_ip,
                   remove_public_ip=settings.privacy_remove_public_client_ip,
                   redact_hostname=settings.privacy_redact_hostname,
                   redact_email=settings.privacy_redact_email,
                   redact_phone=settings.privacy_redact_phone)


current_policy: ContextVar[PrivacyPolicy] = ContextVar("privacy_policy", default=PrivacyPolicy())
