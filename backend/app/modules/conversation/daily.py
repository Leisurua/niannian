import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from app.modules.reminder import service as reminders
from app.modules.audit import service as audit
from app.modules.reminder.models import Reminder, ReminderExecution
from app.modules.reminder.schedule import occurrences, next_occurrence
from app.modules.reminder.schemas import ReminderFeedback
from app.modules.safety.rules import evaluate
from app.platform.errors import AppError
from app.platform.identifiers import utcnow, uuid7
from app.platform.resource_access import authorize


@dataclass(frozen=True)
class Choice:
    reminder_id: UUID
    version: int
    scheduled_at: datetime
    occurrence_key: str
    title: str
    status: str
    next_due_at: datetime | None = None
    triggered_at: datetime | None = None


@dataclass(frozen=True)
class Answer:
    kind: str
    text: str
    choices: tuple[Choice, ...] = ()
    sources: tuple[str, ...] = ('查询提示',)
    reminders_changed: bool = False


def normalized(text):
    return re.sub(r'[\s，,。！!]', '', text)


def feedback_command(text):
    value = normalized(text)
    if any(word in value for word in ('不', '没', '未', '别', '无须', '无需', '如果', '假如', '假设', '要是',
            '可能', '也许', '大概', '好像', '应该', '准备', '打算', '说', '吗', '么', '?', '？', '“', '”', '"', "'", '「', '」', '‘', '’')):
        return None
    value = re.sub(r'^(?:请|帮我|我把|我)', '', value)
    done = re.fullmatch(r'(.*?)(?:已经|已)?(?:完成了?|做完了?|办完了?)', value)
    if done:
        return 'DONE', done[1], None
    if value in ('吃过药了', '吃药了', '药吃过了', '药吃了'):
        return 'DONE', '药', None
    if value in ('喝过水了', '喝水了', '水喝了'):
        return 'DONE', '水', None
    later = re.fullmatch(r'(.*?)(?:稍后处理|稍后提醒我|稍后再提醒我|稍后提醒|等会儿?再提醒我|等会儿?处理)', value)
    if later:
        return 'LATER', later[1], 10
    delay = re.fullmatch(r'(.*?)([一二三四五六七八九十两\d]+)分钟后(?:再)?提醒我', value)
    if delay:
        number = delay[2]
        digits = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
        if number.isdigit():
            minutes = int(number) if len(number) <= 4 else 0
        elif number in digits:
            minutes = digits[number]
        elif number.count('十') == 1:
            tens, ones = number.split('十')
            minutes = (digits.get(tens, 1) * 10 + digits.get(ones, 0)) if (not tens or tens in digits) and (not ones or ones in digits) else 0
        else:
            minutes = 0
        return 'LATER', delay[1], minutes
    return None


def intent(text):
    if evaluate(text).kind in ('SCAM_RISK', 'EMERGENCY'):
        return None
    value = normalized(text)
    if feedback_command(text):
        return 'FEEDBACK'
    if any(word in value for word in ('完成', '做完', '稍后处理', '稍后提醒', '分钟后再提醒', '吃药了', '喝水了')):
        return 'FEEDBACK_CLARIFY'
    if any(word in value for word in ('天气', '下雨', '会冷', '气温', '温度', '带伞')):
        return 'WEATHER' if not any(word in value for word in ('明天', '后天', '昨天', '下周')) else 'UNSUPPORTED'
    if any(word in value for word in ('安排', '提醒', '日程', '计划', '要做什么', '有什么事')):
        return 'REMINDERS' if not any(word in value for word in ('明天', '后天', '昨天', '下周')) else 'UNSUPPORTED'
    if any(word in value for word in ('几月几', '几号', '星期几', '周几', '日期', '几点', '什么日子')):
        return 'DATE' if not any(word in value for word in ('明天', '后天', '昨天', '下周')) else 'UNSUPPORTED'
    return None


def date_text(now, zone):
    local = now.astimezone(zone)
    weekday = '一二三四五六日'[local.weekday()]
    return f'今天是{local.year}年{local.month}月{local.day}日，星期{weekday}，现在是{local.hour}点{local.minute:02d}分（{zone.key}）。'


async def today_choices(db, actor, conversation, zone, now):
    await authorize(db, actor, conversation.family_id, actor.user_id, 'REMINDER_READ')
    day = now.astimezone(zone).date()
    start = datetime.combine(day, time.min, zone).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    parents = (await db.scalars(select(Reminder).where(Reminder.family_id == conversation.family_id,
        Reminder.owner_user_id == actor.user_id, Reminder.active.is_(True), Reminder.deleted_at.is_(None)))).all()
    executions = (await db.scalars(select(ReminderExecution).join(Reminder).where(
        Reminder.family_id == conversation.family_id, Reminder.owner_user_id == actor.user_id,
        ReminderExecution.owner_user_id == actor.user_id, Reminder.active.is_(True), Reminder.deleted_at.is_(None),
        or_((ReminderExecution.scheduled_at >= start) & (ReminderExecution.scheduled_at < end),
            (ReminderExecution.triggered_at >= start) & (ReminderExecution.triggered_at < end),
            (ReminderExecution.feedback_status == 'LATER') & (ReminderExecution.next_due_at >= start) & (ReminderExecution.next_due_at < end))))).all()
    by_key = {(row.reminder_id, row.occurrence_key): row for row in executions}
    by_id = {parent.id: parent for parent in parents}
    choices = {}
    for parent in parents:
        for item in occurrences(reminders.schedule(parent), window_start=start, window_end=end, policy=reminders.POLICY):
            row = by_key.get((parent.id, item.occurrence_key))
            choice = Choice(parent.id, parent.version, item.scheduled_at, item.occurrence_key, parent.title,
                row.feedback_status if row else 'PENDING', row.next_due_at if row else None, row.triggered_at if row else None)
            choices[(parent.id, item.occurrence_key)] = choice
    for row in executions:
        parent = by_id[row.reminder_id]
        item = next_occurrence(reminders.schedule(parent), row.scheduled_at, reminders.POLICY)
        matches_current_schedule = item is not None and item.occurrence_key == row.occurrence_key
        if matches_current_schedule:
            choices[(parent.id, row.occurrence_key)] = Choice(parent.id, parent.version, row.scheduled_at,
                row.occurrence_key, parent.title, row.feedback_status, row.next_due_at, row.triggered_at)
    await audit.record(db, actor.user_id, 'REMINDER_LIST_READ', 'REMINDER', family_id=conversation.family_id)
    return tuple(sorted(choices.values(), key=lambda c: (display_at(c, zone, now), str(c.reminder_id))))


def display_at(choice, zone, now):
    if choice.next_due_at:
        return choice.next_due_at
    if choice.triggered_at and choice.scheduled_at.astimezone(zone).date() != now.astimezone(zone).date():
        return choice.triggered_at
    return choice.scheduled_at


def arrangements(choices, zone, now):
    if not choices:
        return '今天没有已设置的提醒安排。您可以请家人在提醒页面添加。'
    parts = []
    labels = {'DONE': '已完成', 'SKIPPED': '已跳过', 'LATER': '稍后处理', 'PENDING': '待处理', 'NO_RESPONSE': '尚未反馈'}
    for i, choice in enumerate(choices[:8], 1):
        local = display_at(choice, zone, now).astimezone(zone)
        clock = local.strftime('%H:%M' if local.date() == now.astimezone(zone).date() else '%m月%d日%H:%M')
        parts.append(f'第{i}项，{clock}，{choice.title[:100]}，{labels[choice.status]}')
    text = '今天的提醒安排：' + '；'.join(parts) + '。'
    if len(choices) > 8:
        text += f'另有{len(choices) - 8}项，请打开提醒页面查看。'
    return text + '您可以说“第一项完成了”或“第一项稍后处理”；稍后处理默认十分钟后再提醒。'


def select_choice(command, context):
    _, target, _ = command
    target = re.sub(r'(?:这条提醒|这个提醒|这件事|这个|这条|提醒|把|标记为|记为|了)', '', target)
    if not target:
        return context[0] if len(context) == 1 else None
    match = re.fullmatch(r'第?([一二三四五六七八1-8])(?:项|个|条)', target)
    if match:
        index = int(match[1]) if match[1].isdigit() else '一二三四五六七八'.index(match[1]) + 1
        return context[index - 1] if index <= len(context) else None
    matches = [c for c in context if target == normalized(c.title) or target == normalized(c.title).removesuffix('提醒')
        or target in ('药', '水') and target in c.title]
    return matches[0] if len(matches) == 1 else None


async def prepare_answer(db, actor, conversation, text, payload, weather, context=(), *, now=None):
    kind = intent(text)
    if kind is None:
        return None
    now = now or utcnow()
    zone = ZoneInfo(payload.get('timezone', 'Asia/Shanghai'))
    if kind == 'DATE':
        return Answer(kind, date_text(now, zone), sources=('服务端时间',))
    if kind == 'WEATHER':
        city_id = payload.get('weather_city_id')
        if city_id is None:
            return Answer(kind, '请先在首页天气卡片选择或重新选择城市，再问我今天的天气。我不会猜测您所在的城市。')
        try:
            forecast = await weather.today(city_id)
            return Answer(kind, f"根据 Open-Meteo 刚获取的今日预报，您选择的{forecast['city']['label']}，"
                f"当地{forecast['date']}，{forecast['description']}，气温{forecast['temperature_2m_min']:g}到{forecast['temperature_2m_max']:g}摄氏度，"
                f"今天最高降水概率为{forecast['precipitation_probability_max']:g}%。降水可能包括雨或雪，预报会变化。",
                sources=('Open-Meteo 今日预报',))
        except AppError:
            return Answer(kind, '现在没有获取到有效的今日天气预报，请稍后再问。我暂时不能确定今天会不会下雨。')
    if kind == 'REMINDERS':
        return Answer(kind, '', sources=('本人提醒记录',))
    if kind == 'FEEDBACK':
        return Answer(kind, '', tuple(context), ('本人提醒反馈',))
    if kind == 'FEEDBACK_CLARIFY':
        return Answer(kind, '尚未更改提醒。请先问“今天有什么安排”，再明确说“第一项完成了”或“第一项稍后处理”。')
    return Answer(kind, '目前我能查询今天的日期、天气和提醒。请问“今天有什么安排”或“今天会下雨吗”。')


async def publish(db, actor, conversation, prepared, text, payload, settings, request_id, *, now=None):
    now = now or utcnow()
    zone = ZoneInfo(payload.get('timezone', 'Asia/Shanghai'))
    if prepared.kind == 'DATE':
        return Answer('DATE', date_text(now, zone), sources=prepared.sources)
    if prepared.kind not in ('REMINDERS', 'FEEDBACK'):
        return prepared
    choices = await today_choices(db, actor, conversation, zone, now)
    if prepared.kind == 'REMINDERS':
        return Answer('REMINDERS', arrangements(choices, zone, now), choices[:8], prepared.sources)
    command = feedback_command(text)
    chosen = select_choice(command, prepared.choices) if command else None
    if chosen is None:
        return Answer('FEEDBACK', '还没有更改提醒。请明确要处理哪一项。' + arrangements(choices, zone, now), choices[:8], prepared.sources)
    current = next((c for c in choices if c.reminder_id == chosen.reminder_id and c.occurrence_key == chosen.occurrence_key), None)
    if current is None or current.version != chosen.version:
        return Answer('FEEDBACK', '这项提醒已变更或不属于今天，请重新问“今天有什么安排”后再反馈。', sources=prepared.sources)
    if current.status in ('DONE', 'SKIPPED'):
        label = '完成' if current.status == 'DONE' else '跳过'
        return Answer('FEEDBACK', f'“{current.title[:100]}”已经记录为{label}，没有重复更改。', prepared.choices, prepared.sources)
    status, _, minutes = command
    if status == 'LATER' and not 1 <= minutes <= 1440:
        return Answer('FEEDBACK', '尚未更改提醒。稍后时间需要在一到一千四百四十分钟内，例如“第一项十分钟后再提醒我”。', prepared.choices, prepared.sources)
    parent = await reminders.access(db, actor, current.reminder_id)
    item = next_occurrence(reminders.schedule(parent), current.scheduled_at, reminders.POLICY)
    if parent.version != chosen.version or not parent.active or not item or item.occurrence_key != current.occurrence_key:
        return Answer('FEEDBACK', '提醒已变更，请重新查询今天的安排。', sources=prepared.sources)
    await db.execute(insert(ReminderExecution).values(id=uuid7(), reminder_id=parent.id, owner_user_id=actor.user_id,
        occurrence_key=item.occurrence_key, scheduled_at=item.scheduled_at, local_date=item.local_date, local_time=item.local_time,
        source='ONLINE', feedback_status='PENDING', created_at=now).on_conflict_do_nothing(constraint='uq_reminder_occurrence'))
    execution = await db.scalar(select(ReminderExecution).where(ReminderExecution.reminder_id == parent.id,
        ReminderExecution.occurrence_key == item.occurrence_key).with_for_update())
    due = now + timedelta(minutes=minutes) if status == 'LATER' else None
    try:
        result = await reminders.feedback(db, actor, execution.id, ReminderFeedback(status=status, next_due_at=due),
            f'voice-feedback:{conversation.id}:{request_id}', settings, request_id)
    except AppError as error:
        if error.status_code != 409:
            raise
        return Answer('FEEDBACK', '这项提醒已有新反馈，请重新查询今天的安排。', sources=prepared.sources)
    updated = tuple(Choice(c.reminder_id, c.version, c.scheduled_at, c.occurrence_key, c.title,
        result['feedback_status'], due, current.triggered_at) if c.reminder_id == current.reminder_id and c.occurrence_key == current.occurrence_key else c
        for c in prepared.choices)
    reply = f'已将“{current.title[:100]}”记录为完成。' if status == 'DONE' else (
        f'已将“{current.title[:100]}”记录为稍后处理，{due.astimezone(zone).strftime("%m月%d日%H:%M")}再提醒。请保持设备联网并允许提醒通知。')
    return Answer('FEEDBACK', reply, updated, prepared.sources, reminders_changed=True)
