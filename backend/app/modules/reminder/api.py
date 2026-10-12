from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, Request, Response

from app.modules.reminder import service
from app.modules.reminder.schemas import ReminderCreate, ReminderFeedback, ReminderType
from app.platform.authentication import current_identity
from app.platform.config import get_settings
from app.platform.resource_access import expected_version
from app.platform.uow import transaction

router = APIRouter(prefix='/v1', tags=['Reminders'])


@router.get('/reminders', operation_id='listReminders')
async def listing(request: Request, family_id: UUID | None = None, owner_user_id: UUID | None = None,
    type: ReminderType | None = None, active: bool | None = None, limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None, max_length=512), actor=Depends(current_identity), db=Depends(transaction)):
    return await service.listing(db, actor, family_id, owner_user_id, type, active, limit, cursor, get_settings(), request.state.request_id)


@router.post('/reminders', status_code=201, operation_id='createReminder')
async def create(body: ReminderCreate, request: Request, idempotency_key: str = Header(), actor=Depends(current_identity), db=Depends(transaction)):
    return await service.create(db, actor, body, idempotency_key, get_settings(), request.state.request_id)


@router.get('/reminders/{reminder_id}', operation_id='getReminder')
async def detail(reminder_id: UUID, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
    return await service.detail(db, actor, reminder_id, request.state.request_id)


@router.patch('/reminders/{reminder_id}', operation_id='updateReminder')
async def update(reminder_id: UUID, body: ReminderCreate, request: Request, if_match: str = Header(), actor=Depends(current_identity), db=Depends(transaction)):
    return await service.update(db, actor, reminder_id, body, expected_version(if_match), request.state.request_id)


@router.delete('/reminders/{reminder_id}', status_code=204, operation_id='deleteReminder')
async def delete(reminder_id: UUID, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
    await service.delete(db, actor, reminder_id, request.state.request_id)
    return Response(status_code=204)


@router.get('/reminders/{reminder_id}/executions', operation_id='listReminderExecutions')
async def executions(reminder_id: UUID, request: Request, limit: int = Query(20, ge=1, le=100), cursor: str | None = Query(None, max_length=512),
    actor=Depends(current_identity), db=Depends(transaction)):
    return await service.executions(db, actor, reminder_id, limit, cursor, get_settings(), request.state.request_id)


@router.post('/reminder-executions/{execution_id}/feedback', operation_id='submitReminderFeedback')
async def feedback(execution_id: UUID, body: ReminderFeedback, request: Request, idempotency_key: str = Header(), actor=Depends(current_identity), db=Depends(transaction)):
    return await service.feedback(db, actor, execution_id, body, idempotency_key, get_settings(), request.state.request_id)
