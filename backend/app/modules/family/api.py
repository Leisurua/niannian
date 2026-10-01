import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.family import service
from app.modules.family.schemas import FamilyCreate, InvitationAccept, InvitationCreate, MemberUpdate
from app.platform.authentication import current_identity
from app.platform.config import get_settings
from app.platform.errors import AppError
from app.platform.uow import transaction

router = APIRouter(prefix='/v1', tags=['Families'])


@router.post('/families', status_code=201, operation_id='createFamily')
async def create(body: FamilyCreate, request: Request, idempotency_key: str = Header(),
                 actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    return {**await service.create(db, actor, body, idempotency_key, get_settings(), request.state.request_id),
            'request_id': request.state.request_id}


@router.get('/families', operation_id='listFamilies')
async def listing(request: Request, limit: int = Query(20, ge=1, le=100), cursor: str | None = Query(None, max_length=512),
                  actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    return await service.family_page(db, actor, limit, cursor, get_settings(), request.state.request_id)


@router.get('/families/{family_id}', operation_id='getFamily')
async def detail(family_id: UUID, request: Request, actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    return {**service.family_view(*await service.context(db, actor.user_id, family_id)), 'request_id': request.state.request_id}


@router.post('/families/{family_id}/invitations', status_code=201, operation_id='createFamilyInvitation')
async def invite(family_id: UUID, body: InvitationCreate, request: Request, idempotency_key: str = Header(),
                 actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    return {**await service.invite(db, actor, family_id, body, idempotency_key, get_settings(), request.state.request_id),
            'request_id': request.state.request_id}


@router.post('/family-invitations/{token}/accept', operation_id='acceptFamilyInvitation')
async def accept(token: str, body: InvitationAccept, request: Request, actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    if not 16 <= len(token) <= 512:
        raise AppError('FAMILY_INVITATION_INVALID', '邀请无效或已失效。', 404)
    return {**await service.accept(db, actor, token, body, request.state.request_id), 'request_id': request.state.request_id}


@router.get('/families/{family_id}/members', operation_id='listFamilyMembers')
async def members(family_id: UUID, request: Request, status: Literal['PENDING','ACTIVE','REVOKED','LEFT'] | None = None,
                  limit: int = Query(20, ge=1, le=100), cursor: str | None = Query(None, max_length=512),
                  actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    return await service.member_page(db, actor, family_id, status, limit, cursor, get_settings(), request.state.request_id)


@router.get('/families/{family_id}/members/{member_id}', operation_id='getFamilyMember')
async def member(family_id: UUID, member_id: UUID, request: Request, actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    result = await service.member_detail(db, actor, family_id, member_id, request.state.request_id)
    return {**result, 'request_id': request.state.request_id}


@router.patch('/families/{family_id}/members/{member_id}', operation_id='updateFamilyMember')
async def update(family_id: UUID, member_id: UUID, body: MemberUpdate, request: Request, if_match: str = Header(),
                 actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    match = re.fullmatch(r'(?:"([1-9][0-9]*)"|([1-9][0-9]*))', if_match) if len(if_match) <= 64 else None
    if not match:
        raise AppError('ETAG_MISMATCH', '请刷新成员信息后重试。', 409)
    result = await service.update_member(db, actor, family_id, member_id, body, int(match[1] or match[2]), request.state.request_id)
    return {**result, 'request_id': request.state.request_id}


@router.post('/families/{family_id}/members/{member_id}/leave', status_code=204, operation_id='leaveFamilyMember')
async def leave(family_id: UUID, member_id: UUID, request: Request, actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    await service.leave(db, actor, family_id, member_id, request.state.request_id)
    return Response(status_code=204)


@router.post('/families/{family_id}/invitations/{invitation_id}/revoke', status_code=204, operation_id='revokeFamilyInvitation')
async def revoke_invitation(family_id: UUID, invitation_id: UUID, request: Request,
                            actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    await service.revoke_invitation(db, actor, family_id, invitation_id, request.state.request_id)
    return Response(status_code=204)
