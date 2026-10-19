import re
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from app.modules.notification import service, preferences
from app.platform.authentication import current_identity
from app.platform.config import get_settings
from app.platform.errors import AppError
from app.platform.uow import transaction

router = APIRouter(prefix='/v1', tags=['Notifications'])
PreferencePath = '/families/{family_id}/notification-preferences/{owner_user_id}'


@router.get('/notifications', operation_id='listNotifications')
async def listing(request: Request, response: Response,
    status: Literal['PENDING','QUEUED','SENT','DELIVERED','READ','FAILED','CANCELLED'] | None = None,
    channel: Literal['IN_APP','PUSH','SMS','PHONE'] | None = None,
    limit: int = Query(20, ge=1, le=100), cursor: str | None = None,
    actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return await service.listing(db, actor, status, channel, limit, cursor, get_settings(), request.state.request_id)


@router.get('/notifications/{notification_id}', operation_id='getNotification')
async def detail(notification_id: UUID, request: Request, response: Response,
    actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return await service.detail(db, actor, notification_id, request.state.request_id)


@router.post('/notifications/{notification_id}/read', operation_id='markNotificationRead')
async def mark_read(notification_id: UUID, request: Request, response: Response, idempotency_key: str = Header(),
    actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return await service.detail(db, actor, notification_id, request.state.request_id,
        read_key=idempotency_key, settings=get_settings())


@router.get(PreferencePath, operation_id='getNotificationPreference')
async def read_preference(family_id: UUID, owner_user_id: UUID, request: Request, response: Response,
    actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return await preferences.read(db, actor, family_id, owner_user_id, request.state.request_id)


@router.put(PreferencePath, operation_id='putNotificationPreference')
async def update_preference(family_id: UUID, owner_user_id: UUID, body: preferences.PreferenceInput,
    request: Request, response: Response, if_match: str = Header(), actor=Depends(current_identity), db=Depends(transaction)):
    match = re.fullmatch(r'(?:"(0|[1-9][0-9]*)"|(0|[1-9][0-9]*))', if_match) if len(if_match) <= 64 else None
    if not match:
        raise AppError('ETAG_MISMATCH', '请重新读取设置后保存。', 409)
    response.headers['Cache-Control'] = 'no-store'
    return await preferences.update(db, actor, family_id, owner_user_id, body, int(match[1] or match[2]), request.state.request_id)
