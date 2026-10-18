"""Pure FR-014 decision policy; not a scheduler or authorization authority.

The service must supply a fresh authorized snapshot and atomically reserve a
daily slot before dispatch. No persistence or delivery is enabled here.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo


Action = Literal['NO_ACTION', 'SUGGEST_INTERACTION', 'REMINDER', 'MEMORY_PROMPT', 'WEATHER_PROMPT']
EXIT_COPY = '不想聊可以说“今天少打扰我”。'


@dataclass(frozen=True)
class ProactiveSnapshot:
    now: datetime
    timezone: str
    window_start: time
    window_end: time
    jointly_enabled: bool
    daily_cap: int
    daily_count: int
    counter_date: date
    quiet_start: time | None = None
    quiet_end: time | None = None
    paused_on: date | None = None
    busy_or_resting: bool = False
    last_interaction: datetime | None = None
    minimum_gap: timedelta = timedelta(minutes=30)
    content_authorized: bool = False
    reminder_due: bool = False
    memory_available: bool = False
    weather_available: bool = False
    same_content_declined: bool = False


@dataclass(frozen=True)
class ProactiveDecision:
    action: Action
    reason: str
    exit_copy: str | None = None
    policy_version: str = '1.0.0'


def _within(value: time, start: time, end: time) -> bool:
    if start == end:
        return False
    return start <= value < end if start < end else value >= start or value < end


def decide(snapshot: ProactiveSnapshot) -> ProactiveDecision:
    """Fail closed on unknown/stale state; quiet affects proactive prompts only.

    REMINDER is a suggestion to discuss a due reminder, never permission to
    suppress or execute the independent necessary-reminder/emergency paths.
    """
    def deny(reason):
        return ProactiveDecision('NO_ACTION', reason)

    if snapshot.now.tzinfo is None or snapshot.now.utcoffset() is None:
        return deny('INVALID_CLOCK')
    try:
        local = snapshot.now.astimezone(ZoneInfo(snapshot.timezone))
    except (KeyError, ValueError):
        return deny('INVALID_TIMEZONE')
    times = [snapshot.window_start, snapshot.window_end, snapshot.quiet_start, snapshot.quiet_end]
    if any(value is not None and value.tzinfo is not None for value in times):
        return deny('INVALID_WINDOW')
    if not snapshot.jointly_enabled:
        return deny('DISABLED')
    if not _within(local.time(), snapshot.window_start, snapshot.window_end):
        return deny('OUTSIDE_WINDOW')
    if (type(snapshot.daily_count) is not int or type(snapshot.daily_cap) is not int
            or snapshot.daily_count < 0 or snapshot.daily_cap <= 0):
        return deny('INVALID_COUNTER')
    if snapshot.counter_date != local.date():
        return deny('STALE_COUNTER')
    if snapshot.daily_count >= snapshot.daily_cap:
        return deny('DAILY_CAP')
    if (snapshot.quiet_start is None) != (snapshot.quiet_end is None):
        return deny('INVALID_QUIET_HOURS')
    if snapshot.quiet_start is not None and _within(local.time(), snapshot.quiet_start, snapshot.quiet_end):
        return deny('QUIET_HOURS')
    if snapshot.paused_on == local.date() or snapshot.busy_or_resting:
        return deny('PAUSED')
    if snapshot.same_content_declined:
        return deny('CONTENT_DECLINED')
    if snapshot.minimum_gap < timedelta(0):
        return deny('INVALID_GAP')
    if snapshot.last_interaction is not None:
        if snapshot.last_interaction.tzinfo is None or snapshot.last_interaction.utcoffset() is None:
            return deny('INVALID_CLOCK')
        elapsed = snapshot.now.astimezone(timezone.utc) - snapshot.last_interaction.astimezone(timezone.utc)
        if elapsed < timedelta(0):
            return deny('CLOCK_ROLLBACK')
        if elapsed < snapshot.minimum_gap:
            return deny('RECENT_INTERACTION')
    if not snapshot.content_authorized:
        return deny('CONTENT_UNAUTHORIZED')
    action: Action = ('REMINDER' if snapshot.reminder_due else 'MEMORY_PROMPT' if snapshot.memory_available
        else 'WEATHER_PROMPT' if snapshot.weather_available else 'SUGGEST_INTERACTION')
    return ProactiveDecision(action, 'ELIGIBLE', EXIT_COPY)
