from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.consent import service
from app.modules.consent.schemas import ConsentCreate, ConsentRevoke
from app.modules.family.schemas import Scope
from app.platform.authentication import current_identity
from app.platform.config import get_settings
from app.platform.uow import transaction

router = APIRouter(prefix='/v1', tags=['Consents'])


@router.get('/consents', operation_id='listConsents')
async def listing(request: Request, family_id: UUID | None = None, subject_user_id: UUID | None = None,
                  grantee_user_id: UUID | None = None, scope: Scope | None = None,
                  limit: int = Query(20, ge=1, le=100), cursor: str | None = Query(None, max_length=512),
                  actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    return await service.listing(db, actor, family_id, subject_user_id, grantee_user_id, scope,
                                 limit, cursor, get_settings(), request.state.request_id)


@router.get('/consents/{consent_id}', operation_id='getConsent')
async def detail(consent_id: UUID, request: Request, actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    return {**await service.detail(db, actor, consent_id, request.state.request_id), 'request_id': request.state.request_id}


@router.post('/consents', status_code=201, operation_id='grantConsent')
async def grant(body: ConsentCreate, request: Request, idempotency_key: str = Header(),
                actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    return {**await service.grant(db, actor, body, idempotency_key, get_settings(), request.state.request_id),
            'request_id': request.state.request_id}


@router.post('/consents/{consent_id}/revoke', status_code=201, operation_id='revokeConsent')
async def revoke(consent_id: UUID, request: Request, body: ConsentRevoke = Body(default_factory=ConsentRevoke),
                 idempotency_key: str = Header(), actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    return {**await service.revoke(db, actor, consent_id, body, idempotency_key, get_settings(), request.state.request_id),
            'request_id': request.state.request_id}
