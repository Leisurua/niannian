from datetime import datetime
import json
from pathlib import Path

import pytest

from app.modules.reminder.schedule import CalendarPolicy, ScheduleRule, occurrences

CASES = json.loads((Path(__file__).resolve().parents[3] /
    'android/feature-reminder/src/test/resources/calendar-cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['name'])
def test_android_backend_calendar_vectors(case):
    rows = occurrences(ScheduleRule.model_validate(case['rule']),
        window_start=datetime.fromisoformat(case['start']), window_end=datetime.fromisoformat(case['end']),
        policy=CalendarPolicy('FIRST', 'SKIP', 'DISABLED'))
    assert [dict(scheduled_at=row.scheduled_at.isoformat(), local_date=row.local_date.isoformat(),
                 local_time=row.local_time.isoformat(), occurrence_key=row.occurrence_key, quiet=row.quiet)
            for row in rows] == case['expected']
