from netpilot.demo.runtime import store_for, runtime_for
"""Explicit authenticated case confirmation/support recommendation, not tickets."""
from uuid import UUID
from fastapi import APIRouter,HTTPException,Request,Response
from netpilot.api.remediation_routes import CurrentUser
from netpilot.agent.session import SessionBusyError,SessionNotFoundError
from netpilot.history import DiagnosisStorageError
from netpilot.resolution.models import ConfirmationRequest,ResolutionRequest

router=APIRouter()


def operate(request,user,sid,**kwargs):
    def persist(task):
        repository=request.app.state.diagnosis_repository
        if repository is not None: return repository.update_resolution(user.id,sid,task)
        if request.app.state.settings.diagnosis_history_enabled: raise DiagnosisStorageError("history_unavailable")
        return False
    try:
        task,events=store_for(request, sid).resolution_action(sid,user.id,persist=persist,**kwargs)
        return {"session_id":str(sid),"resolution":task.resolution.model_dump(mode="json"),
            "resolution_transitions":[t.model_dump(mode="json") for t in task.resolution_transitions],
            "reasoning_trace":[e.model_dump(mode="json") for e in events],"task_version":task.task_version}
    except SessionNotFoundError as exc: raise HTTPException(404,"会话不存在或已失效。") from exc
    except SessionBusyError as exc: raise HTTPException(409,"会话正在处理，请稍后确认。") from exc
    except ValueError as exc: raise HTTPException(409,"当前案例状态发生变化，请刷新后重试。") from exc
    except DiagnosisStorageError as exc: raise HTTPException(503,"处理状态保存失败，请稍后重试。") from exc


@router.get("/session/resolution",tags=["resolution"])
def get_resolution(session_id:UUID,request:Request,response:Response,user:CurrentUser):
    response.headers["Cache-Control"]="no-store"
    return operate(request,user,session_id)


@router.post("/session/resolution/confirm",tags=["resolution"])
def confirm(payload:ConfirmationRequest,request:Request,response:Response,user:CurrentUser):
    response.headers["Cache-Control"]="no-store"
    return operate(request,user,payload.session_id,action="confirm",confirmation=payload.status)


@router.post("/session/resolution/request-support",tags=["resolution"])
def request_support(payload:ResolutionRequest,request:Request,response:Response,user:CurrentUser):
    response.headers["Cache-Control"]="no-store"
    return operate(request,user,payload.session_id,action="support")
