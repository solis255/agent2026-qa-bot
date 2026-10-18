"""Manual plan generation/feedback only. There is intentionally no execute API."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from netpilot.agent.session import SessionBusyError, SessionNotFoundError
from netpilot.auth.dependencies import require_current_user
from netpilot.auth.models import UserRecord
from netpilot.history import DiagnosisStorageError
from netpilot.remediation.models import RemediationRequest, StepFeedback

router=APIRouter()
CurrentUser=Annotated[UserRecord,Depends(require_current_user)]


def operate(request,user,session_id,**kwargs):
    def persist(task):
        repository=request.app.state.diagnosis_repository
        if repository is not None: return repository.update_remediation(user.id,session_id,task)
        if request.app.state.settings.diagnosis_history_enabled: raise DiagnosisStorageError("history_unavailable")
        return False
    try:
        task,events=request.app.state.sessions.remediation(session_id,user.id,
            max_steps=request.app.state.settings.remediation_max_steps,persist=persist,**kwargs)
        return {"session_id":str(session_id),"remediation_plan":task.remediation_plan.model_dump(mode="json") if task.remediation_plan else None,
                "remediation_plan_history":[item.model_dump(mode="json") for item in task.remediation_plan_history],
                "remediation_readiness":task.remediation_readiness.model_dump(),
                "reasoning_trace":[item.model_dump(mode="json") for item in events]}
    except SessionNotFoundError as exc:
        raise HTTPException(404,"会话不存在或已失效。") from exc
    except SessionBusyError as exc:
        raise HTTPException(409,"会话正在诊断，请稍后操作修复计划。") from exc
    except KeyError as exc:
        raise HTTPException(404,"当前计划中没有此步骤。") from exc
    except ValueError as exc:
        raise HTTPException(409,"计划已失效或步骤已结束，请刷新；P0 不支持重新打开已结束步骤。") from exc
    except DiagnosisStorageError as exc:
        raise HTTPException(503,"修复计划保存失败，请稍后重试。") from exc


@router.get("/session/remediation-plan",tags=["remediation"])
def get_plan(session_id:UUID,request:Request,response:Response,user:CurrentUser):
    response.headers["Cache-Control"]="no-store"
    return operate(request,user,session_id)


@router.post("/session/remediation-plan",tags=["remediation"])
def create_plan(payload:RemediationRequest,request:Request,response:Response,user:CurrentUser):
    response.headers["Cache-Control"]="no-store"
    return operate(request,user,payload.session_id,generate=True)


@router.patch("/session/remediation-plan/steps/{step_id}",tags=["remediation"])
def feedback(step_id:UUID,payload:StepFeedback,request:Request,response:Response,user:CurrentUser):
    response.headers["Cache-Control"]="no-store"
    return operate(request,user,payload.session_id,step_id=step_id,feedback=payload)
