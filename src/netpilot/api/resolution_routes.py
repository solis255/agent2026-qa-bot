"""Explicit authenticated case confirmation/support recommendation, not tickets."""
from uuid import UUID
from fastapi import APIRouter,HTTPException,Request,Response
from netpilot.api.presenters import present_session
from netpilot.api.remediation_routes import CurrentUser
from netpilot.agent.session import SessionBusyError,SessionNotFoundError
from netpilot.chat_actions.validation import StaleChatActionError
from netpilot.demo.runtime import store_for
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
        sessions = store_for(request, sid)
        task, events = sessions.resolution_action(sid, user.id, persist=persist, **kwargs)
        body = present_session(task, sessions.get(sid, user.id).created_at).model_dump(mode="json")
        body["reasoning_trace"] = [event.model_dump(mode="json") for event in events]
        return body
    except SessionNotFoundError as exc: raise HTTPException(404,"会话不存在或已失效。") from exc
    except SessionBusyError as exc: raise HTTPException(409,"会话正在处理，请稍后确认。") from exc
    except StaleChatActionError as exc: raise HTTPException(409, exc.message) from exc
    except ValueError as exc: raise HTTPException(409,"当前案例状态发生变化，请刷新后重试。") from exc
    except DiagnosisStorageError as exc: raise HTTPException(503,"处理状态保存失败，请稍后重试。") from exc


@router.get("/session/resolution",tags=["resolution"])
def get_resolution(session_id:UUID,request:Request,response:Response,user:CurrentUser):
    response.headers["Cache-Control"]="no-store"
    return operate(request,user,session_id)


@router.post("/session/resolution/confirm",tags=["resolution"])
def confirm(payload:ConfirmationRequest,request:Request,response:Response,user:CurrentUser):
    response.headers["Cache-Control"]="no-store"
    return operate(request,user,payload.session_id,action="confirm",confirmation=payload.status,submission=payload)


@router.post("/session/resolution/request-support",tags=["resolution"])
def request_support(payload:ResolutionRequest,request:Request,response:Response,user:CurrentUser):
    response.headers["Cache-Control"]="no-store"
    return operate(request,user,payload.session_id,action="support")
