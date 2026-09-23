"""Typed, secret-free runtime profiles for the three course environments."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "test", "demo"]
ProviderMode = Literal["mock", "real"]
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_env: Environment = "dev"
    provider_mode: ProviderMode = "mock"
    demo_data: bool = False
    log_level: str = "INFO"
    database_url: str = Field(default="postgresql+psycopg://localhost:5432/nianian", repr=False)
    llm_api_key: str | None = Field(default=None, repr=False)
    asr_api_key: str | None = Field(default=None, repr=False)
    tts_api_key: str | None = Field(default=None, repr=False)
    embedding_api_key: str | None = Field(default=None, repr=False)
    push_api_key: str | None = Field(default=None, repr=False)
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "nianian-private"
    s3_access_key: str | None = Field(default=None, repr=False)
    s3_secret_key: str | None = Field(default=None, repr=False)

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    @model_validator(mode="after")
    def keep_demo_fictional(self) -> "Settings":
        if self.app_env == "demo" and (not self.demo_data or self.provider_mode != "mock"):
            raise ValueError("demo requires fictional data and mock providers")
        if self.app_env == "test" and self.provider_mode != "mock":
            raise ValueError("test requires mock providers")
        return self

    @property
    def provider_label(self) -> str:
        return "Mock" if self.provider_mode == "mock" else "Real"

    @property
    def data_label(self) -> str:
        return "Demo Data" if self.demo_data else "Local Data"


def load_settings(environment: Environment, *, local_env_file: Path | None = None) -> Settings:
    """Load a checked-in profile, then optional ignored local overrides."""
    profile = _BACKEND_ROOT / "config" / f"{environment}.env"
    env_files = (profile, local_env_file) if local_env_file else (profile,)
    return Settings(_env_file=env_files, app_env=environment)


@lru_cache
def get_settings() -> Settings:
    environment = os.environ.get("APP_ENV", "dev")
    if environment not in ("dev", "test", "demo"):
        raise ValueError("APP_ENV must be dev, test, or demo")
    return load_settings(environment, local_env_file=_BACKEND_ROOT.parent / ".env")
