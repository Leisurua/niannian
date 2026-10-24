from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app.modules.audit import service as audit
from app.modules.auth.service import active_user
from app.modules.consent import service as consent
from app.modules.conversation.models import Conversation
from app.modules.family import service as family
from app.modules.reminder.models import Reminder, ReminderExecution
from app.modules.report import metrics
from app.modules.report.models import InteractionMetric
from app.modules.signal.models import SignalEvent
from app.modules.signal.service import accessible
from app.platform.errors import AppError
from app.platform.identifiers import utcnow
from app.platform.resource_access import authorize

NOTICE = '交流观察线索：仅反映系统中可用的交流与反馈记录，不用于判断疾病、心理状态、睡眠质量或认知能力。'
METHOD = ('互动次数为有成功文字交互的不同会话数，轮次按服务端完成时间归属。活跃交流时长为回复耗时与同会话内不超过五分钟的相邻轮次间隔之和，'
          '每轮最多计五分钟，不是录音时长。夜间为所选时区 22:00—06:00。情绪只识别有限的第一人称明确表达，未识别不代表没有相关感受。'
          '重复主题按本地固定词组及同义词分类，计算不同会话数；同一会话多次提及只计一次，不能等同于完整语义相似度分析。')


def period(start, end, timezone_name, *, now=None):
    try:
        zone = ZoneInfo(timezone_name)
    except (ValueError, ZoneInfoNotFoundError):
        raise AppError('VALIDATION_ERROR', '请使用有效的 IANA 时区。', 422) from None
    today = (now or utcnow()).astimezone(zone).date()
    if not 1 <= (end - start).days <= 31 or start > today or start < today - timedelta(days=35):
        raise AppError('VALIDATION_ERROR', '统计范围需为最近 35 天内开始、长度 1—31 天的日期范围。', 422)
    if end > today + timedelta(days=7):
        raise AppError('VALIDATION_ERROR', '结束日期超出允许范围。', 422)
    return zone, datetime.combine(start, time.min, zone).astimezone(timezone.utc), datetime.combine(end, time.min, zone).astimezone(timezone.utc)


async def access(db, actor, fid, owner, reason):
    await active_user(db, owner, lock=False)
    await authorize(db, actor, fid, owner, 'REPORT_READ', 'INTERACTION_STATS')
    member = await family.require_member(db, fid, owner)
    if member.role != 'ELDER':
        raise AppError('VALIDATION_ERROR', '请选择当前家庭中的长辈。', 422)
    if reason not in (None, 'FAMILY_CHECK_IN', 'FOLLOW_UP') or actor.user_id != owner and reason is None:
        raise AppError('VALIDATION_ERROR', '查看家人统计需要选择关心近况或跟进交流。', 422)


async def allowed(db, actor, fid, owner, permission, scope=None):
    try:
        await authorize(db, actor, fid, owner, permission, scope)
        return True
    except AppError as error:
        if error.status_code in (403, 404):
            return False
        raise


async def build(db, actor, fid, owner, start, end, timezone_name):
    now = utcnow()
    zone, since, until = period(start, end, timezone_name, now=now)
    until = min(until, now)
    missing = []
    grant = await consent.latest(db, fid, owner, owner, 'INTERACTION_STATS')
    collecting = bool(grant and grant.status == 'GRANTED' and (grant.expires_at is None or grant.expires_at > now))
    rows = []
    if collecting:
        rows = (await db.scalars(select(InteractionMetric).join(Conversation).where(
            InteractionMetric.family_id == fid, InteractionMetric.owner_user_id == owner,
            InteractionMetric.consent_id == grant.id, InteractionMetric.retention_until > now,
            InteractionMetric.occurred_at >= since, InteractionMetric.occurred_at < until,
            Conversation.deleted_at.is_(None), Conversation.status != 'DELETED',
        ).order_by(InteractionMetric.occurred_at, InteractionMetric.sequence))).all()
        if grant.granted_at > since:
            missing.append('本期统计授权未覆盖完整时间范围；开启前的交流不会补录。')
    else:
        missing.append('长辈尚未开启或已撤回本人互动统计，交流指标没有可用数据。')
    interaction = metrics.aggregate(rows, start, end, zone)
    if not rows:
        missing.append('本期没有可用互动记录；不能据此判断是否进行过交流。')
    if interaction['simulated_turns']:
        missing.append(f"包含 {interaction['simulated_turns']} 轮 Mock 对话，不能作为真实陪伴效果证据。")
    reminder_stats = None
    if await allowed(db, actor, fid, owner, 'REMINDER_READ'):
        health = await allowed(db, actor, fid, owner, 'REMINDER_READ', 'HEALTH_MEDICATION')
        query = select(ReminderExecution).join(Reminder).where(
            Reminder.family_id == fid, Reminder.owner_user_id == owner, Reminder.deleted_at.is_(None),
            ReminderExecution.owner_user_id == owner, ReminderExecution.scheduled_at >= since,
            ReminderExecution.scheduled_at < until)
        if not health:
            query = query.where(Reminder.type != 'MEDICATION')
            missing.append('未获健康与用药授权，用药提醒未计入。')
        executions = (await db.scalars(query)).all()
        feedback = {key: sum(row.feedback_status == key for row in executions) for key in ('DONE', 'LATER', 'SKIPPED', 'PENDING', 'NO_RESPONSE')}
        response_seconds = [max(0, (row.feedback_at - (row.triggered_at or row.scheduled_at)).total_seconds())
            for row in executions if row.feedback_at and row.feedback_status in ('DONE', 'LATER', 'SKIPPED')]
        reminder_stats = dict(total=len(executions), feedback=feedback,
            average_response_seconds=round(sum(response_seconds) / len(response_seconds)) if response_seconds else None)
        if not executions:
            missing.append('本期无可用提醒执行记录；未调度、已删除或未授权的数据不在统计中。')
    else:
        missing.append('当前成员无提醒读取权限，提醒反馈不可用。')
    signals = None
    if await allowed(db, actor, fid, owner, 'SIGNAL_READ', 'NOTIFICATION_TO_FAMILY',):
        candidates = (await db.scalars(select(SignalEvent).where(SignalEvent.family_id == fid,
            SignalEvent.owner_user_id == owner, SignalEvent.detected_at >= since, SignalEvent.detected_at < until,
            SignalEvent.retention_until > now, SignalEvent.deleted_at.is_(None),
            SignalEvent.status.not_in(('DETECTED', 'WITHHELD', 'FALSE_POSITIVE'))))).all()
        visible = [row for row in candidates if await accessible(db, row, actor, owner_status=actor.user_id == owner)]
        signals = dict(total=len(visible), by_type={kind: sum(row.type == kind for row in visible) for kind in sorted({row.type for row in visible})},
            simulated=sum(row.policy_version.startswith('w7-mock') for row in visible))
        missing.append('关注提示仅计当前仍可访问的事件（现有事件保留七天），不是完整健康记录。')
    else:
        missing.append('未获关注提示权限或授权，关注提示不可用。')
    if end > now.astimezone(zone).date():
        missing.append('本期尚未结束，统计截至生成时间，后续数据会随刷新更新。')
    return dict(period=dict(start=start.isoformat(), end_exclusive=end.isoformat(), timezone=timezone_name),
        interaction=interaction, reminders=reminder_stats, attention=signals, missing_data=missing,
        collection_enabled=collecting, generated_at=now.isoformat(), notice=NOTICE, methodology=METHOD)


def narrative(report):
    data = report['current']
    count = data['interaction']
    lines = [f"念念周报 · {data['period']['start']} 至 {data['period']['end_exclusive']}（结束日不含）",
        f"时区：{data['period']['timezone']}；生成时间：{data['generated_at']}", NOTICE,
        f"可用记录：{count['sessions']} 次交流、{count['turns']} 轮；活跃交流时长约 {count['active_seconds'] / 60:.1f} 分钟。",
        f"夜间互动：{count['night_turns']} 轮；Mock 对话：{count['simulated_turns']} 轮。"]
    delta = report['comparison']['sessions_delta']
    if delta is not None:
        comparison = report['comparison']
        lines.append(f"相比上周：交流次数 {delta:+d}，互动轮数 {comparison['turns_delta']:+d}，"
            f"活跃时长 {comparison['active_seconds_delta'] / 60:+.1f} 分钟，夜间互动 {comparison['night_turns_delta']:+d} 轮。")
    else:
        lines.append('上周或本周缺少互动数据，暂不计算趋势。')
    hours = [(hour, total) for hour, total in enumerate(count['hourly_turns']) if total]
    lines.append('互动时段（轮次）：' + ('、'.join(f'{hour:02d}:00—{hour + 1:02d}:00 {total}' for hour, total in hours) or '暂无记录') + '。')
    lines.append('情绪相关明确表达（轮次）：' + '、'.join(f'{key} {value}' for key, value in count['emotions'].items()) + '。')
    lines.append('重复主题：' + ('；'.join(f"{item['topic']}涉及 {item['sessions']} 次交流" for item in count['repeated_topics']) or '未观察到可分类的跨会话重复主题') + '。')
    lines.append(f"未分类主题：{count['unclassified_topic_turns']} 轮。")
    for day in count['days']:
        if day['turns']:
            lines.append(f"{day['date']}：{day['turns']} 轮，首次 {day['first_interaction'][11:16]}，末次 {day['last_interaction'][11:16]}。")
    reminders = data['reminders']
    if reminders is not None:
        feedback = reminders['feedback']
        lines.append(f"提醒 {reminders['total']} 次：完成 {feedback['DONE']}、稍后 {feedback['LATER']}、跳过 {feedback['SKIPPED']}、尚未收到反馈 {feedback['PENDING'] + feedback['NO_RESPONSE']}。")
        if reminders['average_response_seconds'] is not None:
            lines.append(f"平均提醒响应时间：{reminders['average_response_seconds']} 秒。")
    if data['attention'] is not None:
        lines.append(f"当前可见关注提示 {data['attention']['total']} 条，其中 Mock {data['attention']['simulated']} 条。")
    lines.extend(['数据说明：', *data['missing_data'], '上周数据说明：', *report['previous']['missing_data'], METHOD])
    return '\n'.join(lines)


async def statistics(db, actor, fid, owner, start, end, timezone_name, reason, request_id):
    await access(db, actor, fid, owner, reason)
    result = await build(db, actor, fid, owner, start, end, timezone_name)
    event = await audit.record(db, actor.user_id, 'STATISTICS_READ', 'REPORT', owner, fid, request_id)
    event.reason = reason
    return result


async def weekly(db, actor, fid, owner, week, timezone_name, reason, request_id):
    await access(db, actor, fid, owner, reason)
    try:
        today = utcnow().astimezone(ZoneInfo(timezone_name)).date()
    except (ValueError, ZoneInfoNotFoundError):
        raise AppError('VALIDATION_ERROR', '请使用有效的 IANA 时区。', 422) from None
    week = week or today - timedelta(days=today.weekday())
    if week.weekday() != 0 or week > today or week < today - timedelta(days=28):
        raise AppError('VALIDATION_ERROR', '周报开始日期须为最近 28 天内的星期一。', 422)
    current = await build(db, actor, fid, owner, week, week + timedelta(days=7), timezone_name)
    previous = await build(db, actor, fid, owner, week - timedelta(days=7), week, timezone_name)
    a, b = current['interaction'], previous['interaction']
    comparison = {key + '_delta': a[key] - b[key] if a['turns'] and b['turns'] else None
        for key in ('sessions', 'turns', 'active_seconds', 'night_turns')}
    result = dict(family_id=str(fid), owner_user_id=str(owner), current=current, previous=previous, comparison=comparison)
    result['text'] = narrative(result)
    event = await audit.record(db, actor.user_id, 'WEEKLY_REPORT_READ', 'REPORT', owner, fid, request_id)
    event.reason = reason
    return result
