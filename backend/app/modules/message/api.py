from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.message import service
from app.modules.message.schemas import MessageCreate
from app.platform.authentication import current_identity
from app.platform.config import get_settings
from app.platform.uow import transaction

router = APIRouter(prefix='/v1', tags=['Messages'])


@router.post('/messages', status_code=201, operation_id='sendMessage')
async def send(body: MessageCreate, request: Request, idempotency_key: str = Header(),
               actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    return {**await service.send(db, actor, body, idempotency_key, get_settings(), request.state.request_id),
            'request_id': request.state.request_id}


@router.get('/messages', operation_id='listMessages')
async def listing(request: Request, box: Literal['INBOX', 'OUTBOX'] = 'INBOX',
                  family_id: UUID | None = None, after_sequence: int = Query(0, ge=0, le=9223372036854775807),
                  cursor: int | None = Query(None, ge=0, le=9223372036854775807), limit: int = Query(20, ge=1, le=100),
                  actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    return {**await service.listing(db, actor, box, cursor if cursor is not None else after_sequence, limit, family_id),
            'request_id': request.state.request_id}


@router.get('/messages/{message_id}', operation_id='getMessage')
async def detail(message_id: UUID, request: Request, actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    return {**await service.view(db, await service.detail(db, actor, message_id), actor),
            'request_id': request.state.request_id}


@router.post('/message-deliveries/{delivery_id}/received', operation_id='receiveMessage')
async def received(delivery_id: UUID, request: Request, idempotency_key: str = Header(),
                   actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    return {**await service.acknowledge(db, actor, delivery_id, False, idempotency_key, request.state.request_id),
            'request_id': request.state.request_id}


@router.post('/message-deliveries/{delivery_id}/read', operation_id='readMessage')
async def read(delivery_id: UUID, request: Request, idempotency_key: str = Header(),
               actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    return {**await service.acknowledge(db, actor, delivery_id, True, idempotency_key, request.state.request_id),
            'request_id': request.state.request_id}
