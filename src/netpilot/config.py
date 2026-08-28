"""Validated application configuration for TJU NetPilot."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

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
    )

    tju_api_key: SecretStr | None = None
    tju_api_base: str = (
        "https://ai.tju.edu.cn/api/agent2026/agent2026-netpilot"
    )
    tju_model: Literal["tju-llm"] = "tju-llm"
    tju_show_token_usage: bool = True
    tju_timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    tju_max_retries: int = Field(default=2, ge=0, le=5)

    max_tool_rounds: int = Field(default=6, ge=1, le=20)
    max_history_messages: int = Field(default=20, ge=1, le=200)
    max_sessions: int = Field(default=500, ge=1, le=10_000)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    diagnosis_history_enabled: bool = True
    diagnosis_db_path: Path = PROJECT_ROOT / "data" / "netpilot.db"
    diagnosis_max_records: int = Field(default=1000, ge=1, le=100_000)
    diagnosis_report_max_bytes: int = Field(
        default=1_000_000,
        ge=1024,
        le=5_000_000,
    )

    tool_mode: ToolMode = ToolMode.MOCK
    mock_scenario: MockScenario = MockScenario.HEALTHY
    network_timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)
    scenario_switch_enabled: bool = False

    rag_enabled: bool = True
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    rag_top_k: int = Field(default=4, ge=1, le=20)
    rag_min_score: float = Field(default=0.35, ge=-1.0, le=1.0)
    rag_chunk_size: int = Field(default=700, ge=200, le=4000)
    rag_chunk_overlap: int = Field(default=120, ge=0, le=1000)
    rag_index_dir: Path = PROJECT_ROOT / "knowledge" / "index"
    rag_model_cache_dir: Path = PROJECT_ROOT / ".cache" / "fastembed"

    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    debug: bool = False

    @field_validator("tju_api_base")
    @classmethod
    def validate_tju_api_base(cls, value: str) -> str:
        """Require an HTTP(S) SDK base URL, not a completion endpoint."""

        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("TJU_API_BASE must be an absolute HTTP(S) URL")
        if parsed.query or parsed.fragment:
            raise ValueError("TJU_API_BASE must not contain a query or fragment")
        if normalized.endswith("/chat/completions"):
            raise ValueError("TJU_API_BASE must stop before /chat/completions")
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

    @property
    def llm_configured(self) -> bool:
        """Return whether a non-empty TJU API key is available without exposing it."""

        if self.tju_api_key is None:
            return False
        return bool(self.tju_api_key.get_secret_value().strip())
