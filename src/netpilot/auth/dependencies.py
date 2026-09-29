"""One cookie-auth dependency for current and future protected routes."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from netpilot.auth.models import UserRecord
from netpilot.auth.repository import AuthStorageError
from netpilot.auth.service import AuthService


def auth_service(request: Request) -> AuthService:
    """Lazily initialize auth tables without changing existing app startup behavior."""

    service: AuthService | None = request.app.state.auth_service
    if service is not None:
        return service
    with request.app.state.auth_lock:
        service = request.app.state.auth_service
        if service is None:
            settings = request.app.state.settings
            try:
                service = AuthService(
                    settings.diagnosis_db_path,
                    session_hours=settings.auth_session_hours,
                    max_sessions=settings.auth_max_active_sessions_per_user,
                )
            except AuthStorageError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="认证服务暂时不可用。",
                ) from exc
            request.app.state.auth_service = service
    return service


def require_current_user(request: Request) -> UserRecord:
    settings = request.app.state.settings
    token = request.cookies.get(settings.auth_cookie_name)
    try:
        user = auth_service(request).current_user(token)
    except AuthStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="认证服务暂时不可用。",
        ) from exc
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录。",
        )
    return user
