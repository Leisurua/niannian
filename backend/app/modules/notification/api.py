from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from app.modules.notification import service, preferences, contacts
from app.platform.authentication import current_identity
from app.platform.config import get_settings
from app.platform.resource_access import expected_version
from app.platform.uow import transaction

router = APIRouter(prefix='/v1', tags=['Notifications'])
PreferencePath = '/families/{family_id}/notification-preferences/{owner_user_id}'
ContactPath = '/families/{family_id}/my-contact'


@router.get('/notification-capabilities', operation_id='getNotificationCapabilities')
async def capabilities(response: Response, actor=Depends(current_identity)):
    from app.integrations.notifications import capabilities as available
    response.headers['Cache-Control'] = 'no-store'
    return available(get_settings())


@router.get(ContactPath, operation_id='getMyFamilyContact')
async def read_contact(family_id: UUID, response: Response, actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return await contacts.read(db, actor, family_id)


@router.put(ContactPath, operation_id='putMyFamilyContact')
async def update_contact(family_id: UUID, body: contacts.ContactInput, request: Request, response: Response,
    if_match: str = Header(), actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return await contacts.update(db, actor, family_id, body, expected_version(if_match, allow_zero=True), request.state.request_id)


@router.delete(ContactPath, status_code=204, operation_id='deleteMyFamilyContact')
async def delete_contact(family_id: UUID, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
    await contacts.remove(db, actor, family_id, request.state.request_id)


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
    response.headers['Cache-Control'] = 'no-store'
    return await preferences.update(db, actor, family_id, owner_user_id, body,
        expected_version(if_match, allow_zero=True), request.state.request_id)
