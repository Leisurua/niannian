from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import record
from app.modules.auth.models import DeviceSession, User
from app.modules.auth.tokens import TokenCodec, digest, new_refresh, refresh_device_name
from app.platform.config import Settings
from app.platform.errors import AppError
from app.platform.identifiers import utcnow, uuid7

DEMO_USERS = {
    "demo-elder": (UUID("01920000-0000-7000-8000-000000000001"), "演示老人"),
    "demo-child": (UUID("01920000-0000-7000-8000-000000000002"), "演示子女"),
    "demo-caregiver": (UUID("01920000-0000-7000-8000-000000000025"), "演示照护人"),
    "demo-other": (UUID("01920000-0000-7000-8000-000000000026"), "演示另一家庭成员"),
}


@dataclass(frozen=True)
class Identity:
    user_id: UUID
    session_id: UUID
    device_name: str
    user: dict
    issued_at: str
    last_seen_at: str


def user_view(user: User) -> dict:
    return {"id": str(user.id), "display_name": user.display_name, "timezone": user.timezone,
            "global_status": user.global_status, "accessibility_settings": user.accessibility_settings,
            "created_at": user.created_at.isoformat()}


def codec(settings: Settings) -> TokenCodec:
    return TokenCodec(settings.auth_signing_key.get_secret_value(), settings.auth_access_seconds)


async def display_names(db: AsyncSession, ids: list[UUID]) -> dict[UUID, str]:
    return dict((await db.execute(select(User.id, User.display_name).where(User.id.in_(ids), User.deleted_at.is_(None)))).all())


async def set_display_name(db: AsyncSession, user_id: UUID, name: str) -> None:
    if not name.strip():
        raise AppError("VALIDATION_ERROR", "称呼不能为空。", 422)
    await db.execute(update(User).where(User.id == user_id).values(display_name=name, updated_at=utcnow()))


async def active_user(db: AsyncSession, user_id: UUID, *, lock: bool = True) -> User:
    query = select(User).where(User.id == user_id)
    if lock:
        query = query.with_for_update()
    user = await db.scalar(query.execution_options(populate_existing=True))
    if not user or user.global_status != "ACTIVE" or user.deleted_at:
        raise AppError("AUTH_SESSION_REVOKED", "当前登录已失效，请重新登录。", 401)
    return user


async def authenticate(db: AsyncSession, bearer: str, settings: Settings) -> Identity:
    claims = codec(settings).verify(bearer)
    user = await active_user(db, UUID(claims["sub"]))
    session = await db.get(DeviceSession, UUID(claims["sid"]))
    if not session or session.user_id != user.id or session.revoked_at or session.expires_at <= utcnow():
        raise AppError("AUTH_SESSION_REVOKED", "当前登录已失效，请重新登录。", 401)
    if session.device_binding_id:
        from app.modules.device.service import require_active_binding
        await require_active_binding(db, session.device_binding_id, user.id)
    return Identity(user.id, session.id, claims["dn"], user_view(user), session.issued_at.isoformat(), session.last_seen_at.isoformat())


async def issue(db: AsyncSession, user_id: UUID, device_name: str, settings: Settings,
                request_id: str, *, binding_id: UUID | None = None) -> tuple[dict, DeviceSession]:
    signer = codec(settings)
    refresh = new_refresh(device_name)
    now = utcnow()
    row = DeviceSession(id=uuid7(), user_id=user_id, device_binding_id=binding_id,
                        refresh_token_hash=digest(refresh), issued_at=now,
                        expires_at=now + timedelta(seconds=settings.auth_refresh_seconds), last_seen_at=now)
    db.add(row)
    await db.flush()
    return {"access_token": signer.access(user_id, row.id, device_name, now), "refresh_token": refresh,
            "token_type": "Bearer", "expires_in": settings.auth_access_seconds}, row


async def login(db: AsyncSession, body, settings: Settings, request_id: str) -> dict:
    codec(settings)
    if settings.provider_mode != "mock" or body.credential.type != "DEMO" or body.credential.identifier not in DEMO_USERS:
        raise AppError("AUTH_INVALID_CREDENTIALS", "仅支持虚构 DEMO 账户，请检查演示配置。", 401)
    user_id, name = DEMO_USERS[body.credential.identifier]
    await db.execute(insert(User).values(id=user_id, display_name=name).on_conflict_do_nothing(index_elements=[User.id]))
    user = await active_user(db, user_id)
    pair, session = await issue(db, user.id, body.device.name, settings, request_id)
    await record(db, user.id, "DEMO_LOGIN", "DEVICE_SESSION", session.id, request_id=request_id,
                 metadata={"provider": "mock", "device_id_hash": digest(body.device.device_id)})
    from app.modules.family.service import summaries
    return {**pair, "user": user_view(user), "families": await summaries(db, user.id),
            "device_session": {"id": str(session.id), "device_name": body.device.name,
                               "created_at": session.issued_at.isoformat()}}


async def refresh(db: AsyncSession, token: str, settings: Settings, request_id: str) -> dict:
    codec(settings)
    row = await db.scalar(select(DeviceSession).where(DeviceSession.refresh_token_hash == digest(token)))
    if not row:
        raise AppError("AUTH_INVALID_CREDENTIALS", "登录凭证无效，请重新登录。", 401)
    await active_user(db, row.user_id)
    await db.refresh(row)
    if row.revoked_at:
        if row.logout_reason == "ROTATED":
            await db.execute(update(DeviceSession).where(DeviceSession.user_id == row.user_id,
                             DeviceSession.revoked_at.is_(None)).values(revoked_at=utcnow(), logout_reason="REFRESH_REUSED"))
            await record(db, row.user_id, "AUTH_REFRESH_REUSED", "DEVICE_SESSION", row.id, request_id=request_id, result="DENIED")
            await db.commit()
            raise AppError("AUTH_REFRESH_REUSED", "检测到旧登录凭证重用，请在各设备重新登录。", 401)
        raise AppError("AUTH_SESSION_REVOKED", "当前登录已失效，请重新登录。", 401)
    if row.expires_at <= utcnow():
        raise AppError("AUTH_TOKEN_EXPIRED", "登录已过期，请重新登录。", 401)
    if row.device_binding_id:
        from app.modules.device.service import require_active_binding
        await require_active_binding(db, row.device_binding_id, row.user_id)
    name = refresh_device_name(token)
    row.revoked_at, row.logout_reason = utcnow(), "ROTATED"
    pair, replacement = await issue(db, row.user_id, name, settings, request_id, binding_id=row.device_binding_id)
    await record(db, row.user_id, "AUTH_REFRESH_ROTATED", "DEVICE_SESSION", replacement.id, request_id=request_id)
    return pair


async def logout(db: AsyncSession, actor: Identity, request_id: str, all_devices: bool = False) -> None:
    query = update(DeviceSession).where(DeviceSession.user_id == actor.user_id, DeviceSession.revoked_at.is_(None))
    if not all_devices:
        query = query.where(DeviceSession.id == actor.session_id)
    await db.execute(query.values(revoked_at=utcnow(), logout_reason="LOGOUT_ALL" if all_devices else "LOGOUT"))
    await record(db, actor.user_id, "AUTH_LOGOUT_ALL" if all_devices else "AUTH_LOGOUT", "DEVICE_SESSION",
                 actor.session_id, request_id=request_id)
