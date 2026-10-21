"""Fixed collector assets and owner-scoped client-check decisions, not a new upload API."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.responses import PlainTextResponse

from netpilot.api.remediation_routes import CurrentUser
from netpilot.api.presenters import present_session
from netpilot.agent.session import SessionNotFoundError, SessionBusyError
from netpilot.client_snapshot.check_models import ClientCheckDecline, CollectorMetadata
from netpilot.client_snapshot.check_flow import check_answer
from netpilot.demo.runtime import store_for

router = APIRouter()
SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
COLLECTOR = "client_diagnostic_windows.ps1"
WRAPPER = "run_client_diagnostic_windows.cmd"


def collector_bundle():
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for name in (COLLECTOR, WRAPPER):
            archive.writestr(ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), (SCRIPTS / name).read_bytes())
    return output.getvalue()


@router.get("/static/client-tools/netpilot-windows-check.zip", include_in_schema=False)
def download_bundle():
    return Response(collector_bundle(), media_type="application/zip", headers={
        "Content-Disposition":'attachment; filename="netpilot-windows-check.zip"', "X-Content-Type-Options":"nosniff"})


@router.get("/static/client-tools/client_diagnostic_windows.ps1", include_in_schema=False)
def download_collector():
    return FileResponse(SCRIPTS / COLLECTOR, media_type="application/octet-stream", filename=COLLECTOR)


@router.get("/static/client-tools/run_client_diagnostic_windows.cmd", include_in_schema=False)
def download_wrapper():
    return FileResponse(SCRIPTS / WRAPPER, media_type="application/octet-stream", filename=WRAPPER)


@router.get("/api/client-tools/windows", response_model=CollectorMetadata, tags=["chat"])
def collector_metadata():
    return CollectorMetadata(collector_version="windows-readonly-v1", sha256={
        COLLECTOR:sha256((SCRIPTS / COLLECTOR).read_bytes()).hexdigest(),
        WRAPPER:sha256((SCRIPTS / WRAPPER).read_bytes()).hexdigest(),
        "netpilot-windows-check.zip":sha256(collector_bundle()).hexdigest()})


@router.post("/api/session/client-check/decline", tags=["chat"])
def decline_check(payload: ClientCheckDecline, request: Request, user: CurrentUser):
    sessions = store_for(request, payload.session_id)
    try:
        task = sessions.decline_client_check(payload, user.id)
        body = present_session(task, sessions.get(payload.session_id, user.id).created_at).model_dump(mode="json")
        body["feedback"] = check_answer(refused=True)
        return body
    except SessionNotFoundError as exc:
        raise HTTPException(404, "会话不存在或已失效。") from exc
    except SessionBusyError as exc:
        raise HTTPException(409, "当前会话正在处理，请稍后重试。") from exc
    except ValueError as exc:
        raise HTTPException(409, "这次网络检查已失效，请根据当前会话继续。") from exc


@router.get("/api/client-tools/windows/source", include_in_schema=False)
def collector_source():
    return PlainTextResponse((SCRIPTS / COLLECTOR).read_text(encoding="utf-8"), headers={"X-Content-Type-Options":"nosniff"})
