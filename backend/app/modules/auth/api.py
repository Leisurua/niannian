from collections import OrderedDict
import logging
import time

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth import service
from app.modules.auth.schemas import LoginRequest, RefreshRequest
from app.modules.auth.tokens import digest
from app.platform.authentication import current_identity
from app.platform.config import get_settings
from app.platform.errors import AppError
from app.platform.logging import log_event
from app.platform.uow import transaction

router = APIRouter(prefix="/v1", tags=["Auth"])
_attempts: OrderedDict[str, tuple[float, int]] = OrderedDict()


def limit_login(request: Request) -> None:
    key = digest(request.client.host if request.client else "unknown")
    now = time.monotonic()
    start, count = _attempts.get(key, (now, 0))
    if now - start >= 60:
        start, count = now, 0
    _attempts[key] = (start, count + 1)
    _attempts.move_to_end(key)
    while len(_attempts) > 2048:
        _attempts.popitem(last=False)
    if count >= get_settings().auth_login_limit:
        raise AppError("AUTH_LOGIN_RATE_LIMITED", "尝试次数较多，请稍后重试。", 429)


@router.post("/auth/login", status_code=201, operation_id="login")
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(transaction)):
    limit_login(request)
    try:
        result = await service.login(db, body, get_settings(), request.state.request_id)
    except AppError:
        log_event(logging.getLogger("nianian.auth"), logging.WARNING, "AUTH_LOGIN_DENIED")
        raise
    return {**result, "request_id": request.state.request_id}


@router.post("/auth/refresh", operation_id="refreshAccessToken")
async def refresh(body: RefreshRequest, request: Request, db: AsyncSession = Depends(transaction)):
    return {**await service.refresh(db, body.refresh_token.get_secret_value(), get_settings(), request.state.request_id),
            "request_id": request.state.request_id}


@router.post("/auth/logout", status_code=204, operation_id="logout")
async def logout(request: Request, actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    await service.logout(db, actor, request.state.request_id)
    return Response(status_code=204)


@router.post("/auth/logout-all", status_code=204, operation_id="logoutAll")
async def logout_all(request: Request, actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    await service.logout(db, actor, request.state.request_id, all_devices=True)
    return Response(status_code=204)


@router.get("/me", operation_id="getCurrentUser")
async def me(request: Request, actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    from app.modules.family.service import own_memberships
    return {"user": actor.user, "family_memberships": await own_memberships(db, actor.user_id),
            "active_device_session": {"id": str(actor.session_id), "device_name": actor.device_name,
                                      "created_at": actor.issued_at, "last_seen_at": actor.last_seen_at},
            "request_id": request.state.request_id}
