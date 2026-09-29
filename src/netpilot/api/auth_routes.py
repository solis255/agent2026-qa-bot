"""Milestone 9A registration, login and server-side session endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from netpilot.auth.dependencies import auth_service, require_current_user
from netpilot.auth.models import UserRecord
from netpilot.auth.repository import AuthStorageError, UsernameExistsError
from netpilot.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UserView,
)
from netpilot.auth.service import AuthService, InvalidCredentialsError


router = APIRouter(prefix="/auth", tags=["auth"])
CurrentUser = Annotated[UserRecord, Depends(require_current_user)]


def _set_cookie(response: Response, request: Request, token: str) -> None:
    settings = request.app.state.settings
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_session_hours * 3600,
        path="/",
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )


def _check_origin(request: Request) -> None:
    """Reject cross-origin browser state changes when an Origin is supplied."""

    origin = request.headers.get("origin")
    if origin is not None and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(status_code=403, detail="跨站请求不被允许。")


@router.post("/register", response_model=UserView, status_code=201)
def register(payload: RegisterRequest, request: Request, response: Response) -> UserView:
    _check_origin(request)
    try:
        user, token = auth_service(request).register(
            payload.username, payload.password.get_secret_value(), payload.nickname
        )
    except UsernameExistsError as exc:
        raise HTTPException(status_code=409, detail="用户名已存在。") from exc
    except AuthStorageError as exc:
        raise HTTPException(status_code=503, detail="认证服务暂时不可用。") from exc
    _set_cookie(response, request, token)
    return UserView.from_record(user)


@router.post("/login", response_model=UserView)
def login(payload: LoginRequest, request: Request, response: Response) -> UserView:
    _check_origin(request)
    try:
        user, token = auth_service(request).login(
            payload.username, payload.password.get_secret_value()
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail="用户名或密码错误。") from exc
    except AuthStorageError as exc:
        raise HTTPException(status_code=503, detail="认证服务暂时不可用。") from exc
    _set_cookie(response, request, token)
    return UserView.from_record(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    _check_origin(request)
    settings = request.app.state.settings
    try:
        auth_service(request).logout(request.cookies.get(settings.auth_cookie_name))
    except AuthStorageError as exc:
        raise HTTPException(status_code=503, detail="认证服务暂时不可用。") from exc
    response.delete_cookie(
        settings.auth_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


@router.get("/me", response_model=UserView)
def me(user: CurrentUser) -> UserView:
    return UserView.from_record(user)


@router.post("/change-password", status_code=204)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: CurrentUser,
) -> None:
    _check_origin(request)
    try:
        token = auth_service(request).change_password(
            user,
            payload.old_password.get_secret_value(),
            payload.new_password.get_secret_value(),
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail="原密码错误。") from exc
    except AuthStorageError as exc:
        raise HTTPException(status_code=503, detail="认证服务暂时不可用。") from exc
    _set_cookie(response, request, token)
