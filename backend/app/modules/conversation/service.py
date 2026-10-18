from typing import Literal
from uuid import UUID

from pydantic import Field

from app.ai.conversation import IDENTITY

from app.modules.auth.schemas import Input
from app.modules.audit import service as audit
from app.modules.conversation.models import Conversation
from app.modules.conversation import summary
from app.modules.device.service import require_active_binding
from app.modules.family import service as family
from app.platform.errors import AppError
from app.platform.identifiers import iso_utc, utcnow, uuid7
from app.platform.resource_access import authorize, resolve_family


class ConversationCreate(Input):
    family_id: UUID | None = None
    device_id: UUID | None = None
    input_mode: Literal['VOICE', 'TEXT', 'LOCAL_WAKEWORD']


class ConversationEnd(Input):
    reason: Literal['USER', 'TIMEOUT', 'ERROR'] = 'USER'


async def access(db, actor, conversation_id, *, owner_only=False, active=False):
    row = await db.get(Conversation, conversation_id)
    if not row:
        raise AppError('CONVERSATION_NOT_FOUND', '会话不存在或无权访问。', 404)
    try:
        await family.context(db, actor.user_id, row.family_id)
        await db.refresh(row)
        if row.deleted_at or row.status == 'DELETED' or owner_only and row.owner_user_id != actor.user_id:
            raise AppError('CONVERSATION_NOT_FOUND', '会话不存在或无权访问。', 404)
        await authorize(db, actor, row.family_id, row.owner_user_id, 'SUMMARY_READ', 'CONVERSATION_SUMMARY')
        if row.device_binding_id:
            await require_active_binding(db, row.device_binding_id, row.owner_user_id)
    except AppError as error:
        if error.status_code in (403, 404):
            raise AppError('CONVERSATION_NOT_FOUND', '会话不存在或无权访问。', 404) from None
        raise
    if active and row.status != 'ACTIVE':
        raise AppError('CONVERSATION_ENDED', '此会话已结束，请重新开始。', 409)
    return row


def view(row):
    result = dict(id=str(row.id), owner_user_id=str(row.owner_user_id), family_id=str(row.family_id),
        status=row.status, backend_state=row.backend_state, summary_status=row.summary_status,
        summary=row.summary_text if row.summary_status == 'READY' else None, started_at=iso_utc(row.started_at))
    if row.ended_at:
        result['ended_at'] = iso_utc(row.ended_at)
    return result


async def create(db, actor, body, request_id):
    fid = await resolve_family(db, actor, actor.user_id, body.family_id)
    _, member = await family.context(db, actor.user_id, fid)
    if member.role != 'ELDER':
        raise AppError('PERMISSION_DENIED', '本阶段会话需由长辈本人主动开始。', 403)
    if body.input_mode != 'TEXT':
        raise AppError('PROVIDER_TEMPORARILY_UNAVAILABLE', '本阶段仅开放文字会话状态，语音尚未启用。', 503)
    if body.device_id:
        await require_active_binding(db, body.device_id, actor.user_id)
    now = utcnow()
    row = Conversation(id=uuid7(), owner_user_id=actor.user_id, family_id=fid, device_binding_id=body.device_id,
        started_at=now, status='ACTIVE', summary_status='NOT_REQUESTED', backend_state='IDLE', input_mode='TEXT',
        client_sequence=0, server_sequence=0, provider_metadata={'provider': 'mock', 'identity_disclosed': False})
    db.add(row)
    await audit.record(db, actor.user_id, 'CONVERSATION_STARTED', 'CONVERSATION', row.id, fid, request_id)
    return view(row)


async def end(db, actor, conversation_id, body, request_id):
    row = await access(db, actor, conversation_id, owner_only=True)
    if row.status == 'ACTIVE':
        finish(row, body.reason)
        await audit.record(db, actor.user_id, 'CONVERSATION_ENDED', 'CONVERSATION', row.id, row.family_id, request_id)
        await summary.request(db, row)
    return view(row)


def finish(row, reason):
    row.status = {'USER': 'COMPLETED', 'TIMEOUT': 'INTERRUPTED', 'ERROR': 'FAILED'}[reason]
    row.ended_at, row.backend_state = utcnow(), 'IDLE'


def event(row, kind, payload):
    row.server_sequence += 1
    return dict(type=kind, conversation_id=str(row.id), sequence=row.server_sequence, occurred_at=utcnow().isoformat(), payload=payload)


def handle(row, message):
    row.client_sequence = message.sequence
    if message.type == 'ping':
        return [event(row, 'pong', {})]
    if message.type == 'session.end':
        finish(row, message.payload.get('reason') or 'USER')
        return [event(row, 'assistant.state', {'state': 'IDLE'})]
    if message.type == 'session.start':
        row.backend_state = 'LISTENING'
        result = [event(row, 'session.ready', {'backend_state': row.backend_state})]
        if not row.provider_metadata.get('identity_disclosed'):
            row.provider_metadata = {**row.provider_metadata, 'identity_disclosed': True}
            result.append(event(row, 'assistant.text', {'text': IDENTITY, 'source_labels': ['Mock']}))
        return result
    if message.type == 'interrupt':
        row.backend_state = 'LISTENING'
        return [event(row, 'assistant.state', {'state': 'LISTENING'})]
    row.backend_state = 'IDLE'
    return [event(row, 'error', {'code': 'PROVIDER_TEMPORARILY_UNAVAILABLE', 'retryable': False}),
            event(row, 'assistant.state', {'state': 'IDLE'})]
