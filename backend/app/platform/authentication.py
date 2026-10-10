from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.service import Identity, authenticate
from app.platform.config import get_settings
from app.platform.errors import AppError
from app.platform.uow import transaction


async def current_identity(request: Request, authorization: str | None = Header(default=None),
                           db: AsyncSession = Depends(transaction)) -> Identity:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError("AUTH_INVALID_CREDENTIALS", "请先登录。", 401)
    identity = await authenticate(db, authorization[7:], get_settings())
    request.state.actor_id = identity.user_id
    return identity
