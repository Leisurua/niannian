from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import AwareDatetime
from app.modules.signal import service
from app.platform.authentication import current_identity
from app.platform.config import get_settings
from app.platform.uow import transaction

router = APIRouter(prefix='/v1/signal-events', tags=['SignalEvents'])
SignalType = Literal['PHYSICAL_DISCOMFORT','EMOTION_EXPRESSION','IMPORTANT_MEMORY','MISS_FAMILY','SCAM_RISK','EMERGENCY']
SignalStatus = Literal['DETECTED','VALIDATED','NOTIFIED','ACKNOWLEDGED','CONTACTED','FALSE_POSITIVE','RESOLVED','WITHHELD','NOTIFICATION_FAILED']


@router.get('', operation_id='listSignalEvents')
async def listing(request: Request, response: Response, family_id: UUID | None = None,
    type: SignalType | None = None, severity: Literal['L0','L1','L2','L3','L4'] | None = None,
    status: SignalStatus | None = None, from_time: AwareDatetime | None = Query(None, alias='from'),
    to_time: AwareDatetime | None = Query(None, alias='to'), limit: int = Query(20, ge=1, le=100), cursor: str | None = None,
    actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    filters = dict(family_id=family_id, type=type, severity=severity, status=status)
    filters.update({'from': from_time, 'to': to_time})
    return await service.listing(db, actor, filters, limit, cursor, get_settings(), request.state.request_id)


@router.get('/{event_id}', operation_id='getSignalEvent')
async def detail(event_id: UUID, request: Request, response: Response, actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return await service.detail(db, actor, event_id, request.state.request_id)
