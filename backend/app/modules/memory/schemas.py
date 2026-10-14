from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.modules.auth.schemas import Input
from app.modules.memory.validation import MemoryDraft, MemoryType, Visibility

MemoryCreate = MemoryDraft


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
