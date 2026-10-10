from pydantic import BaseModel, ConfigDict, Field, SecretStr
from typing import Literal


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credential(Input):
    type: Literal["DEMO", "VERIFICATION_CODE"]
    identifier: str = Field(max_length=160)
    proof: SecretStr | None = Field(default=None, max_length=256)


class LoginDevice(Input):
    device_id: str = Field(max_length=160)
    name: str = Field(max_length=120)
    app_version: str = Field(max_length=64)


class LoginRequest(Input):
    credential: Credential
    device: LoginDevice


class RefreshRequest(Input):
    refresh_token: SecretStr = Field(max_length=4096)
