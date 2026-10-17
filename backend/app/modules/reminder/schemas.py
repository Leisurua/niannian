from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.modules.auth.schemas import Input
from app.modules.reminder.schedule import ScheduleRule

ReminderType = Literal['CALENDAR', 'WEATHER', 'MEDICATION', 'WATER', 'CLOTHING', 'COMPANIONSHIP']


class ReminderCreate(ScheduleRule):
    owner_user_id: UUID
    family_id: UUID | None = None
    type: ReminderType
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=2000)
    escalation_policy: dict = Field(default_factory=dict)


class ReminderFeedback(Input):
    status: Literal['DONE', 'LATER', 'SKIPPED']
    note: str | None = Field(default=None, max_length=500)
    next_due_at: AwareDatetime | None = None


class OfflineReminderFeedback(Input):
    reminder_version: int = Field(gt=0, strict=True)
    scheduled_at: AwareDatetime
    feedback_at: AwareDatetime
    status: Literal['DONE', 'LATER', 'SKIPPED']
    next_due_at: AwareDatetime | None = None
