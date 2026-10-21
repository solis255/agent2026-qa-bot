"""Small, server-owned client-check interactions; no observations or raw files."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CONTINUATION_MESSAGE = "[系统自动继续：网络检查结果已上传]"


class CheckModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClientCheckScope(CheckModel):
    task_version: int = Field(ge=1)
    target_version: int = Field(ge=1)


class ClientCheckAction(ClientCheckScope):
    type: Literal["client_check"] = "client_check"
    session_id: UUID
    action_id: UUID
    mode: Literal["initial", "recheck"]
    platform: Literal["windows"] = "windows"
    reason: str = Field(min_length=1, max_length=100, pattern=r"^[a-z_]+$")
    collector_supported: Literal[True] = True
    upload_required: Literal[True] = True


class ClientCheckReceipt(ClientCheckScope):
    receipt_id: UUID
    snapshot_id: UUID


class ClientCheckState(CheckModel):
    declined: ClientCheckScope | None = None
    pending_continuation: ClientCheckReceipt | None = None


class ClientCheckDecline(ClientCheckScope):
    session_id: UUID
    action_id: UUID


class CollectorMetadata(CheckModel):
    platform: Literal["windows"] = "windows"
    collector_version: str = Field(max_length=40)
    snapshot_schema_version: Literal[1] = 1
    sha256: dict[str, str]
