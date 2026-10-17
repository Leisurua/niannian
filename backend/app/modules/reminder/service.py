from datetime import timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.modules.audit import service as audit
from app.modules.auth.service import codec
from app.modules.family import service as family
from app.modules.reminder.models import Reminder, ReminderExecution
from app.modules.reminder.schedule import CalendarPolicy, ScheduleRule, in_quiet_hours, next_occurrence
from app.platform.errors import AppError
from app.platform.identifiers import iso_utc, utcnow, uuid7
from app.platform.pagination import page_rows
from app.platform.resource_access import authorize, check_version, resolve_family, visible_subjects

POLICY = CalendarPolicy('FIRST', 'SKIP', 'DISABLED')


def schedule(row):
    data = {key: getattr(row, key) for key in ScheduleRule.model_fields if key != 'quiet_hours'}
    if row.quiet_hours_start is not None:
        data['quiet_hours'] = dict(start=row.quiet_hours_start, end=row.quiet_hours_end, timezone=row.quiet_hours_timezone)
    return ScheduleRule.model_validate(data)


def view(row):
    result = schedule(row).model_dump(mode='json', exclude_none=True)
    result.update(id=str(row.id), family_id=str(row.family_id), owner_user_id=str(row.owner_user_id),
        type=row.type, title=row.title, content=row.content, active=row.active, version=row.version,
        escalation_policy=row.escalation_policy, created_at=iso_utc(row.created_at), updated_at=iso_utc(row.updated_at))
    if row.next_due_at:
        result['next_due_at'] = iso_utc(row.next_due_at)
    return result


def execution_view(row):
    result = dict(id=str(row.id), reminder_id=str(row.reminder_id), scheduled_at=iso_utc(row.scheduled_at),
                  feedback_status=row.feedback_status, source=row.source)
    for key in ('triggered_at', 'feedback_at', 'next_due_at'):
        if getattr(row, key):
            result[key] = iso_utc(getattr(row, key))
    if row.feedback_note:
        result['feedback_note'] = row.feedback_note
    return result


async def access(db, actor, reminder_id, *, write=False):
    row = await db.get(Reminder, reminder_id)
    if not row:
        raise AppError('REMINDER_NOT_FOUND', '提醒不存在或无权访问。', 404)
    try:
        await family.context(db, actor.user_id, row.family_id)
        await db.refresh(row)
        if row.deleted_at:
            raise AppError('REMINDER_NOT_FOUND', '提醒不存在或无权访问。', 404)
        await authorize(db, actor, row.family_id, row.owner_user_id, 'REMINDER_WRITE' if write else 'REMINDER_READ',
            'HEALTH_MEDICATION' if row.type == 'MEDICATION' else None, allow_self=not(write and row.type == 'MEDICATION'))
    except AppError as error:
        if error.status_code in (403, 404):
            raise AppError('REMINDER_NOT_FOUND', '提醒不存在或无权访问。', 404) from None
        raise
    return row


def assign(row, body, now):
    for key in ('type', 'title', 'content', 'schedule_time_local', 'timezone', 'start_date', 'end_date',
                'recurrence_kind', 'recurrence_interval', 'escalation_policy'):
        setattr(row, key, getattr(body, key))
    row.days_of_week = list(body.days_of_week)
    quiet = body.quiet_hours
    row.quiet_hours_start, row.quiet_hours_end, row.quiet_hours_timezone = (quiet.start, quiet.end, quiet.timezone) if quiet else (None, None, None)
    next_item = next_occurrence(schedule(row), now, POLICY)
    row.next_due_at = next_item.scheduled_at if next_item else None
    row.updated_at = now


async def create(db, actor, body, key, settings, request_id):
    fid = await resolve_family(db, actor, body.owner_user_id, body.family_id)
    await authorize(db, actor, fid, body.owner_user_id, 'REMINDER_WRITE', 'HEALTH_MEDICATION' if body.type == 'MEDICATION' else None,
                    allow_self=body.type != 'MEDICATION')
    idem = audit.Idempotency(key, 'reminder-create', body.model_dump(mode='json'))
    previous = await idem.previous(db, actor.user_id, settings.idempotency_seconds)
    if previous:
        return view(await access(db, actor, previous))
    now = utcnow()
    row = Reminder(id=uuid7(), family_id=fid, owner_user_id=body.owner_user_id, created_by_user_id=actor.user_id,
                   active=True, version=1, created_at=now)
    assign(row, body, now)
    db.add(row)
    await audit.record(db, actor.user_id, 'REMINDER_CREATED', 'REMINDER', row.id, fid, request_id, metadata=idem.metadata)
    return view(row)


async def update(db, actor, reminder_id, body, expected, request_id):
    row = await access(db, actor, reminder_id, write=True)
    check_version(row, expected)
    if body.owner_user_id != row.owner_user_id or body.family_id and body.family_id != row.family_id:
        raise AppError('PERMISSION_DENIED', '不能通过修改提醒变更所属家庭或长辈。', 403)
    if body.type == 'MEDICATION':
        await authorize(db, actor, row.family_id, row.owner_user_id, 'REMINDER_WRITE', 'HEALTH_MEDICATION', allow_self=False)
    assign(row, body, utcnow())
    row.version += 1
    await audit.record(db, actor.user_id, 'REMINDER_UPDATED', 'REMINDER', row.id, row.family_id, request_id)
    return view(row)


async def detail(db, actor, reminder_id, request_id):
    row = await access(db, actor, reminder_id)
    await audit.record(db, actor.user_id, 'REMINDER_READ', 'REMINDER', row.id, row.family_id, request_id)
    return view(row)


async def delete(db, actor, reminder_id, request_id):
    row = await access(db, actor, reminder_id, write=True)
    row.active, row.deleted_at, row.next_due_at = False, utcnow(), None
    row.version += 1
    await audit.record(db, actor.user_id, 'REMINDER_DELETED', 'REMINDER', row.id, row.family_id, request_id)


async def listing(db, actor, family_id, owner_user_id, type, active, limit, cursor, settings, request_id):
    clauses = []
    for fid, _ in sorted(await family.visibility(db, actor.user_id), key=lambda x: str(x[0])):
        if family_id and fid != family_id:
            continue
        general = await visible_subjects(db, actor, fid, 'REMINDER_READ')
        health = await visible_subjects(db, actor, fid, 'REMINDER_READ', 'HEALTH_MEDICATION')
        clauses += [and_(Reminder.family_id == fid, Reminder.owner_user_id.in_(general), Reminder.type != 'MEDICATION'),
                    and_(Reminder.family_id == fid, Reminder.owner_user_id.in_(health), Reminder.type == 'MEDICATION')]
    query = select(Reminder).where(or_(*clauses) if clauses else Reminder.id.is_(None), Reminder.deleted_at.is_(None))
    for column, value in ((Reminder.owner_user_id, owner_user_id), (Reminder.type, type), (Reminder.active, active)):
        if value is not None:
            query = query.where(column == value)
    rows, page = await page_rows(db, query, Reminder, codec(settings), f'reminders:{actor.user_id}:{family_id}:{owner_user_id}:{type}:{active}', limit, cursor)
    await audit.record(db, actor.user_id, 'REMINDER_LIST_READ', 'REMINDER', request_id=request_id)
    return dict(items=[view(r) for r in rows], page=page)


async def executions(db, actor, reminder_id, limit, cursor, settings, request_id):
    row = await access(db, actor, reminder_id)
    rows, page = await page_rows(db, select(ReminderExecution).where(ReminderExecution.reminder_id == row.id),
        ReminderExecution, codec(settings), f'executions:{actor.user_id}:{row.id}', limit, cursor)
    await audit.record(db, actor.user_id, 'REMINDER_EXECUTIONS_READ', 'REMINDER', row.id, row.family_id, request_id)
    return dict(items=[execution_view(r) for r in rows], page=page)


async def feedback(db, actor, execution_id, body, key, settings, request_id):
    row = await db.get(ReminderExecution, execution_id)
    if not row or row.owner_user_id != actor.user_id:
        raise AppError('REMINDER_NOT_FOUND', '提醒记录不存在或无权访问。', 404)
    parent = await access(db, actor, row.reminder_id)
    await db.refresh(row)
    idem = audit.Idempotency(key, f'reminder-feedback:{row.id}', body.model_dump(mode='json'))
    if await idem.previous(db, actor.user_id, settings.idempotency_seconds):
        return execution_view(row)
    if row.feedback_status in ('DONE', 'SKIPPED'):
        raise AppError('ETAG_MISMATCH', '此提醒已有反馈，请刷新。', 409)
    now = utcnow()
    if body.status == 'LATER' and (body.next_due_at is None or not now < body.next_due_at <= now + timedelta(days=1)):
        raise AppError('VALIDATION_ERROR', '稍后时间需在未来一天内。', 422)
    if body.status != 'LATER' and body.next_due_at is not None:
        raise AppError('VALIDATION_ERROR', '只有稍后提醒可设置下一次时间。', 422)
    row.feedback_status, row.feedback_at, row.feedback_note = body.status, now, body.note
    row.next_due_at = body.next_due_at if body.status == 'LATER' else None
    await audit.record(db, actor.user_id, 'REMINDER_FEEDBACK', 'REMINDER_EXECUTION', row.id, parent.family_id, request_id, metadata=idem.metadata)
    return execution_view(row)


async def offline_feedback(db, actor, reminder_id, body, key, settings, request_id):
    parent = await access(db, actor, reminder_id)
    if parent.owner_user_id != actor.user_id or not parent.active:
        raise AppError('REMINDER_NOT_FOUND', '提醒不存在或无权反馈。', 404)
    check_version(parent, body.reminder_version)
    idem = audit.Idempotency(key, f'offline-feedback:{parent.id}', body.model_dump(mode='json'))
    previous = await idem.previous(db, actor.user_id, max(86400, settings.idempotency_seconds))
    if previous:
        return execution_view(await db.get(ReminderExecution, previous))
    now = utcnow()
    if not body.scheduled_at <= body.feedback_at <= now or body.feedback_at < now - timedelta(hours=24):
        raise AppError('VALIDATION_ERROR', '离线反馈时间无效或已过期，请联网核对。', 422)
    item = next_occurrence(schedule(parent), body.scheduled_at, POLICY)
    if not item or item.scheduled_at != body.scheduled_at:
        raise AppError('VALIDATION_ERROR', '该时间不是有效的计划提醒。', 422)
    if body.status == 'LATER' and (body.next_due_at is None or not now < body.next_due_at <= now + timedelta(days=1)):
        raise AppError('VALIDATION_ERROR', '稍后时间已过或无效，请重新选择。', 422)
    if body.status != 'LATER' and body.next_due_at is not None:
        raise AppError('VALIDATION_ERROR', '只有稍后反馈可设置下次时间。', 422)
    await db.execute(insert(ReminderExecution).values(id=uuid7(), reminder_id=parent.id, owner_user_id=actor.user_id,
        occurrence_key=item.occurrence_key, scheduled_at=item.scheduled_at, local_date=item.local_date,
        local_time=item.local_time, source='OFFLINE', feedback_status='PENDING', created_at=now).on_conflict_do_nothing(
        constraint='uq_reminder_occurrence'))
    row = await db.scalar(select(ReminderExecution).where(ReminderExecution.reminder_id == parent.id,
        ReminderExecution.occurrence_key == item.occurrence_key).with_for_update())
    if row.feedback_status in ('DONE', 'SKIPPED'):
        raise AppError('ETAG_MISMATCH', '提醒已有反馈，请刷新核对。', 409)
    row.feedback_status, row.feedback_at, row.next_due_at = body.status, now, body.next_due_at
    await audit.record(db, actor.user_id, 'REMINDER_OFFLINE_FEEDBACK', 'REMINDER_EXECUTION', row.id,
        parent.family_id, request_id, metadata=idem.metadata)
    return execution_view(row)


async def tick(db, settings, now=None):
    """One PostgreSQL-serialized cycle. Executions represent availability, not delivery."""
    now = now or utcnow()
    due = (await db.scalars(select(Reminder).where(Reminder.active.is_(True), Reminder.deleted_at.is_(None),
        Reminder.next_due_at <= now).order_by(Reminder.next_due_at).limit(100).with_for_update(skip_locked=True))).all()
    count = 0
    for row in due:
        rule = schedule(row)
        item = next_occurrence(rule, row.next_due_at, POLICY)
        if item and item.scheduled_at <= now:
            await db.execute(insert(ReminderExecution).values(id=uuid7(), reminder_id=row.id, owner_user_id=row.owner_user_id,
                occurrence_key=item.occurrence_key, scheduled_at=item.scheduled_at, local_date=item.local_date, local_time=item.local_time,
                source='ONLINE', feedback_status='PENDING', attempt_count=0, created_at=now).on_conflict_do_nothing(
                    constraint='uq_reminder_occurrence'))
            count += 1
            following = next_occurrence(rule, item.scheduled_at + timedelta(seconds=1), POLICY)
            row.next_due_at = following.scheduled_at if following else None
    pending = (await db.execute(select(ReminderExecution, Reminder).join(Reminder).where(
        Reminder.active.is_(True), Reminder.deleted_at.is_(None),
        ReminderExecution.feedback_status.in_(('PENDING', 'LATER'))).limit(500).with_for_update(skip_locked=True))).all()
    for execution, parent in pending:
        quiet = in_quiet_hours(now, schedule(parent).quiet_hours, POLICY)
        if execution.feedback_status == 'LATER' and execution.next_due_at <= now and not quiet:
            execution.feedback_status, execution.next_due_at, execution.triggered_at = 'PENDING', None, now
            execution.attempt_count += 1
        elif execution.feedback_status == 'PENDING':
            if execution.triggered_at is None and not quiet:
                execution.triggered_at, execution.attempt_count = now, execution.attempt_count + 1
            elif execution.triggered_at and execution.triggered_at + timedelta(seconds=settings.reminder_feedback_seconds) <= now:
                execution.feedback_status = 'NO_RESPONSE'
    return count
