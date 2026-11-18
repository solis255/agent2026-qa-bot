"""Validated application configuration for TJU NetPilot."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
import re
from typing import Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


class ToolMode(str, Enum):
    """Supported network-tool providers."""

    MOCK = "mock"
    LOCAL = "local"


class MockScenario(str, Enum):
    """Deterministic scenarios reserved for the mock provider."""

    HEALTHY = "healthy"
    DNS_FAILURE = "dns_failure"
    GATEWAY_UNREACHABLE = "gateway_unreachable"
    TCP_SSH_BLOCKED = "tcp_ssh_blocked"
    HTTP_FAILURE = "http_failure"
    PARTIAL_CONNECTIVITY = "partial_connectivity"


class Settings(BaseSettings):
    """NetPilot settings loaded from environment variables or the root .env file."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )

    llm_provider: str = "tju"
    llm_api_key: SecretStr | None = None
    llm_api_base: str | None = None
    llm_model: str | None = None
    tju_api_key: SecretStr | None = None
    tju_api_base: str = (
        "https://ai.tju.edu.cn/api/agent2026/agent2026-netpilot"
    )
    tju_model: str = "tju-llm"
    tju_show_token_usage: bool = True
    tju_timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    tju_max_retries: int = Field(default=2, ge=0, le=5)
    llm_max_output_tokens: int = Field(default=1600, ge=1, le=32_768)
    llm_report_max_output_tokens: int = Field(default=2800, ge=1, le=32_768)
    llm_knowledge_max_output_tokens: int = Field(default=2200, ge=1, le=32_768)

    max_tool_rounds: int = Field(default=6, ge=1, le=20)
    max_rag_calls_per_turn: int = Field(default=2, ge=1, le=10)
    max_history_messages: int = Field(default=20, ge=1, le=200)
    max_sessions: int = Field(default=500, ge=1, le=10_000)
    client_snapshot_max_bytes: int = Field(default=262144, ge=1024, le=1_048_576)
    client_snapshot_freshness_minutes: int = Field(default=15, ge=1, le=1440)
    remediation_max_steps: int = Field(default=5, ge=1, le=10)
    verification_max_cycles: int = Field(default=10, ge=1, le=50)
    resolution_max_transitions: int = Field(default=30, ge=1, le=200)
    resolution_escalate_after_no_improvement: int = Field(default=2, ge=1, le=20)
    escalation_max_evidence_items: int = Field(default=12, ge=1, le=50)
    escalation_max_packages: int = Field(default=5, ge=1, le=20)
    escalation_mask_private_ip: bool = False
    privacy_mask_private_ip: bool = False
    privacy_remove_public_client_ip: bool = True
    privacy_redact_hostname: bool = True
    privacy_redact_email: bool = False
    privacy_redact_phone: bool = False
    privacy_policy_version: Literal["1"] = "1"
    reasoning_trace_enabled: bool = True
    reasoning_trace_max_steps: int = Field(default=50, ge=1, le=200)
    reasoning_summary_llm_enabled: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    diagnosis_history_enabled: bool = True
    diagnosis_db_path: Path = PROJECT_ROOT / "data" / "netpilot.db"
    diagnosis_max_records: int = Field(default=1000, ge=1, le=100_000)
    diagnosis_report_max_bytes: int = Field(
        default=1_000_000,
        ge=1024,
        le=5_000_000,
    )

    # Authentication is mandatory; a false env value fails closed at startup.
    auth_enabled: Literal[True] = True
    # Auth sessions use the same SQLite file as diagnosis history.
    auth_cookie_name: str = "netpilot_session"
    auth_cookie_secure: bool = False
    auth_session_hours: int = Field(default=12, ge=1, le=168)
    auth_max_active_sessions_per_user: int = Field(default=5, ge=1, le=50)

    tool_mode: ToolMode = ToolMode.MOCK
    mock_scenario: MockScenario = MockScenario.HEALTHY
    network_timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)
    scenario_switch_enabled: bool = False
    custom_scenario_max_count: int = Field(default=20, ge=1, le=100)
    sse_chunk_chars: int = Field(default=32, ge=1, le=256)
    sse_heartbeat_seconds: float = Field(default=15.0, ge=1.0, le=30.0)

    rag_enabled: bool = True
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    rag_top_k: int = Field(default=4, ge=1, le=20)
    rag_min_score: float = Field(default=0.35, ge=-1.0, le=1.0)
    rag_chunk_size: int = Field(default=700, ge=200, le=4000)
    rag_chunk_overlap: int = Field(default=120, ge=0, le=1000)
    rag_index_dir: Path = PROJECT_ROOT / "knowledge" / "index"
    rag_model_cache_dir: Path = PROJECT_ROOT / ".cache" / "fastembed"

    app_host: str = "127.0.0.1"
    app_timezone: str = "Asia/Shanghai"
    app_port: int = Field(default=8000, ge=1, le=65535)
    debug: bool = False
    demo_mode: bool = False

    @field_validator("app_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("APP_TIMEZONE must be a valid IANA timezone") from exc
        return value

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        value = value.strip().lower() or "tju"
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", value):
            raise ValueError("LLM_PROVIDER must be a provider identifier")
        return value

    @field_validator("tju_model", "llm_model")
    @classmethod
    def validate_llm_model(cls, value: str | None, info) -> str | None:
        if value is None or not value.strip():
            return "tju-llm" if info.field_name == "tju_model" else None
        normalized = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}", normalized) or "://" in normalized:
            raise ValueError("LLM model must be a valid model identifier")
        return normalized

    @field_validator("tju_api_base", "llm_api_base")
    @classmethod
    def validate_llm_api_base(cls, value: str | None, info) -> str | None:
        """Require an HTTP(S) SDK base URL, not a completion endpoint."""

        if value is None or not value.strip():
            if info.field_name == "tju_api_base":
                raise ValueError("TJU_API_BASE must not be blank")
            return None
        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("API base must be an absolute HTTP(S) URL")
        if parsed.query or parsed.fragment or parsed.username is not None or parsed.password is not None:
            raise ValueError("API base must not contain credentials, a query or fragment")
        if normalized.endswith("/chat/completions"):
            raise ValueError("API base must stop before /chat/completions")
        return normalized

    @field_validator("embedding_model", "app_host")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        """Reject empty operational settings early."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("rag_chunk_overlap")
    @classmethod
    def validate_chunk_overlap(cls, value: int, info) -> int:
        chunk_size = info.data.get("rag_chunk_size", 700)
        if value >= chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE")
        return value

    @field_validator("auth_cookie_name")
    @classmethod
    def validate_auth_cookie_name(cls, value: str) -> str:
        normalized = value.strip()
        allowed = normalized.replace("_", "").replace("-", "")
        if not normalized or not normalized.isascii() or not allowed.isalnum():
            raise ValueError("AUTH_COOKIE_NAME must contain only ASCII letters, digits, _ or -")
        return normalized

    @property
    def effective_llm_api_key(self) -> SecretStr | None:
        if self.llm_api_key and self.llm_api_key.get_secret_value().strip():
            return self.llm_api_key
        if self.llm_provider == "tju" and self.effective_llm_api_base == self.tju_api_base:
            return self.tju_api_key
        return None

    @property
    def effective_llm_api_base(self) -> str | None:
        return self.llm_api_base or (self.tju_api_base if self.llm_provider == "tju" else None)

    @property
    def effective_llm_model(self) -> str | None:
        return self.llm_model or (self.tju_model if self.llm_provider == "tju" else None)

    @property
    def llm_configured(self) -> bool:
        key = self.effective_llm_api_key
        return bool(key and key.get_secret_value().strip() and self.effective_llm_api_base and self.effective_llm_model)
