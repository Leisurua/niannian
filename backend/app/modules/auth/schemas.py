from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from typing import Literal


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credential(Input):
    type: Literal["DEMO", "VERIFICATION_CODE", "PASSWORD"]
    identifier: str = Field(max_length=160)
    proof: SecretStr | None = Field(default=None, max_length=256)


class LoginDevice(Input):
    device_id: str = Field(max_length=160)
    name: str = Field(max_length=120)
    app_version: str = Field(max_length=64)


class LoginRequest(Input):
    credential: Credential
    device: LoginDevice


class RegisterRequest(Input):
    username: str = Field(pattern=r"^[a-z0-9_]{4,32}$")
    password: SecretStr = Field(min_length=15, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    device: LoginDevice

    @field_validator("username", "display_name", mode="before")
    @classmethod
    def trim_profile(cls, value, info):
        if isinstance(value, str):
            return value.strip().lower() if info.field_name == "username" else value.strip()
        return value


class RefreshRequest(Input):
    refresh_token: SecretStr = Field(max_length=4096)
