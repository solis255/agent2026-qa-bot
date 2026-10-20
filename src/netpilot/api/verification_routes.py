from netpilot.demo.runtime import store_for, runtime_for
"""Authenticated verification endpoints; no arbitrary tool arguments accepted."""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Response
from netpilot.api.remediation_routes import CurrentUser
from netpilot.agent.session import SessionBusyError, SessionNotFoundError
from netpilot.history import DiagnosisStorageError
from netpilot.verification.models import VerificationRequest, ObservationRequest, UserVerificationObservation

router = APIRouter()


def operate(request,user,sid,**kwargs):
    def persist(task):
        repository = request.app.state.diagnosis_repository
        if repository is not None: return repository.update_remediation(user.id,sid,task)
        if request.app.state.settings.diagnosis_history_enabled: raise DiagnosisStorageError("history_unavailable")
        return False
    try:
        with request.app.state.runtime_lock:
            task,events = store_for(request, sid).verification(sid,user.id,registry=(runtime_for(request, sid).registry if runtime_for(request, sid) else request.app.state.tool_registry),persist=persist,**kwargs)
        from netpilot.api.presenters import _present_tool_call
        return {"session_id":str(sid),"verification_cycles":[c.model_dump(mode="json") for c in task.verification_cycles],
                "resolution":task.resolution.model_dump(mode="json"),"resolution_transitions":[t.model_dump(mode="json") for t in task.resolution_transitions],
                "verification_tool_calls":[_present_tool_call(s).model_dump(mode="json") for s in task.verification_tool_steps],
                "reasoning_trace":[e.model_dump(mode="json") for e in events],"task_version":task.task_version}
    except SessionNotFoundError as exc: raise HTTPException(404,"会话不存在或已失效。") from exc
    except SessionBusyError as exc: raise HTTPException(409,"会话正在处理，请稍后验证。") from exc
    except KeyError as exc: raise HTTPException(404,"没有当前验证记录。") from exc
    except ValueError as exc: raise HTTPException(409,"验证已失效或尚未完成手动步骤，请刷新并核对诊断对象和计划。") from exc
    except DiagnosisStorageError as exc: raise HTTPException(503,"验证保存失败，请稍后重试。") from exc


@router.get("/session/verification",tags=["verification"])
def get_verification(session_id:UUID,request:Request,response:Response,user:CurrentUser):
    response.headers["Cache-Control"] = "no-store"
    return operate(request,user,session_id)


@router.post("/session/verification",tags=["verification"])
def create_verification(payload:VerificationRequest,request:Request,response:Response,user:CurrentUser):
    response.headers["Cache-Control"] = "no-store"
    return operate(request,user,payload.session_id,action="create",reverify=payload.reverify)


@router.post("/session/verification/{verification_id}/start",tags=["verification"])
def start_verification(verification_id:UUID,payload:VerificationRequest,request:Request,response:Response,user:CurrentUser):
    response.headers["Cache-Control"] = "no-store"
    if payload.reverify: raise HTTPException(422,"请使用创建接口显式重新验证。")
    return operate(request,user,payload.session_id,action="start",cycle_id=verification_id)


@router.post("/session/verification/{verification_id}/user-observation",tags=["verification"])
def observation(verification_id:UUID,payload:ObservationRequest,request:Request,response:Response,user:CurrentUser):
    response.headers["Cache-Control"] = "no-store"
    value = UserVerificationObservation(**payload.model_dump(exclude={"session_id"}))
    return operate(request,user,payload.session_id,action="observation",cycle_id=verification_id,observation=value)
