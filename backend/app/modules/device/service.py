from uuid import UUID
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.audit import service as audit
from app.modules.auth.models import DeviceSession
from app.modules.auth.service import codec
from app.modules.auth.tokens import digest
from app.modules.device.models import DeviceBinding
from app.modules.family import service as family
from app.platform.errors import AppError
from app.platform.identifiers import utcnow
from app.platform.pagination import page_rows


async def require_active_binding(db: AsyncSession, binding_id: UUID, owner_id: UUID) -> None:
    binding = await db.get(DeviceBinding, binding_id)
    if not binding or binding.owner_user_id != owner_id or binding.status != "ACTIVE":
        raise AppError("AUTH_SESSION_REVOKED", "设备绑定已失效，请重新登录。", 401)


def view(row):
    return dict(id=str(row.id), family_id=str(row.family_id), owner_user_id=str(row.owner_user_id),
                client_kind=row.client_kind, device_type=row.device_type, status=row.status,
                last_seen_at=row.last_seen_at, created_at=row.created_at)


async def current_binding(db, actor, family_id=None):
    session = await db.get(DeviceSession, actor.session_id)
    row = await db.get(DeviceBinding, session.device_binding_id) if session.device_binding_id else None
    if not row or row.status != 'ACTIVE' or row.owner_user_id != actor.user_id or not row.family_id:
        raise AppError('DEVICE_REGISTRATION_REQUIRED', '请先为当前家庭注册设备。', 409)
    if family_id is not None and row.family_id != family_id:
        raise AppError('DEVICE_FAMILY_MISMATCH', '设备绑定的家庭已变化，请重新选择家庭。', 409)
    _, member = await family.context(db, actor.user_id, row.family_id)
    if member.role not in ('ELDER', 'CHILD', 'CAREGIVER'):
        raise AppError('PERMISSION_DENIED', '当前家庭角色不能使用留言功能。', 403)
    row.last_seen_at = utcnow()
    session.last_seen_at = row.last_seen_at
    return row


async def register(db, actor, body, key, settings, request_id):
    _, member = await family.context(db, actor.user_id, body.family_id)
    if member.role not in ('ELDER', 'CHILD', 'CAREGIVER'):
        raise AppError('PERMISSION_DENIED', '当前家庭角色不能注册通信设备。', 403)
    expected = 'ELDER_MOBILE' if member.role == 'ELDER' else 'FAMILY_MOBILE'
    if body.client_kind != expected:
        raise AppError('PERMISSION_DENIED', '设备端类型必须与当前家庭角色一致。', 403)
    idem = audit.Idempotency(key, 'device-register', body.model_dump(mode='json'))
    previous = await idem.previous(db, actor.user_id, settings.idempotency_seconds)
    device_hash = digest(body.device_id)
    await db.execute(insert(DeviceBinding).values(device_id_hash=device_hash, owner_user_id=actor.user_id,
        family_id=body.family_id, client_kind=body.client_kind, device_type=body.device_type,
        app_version=body.app_version, os_version=body.os_version, capabilities=body.capabilities)
        .on_conflict_do_nothing(index_elements=[DeviceBinding.device_id_hash]))
    row = await db.scalar(select(DeviceBinding).where(DeviceBinding.device_id_hash == device_hash))
    if row and (row.owner_user_id != actor.user_id or row.status != 'ACTIVE'):
        raise AppError('DEVICE_UNAVAILABLE', '此设备标识不可用。', 409)
    row.family_id, row.client_kind = body.family_id, body.client_kind
    row.device_type, row.app_version, row.os_version = body.device_type, body.app_version, body.os_version
    row.capabilities = body.capabilities
    row.last_seen_at = row.updated_at = utcnow()
    await db.flush()
    session = await db.get(DeviceSession, actor.session_id)
    session.device_binding_id = row.id
    if not previous:
        await audit.record(db, actor.user_id, 'DEVICE_REGISTERED', 'DEVICE_BINDING', row.id,
                           row.family_id, request_id, metadata=idem.metadata)
    return view(row)


async def listing(db, actor, family_id, limit, cursor, settings, request_id):
    if family_id:
        await family.context(db, actor.user_id, family_id)
        families = [family_id]
    else:
        families = [fid for fid, _ in await family.visibility(db, actor.user_id)]
    from app.modules.family.models import FamilyMember
    query = select(DeviceBinding).where(DeviceBinding.family_id.in_(families), DeviceBinding.status == 'ACTIVE',
        select(FamilyMember.id).where(FamilyMember.family_id == DeviceBinding.family_id,
            FamilyMember.user_id == DeviceBinding.owner_user_id, FamilyMember.status == 'ACTIVE').exists())
    rows, page = await page_rows(db, query, DeviceBinding, codec(settings),
                               f'devices:{actor.user_id}:{family_id}', limit, cursor)
    return dict(items=[view(row) for row in rows], page=page, request_id=request_id)
