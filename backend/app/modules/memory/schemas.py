from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.auth.schemas import Input

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


class MemoryUpdate(Input):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    content: str | None = Field(default=None, max_length=10000)
    type: MemoryType | None = None
    visibility: Visibility | None = None
    expires_at: AwareDatetime | None = None
    attachment_ids: list[UUID] | None = None

    @model_validator(mode='after')
    def fields_present(self):
        if not self.model_fields_set or any(getattr(self, f) is None for f in self.model_fields_set if f != 'expires_at'):
            raise ValueError('Provide at least one editable field')
        if self.title is not None and not self.title.strip():
            raise ValueError('Title must not be blank')
        if self.attachment_ids is not None and len(set(self.attachment_ids)) != len(self.attachment_ids):
            raise ValueError('Duplicate attachment references')
        return self


class MemoryFeedback(Input):
    kind: Literal['INCORRECT', 'UNKNOWN', 'OUTDATED']
    note: str | None = Field(default=None, max_length=500)


class FileUpload(Input):
    media_type: Literal['PHOTO', 'AUDIO', 'OTHER']
    mime_type: str = Field(max_length=120)
    size_bytes: int = Field(ge=1, le=104857600, strict=True)
    checksum: str = Field(pattern=r'^[a-fA-F0-9]{64}$')
    memory_id: UUID


class FileConfirm(Input):
    checksum: str = Field(pattern=r'^[a-fA-F0-9]{64}$')


class Action(Input):
    reason: str | None = Field(default=None, max_length=500)
