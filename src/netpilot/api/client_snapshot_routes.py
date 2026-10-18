"""Bounded authenticated multipart transport; all snapshot logic lives separately."""

from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from python_multipart.exceptions import MultipartParseError

from netpilot.auth.dependencies import require_current_user
from netpilot.auth.models import UserRecord
from netpilot.agent.session import SessionBusyError, SessionCapacityError, SessionNotFoundError
from netpilot.client_snapshot.validation import parse_snapshot, SnapshotValidationError
from netpilot.history import DiagnosisStorageError
from netpilot.models.schemas import SessionResponse

router = APIRouter()
CurrentUser = Annotated[UserRecord, Depends(require_current_user)]
SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "client_diagnostic_windows.ps1"


@router.get("/static/scripts/client_diagnostic_windows.ps1", include_in_schema=False)
def download_script():
    return FileResponse(SCRIPT_PATH, media_type="application/octet-stream", filename="client_diagnostic_windows.ps1", headers={"X-Content-Type-Options":"nosniff"})


@router.post("/api/session/client-snapshot", tags=["chat"])
async def upload_snapshot(request: Request, response: Response, user: CurrentUser):
    """No uploaded filename is ever used as a filesystem path."""
    origin = request.headers.get("origin")
    try:
        parsed_origin = urlsplit(origin) if origin else None
    except ValueError as exc:
        raise HTTPException(403, "上传来源格式不正确。") from exc
    if request.headers.get("sec-fetch-site") == "cross-site" or (parsed_origin and (parsed_origin.scheme, parsed_origin.netloc) != (request.url.scheme, request.url.netloc)):
        raise HTTPException(403, "跨站快照上传被拒绝。")
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data;"):
        raise HTTPException(415, "请通过 multipart/form-data 上传一个 JSON 文件及 session_id。")
    settings = request.app.state.settings
    response.headers["Cache-Control"] = "no-store"
    limit = settings.client_snapshot_max_bytes
    total = 0

    async def bounded_stream():
        nonlocal total
        async for chunk in request.stream():
            total += len(chunk)
            if total > limit + 16384:
                # MultiPartException also closes parser temporary handles.
                raise MultiPartException("snapshot_body_too_large")
            yield chunk

    form = None
    try:
        parser = MultiPartParser(request.headers, bounded_stream(), max_files=1, max_fields=1, max_part_size=256)
        form = await parser.parse()
        if set(form) != {"session_id", "file"} or len(form.multi_items()) != 2:
            raise HTTPException(422, "只接受 session_id 和一个 JSON 文件。")
        sid_value, file = form["session_id"], form["file"]
        if not isinstance(sid_value, str) or not isinstance(file, UploadFile):
            raise HTTPException(422, "上传字段类型不正确。")
        try:
            sid = UUID(sid_value)
        except ValueError as exc:
            raise HTTPException(422, "session_id 格式不正确。") from exc
        sessions = request.app.state.sessions
        session = sessions.get(sid, user.id)
        if not (file.filename or "").lower().endswith(".json"):
            raise HTTPException(415, "仅接受 .json 快照。")
        raw = await file.read(limit + 1)
        snapshot, digest = parse_snapshot(raw, max_bytes=limit)
        del raw

        def persist(task):
            repository = request.app.state.diagnosis_repository
            if repository is not None:
                return repository.update_client_snapshot(user.id, sid, task)
            if settings.diagnosis_history_enabled:
                raise DiagnosisStorageError("诊断历史不可用")
            return False

        task, duplicate, events = sessions.import_client_snapshot(
            sid, user.id, snapshot, digest,
            freshness_minutes=settings.client_snapshot_freshness_minutes, persist=persist,
        )
        del snapshot
        body = SessionResponse(
            session_id=sid, created_at=session.created_at,
            environment_profile=task.environment_profile, diagnostic_target=task.diagnostic_target,
            client_snapshot_summary=task.client_snapshot_summary,
            remediation_plan=task.remediation_plan,
            remediation_plan_history=task.remediation_plan_history,
            remediation_readiness=task.remediation_readiness,
            client_evidence=[item for item in task.evidence if item.evidence_origin == "client_snapshot"],
        ).model_dump(mode="json")
        body.update(snapshot_id=task.client_snapshot_id, snapshot_sequence=task.snapshot_sequence,
                    duplicate=duplicate, reasoning_trace=[item.model_dump(mode="json") for item in events])
        return body
    except MultiPartException as exc:
        raise HTTPException(413 if total > limit + 16384 else 422, "上传超过大小限制或 multipart 结构不符合要求。") from exc
    except MultipartParseError as exc:
        raise HTTPException(422, "multipart 上传格式不正确。") from exc
    except SnapshotValidationError as exc:
        raise HTTPException(413 if exc.code == "file_too_large" else 422, "快照被拒绝：" + exc.code) from exc
    except SessionNotFoundError as exc:
        raise HTTPException(404, "会话不存在或已失效。") from exc
    except SessionBusyError as exc:
        raise HTTPException(409, "当前会话正在诊断，请完成后上传。") from exc
    except SessionCapacityError as exc:
        raise HTTPException(409, "此会话的快照归档已满，请创建新会话。") from exc
    except DiagnosisStorageError as exc:
        raise HTTPException(503, "快照保存失败，请稍后重试。") from exc
    except ValueError as exc:
        raise HTTPException(409, "请先选择远程的当前浏览器设备；Mock/服务主机不接受客户端快照。") from exc
    finally:
        if form is not None:
            await form.close()
