import asyncio
import hashlib
import time
from dataclasses import dataclass, replace
from uuid import UUID
from zoneinfo import ZoneInfo
import psycopg

from anyio import CancelScope
from fastapi import APIRouter, Depends, Header, Request, Response, WebSocket, WebSocketDisconnect
from sqlalchemy import text

from app.ai.conversation import TurnResult, configured_orchestrator, UNKNOWN, UNAVAILABLE
from app.integrations.contracts import AvatarState
from app.modules.memory import rag
from app.modules.audit import service as audit
from app.modules.auth.service import authenticate
from app.modules.conversation import service, summary as recap, proactive, daily
from app.modules.weather.service import WeatherService
from app.platform.identifiers import utcnow
from app.modules.conversation.protocol import InputLimits, MessageBudget, ProtocolError, parse_client_frame
from app.platform.authentication import current_identity
from app.platform.config import get_settings
from app.platform.db import session_factory
from app.platform.errors import AppError
from app.platform.uow import transaction

router = APIRouter(prefix='/v1', tags=['Conversations'])
_connections = {}


@dataclass(frozen=True)
class DailyTurn(TurnResult):
    answer: daily.Answer | None = None


async def generate_turn(factory, bearer, settings, orchestrator, conversation_id, text_input, request_id, history=(),
                        query_payload=None, weather=None, reminder_context=()):
    async with factory() as db:
        # Authentication failures must never fall through into an external LLM call.
        actor = await authenticate(db, bearer[7:], settings)
        row = await service.access(db, actor, conversation_id, owner_only=True, active=True)
        if daily.intent(text_input):
            # All tool answers bypass RAG and the LLM, including Mock mode.
            # Release business locks before the public weather network request.
            # The socket authenticates again before publishing or writing feedback.
            await db.commit()
            try:
                async with asyncio.timeout(18):
                    answer = await daily.answer(db, actor, row, text_input, query_payload or {},
                        weather or WeatherService(), reminder_context)
            except TimeoutError:
                answer = daily.Answer('WEATHER', '天气查询超时，暂时不能确定今天会不会下雨，请稍后再问。')
            return DailyTurn(answer.text, AvatarState.IDLE, None,
                dict(request_id=request_id, conversation_id=str(conversation_id), provider='daily-data',
                    model='deterministic', result_status='SUCCEEDED', query_kind=answer.kind), answer=answer)
        history_records = tuple(record for _, records in history for record in records)
        if not await rag.revalidate(db, actor, history_records):
            history, history_records = (), ()
        try:
            records = await rag.retrieve(db, actor, row.family_id, row.owner_user_id, text_input, request_id)
        except Exception:
            records = ()
        if getattr(orchestrator.llm, 'provider', settings.llm_provider) != 'mock':
            from app.modules.account.service import note_possible_copy, llm_copy_provider
            await note_possible_copy(db, actor.user_id, llm_copy_provider(settings))
        await db.commit()
    if getattr(orchestrator.llm, 'provider', settings.llm_provider) != 'mock':
        # Keep in-flight sends visible to account erasure, without holding user
        # or family row locks that would block consent revocation/interrupts.
        from app.modules.account.service import send_gate
        async with factory() as gate:
            await send_gate(gate, actor.user_id, shared=True)
            async with factory() as db:
                actor = await authenticate(db, bearer[7:], settings)
                await service.access(db, actor, conversation_id, owner_only=True, active=True)
                if not await rag.revalidate(db, actor, (*records, *history_records)):
                    records, history, history_records = (), (), ()
                await db.commit()
            result = await orchestrator.handle(request_id=request_id, conversation_id=conversation_id, text=text_input,
                memory_records=records, recent_turns=[turn for turn, _ in history])
    else:
        result = await orchestrator.handle(request_id=request_id, conversation_id=conversation_id, text=text_input,
            memory_records=records, recent_turns=[turn for turn, _ in history])
    dependencies = {(r.id, r.version): r for r in (*result.memory_records, *history_records)}
    return replace(result, memory_records=tuple(dependencies.values()))


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


async def listen_proactive(connection, queue):
    async for notification in connection.notifies():
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(notification.payload)


@router.post('/conversations', status_code=201, operation_id='createConversation')
async def create(body: service.ConversationCreate, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
    return await service.create(db, actor, body, request.state.request_id)


@router.get('/conversations/{conversation_id}', operation_id='getConversation')
async def detail(conversation_id: UUID, request: Request, response: Response,
                 x_access_reason: str | None = Header(default=None), actor=Depends(current_identity), db=Depends(transaction)):
    row = await service.access(db, actor, conversation_id)
    reason = access_reason(row, actor, x_access_reason)
    content = await recap.readable(db, row)
    event = await audit.record(db, actor.user_id, 'CONVERSATION_READ', 'CONVERSATION', row.id, row.family_id, request.state.request_id)
    event.reason = reason
    response.headers['Cache-Control'] = 'no-store'
    return {**service.view(row), 'summary': content}


@router.post('/conversations/{conversation_id}/end', operation_id='endConversation')
async def end(conversation_id: UUID, body: service.ConversationEnd, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
    return await service.end(db, actor, conversation_id, body, request.state.request_id)


@router.post('/conversations/{conversation_id}/summary', status_code=202, operation_id='requestConversationSummary')
async def summary(conversation_id: UUID, request: Request, response: Response,
                  x_access_reason: str | None = Header(default=None), actor=Depends(current_identity), db=Depends(transaction)):
    row = await service.access(db, actor, conversation_id)
    reason = access_reason(row, actor, x_access_reason)
    await recap.request(db, row, explicit=True)
    event = await audit.record(db, actor.user_id, 'CONVERSATION_SUMMARY_REQUESTED', 'CONVERSATION', row.id, row.family_id, request.state.request_id)
    event.reason = reason
    response.headers['Cache-Control'] = 'no-store'
    return dict(conversation_id=str(row.id), status=row.summary_status if row.summary_status in ('READY', 'PENDING') else 'FAILED')


def access_reason(row, actor, reason):
    if (reason is not None and reason not in ('FAMILY_CHECK_IN', 'FOLLOW_UP')) or (actor.user_id != row.owner_user_id and reason is None):
        raise AppError('VALIDATION_ERROR', '查看家人会话需要选择明确理由。', 422)
    return reason


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
    receive_task = None
    turn_task = None
    last_reply = None
    last_records = ()
    pending_topic = None
    pending_signal_input = None
    pending_sequence = None
    pending_query_payload = None
    reminder_context = ()
    last_daily = None
    last_query = None
    last_source_labels = None
    listener = None
    listen_task = None
    notices = asyncio.Queue(maxsize=1)
    last_interaction = utcnow()
    history = []
    orchestrator = getattr(websocket.app.state, 'conversation_orchestrator', None) or configured_orchestrator(settings)
    # The handshake must not consult a provider: local safety replies remain
    # available even when provider capability discovery is broken.
    provider = getattr(orchestrator.llm, 'provider', settings.llm_provider)
    llm_mode = 'mock' if provider == 'mock' else 'real'
    source_labels = ['Mock'] if llm_mode == 'mock' else ['AI']
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
            row.provider_metadata = {**row.provider_metadata, 'provider': provider}
            voice_allowed = await service.voice_allowed(db, row)
            ready = service.event(row, 'session.ready', {'backend_state': row.backend_state,
                'llm_mode': llm_mode, 'voice_allowed': voice_allowed})
            await audit.record(db, actor_id, 'CONVERSATION_WS_CONNECTED', 'CONVERSATION', row.id, row.family_id)
            await db.commit()
        async with asyncio.timeout(5):
            args, kwargs = lease.bind.dialect.create_connect_args(lease.bind.url)
            listener = await psycopg.AsyncConnection.connect(*args, **kwargs, autocommit=True)
            await listener.execute('LISTEN nn_proactive_' + conversation_id.hex)
        listen_task = asyncio.create_task(listen_proactive(listener, notices))
        await websocket.accept()
        accepted = True
        await websocket.send_json(ready)
        while True:
            if receive_task is None:
                receive_task = asyncio.create_task(websocket.receive())
            waiting = {receive_task} | ({turn_task} if turn_task else set())
            done, _ = await asyncio.wait(waiting, timeout=1.0, return_when=asyncio.FIRST_COMPLETED)
            raw = receive_task.result() if receive_task in done else None
            if receive_task in done:
                receive_task = None
            if raw and raw['type'] == 'websocket.disconnect':
                break
            if listen_task.done():
                await websocket.close(code=1011)
                break
            notice = notices.get_nowait() if not notices.empty() else None
            async with factory() as db:
                actor = await authenticate(db, bearer[7:], settings)
                row = await service.access(db, actor, conversation_id, owner_only=True, active=True)
                current_voice_allowed = await service.voice_allowed(db, row)
                voice_changed = current_voice_allowed != voice_allowed
                if last_records and not await rag.revalidate(db, actor, last_records):
                    last_reply, last_records = UNKNOWN, ()
                    history.clear()
                if raw is None and notice is None and not voice_changed and (turn_task is None or turn_task not in done):
                    await db.commit()
                    continue
                try:
                    outgoing = []
                    permission_event = None
                    if voice_changed:
                        voice_allowed = current_voice_allowed
                        permission_event = service.event(row, 'voice.permission', {'allowed': voice_allowed})
                    if raw is not None:
                        budget.take(time.monotonic())
                        message = parse_client_frame(raw.get('text'), conversation_id=conversation_id, last_sequence=row.client_sequence, limits=limits)
                        row.client_sequence = message.sequence
                        if message.type not in ('ping', 'session.start'):
                            last_interaction = utcnow()
                        if message.type in ('interrupt', 'session.end'):
                            if turn_task:
                                turn_task.cancel()
                                await asyncio.gather(turn_task, return_exceptions=True)
                                turn_task = None
                            last_reply = None
                            last_records = ()
                            pending_topic = None
                            pending_signal_input = None
                            pending_sequence = None
                            pending_query_payload = None
                            last_daily = last_query = None
                            outgoing = service.handle(row, message)
                        elif message.type == 'text.input':
                            if turn_task or not row.provider_metadata.get('identity_disclosed'):
                                outgoing = [service.event(row, 'error', {'code': 'PROVIDER_TEMPORARILY_UNAVAILABLE', 'retryable': False})]
                            elif message.payload['text'].strip('。！! ') in ('今天少打扰我', '今天别打扰我', '今天别主动提醒我', '不要打扰', '我在忙', '我在休息'):
                                try:
                                    await proactive.command(db, actor, row.family_id, actor.user_id, 'pause', {},
                                        f'ws-pause:{conversation_id}:{message.sequence}', settings, f'turn-{message.sequence}')
                                    reply = '今天已减少主动互动，必要提醒和紧急联系仍可使用。'
                                except AppError:
                                    reply = '当前没有已启用的主动陪伴设置；必要提醒和紧急联系仍可使用。'
                                outgoing = [service.event(row, 'assistant.text', {'text': reply, 'source_labels': source_labels}),
                                    service.event(row, 'assistant.state', {'state': 'IDLE'})]
                            else:
                                last_reply = None
                                last_records = ()
                                context_records = tuple(r for _, records in history for r in records)
                                if (len({r.id for r in context_records}) > 30
                                        or not await rag.revalidate(db, actor, context_records)):
                                    history.clear()
                                row.backend_state = 'THINKING'
                                pending_topic = recap.topic_for(message.payload['text'])
                                pending_signal_input = (message.payload['text'], f'turn-{message.sequence}', utcnow())
                                pending_sequence = message.sequence
                                pending_query_payload = message.payload
                                outgoing = [service.event(row, 'assistant.state', {'state': 'THINKING'})]
                                outgoing += service.scam_warning(row, message.payload['text'])
                                turn_task = asyncio.create_task(generate_turn(factory, bearer, settings, orchestrator,
                                    conversation_id, message.payload['text'], f'turn-{message.sequence}', tuple(history),
                                    message.payload, getattr(websocket.app.state, 'weather_service', None), reminder_context))
                        elif message.type in ('repeat', 'slow_down'):
                            if turn_task or last_reply is None:
                                outgoing = [service.event(row, 'error', {'code': 'PROVIDER_TEMPORARILY_UNAVAILABLE', 'retryable': False})]
                            elif last_daily and last_daily.kind in ('DATE', 'WEATHER', 'REMINDERS'):
                                pending_sequence = message.sequence
                                pending_query_payload = last_query
                                pending_signal_input = None
                                row.backend_state = 'THINKING'
                                outgoing = [service.event(row, 'assistant.state', {'state': 'THINKING'})]
                                turn_task = asyncio.create_task(generate_turn(factory, bearer, settings, orchestrator,
                                    conversation_id, last_query['text'], f'repeat-{message.sequence}', (), last_query,
                                    getattr(websocket.app.state, 'weather_service', None), reminder_context))
                            else:
                                if not await rag.revalidate(db, actor, last_records):
                                    last_reply, last_records = UNKNOWN, ()
                                if last_daily and last_daily.choices:
                                    current_choices = await daily.today_choices(db, actor, row,
                                        ZoneInfo(last_query.get('timezone', 'Asia/Shanghai')), utcnow())
                                    if any(not any(c.reminder_id == old.reminder_id and c.occurrence_key == old.occurrence_key
                                            and c.version == old.version and c.status == old.status for c in current_choices)
                                            for old in last_daily.choices):
                                        last_reply = '提醒状态已变更，请重新问“今天有什么安排”。'
                                outgoing = [service.event(row, 'assistant.text', {'text': last_reply, 'source_labels': last_source_labels or source_labels}),
                                    service.event(row, 'assistant.state', {'state': 'IDLE'})]
                        else:
                            outgoing = service.handle(row, message)
                        outgoing = [{**item, 'in_reply_to': message.sequence} for item in outgoing]
                    if turn_task and turn_task in done:
                        result_start = len(outgoing)
                        result = turn_task.result()
                        turn_task = None
                        if isinstance(result, DailyTurn):
                            published = await daily.publish(db, actor, row, result.answer, pending_query_payload['text'],
                                pending_query_payload, settings, result.trace['request_id'])
                            result = replace(result, assistant_text=published.text, answer=published)
                            reminder_context = published.choices if published.kind in ('REMINDERS', 'FEEDBACK') else reminder_context
                            last_daily, last_query = published, pending_query_payload
                            last_source_labels = list(published.sources)
                        else:
                            last_daily = last_query = None
                            last_source_labels = source_labels
                        if not await rag.revalidate(db, actor, result.memory_records):
                            last_reply, last_records = UNKNOWN, ()
                            history.clear()
                        else:
                            last_reply, last_records = result.assistant_text, result.memory_records
                            if pending_signal_input and not isinstance(result, DailyTurn) and result.trace.get('result_status') != 'FAILED':
                                history.append((dict(user=pending_signal_input[0], assistant=last_reply), last_records))
                                history = history[-6:]
                                while sum(len(t['user']) + len(t['assistant']) for t, _ in history) > 12000:
                                    history.pop(0)
                        row.backend_state = result.avatar_state.value
                        row.provider_metadata = {**row.provider_metadata, 'trace': result.trace}
                        if pending_topic and result.trace.get('result_status') != 'FAILED' and last_reply != UNAVAILABLE:
                            await recap.add_topic(db, row, pending_topic)
                        pending_topic = None
                        if pending_signal_input and result.trace.get('result_status') != 'FAILED' and last_reply not in (UNAVAILABLE, UNKNOWN):
                            from app.modules.report.metrics import collect
                            await collect(db, row, pending_sequence, pending_signal_input[0], pending_signal_input[2], utcnow(),
                                simulated=False if isinstance(result, DailyTurn) else None)
                        if pending_signal_input and result.trace.get('result_status') != 'FAILED':
                            from app.modules.signal.service import record_turn
                            signal_events = await record_turn(db, actor, row.id, pending_signal_input[1],
                                pending_signal_input[0], result.signal_candidates, candidate_mode=result.signal_mode)
                            outgoing += [service.event(row, 'signal.created', item) for item in signal_events]
                        pending_signal_input = None
                        response_payload = {'text': last_reply, 'source_labels': last_source_labels}
                        if isinstance(result, DailyTurn) and result.answer.reminders_changed:
                            response_payload['reminders_changed'] = True
                        outgoing += [service.event(row, 'assistant.text', response_payload)]
                        if result.fallback_code:
                            outgoing += [service.event(row, 'error', {'code': 'PROVIDER_TEMPORARILY_UNAVAILABLE', 'retryable': False})]
                        outgoing += [service.event(row, 'assistant.state', {'state': row.backend_state})]
                        outgoing[result_start:] = [
                            {**item, 'in_reply_to': pending_sequence} for item in outgoing[result_start:]
                        ]
                        pending_sequence = None
                        pending_query_payload = None
                    if notice and raw is None and turn_task is None and not outgoing and await proactive.accept(db, row, notice, last_interaction):
                        outgoing = [service.event(row, 'assistant.text', {'text': proactive.INVITATION, 'source_labels': ['Mock']})]
                        last_interaction = utcnow()
                    if permission_event:
                        outgoing.insert(0, permission_event)
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
                    await recap.request(db, row)
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
        tasks = [task for task in (receive_task, turn_task, listen_task) if task is not None]
        for task in tasks:
            task.cancel()
        try:
            with CancelScope(shield=True):
                await asyncio.gather(*tasks, return_exceptions=True)
                if listener:
                    try:
                        async with asyncio.timeout(2):
                            await listener.close()
                    except Exception:
                        pass
        finally:
            await release_connection_lease(lease, actor_id)
