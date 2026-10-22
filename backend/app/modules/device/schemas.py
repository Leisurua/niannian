from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeviceRegister(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    device_id: str = Field(min_length=1, max_length=200)
    family_id: UUID
    device_type: Literal['ANDROID_TABLET', 'ANDROID_PHONE', 'OTHER']
    client_kind: Literal['ELDER_MOBILE', 'FAMILY_MOBILE']
    app_version: str = Field(min_length=1, max_length=64)
    os_version: str = Field(min_length=1, max_length=64)
    capabilities: dict[str, bool] = Field(default_factory=dict, max_length=20)
