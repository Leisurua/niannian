import asyncio
import hashlib
import time
from uuid import UUID

from anyio import CancelScope
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import text

from app.modules.audit import service as audit
from app.modules.auth.service import authenticate
from app.modules.conversation import service
from app.modules.conversation.protocol import InputLimits, MessageBudget, ProtocolError, parse_client_frame
from app.platform.authentication import current_identity
from app.platform.config import get_settings
from app.platform.db import session_factory
from app.platform.errors import AppError
from app.platform.uow import transaction

router = APIRouter(prefix='/v1', tags=['Conversations'])
_connections = {}


async def release_connection_lease(lease, actor_id):
    try:
        with CancelScope(shield=True):
            try:
                await lease.rollback()
            finally:
                await lease.close()
    finally:
        if actor_id:
            remaining = _connections.get(actor_id, 0) - 1
            if remaining > 0:
                _connections[actor_id] = remaining
            else:
                _connections.pop(actor_id, None)


@router.post('/conversations', status_code=201, operation_id='createConversation')
async def create(body: service.ConversationCreate, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
    return await service.create(db, actor, body, request.state.request_id)


@router.get('/conversations/{conversation_id}', operation_id='getConversation')
async def detail(conversation_id: UUID, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
    row = await service.access(db, actor, conversation_id)
    await audit.record(db, actor.user_id, 'CONVERSATION_READ', 'CONVERSATION', row.id, row.family_id, request.state.request_id)
    return service.view(row)


@router.post('/conversations/{conversation_id}/end', operation_id='endConversation')
async def end(conversation_id: UUID, body: service.ConversationEnd, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
    return await service.end(db, actor, conversation_id, body, request.state.request_id)


@router.post('/conversations/{conversation_id}/summary', status_code=202, operation_id='requestConversationSummary')
async def summary(conversation_id: UUID, actor=Depends(current_identity), db=Depends(transaction)):
    await service.access(db, actor, conversation_id)
    raise AppError('PROVIDER_TEMPORARILY_UNAVAILABLE', '摘要生成尚未启用，不会保存或分享逐字稿。', 503)


@router.websocket('/ws/conversations/{conversation_id}')
async def socket(websocket: WebSocket, conversation_id: UUID):
    settings = get_settings()
    factory = getattr(websocket.app.state, 'session_factory', session_factory)
    bearer = websocket.headers.get('authorization', '')
    if not bearer.startswith('Bearer ') or websocket.query_params:
        await websocket.close(code=4401)
        return
    limits = InputLimits(settings.ws_max_frame_bytes, settings.ws_max_text_chars, settings.ws_messages_per_second, 1.0)
    budget = MessageBudget(limits)
    actor_id = None
    accepted = False
    lease = factory()
    try:
        async with factory() as db:
            actor = await authenticate(db, bearer[7:], settings)
            row = await service.access(db, actor, conversation_id, owner_only=True, active=True)
            if _connections.get(actor.user_id, 0) >= 2 or sum(_connections.values()) >= 128:
                raise AppError('RATE_LIMITED', '连接过多。', 429)
            # Transaction-scoped PostgreSQL advisory lock prevents simultaneous
            # connections to one conversation across API processes; released on
            # close/rollback/crash. This connection never locks business rows.
            lock_id = int.from_bytes(hashlib.sha256(conversation_id.bytes).digest()[:8], 'big', signed=True)
            if not await lease.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'), {'key': lock_id}):
                raise AppError('CONVERSATION_IN_USE', '此会话已在另一连接中打开。', 409)
            actor_id = actor.user_id
            _connections[actor_id] = _connections.get(actor_id, 0) + 1
            row.backend_state = 'IDLE'
            ready = service.event(row, 'session.ready', {'backend_state': row.backend_state})
            await audit.record(db, actor_id, 'CONVERSATION_WS_CONNECTED', 'CONVERSATION', row.id, row.family_id)
            await db.commit()
        await websocket.accept()
        accepted = True
        await websocket.send_json(ready)
        while True:
            raw = None
            try:
                raw = await asyncio.wait_for(websocket.receive(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
            if raw and raw['type'] == 'websocket.disconnect':
                break
            async with factory() as db:
                actor = await authenticate(db, bearer[7:], settings)
                row = await service.access(db, actor, conversation_id, owner_only=True, active=True)
                if raw is None:
                    await db.commit()
                    continue
                try:
                    budget.take(time.monotonic())
                    message = parse_client_frame(raw.get('text'), conversation_id=conversation_id, last_sequence=row.client_sequence, limits=limits)
                    outgoing = service.handle(row, message)
                except ProtocolError as error:
                    outgoing = [service.event(row, 'error', {'code': str(error), 'retryable': False})]
                    await audit.record(db, actor_id, 'CONVERSATION_WS_REJECTED', 'CONVERSATION', row.id, row.family_id,
                                       result='DENIED', metadata={'error_code': str(error)})
                    await db.commit()
                    await websocket.send_json(outgoing[0])
                    await websocket.close(code=4400)
                    break
                ended = row.status != 'ACTIVE'
                if ended:
                    await audit.record(db, actor_id, 'CONVERSATION_ENDED', 'CONVERSATION', row.id, row.family_id)
                await db.commit()
            for outgoing_event in outgoing:
                await websocket.send_json(outgoing_event)
            if ended:
                await websocket.close(code=1000)
                break
    except AppError as error:
        await websocket.close(code=4401 if error.status_code == 401 else 4403)
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:
        if accepted:
            await websocket.close(code=1011)
        else:
            await websocket.close(code=4403)
    finally:
        await release_connection_lease(lease, actor_id)
