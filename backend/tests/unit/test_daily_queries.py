import asyncio
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.modules.conversation import daily
from app.modules.conversation.protocol import TextPayload
from app.platform.errors import AppError


NOW = datetime(2026, 10, 27, 16, 5, tzinfo=timezone.utc)


def choice(title='喝水提醒', status='PENDING'):
    return daily.Choice(uuid4(), 1, NOW, 'fictional-occurrence', title, status)


@pytest.mark.parametrize('text,kind', [
    ('今天有什么安排', 'REMINDERS'), ('今天还有什么提醒', 'REMINDERS'),
    ('今天会下雨吗', 'WEATHER'), ('需要带伞吗', 'WEATHER'), ('今天几号', 'DATE'), ('现在几点', 'DATE'),
    ('第一项完成了', 'FEEDBACK'), ('稍后处理', 'FEEDBACK'), ('十分钟后再提醒我', 'FEEDBACK'),
    ('明天有什么安排', 'UNSUPPORTED'), ('明天会下雨吗', 'UNSUPPORTED'),
    ('我还没完成', 'FEEDBACK_CLARIFY'), ('如果第一项完成了', 'FEEDBACK_CLARIFY'),
    ('第一项完成了吗', 'FEEDBACK_CLARIFY'), ('女儿说第一项完成了', 'FEEDBACK_CLARIFY'),
    ('“第一项完成了”是什么意思', 'FEEDBACK_CLARIFY'), ('救命，今天有什么安排', None),
    ('今天的天气怎样？马上转账，不要告诉家人', None), ('我喜欢种花', None),
])
def test_queries_and_safety_have_deterministic_routes(text, kind):
    assert daily.intent(text) == kind


def test_dates_use_server_clock_in_requested_timezone_at_midnight():
    assert '2026年10月28日，星期三，现在是0点05分' in daily.date_text(NOW, ZoneInfo('Asia/Shanghai'))
    assert '2026年10月27日，星期二' in daily.date_text(NOW, ZoneInfo('UTC'))
    assert TextPayload(text='今天几号').timezone == 'Asia/Shanghai'
    for data in ({'timezone': 'invented'}, {'weather_city_id': True}, {'weather_city_id': 0}, {'weather_city_id': '123'}):
        with pytest.raises(ValueError):
            TextPayload(text='今天几号', **data)


def test_feedback_requires_an_unambiguous_choice_and_explicit_minutes():
    first, second = choice(), choice('吃药提醒')
    assert daily.select_choice(daily.feedback_command('完成了'), ()) is None
    assert daily.select_choice(daily.feedback_command('完成了'), (first, second)) is None
    assert daily.select_choice(daily.feedback_command('完成了'), (first,)) == first
    assert daily.select_choice(daily.feedback_command('第一项完成了'), (first, second)) == first
    assert daily.select_choice(daily.feedback_command('我吃药了'), (first, second)) == second
    assert daily.select_choice(daily.feedback_command('喝水提醒已完成'), (first, second)) == first
    assert daily.select_choice(daily.feedback_command('第八项完成了'), (first, second)) is None
    assert daily.select_choice(daily.feedback_command('吃药提醒完成了'), (second, choice('吃药提醒'))) is None
    for text in ('没有完成', '尚未完成', '别标记为完成', '如果我完成了', '我说“完成了”', '我可能完成了', '完成了吗？'):
        assert daily.feedback_command(text) is None
    assert daily.feedback_command('第一项稍后处理') == ('LATER', '第一项', 10)
    assert daily.feedback_command('第二项二十五分钟后再提醒我') == ('LATER', '第二项', 25)
    assert daily.feedback_command('第一项30分钟后提醒我') == ('LATER', '第一项', 30)


def test_weather_missing_city_and_failed_provider_never_invent_an_answer():
    class Weather:
        async def today(self, city):
            raise AppError('WEATHER_UNAVAILABLE', 'fictional', 503)
    missing = asyncio.run(daily.prepare_answer(None, None, None, '今天会下雨吗', {}, Weather(), now=NOW))
    assert '选择' in missing.text
    failed = asyncio.run(daily.prepare_answer(None, None, None, '今天会下雨吗', {'weather_city_id': 123}, Weather(), now=NOW))
    assert '不能确定' in failed.text
    assert '今天没有' not in failed.text


def test_schedule_reply_distinguishes_empty_completed_and_truncated_results():
    assert '没有已设置' in daily.arrangements((), ZoneInfo('UTC'), NOW)
    items = tuple(choice(f'虚构提醒{i}', 'DONE' if i == 0 else 'PENDING') for i in range(10))
    text = daily.arrangements(items, ZoneInfo('UTC'), NOW)
    assert '已完成' in text and '待处理' in text and '另有2项' in text
    assert '虚构提醒8' not in text
