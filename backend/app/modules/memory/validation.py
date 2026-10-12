"""Memory creation validation; authorization and provenance remain service decisions."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

MemoryType = Literal['PERSON', 'RELATIONSHIP', 'EVENT', 'PLACE', 'PREFERENCE', 'TABOO', 'PHOTO']
MemorySource = Literal['FAMILY_MEMBER', 'USER', 'AI_CANDIDATE', 'IMPORT']
MemoryStatus = Literal['PENDING', 'CONFIRMED', 'REJECTED', 'REVOKED', 'DELETED']
Visibility = Literal['OWNER_ONLY', 'AUTHORIZED_SCOPE', 'SPECIFIC_CONSENT']
ConsentScope = Literal['VOICE', 'PORTRAIT', 'FAMILY_MEMORY', 'HEALTH_MEDICATION',
                       'CONVERSATION_SUMMARY', 'CAMERA_PROXIMITY', 'NOTIFICATION_TO_FAMILY']


class MemoryDraft(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    family_id: UUID
    subject_user_id: UUID
    type: MemoryType
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=10000)
    # Preserve absence: the service must establish provenance from the actor.
    source: MemorySource | None = None
    required_consent_scope: ConsentScope
    visibility: Visibility = 'AUTHORIZED_SCOPE'
    verification_status: MemoryStatus = 'PENDING'
    expires_at: AwareDatetime | None = None
    attachment_ids: tuple[UUID, ...] = ()

    @field_validator('title')
    @classmethod
    def nonblank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Title must not be blank')
        return value

    @model_validator(mode='after')
    def candidate_cannot_confirm_itself(self):
        if self.verification_status not in ('PENDING', 'CONFIRMED'):
            raise ValueError('New memories must be pending or explicitly confirmed')
        if self.source == 'AI_CANDIDATE' and self.verification_status != 'PENDING':
            raise ValueError('AI candidates cannot be confirmed by model output')
        if len(self.attachment_ids) != len(set(self.attachment_ids)):
            raise ValueError('Duplicate attachment references')
        return self
