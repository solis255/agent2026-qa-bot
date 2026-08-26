"""Validated document, chunk, index, and search contracts for NetPilot RAG."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _require_web_source(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source must be an absolute HTTP(S) URL")
    return value


class SourceType(str, Enum):
    OFFICIAL = "official"
    COMMUNITY = "community"
    MAINTAINER = "maintainer"


class KnowledgeDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    source: str = Field(min_length=1, max_length=2000)
    source_type: SourceType
    file: str = Field(min_length=1, max_length=1000)
    content: str = Field(min_length=1, max_length=2_000_000)
    retrieved_at: str | None = Field(default=None, max_length=64)

    @field_validator("retrieved_at", mode="before")
    @classmethod
    def normalize_yaml_date(cls, value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value

    @field_validator("title", "source", "file", "content", "retrieved_at")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("source")
    @classmethod
    def require_web_source(cls, value: str) -> str:
        return _require_web_source(value)


class KnowledgeChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=8, max_length=64)
    title: str = Field(min_length=1, max_length=300)
    source: str = Field(min_length=1, max_length=2000)
    source_type: SourceType
    file: str = Field(min_length=1, max_length=1000)
    content: str = Field(min_length=1, max_length=10_000)

    @field_validator("source")
    @classmethod
    def require_web_source(cls, value: str) -> str:
        return _require_web_source(value)


class KnowledgeSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=2,
        max_length=500,
        description="需要从校园网络知识库检索的问题或关键词",
    )

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("query is too short")
        return normalized


class KnowledgeSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    source: str
    source_type: SourceType
    file: str
    chunk_id: str
    content: str
    score: float = Field(ge=-1.0, le=1.0)

    @field_validator("source")
    @classmethod
    def require_web_source(cls, value: str) -> str:
        return _require_web_source(value)


class KnowledgeSearchData(BaseModel):
    results: list[KnowledgeSearchResult] = Field(default_factory=list)


class KnowledgeSource(BaseModel):
    """Compact citation exposed by AgentResult and the future Web API."""

    title: str
    source: str
    source_type: SourceType
    file: str
    chunk_id: str
    score: float = Field(ge=-1.0, le=1.0)

    @field_validator("source")
    @classmethod
    def require_web_source(cls, value: str) -> str:
        return _require_web_source(value)


class IndexManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    embedding_model: str = Field(min_length=1)
    dimension: int = Field(ge=1)
    document_count: int = Field(ge=1)
    chunk_count: int = Field(ge=1)
    chunk_size: int = Field(ge=1)
    chunk_overlap: int = Field(ge=0)
    built_at: datetime
    source_files: list[str] = Field(min_length=1)

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
