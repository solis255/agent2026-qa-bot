"""Authenticated artifact generation/read/export; no external submission routes."""
import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from netpilot.api.remediation_routes import CurrentUser
from netpilot.agent.session import SessionNotFoundError, SessionBusyError
from netpilot.escalation.models import EscalationPackage, PackageRequest
from netpilot.escalation.builder import state_fingerprint
from netpilot.escalation.exports import export_package
from netpilot.history import DiagnosisStorageError
from netpilot.reports import DiagnosisReportTooLargeError

router = APIRouter()
logger = logging.getLogger(__name__)


def _view(request, user, sid, *, generate=False):
    repository=request.app.state.diagnosis_repository
    def persist(task):
        if repository is not None: return repository.update_escalation(user.id,sid,task)
        if request.app.state.settings.diagnosis_history_enabled: raise DiagnosisStorageError("history_unavailable")
        return False
    try:
        task,events=request.app.state.sessions.escalation(sid,user.id,generate=generate,persist=persist)
        store=request.app.state.sessions
        try:
            fingerprint=state_fingerprint(task,max_evidence=store.escalation_max_evidence_items,policy=store.escalation_privacy_policy)
        except Exception as exc:
            # An unavailable current builder must not make an already-created
            # immutable artifact impossible to read/export.
            logger.warning("escalation_freshness_unavailable: %s",type(exc).__name__)
            fingerprint=None
        return {"session_id":str(sid),"packages":[p.model_dump(mode="json") for p in task.escalation_packages],
                "stale_package_ids":[str(p.package_id) for p in task.escalation_packages if p.source_state_fingerprint != fingerprint],
                "historical":False,"freshness_unknown":fingerprint is None,
                "persistence":"sqlite" if repository is not None else "memory",
                "reasoning_trace":[e.model_dump(mode="json") for e in events]}
    except SessionNotFoundError as exc:
        if not generate and repository is not None:
            packages=repository.escalation_packages(user.id,sid)
            if packages:
                return {"session_id":str(sid),"packages":[p.model_dump(mode="json") for p in packages],"historical":True,
                    "stale_package_ids":[],"reasoning_trace":[]}
        raise HTTPException(404,"会话或报修材料不存在。") from exc
    except SessionBusyError as exc: raise HTTPException(409,"会话正在处理，请稍后重试。") from exc


def view(request,user,sid,*,generate=False):
    try: return _view(request,user,sid,generate=generate)
    except HTTPException: raise
    except DiagnosisStorageError as exc: raise HTTPException(503,"报修材料存储暂不可用，请稍后重试。") from exc
    except Exception as exc:
        logger.warning("escalation_failed: %s",type(exc).__name__)
        raise HTTPException(503,"报修材料暂时生成或读取失败，原诊断状态已保留。") from exc


@router.post("/session/escalation-package",tags=["escalation"])
def generate(payload:PackageRequest,request:Request,response:Response,user:CurrentUser):
    response.headers["Cache-Control"]="no-store"
    return view(request,user,payload.session_id,generate=True)


@router.get("/session/escalation-package",tags=["escalation"])
def packages(session_id:UUID,request:Request,response:Response,user:CurrentUser):
    response.headers["Cache-Control"]="no-store"
    return view(request,user,session_id)


def get_package(request,user,sid,pid):
    data=view(request,user,sid)
    for p in data["packages"]:
        if p["package_id"] == str(pid): return EscalationPackage.model_validate(p)
    raise HTTPException(404,"报修材料不存在。")


@router.get("/session/escalation-package/{package_id}",response_model=EscalationPackage,tags=["escalation"])
def package(package_id:UUID,session_id:UUID,request:Request,response:Response,user:CurrentUser):
    response.headers["Cache-Control"]="no-store"
    return get_package(request,user,session_id,package_id)


@router.get("/session/escalation-package/{package_id}/export",tags=["escalation"])
def export(package_id:UUID,session_id:UUID,request:Request,user:CurrentUser,format:Literal["md","json"]="md"):
    p=get_package(request,user,session_id,package_id)
    try:
        artifact=export_package(p,format,max_bytes=request.app.state.settings.diagnosis_report_max_bytes)
    except DiagnosisReportTooLargeError as exc: raise HTTPException(413,"报修材料超过导出大小限制。") from exc
    except ValueError as exc: raise HTTPException(503,"报修材料完整性校验失败。") from exc
    return Response(artifact.content,media_type=artifact.media_type,headers={"Cache-Control":"no-store",
        "Content-Disposition":f'attachment; filename="{artifact.filename}"',"X-Content-Type-Options":"nosniff"})
