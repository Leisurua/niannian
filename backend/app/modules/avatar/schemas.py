from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class AvatarCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    family_id: UUID
    consent_id: UUID
    provider_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    authorized_photo: Literal[True]
    mime_type: Literal['image/jpeg', 'image/png', 'image/webp']
    size_bytes: int = Field(gt=0, le=5242880)
    checksum: str = Field(pattern=r'^[a-f0-9]{64}$')


class AvatarConfirm(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pack_checksum: str = Field(pattern=r'^[a-f0-9]{64}$')
