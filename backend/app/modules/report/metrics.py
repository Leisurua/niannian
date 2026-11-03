import re
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert

from app.modules.consent import service as consent
from app.modules.conversation.models import Conversation
from app.modules.family import service as family
from app.modules.report.models import InteractionMetric
from app.modules.report.semantics import TOPICS, affirmed_parts, rule_topics, classify_topics
from app.platform.config import get_settings
from app.platform.errors import AppError
from app.platform.identifiers import utcnow

EMOTIONS = {'HAPPY': '开心', 'SAD': '难过', 'LONELY': '孤独', 'WORRIED': '担忧', 'MISS_FAMILY': '思念家人'}



def classify(text):
    emotions = set()
    parts = affirmed_parts(text)
    for clause in parts:
        clause = clause.strip()
        if any(mark in clause for mark in ('不', '没', '别', '？', '?', '吗', '说', '"', '“', '”')):
            continue
        for code, words in {
            'HAPPY': '开心|高兴|快乐|舒心|愉快|乐呵呵', 'SAD': '难过|伤心|悲伤|低落|难受',
            'LONELY': '孤单|孤独|寂寞|冷清', 'WORRIED': '担心|担忧|忧虑|发愁|焦虑',
            'MISS_FAMILY': '(?:想念|思念|想)(?:我的)?(?:女儿|儿子|家人|孩子)',
        }.items():
            if re.fullmatch(r'我(?:今天|现在|这几天|最近)?(?:觉得|感到|心里|心情)?(?:有点|很|非常|特别|真|挺)?(?:' + words + r')(?:了|啊|呀)?', clause):
                emotions.add(code)
    topics = rule_topics(parts)
    return sorted(emotions), topics


async def collect(db, row, sequence, text, started_at, completed_at, *, simulated=None):
    try:
        grant_id = await consent.explicit_scope(db, row.family_id, row.owner_user_id, row.owner_user_id, 'INTERACTION_STATS')
    except AppError as error:
        if error.status_code in (401, 403, 404):
            return
        raise
    grant = await consent.latest(db, row.family_id, row.owner_user_id, row.owner_user_id, 'INTERACTION_STATS')
    if started_at < grant.granted_at:
        return
    cleared = row.provider_metadata.get('stats_cleared_at')
    if cleared and started_at < datetime.fromisoformat(cleared):
        return
    previous = await db.scalar(select(InteractionMetric).where(
        InteractionMetric.conversation_id == row.id, InteractionMetric.consent_id == grant_id,
        InteractionMetric.sequence < sequence).order_by(InteractionMetric.sequence.desc()).limit(1))
    start = max(started_at, previous.occurred_at) if previous else started_at
    if previous and (started_at - previous.occurred_at).total_seconds() <= 300:
        start = previous.occurred_at
    duration = min(300, max(0, int((completed_at - start).total_seconds())))
    if await db.get(InteractionMetric, (row.id, sequence)) is not None:
        return
    emotions, _ = classify(text)
    classified = await classify_topics(text, get_settings())
    topics = list(classified.topics)
    # Recheck expiry after local inference; no result may outlive its grant.
    try:
        if await consent.explicit_scope(db, row.family_id, row.owner_user_id, row.owner_user_id, 'INTERACTION_STATS') != grant_id:
            return
    except AppError as error:
        if error.status_code in (401, 403, 404):
            return
        raise
    await db.execute(insert(InteractionMetric).values(
        conversation_id=row.id, sequence=sequence, family_id=row.family_id, owner_user_id=row.owner_user_id,
        consent_id=grant_id, occurred_at=completed_at, duration_seconds=duration, emotions=emotions, topics=topics,
        topic_method=classified.method, topic_model_version=classified.model_version,
        simulated=row.provider_metadata.get('provider') == 'mock' if simulated is None else simulated,
        retention_until=min(completed_at + timedelta(days=35), grant.expires_at or completed_at + timedelta(days=35)),
    ).on_conflict_do_nothing(index_elements=['conversation_id', 'sequence']))


async def erase(db, family_id, owner):
    await db.execute(delete(InteractionMetric).where(InteractionMetric.family_id == family_id, InteractionMetric.owner_user_id == owner))
    await db.execute(update(Conversation).where(Conversation.family_id == family_id, Conversation.owner_user_id == owner).values(
        provider_metadata=Conversation.provider_metadata.op('||')({'stats_cleared_at': utcnow().isoformat()})))


async def maintenance(db):
    await db.execute(delete(InteractionMetric).where(InteractionMetric.retention_until <= utcnow()))
    pairs = (await db.execute(select(InteractionMetric.family_id, InteractionMetric.owner_user_id).distinct())).all()
    for fid, owner in sorted(pairs):
        try:
            await family.context(db, owner, fid)
            grant_id = await consent.explicit_scope(db, fid, owner, owner, 'INTERACTION_STATS')
        except AppError:
            await erase(db, fid, owner)
            continue
        await db.execute(delete(InteractionMetric).where(InteractionMetric.family_id == fid,
            InteractionMetric.owner_user_id == owner, InteractionMetric.consent_id != grant_id))
    await db.execute(delete(InteractionMetric).where(InteractionMetric.conversation_id.in_(
        select(Conversation.id).where((Conversation.deleted_at.is_not(None)) | (Conversation.status == 'DELETED')))))


def aggregate(rows, start, end, zone):
    days = {}
    for offset in range((end - start).days):
        day = (start + timedelta(days=offset)).isoformat()
        days[day] = dict(date=day, turns=0, sessions=0, active_seconds=0, first_interaction=None, last_interaction=None)
    sessions, daily_sessions = set(), {day: set() for day in days}
    emotions, topic_sessions = Counter(), {key: set() for key in TOPICS}
    hours = [0] * 24
    simulated, unclassified = 0, 0
    classification = Counter({method: 0 for method in ("RULE", "LOCAL_SEMANTIC", "RULE_FALLBACK")})
    for row in rows:
        local = row.occurred_at.astimezone(zone)
        if local.date().isoformat() not in days:
            continue
        day = days[local.date().isoformat()]
        stamp = local.isoformat()
        day['turns'] += 1
        day['active_seconds'] += row.duration_seconds
        day['first_interaction'] = min(day['first_interaction'] or stamp, stamp)
        day['last_interaction'] = max(day['last_interaction'] or stamp, stamp)
        sessions.add(row.conversation_id)
        daily_sessions[day['date']].add(row.conversation_id)
        hours[local.hour] += 1
        simulated += int(row.simulated)
        emotions.update(label for label in set(row.emotions) if label in EMOTIONS)
        classification[getattr(row, "topic_method", "RULE")] += 1
        valid_topics = set(row.topics) & TOPICS.keys()
        unclassified += int(not valid_topics)
        for topic in valid_topics:
            topic_sessions[topic].add(row.conversation_id)
    for day in days.values():
        day['sessions'] = len(daily_sessions[day['date']])
    return dict(sessions=len(sessions), turns=sum(hours), active_seconds=sum(day['active_seconds'] for day in days.values()),
        simulated_turns=simulated, days=list(days.values()), hourly_turns=hours, night_turns=sum(hours[:6]) + sum(hours[22:]),
        emotions={EMOTIONS[key]: emotions[key] for key in EMOTIONS},
        repeated_topics=[dict(topic=TOPICS[key][0], sessions=len(ids)) for key, ids in topic_sessions.items() if len(ids) >= 2],
        unclassified_topic_turns=unclassified, topic_classification=dict(classification))
