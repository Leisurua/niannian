from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit import service as audit
from app.modules.auth.service import Identity, codec, display_names, set_display_name
from app.modules.auth.tokens import digest
from app.modules.family.models import Family, FamilyInvitation, FamilyMember
from app.platform.errors import AppError
from app.platform.identifiers import utcnow, uuid7
from app.platform.pagination import page_rows

PERMISSIONS = frozenset({"MEMBER_READ", "MEMBER_ADMIN", "MEMORY_READ", "MEMORY_WRITE", "REMINDER_READ",
                         "REMINDER_WRITE", "SIGNAL_READ", "REPORT_READ", "SUMMARY_READ"})


def version(member: FamilyMember) -> int:
    return int(member.updated_at.timestamp() * 1_000_000)


def member_view(member: FamilyMember, name: str = "") -> dict:
    result = {"id": str(member.id), "family_id": str(member.family_id), "user_id": str(member.user_id),
              "display_name": name, "role": member.role, "status": member.status, "version": version(member),
              "permission_codes": sorted(k for k, enabled in member.permission_codes.items() if enabled is True)}
    if member.joined_at:
        result["joined_at"] = member.joined_at.isoformat()
    return result


def family_view(family: Family, member: FamilyMember) -> dict:
    return {"id": str(family.id), "name": family.name, "status": family.status, "role": member.role,
            "member_status": member.status, "created_by_user_id": str(family.created_by_user_id),
            "created_at": family.created_at.isoformat(), "updated_at": family.updated_at.isoformat()}


async def context(db: AsyncSession, user_id: UUID, family_id: UUID, *, admin: bool = False,
                  member_read: bool = False) -> tuple[Family, FamilyMember]:
    family = await db.scalar(select(Family).where(Family.id == family_id, Family.status == "ACTIVE",
                                                  Family.deleted_at.is_(None)).with_for_update())
    member = await db.scalar(select(FamilyMember).where(FamilyMember.family_id == family_id,
                            FamilyMember.user_id == user_id, FamilyMember.status == "ACTIVE"))
    if not family or not member:
        raise AppError("FAMILY_NOT_FOUND", "家庭不存在或当前尚无访问权限。", 404)
    is_admin = family.created_by_user_id == user_id or member.permission_codes.get("MEMBER_ADMIN") is True
    if admin and not is_admin or member_read and not is_admin and member.permission_codes.get("MEMBER_READ") is not True:
        raise AppError("PERMISSION_DENIED", "当前成员没有此项权限。", 403)
    return family, member


async def require_member(db: AsyncSession, family_id: UUID, user_id: UUID) -> FamilyMember:
    member = await db.scalar(select(FamilyMember).where(FamilyMember.family_id == family_id,
                             FamilyMember.user_id == user_id, FamilyMember.status == "ACTIVE"))
    if not member:
        raise AppError("PERMISSION_FAMILY_SCOPE_REQUIRED", "相关成员尚未加入当前家庭。", 403)
    return member


async def own_memberships(db: AsyncSession, user_id: UUID) -> list[dict]:
    rows = (await db.scalars(select(FamilyMember).join(Family).where(FamilyMember.user_id == user_id,
            FamilyMember.status.in_(["PENDING", "ACTIVE"]), Family.deleted_at.is_(None),
            Family.status != "DELETED").order_by(FamilyMember.created_at.desc(), FamilyMember.id.desc()))).all()
    names = await display_names(db, [user_id])
    return [member_view(row, names.get(user_id, "")) for row in rows]


async def summaries(db: AsyncSession, user_id: UUID) -> list[dict]:
    rows = (await db.execute(select(Family, FamilyMember).join(FamilyMember).where(
        FamilyMember.user_id == user_id, FamilyMember.status.in_(["ACTIVE", "PENDING"]),
        Family.deleted_at.is_(None), Family.status != "DELETED").order_by(Family.created_at.desc(), Family.id.desc()))).all()
    return [{k: v for k, v in family_view(family, member).items() if k in
             {"id", "name", "status", "role", "member_status"}} for family, member in rows]


async def visibility(db, user_id):
    rows = (await db.execute(select(Family.id, Family.created_by_user_id, FamilyMember.permission_codes)
            .join(FamilyMember).where(FamilyMember.user_id == user_id, FamilyMember.status == 'ACTIVE',
                                    Family.status == 'ACTIVE', Family.deleted_at.is_(None)))).all()
    return [(fid, creator == user_id or codes.get('MEMBER_ADMIN') is True) for fid, creator, codes in rows]


async def family_page(db, actor, limit, cursor, settings, request_id):
    query = select(Family).join(FamilyMember).where(FamilyMember.user_id == actor.user_id,
                FamilyMember.status.in_(['ACTIVE', 'PENDING']), Family.deleted_at.is_(None), Family.status != 'DELETED')
    rows, page = await page_rows(db, query, Family, codec(settings), 'families:' + str(actor.user_id), limit, cursor)
    memberships = (await db.scalars(select(FamilyMember).where(FamilyMember.user_id == actor.user_id,
                   FamilyMember.family_id.in_([row.id for row in rows]), FamilyMember.status.in_(['ACTIVE','PENDING'])))).all()
    by_family = {row.family_id: row for row in memberships}
    return {'items': [family_view(row, by_family[row.id]) for row in rows], 'page': page, 'request_id': request_id}


async def member_page(db, actor, family_id, status, limit, cursor, settings, request_id):
    await context(db, actor.user_id, family_id, member_read=True)
    query = select(FamilyMember).where(FamilyMember.family_id == family_id)
    if status:
        query = query.where(FamilyMember.status == status)
    rows, page = await page_rows(db, query, FamilyMember, codec(settings), f'members:{actor.user_id}:{family_id}:{status}', limit, cursor)
    names = await display_names(db, [row.user_id for row in rows if row.status in ('ACTIVE','PENDING')])
    await audit.record(db, actor.user_id, 'FAMILY_MEMBERS_READ', 'FAMILY', family_id, family_id, request_id)
    return {'items': [member_view(row, names.get(row.user_id,'')) for row in rows], 'page': page, 'request_id': request_id}


async def create(db: AsyncSession, actor: Identity, body, key: str, settings, request_id: str) -> dict:
    idem = audit.Idempotency(key, "family-create", body.model_dump())
    previous = await idem.previous(db, actor.user_id, settings.idempotency_seconds)
    if previous:
        return family_view(*await context(db, actor.user_id, previous))
    now = utcnow()
    family = Family(id=uuid7(), name=body.name, created_by_user_id=actor.user_id, created_at=now, updated_at=now)
    db.add(family)
    await db.flush()
    member = FamilyMember(id=uuid7(), family_id=family.id, user_id=actor.user_id, role="CHILD", status="ACTIVE",
                          permission_codes={"MEMBER_READ": True, "MEMBER_ADMIN": True}, joined_at=now, created_at=now, updated_at=now)
    db.add(member)
    await db.flush()
    await audit.record(db, actor.user_id, "FAMILY_CREATED", "FAMILY", family.id, family.id, request_id, metadata=idem.metadata)
    return family_view(family, member)


def invitation_view(row: FamilyInvitation, token: str) -> dict:
    return {"id": str(row.id), "family_id": str(row.family_id), "target_role": row.target_role,
            "status": row.status, "expires_at": row.expires_at.isoformat(), "token": token}


async def invite(db: AsyncSession, actor: Identity, family_id: UUID, body, key: str, settings, request_id: str) -> dict:
    await context(db, actor.user_id, family_id, admin=True)
    idem = audit.Idempotency(key, "invite:" + str(family_id), body.model_dump(mode="json"))
    previous = await idem.previous(db, actor.user_id, settings.idempotency_seconds)
    if previous:
        row = await db.get(FamilyInvitation, previous)
        if not row or row.family_id != family_id:
            raise AppError("FAMILY_INVITATION_INVALID", "邀请不可用。", 404)
        return invitation_view(row, codec(settings).opaque("invitation", str(row.id)))
    if body.expires_at <= utcnow():
        raise AppError("VALIDATION_ERROR", "邀请有效期必须晚于当前时间。", 422)
    row_id = uuid7()
    token = codec(settings).opaque("invitation", str(row_id))
    row = FamilyInvitation(id=row_id, family_id=family_id, created_by_user_id=actor.user_id,
                           token_hash=digest(token), target_role=body.target_role, expires_at=body.expires_at,
                           max_usage=body.max_usage, used_count=0, status="ACTIVE", created_at=utcnow())
    db.add(row)
    await db.flush()
    await audit.record(db, actor.user_id, "FAMILY_INVITATION_CREATED", "FAMILY_INVITATION", row.id,
                       family_id, request_id, metadata={**idem.metadata, "requested_scopes": sorted(set(body.requested_scopes))})
    return invitation_view(row, token)


async def accept(db: AsyncSession, actor: Identity, token: str, body, request_id: str) -> dict:
    invitation = await db.scalar(select(FamilyInvitation).where(FamilyInvitation.token_hash == digest(token)))
    if not invitation:
        raise AppError("FAMILY_INVITATION_INVALID", "邀请无效或已失效。", 404)
    family = await db.scalar(select(Family).where(Family.id == invitation.family_id).with_for_update())
    await db.refresh(invitation)
    if not family or family.status != "ACTIVE" or family.deleted_at or invitation.status in ("REVOKED", "EXPIRED") or invitation.expires_at <= utcnow():
        raise AppError("FAMILY_INVITATION_INVALID", "邀请无效或已失效。", 404)
    await require_member(db, family.id, invitation.created_by_user_id)
    existing_id = await audit.event_target(db, actor.user_id, "INVITATION_REDEEMED", "invitation_id", str(invitation.id))
    existing = await db.get(FamilyMember, existing_id) if existing_id else None
    if existing_id:
        if not existing or existing.user_id != actor.user_id or existing.status != "PENDING":
            raise AppError("FAMILY_INVITATION_INVALID", "邀请无效或已失效。", 404)
        member = existing
    else:
        if invitation.status != "ACTIVE" or invitation.used_count >= invitation.max_usage:
            raise AppError("FAMILY_INVITATION_INVALID", "邀请无效或已失效。", 404)
        member = await db.scalar(select(FamilyMember).where(FamilyMember.family_id == family.id,
                                FamilyMember.user_id == actor.user_id, FamilyMember.status.in_(["PENDING", "ACTIVE"])))
        if member:
            raise AppError("FAMILY_MEMBER_STATE_INVALID", "您已加入此家庭或已有待确认的邀请。", 409)
        now = utcnow()
        member = FamilyMember(id=uuid7(), family_id=family.id, user_id=actor.user_id,
                              role=invitation.target_role, status="PENDING", permission_codes={},
                              invited_by_user_id=invitation.created_by_user_id, created_at=now, updated_at=now)
        db.add(member)
        invitation.used_count += 1
        invitation.used_at = invitation.used_at or now
        if invitation.used_count >= invitation.max_usage:
            invitation.status = "USED"
        await db.flush()
        await audit.record(db, actor.user_id, "INVITATION_REDEEMED", "FAMILY_MEMBER", member.id,
                           family.id, request_id, metadata={"invitation_id": str(invitation.id)})
    if body.confirm_identity is True:
        member.status, member.joined_at = "ACTIVE", utcnow()
        member.updated_at = max(utcnow(), member.updated_at + timedelta(microseconds=1))
        await audit.record(db, actor.user_id, "MEMBER_CONFIRMED", "FAMILY_MEMBER", member.id, family.id, request_id)
    if body.requested_display_name is not None:
        await set_display_name(db, actor.user_id, body.requested_display_name)
    await db.flush()
    names = await display_names(db, [actor.user_id])
    return member_view(member, names.get(actor.user_id, ""))


async def members(db: AsyncSession, actor: Identity, family_id: UUID, status: str | None = None) -> list[dict]:
    await context(db, actor.user_id, family_id, member_read=True)
    query = select(FamilyMember).where(FamilyMember.family_id == family_id)
    if status:
        query = query.where(FamilyMember.status == status)
    rows = (await db.scalars(query.order_by(FamilyMember.created_at.desc(), FamilyMember.id.desc()))).all()
    names = await display_names(db, [row.user_id for row in rows if row.status in ("ACTIVE", "PENDING")])
    return [member_view(row, names.get(row.user_id, "")) for row in rows]


async def member_detail(db: AsyncSession, actor: Identity, family_id: UUID, member_id: UUID, request_id: str) -> dict:
    await context(db, actor.user_id, family_id, member_read=True)
    member = await db.scalar(select(FamilyMember).where(FamilyMember.id == member_id, FamilyMember.family_id == family_id))
    if not member:
        raise AppError("FAMILY_MEMBER_NOT_FOUND", "成员不存在或无权查看。", 404)
    names = await display_names(db, [member.user_id]) if member.status in ("ACTIVE", "PENDING") else {}
    await audit.record(db, actor.user_id, "FAMILY_MEMBER_READ", "FAMILY_MEMBER", member.id, family_id, request_id)
    return member_view(member, names.get(member.user_id, ""))


async def update_member(db: AsyncSession, actor: Identity, family_id: UUID, member_id: UUID,
                        body, expected: int, request_id: str) -> dict:
    await context(db, actor.user_id, family_id, admin=True)
    member = await db.scalar(select(FamilyMember).where(FamilyMember.id == member_id, FamilyMember.family_id == family_id))
    if not member:
        raise AppError("FAMILY_MEMBER_NOT_FOUND", "成员不存在或无权查看。", 404)
    if expected != version(member):
        raise AppError("ETAG_MISMATCH", "信息已变化，请刷新后重试。", 409)
    if not body.model_fields_set or any(getattr(body, key) is None for key in body.model_fields_set):
        raise AppError("VALIDATION_ERROR", "请提供需要修改的有效字段。", 422)
    if member.status != "ACTIVE" or body.status in ("PENDING", "LEFT"):
        raise AppError("FAMILY_MEMBER_STATE_INVALID", "请由受邀者确认加入；离开家庭请使用本人退出操作。", 409)
    if body.permission_codes is not None and not set(body.permission_codes) <= PERMISSIONS:
        raise AppError("PERMISSION_DENIED", "包含未支持的权限代码。", 403)
    if body.role:
        member.role = body.role
    if body.status == "REVOKED":
        member.status, member.left_at = "REVOKED", utcnow()
    if body.permission_codes is not None:
        member.permission_codes = dict.fromkeys(body.permission_codes, True)
    member.updated_at = max(utcnow(), member.updated_at + timedelta(microseconds=1))
    await audit.record(db, actor.user_id, "FAMILY_MEMBER_UPDATED", "FAMILY_MEMBER", member.id, family_id, request_id)
    names = await display_names(db, [member.user_id])
    return member_view(member, names.get(member.user_id, ""))


async def leave(db: AsyncSession, actor: Identity, family_id: UUID, member_id: UUID, request_id: str) -> None:
    _, member = await context(db, actor.user_id, family_id)
    if member.id != member_id:
        raise AppError("PERMISSION_DENIED", "只能退出您自己的成员关系。", 403)
    member.status, member.left_at = "LEFT", utcnow()
    member.updated_at = max(utcnow(), member.updated_at + timedelta(microseconds=1))
    await audit.record(db, actor.user_id, "FAMILY_MEMBER_LEFT", "FAMILY_MEMBER", member.id, family_id, request_id)


async def revoke_invitation(db: AsyncSession, actor: Identity, family_id: UUID, invitation_id: UUID, request_id: str) -> None:
    await context(db, actor.user_id, family_id, admin=True)
    invitation = await db.scalar(select(FamilyInvitation).where(FamilyInvitation.id == invitation_id, FamilyInvitation.family_id == family_id))
    if not invitation:
        raise AppError("FAMILY_INVITATION_INVALID", "邀请不可用。", 404)
    invitation.status = "REVOKED"
    await audit.record(db, actor.user_id, "FAMILY_INVITATION_REVOKED", "FAMILY_INVITATION", invitation.id, family_id, request_id)
