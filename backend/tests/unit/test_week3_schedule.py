from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.modules.reminder.schedule import CalendarPolicy, QuietHours, ScheduleRule, in_quiet_hours, occurrences, next_occurrence

POLICY = CalendarPolicy(ambiguous_time='FIRST', nonexistent_time='SKIP', equal_quiet_hours='DISABLED')


def rule(**changes):
    return ScheduleRule.model_validate(dict(
        schedule_time_local='08:00', timezone='Asia/Shanghai', start_date='2026-10-09',
        recurrence_kind='DAILY',
    ) | changes)


def window(value, start, end, policy=POLICY):
    return occurrences(value, window_start=datetime.fromisoformat(start),
                       window_end=datetime.fromisoformat(end), policy=policy)


def test_local_daily_window_is_half_open_and_retry_identity_is_stable():
    items = window(rule(), '2026-10-09T00:00:00+00:00', '2026-10-11T00:00:00+00:00')
    assert [item.local_date for item in items] == [date(2026, 10, 9), date(2026, 10, 10)]
    assert all(item.scheduled_at.hour == 0 and item.scheduled_at.tzinfo == timezone.utc for item in items)
    retry = window(rule(), '2026-10-10T00:00:00+00:00', '2026-10-12T00:00:00+00:00')
    assert items[1].occurrence_key == retry[0].occurrence_key
    assert items[0].occurrence_key != items[1].occurrence_key
    assert len(items[0].occurrence_key) <= 96


def test_once_interval_weekly_and_end_date():
    span = ('2026-10-08T00:00:00+00:00', '2026-11-01T00:00:00+00:00')
    assert len(window(rule(recurrence_kind='ONCE'), *span)) == 1
    interval = window(rule(recurrence_kind='INTERVAL', recurrence_interval=3, end_date='2026-10-15'), *span)
    assert [o.local_date.day for o in interval] == [9, 12, 15]
    weekly = window(rule(recurrence_kind='WEEKLY', recurrence_interval=2, days_of_week=[0, 4]), *span)
    assert [o.local_date.day for o in weekly] == [9, 19, 23]


def test_spring_dst_skips_nonexistent_wall_time():
    items = window(rule(timezone='America/New_York', start_date='2026-03-07', schedule_time_local='02:30'),
                   '2026-03-07T00:00:00+00:00', '2026-03-10T00:00:00+00:00')
    assert [o.local_date.day for o in items] == [7, 9]
    assert [o.scheduled_at.hour for o in items] == [7, 6]


def test_autumn_dst_generates_exactly_one_occurrence_with_explicit_fold_policy():
    value = rule(timezone='America/New_York', start_date='2026-11-01', schedule_time_local='01:30', recurrence_kind='ONCE')
    span = ('2026-11-01T00:00:00+00:00', '2026-11-02T00:00:00+00:00')
    first = window(value, *span)
    second = window(value, *span, policy=CalendarPolicy('SECOND', 'SKIP', 'DISABLED'))
    assert len(first) == len(second) == 1
    assert first[0].scheduled_at.hour == 5
    assert second[0].scheduled_at.hour == 6
    assert first[0].local_time == second[0].local_time


def test_skipped_whole_local_day_and_half_hour_dst():
    # Samoa skipped 2011-12-30; Australia/Lord_Howe jumps by thirty minutes.
    samoa = window(rule(timezone='Pacific/Apia', start_date='2011-12-29'),
                   '2011-12-29T00:00:00+00:00', '2012-01-01T00:00:00+00:00')
    assert date(2011, 12, 30) not in [o.local_date for o in samoa]
    lord_howe = window(rule(timezone='Australia/Lord_Howe', start_date='2026-10-04', schedule_time_local='02:15', recurrence_kind='ONCE'),
                      '2026-10-03T00:00:00+00:00', '2026-10-05T00:00:00+00:00')
    assert lord_howe == ()


@pytest.mark.parametrize('local,expected', [('21:59', False), ('22:00', True), ('00:00', True), ('06:59', True), ('07:00', False)])
def test_cross_midnight_quiet_hours(local, expected):
    quiet = QuietHours(start='22:00', end='07:00', timezone='Asia/Shanghai')
    instant = datetime.fromisoformat(f'2026-10-09T{local}:00+08:00')
    assert in_quiet_hours(instant, quiet, POLICY) is expected


def test_quiet_hours_use_own_timezone_and_preserve_occurrence():
    value = rule(quiet_hours={'start': '18:00', 'end': '22:00', 'timezone': 'America/New_York'})
    items = window(value, '2026-10-09T00:00:00+00:00', '2026-10-10T00:00:00+00:00')
    original = window(rule(), '2026-10-09T00:00:00+00:00', '2026-10-10T00:00:00+00:00')
    assert items[0].quiet is True
    assert items[0].occurrence_key == original[0].occurrence_key


def test_equal_quiet_hours_requires_explicit_behavior():
    quiet = QuietHours(start='08:00', end='08:00', timezone='Asia/Shanghai')
    now = datetime(2026, 10, 9, tzinfo=timezone.utc)
    assert not in_quiet_hours(now, quiet, POLICY)
    assert in_quiet_hours(now, quiet, CalendarPolicy('FIRST', 'SKIP', 'ALL_DAY'))


@pytest.mark.parametrize('changes', [
    {'timezone': 'Not/A_Zone'}, {'timezone': '../UTC'}, {'schedule_time_local': '25:00'},
    {'schedule_time_local': '08:00+08:00'}, {'schedule_time_local': '08:00:00.001'},
    {'schedule_time_local': 123}, {'end_date': '2026-10-08'}, {'recurrence_interval': 0},
    {'recurrence_interval': True}, {'days_of_week': [0]}, {'recurrence_kind': 'WEEKLY'},
    {'recurrence_kind': 'WEEKLY', 'days_of_week': [7]},
    {'recurrence_kind': 'WEEKLY', 'days_of_week': [True]},
    {'recurrence_kind': 'WEEKLY', 'days_of_week': [1, 1]},
])
def test_invalid_rules_fail_without_scheduling(changes):
    with pytest.raises(ValidationError):
        rule(**changes)


def test_unbounded_or_naive_windows_are_rejected():
    with pytest.raises(ValueError, match='aware'):
        window(rule(), '2026-10-09T00:00:00', '2026-10-10T00:00:00+00:00')
    with pytest.raises(ValueError, match='bound'):
        window(rule(), '2026-10-09T00:00:00+00:00', '2030-10-09T00:00:00+00:00')
    with pytest.raises(ValueError, match='follow'):
        window(rule(), '2026-10-09T00:00:00+00:00', '2026-10-09T00:00:00+00:00')


def test_next_occurrence_handles_long_intervals_without_fixed_year_horizon():
    value = rule(recurrence_kind='INTERVAL', recurrence_interval=400)
    after = datetime(2026, 10, 10, tzinfo=timezone.utc)
    result = next_occurrence(value, after, POLICY)
    from datetime import timedelta
    assert result.local_date == date(2026, 10, 9) + timedelta(days=400)
    weekly = rule(recurrence_kind='WEEKLY', recurrence_interval=80, days_of_week=[4])
    assert next_occurrence(weekly, after, POLICY).local_date == date(2026, 10, 9) + timedelta(weeks=80)
