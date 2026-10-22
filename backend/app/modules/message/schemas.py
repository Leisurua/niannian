from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Destination(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['FAMILY_ROLE']
    role: Literal['ELDER', 'CHILD', 'CAREGIVER']


class TextPayload(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=2000)


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    family_id: UUID | None = None
    destination: Destination
    message_type: Literal['TEXT']
    priority: Literal['NORMAL', 'IMPORTANT'] = 'NORMAL'
    payload: TextPayload
