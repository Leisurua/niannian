"""W6 controlled Mock recap. Only curated themes, never transcripts, are stored."""
from datetime import timedelta

from sqlalchemy import select, update

from app.modules.auth.service import active_user
from app.modules.consent import service as consent
from app.modules.conversation.models import Conversation
from app.modules.device.service import require_active_binding
from app.platform import tasks
from app.platform.errors import AppError
from app.platform.identifiers import utcnow

TOPICS = (
    '这次交流谈到了日常生活。', '这次交流了解了念念的 AI 身份与能力边界。',
    '这次交流询问了家庭记忆；内容以当前授权和已确认记录为准。',
    '这次交流询问了天气或日程；Mock 不提供真实天气或执行结果。',
    '这次交流提到了需要核实的问题，可主动联系身边的人。',
)


def topic_for(text):
    if any(word in text for word in ('救命', '急救', '不舒服', '疼', '验证码', '转账', '密码')):
        return TOPICS[4]
    if any(word in text for word in ('你是谁', '你是AI', '你是 AI', '真人')):
        return TOPICS[1]
    if any(word in text for word in ('天气', '下雨', '提醒', '日程', '几点')):
        return TOPICS[3]
    if any(word in text for word in ('女儿', '儿子', '家人', '记得', '家庭')):
        return TOPICS[2]
    return TOPICS[0]


def controlled_text(value):
    if not value or len(value) > 1000:
        return None
    lines = value.split('\n')
    if not 1 <= len(lines) <= 4 or len(set(lines)) != len(lines) or any(line not in TOPICS for line in lines):
        return None
    return '\n'.join(lines)


async def eligible(db, row):
    if (row.deleted_at or row.status == 'DELETED' or row.provider_metadata.get('provider') != 'mock'
            or row.summary_text and row.summary_retention_until is None
            or row.summary_retention_until and row.summary_retention_until <= utcnow()):
        return None
    try:
        await active_user(db, row.owner_user_id, lock=False)
        if row.device_binding_id:
            await require_active_binding(db, row.device_binding_id, row.owner_user_id)
        await consent.explicit_scope(db, row.family_id, row.owner_user_id, row.owner_user_id, 'CONVERSATION_SUMMARY')
        return await consent.latest(db, row.family_id, row.owner_user_id, row.owner_user_id, 'CONVERSATION_SUMMARY')
    except AppError as error:
        if error.status_code in (401, 403, 404):
            return None
        raise


async def invalidate(db, row):
    if row.summary_status != 'DELETED' and (row.summary_text is not None or row.summary_status in ('PENDING', 'READY')):
        row.summary_status = 'DELETED'
        row.summary_version += 1
        await tasks.enqueue(db, 'CONVERSATION_SUMMARY_CLEANUP', row.family_id, row.id, row.summary_version)


async def add_topic(db, row, topic):
    if topic not in TOPICS:
        return
    grant = await eligible(db, row)
    if grant is None:
        await invalidate(db, row)
        return
    now = utcnow()
    if row.summary_retention_until is None:
        row.summary_retention_until = min(now + timedelta(hours=24), grant.expires_at or now + timedelta(hours=24))
    previous = controlled_text(row.summary_text) if row.summary_status in ('PENDING', 'READY') else None
    lines = list(dict.fromkeys((previous.split('\n') if previous else []) + [topic]))[-4:]
    row.summary_text = '\n'.join(lines)
    row.summary_status = 'PENDING'
    row.summary_version += 1


async def request(db, row, *, explicit=False):
    if not await eligible(db, row):
        await invalidate(db, row)
        if explicit:
            raise AppError('PERMISSION_CONSENT_REQUIRED', '请先由长辈本人允许生成会话回顾；过期摘要不可恢复。', 403)
        return
    if not controlled_text(row.summary_text):
        if explicit:
            row.summary_text, row.summary_status = None, 'FAILED'
        return
    if row.summary_status == 'PENDING':
        await tasks.enqueue(db, 'CONVERSATION_SUMMARY', row.family_id, row.id, row.summary_version)


async def readable(db, row):
    if not await eligible(db, row):
        await invalidate(db, row)
        return None
    return controlled_text(row.summary_text) if row.summary_status == 'READY' else None


async def prepare(db, resource_id, version):
    row = await db.get(Conversation, resource_id)
    if not row:
        return None
    grant = await eligible(db, row)  # locks family before task fence
    await db.refresh(row)
    if grant is None or row.summary_version != version or row.summary_status != 'PENDING':
        return None
    value = controlled_text(row.summary_text)
    if value is None:
        return None
    return row.family_id, grant.id, value


async def complete(db, resource_id, version, prepared):
    if prepared and await prepare(db, resource_id, version) == prepared:
        row = await db.get(Conversation, resource_id)
        row.summary_status = 'READY'


async def cleanup(db, resource_id, version):
    await db.execute(update(Conversation).where(Conversation.id == resource_id,
        Conversation.summary_version == version, Conversation.summary_status == 'DELETED').values(summary_text=None))


async def consent_changed(db, family_id, subject, grantee, scope):
    if scope != 'CONVERSATION_SUMMARY' or subject != grantee:
        return
    rows = (await db.scalars(select(Conversation).where(Conversation.family_id == family_id,
        Conversation.owner_user_id == subject, Conversation.summary_text.is_not(None)))).all()
    for row in rows:
        await invalidate(db, row)


async def maintenance(db):
    rows = (await db.scalars(select(Conversation).where(
        Conversation.summary_text.is_not(None)).order_by(Conversation.started_at))).all()
    for row in rows:
        if not await eligible(db, row):
            await invalidate(db, row)
        elif row.summary_status in ('PENDING', 'READY') and controlled_text(row.summary_text) is None:
            row.summary_version += 1
            row.summary_status, row.summary_text = 'FAILED', None
    dead = (await db.scalars(select(tasks.Task).where(tasks.Task.kind == 'CONVERSATION_SUMMARY', tasks.Task.status == 'DEAD'))).all()
    for task in dead:
        row = await db.get(Conversation, task.resource_id)
        if row and row.summary_version == task.resource_version and row.summary_status == 'PENDING':
            row.summary_status, row.summary_text = 'FAILED', None
