"""Bounded local-time occurrence calculations with explicit calendar policy."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RecurrenceKind = Literal['ONCE', 'DAILY', 'WEEKLY', 'INTERVAL']
UTC = timezone.utc


def iana_zone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValueError('Unknown IANA timezone') from None


def _local_time(value):
    # Same lexical format as OpenAPI TimeOfDay; offsets/fractions are not local HH:MM.
    if isinstance(value, str):
        import re
        if not re.fullmatch(r'([01][0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9])?', value):
            raise ValueError('Expected local HH:MM or HH:MM:SS')
        return time.fromisoformat(value)
    if not isinstance(value, time) or value.tzinfo is not None or value.microsecond:
        raise ValueError('Expected a local time without timezone or fractions')
    return value


class QuietHours(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    start: time
    end: time
    timezone: str

    _times = field_validator('start', 'end', mode='before')(_local_time)

    @field_validator('timezone')
    @classmethod
    def valid_zone(cls, value):
        iana_zone(value)
        return value


class ScheduleRule(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schedule_time_local: time
    timezone: str
    start_date: date
    end_date: date | None = None
    recurrence_kind: RecurrenceKind
    recurrence_interval: int = Field(default=1, ge=1, strict=True)
    days_of_week: tuple[int, ...] = ()
    quiet_hours: QuietHours | None = None

    _time = field_validator('schedule_time_local', mode='before')(_local_time)

    @field_validator('timezone')
    @classmethod
    def valid_zone(cls, value):
        iana_zone(value)
        return value

    @field_validator('days_of_week', mode='before')
    @classmethod
    def valid_days(cls, value):
        if not isinstance(value, (tuple, list)) or any(type(d) is not int or not 0 <= d <= 6 for d in value):
            raise ValueError('Weekdays must be integers in 0..6')
        if len(value) != len(set(value)):
            raise ValueError('Weekdays must be unique')
        return value

    @model_validator(mode='after')
    def valid_range(self):
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError('End date precedes start date')
        if self.recurrence_kind == 'WEEKLY' and not self.days_of_week:
            raise ValueError('Weekly recurrence requires weekdays')
        if self.recurrence_kind != 'WEEKLY' and self.days_of_week:
            raise ValueError('Weekdays apply only to weekly recurrence')
        return self


@dataclass(frozen=True)
class CalendarPolicy:
    """Caller must explicitly select the reviewable DST/quiet-hours behavior."""
    ambiguous_time: Literal['FIRST', 'SECOND']
    nonexistent_time: Literal['SKIP']
    equal_quiet_hours: Literal['DISABLED', 'ALL_DAY']

    def __post_init__(self):
        if (self.ambiguous_time not in ('FIRST', 'SECOND') or self.nonexistent_time != 'SKIP'
                or self.equal_quiet_hours not in ('DISABLED', 'ALL_DAY')):
            raise ValueError('Unsupported calendar policy')


@dataclass(frozen=True)
class Occurrence:
    scheduled_at: datetime
    local_date: date
    local_time: time
    occurrence_key: str
    quiet: bool


def local_instant(day: date, clock: time, zone: ZoneInfo, policy: CalendarPolicy) -> datetime | None:
    naive = datetime.combine(day, clock)
    candidates = set()
    for fold in (0, 1):
        utc = naive.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if utc.astimezone(zone).replace(tzinfo=None) == naive:
            candidates.add(utc)
    if not candidates:
        return None
    return min(candidates) if policy.ambiguous_time == 'FIRST' else max(candidates)


def in_quiet_hours(instant: datetime, quiet: QuietHours | None, policy: CalendarPolicy) -> bool:
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('An aware instant is required')
    if quiet is None:
        return False
    clock = instant.astimezone(iana_zone(quiet.timezone)).time()
    if quiet.start == quiet.end:
        return policy.equal_quiet_hours == 'ALL_DAY'
    if quiet.start < quiet.end:
        return quiet.start <= clock < quiet.end
    return clock >= quiet.start or clock < quiet.end


def _matches(rule: ScheduleRule, day: date) -> bool:
    elapsed = (day - rule.start_date).days
    if rule.recurrence_kind == 'ONCE':
        return elapsed == 0
    if rule.recurrence_kind in ('DAILY', 'INTERVAL'):
        return elapsed % rule.recurrence_interval == 0
    week = (elapsed + rule.start_date.weekday()) // 7
    return week % rule.recurrence_interval == 0 and day.weekday() in rule.days_of_week


def occurrences(
    rule: ScheduleRule, *, window_start: datetime, window_end: datetime,
    policy: CalendarPolicy, max_days: int = 366,
) -> tuple[Occurrence, ...]:
    """Return a bounded [start, end) window; UTC occurrence identity is retry-stable.

    Quiet hours are annotated, not silently dropped or rescheduled. A later worker
    must apply the approved presentation policy without inventing medication truth.
    """
    if any(v.tzinfo is None or v.utcoffset() is None for v in (window_start, window_end)):
        raise ValueError('An aware time window is required')
    start, end = window_start.astimezone(UTC), window_end.astimezone(UTC)
    if end <= start:
        raise ValueError('Window end must follow start')
    if type(max_days) is not int or max_days < 1 or end - start > timedelta(days=max_days):
        raise ValueError('Occurrence window exceeds the configured bound')
    zone = iana_zone(rule.timezone)
    day = max(rule.start_date, start.astimezone(zone).date())
    last = end.astimezone(zone).date()
    if rule.end_date is not None:
        last = min(last, rule.end_date)
    result = []
    while day <= last:
        if _matches(rule, day):
            instant = local_instant(day, rule.schedule_time_local, zone, policy)
            if instant is not None and start <= instant < end:
                identity = f'{rule.timezone}|{day.isoformat()}|{rule.schedule_time_local.isoformat()}|{instant.isoformat()}'
                result.append(Occurrence(
                    scheduled_at=instant, local_date=day, local_time=rule.schedule_time_local,
                    occurrence_key=hashlib.sha256(identity.encode('utf-8')).hexdigest(),
                    quiet=in_quiet_hours(instant, rule.quiet_hours, policy),
                ))
        if day == date.max:
            break
        day += timedelta(days=1)
    return tuple(result)


def next_occurrence(rule: ScheduleRule, after: datetime, policy: CalendarPolicy) -> Occurrence | None:
    """Find the next instant >= after without iterating an arbitrary day interval."""
    if after.tzinfo is None or after.utcoffset() is None:
        raise ValueError('An aware instant is required')
    zone = iana_zone(rule.timezone)
    day = max(rule.start_date, after.astimezone(zone).date())
    try:
        for _ in range(8):  # bounded DST gaps, including a skipped civil day
            elapsed = (day - rule.start_date).days
            if rule.recurrence_kind == 'ONCE':
                candidate = rule.start_date
                if candidate < day:
                    return None
            elif rule.recurrence_kind in ('DAILY', 'INTERVAL'):
                offset = ((elapsed + rule.recurrence_interval - 1) // rule.recurrence_interval) * rule.recurrence_interval
                candidate = rule.start_date + timedelta(days=offset)
            else:
                monday = rule.start_date - timedelta(days=rule.start_date.weekday())
                week = (day - monday).days // 7
                active_week = ((week + rule.recurrence_interval - 1) // rule.recurrence_interval) * rule.recurrence_interval
                candidates = [monday + timedelta(weeks=active_week, days=d) for d in sorted(rule.days_of_week)]
                future = [d for d in candidates if d >= day]
                candidate = min(future) if future else monday + timedelta(weeks=active_week + rule.recurrence_interval, days=min(rule.days_of_week))
            if rule.end_date and candidate > rule.end_date:
                return None
            instant = local_instant(candidate, rule.schedule_time_local, zone, policy)
            if instant is not None and instant >= after:
                return occurrences(rule, window_start=instant, window_end=instant + timedelta(seconds=1), policy=policy)[0]
            if rule.recurrence_kind == 'ONCE':
                return None
            day = candidate + timedelta(days=1)
    except OverflowError:
        return None
    return None
