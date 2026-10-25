"""Typed, secret-free runtime profiles for the three course environments."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
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
    llm_provider: Literal["mock", "openai_compatible"] = "mock"
    llm_base_url: str | None = None
    llm_model: str | None = None
    # DeepSeek Chat Completions extension; omit for other compatible providers.
    llm_thinking: Literal["enabled", "disabled"] | None = None
    llm_timeout_seconds: float = Field(default=20, gt=0, le=20)
    asr_api_key: str | None = Field(default=None, repr=False)
    tts_api_key: str | None = Field(default=None, repr=False)
    embedding_api_key: str | None = Field(default=None, repr=False)
    push_api_key: str | None = Field(default=None, repr=False)
    notification_external_enabled: bool = False
    notification_push_provider: Literal['mock', 'ntfy'] = 'mock'
    ntfy_base_url: str | None = None
    twilio_account_sid: str | None = Field(default=None, repr=False)
    twilio_auth_token: str | None = Field(default=None, repr=False)
    twilio_from_number: str | None = Field(default=None, repr=False)
    contact_encryption_key: SecretStr = Field(default=SecretStr(''), repr=False)
    s3_endpoint: str = "http://localhost:9000"
    s3_public_endpoint: str | None = None
    s3_bucket: str = "nianian-private"
    s3_access_key: str | None = Field(default=None, repr=False)
    s3_secret_key: str | None = Field(default=None, repr=False)
    auth_signing_key: SecretStr = Field(default=SecretStr(""), repr=False)
    auth_access_seconds: int = Field(default=900, ge=60, le=3600)
    auth_refresh_seconds: int = Field(default=604800, ge=900, le=2592000)
    auth_login_limit: int = Field(default=10, ge=1, le=1000)
    idempotency_seconds: int = Field(default=86400, ge=60, le=604800)
    public_base_url: str = 'http://localhost:8000'
    file_max_size_bytes: int = Field(default=5242880, ge=1024, le=104857600)
    file_max_pixels: int = Field(default=12000000, ge=1, le=24000000)
    file_url_seconds: int = Field(default=120, ge=30, le=300)
    upload_expiry_seconds: int = Field(default=3600, ge=300, le=86400)
    reminder_feedback_seconds: int = Field(default=3600, ge=60, le=86400)
    ws_max_frame_bytes: int = Field(default=16384, ge=1024, le=65536)
    ws_max_text_chars: int = Field(default=2000, ge=1, le=10000)
    ws_messages_per_second: int = Field(default=20, ge=1, le=100)
    backup_retention_days: int = Field(default=30, ge=1, le=365)
    backup_directory: str | None = None
    audit_retention_days: int = Field(default=90, ge=7, le=365)
    task_retention_days: int = Field(default=7, ge=1, le=30)
    account_export_max_bytes: int = Field(default=104857600, ge=1048576, le=1073741824)

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False, hide_input_in_errors=True)

    @model_validator(mode="after")
    def keep_demo_fictional(self) -> "Settings":
        if self.notification_external_enabled and self.app_env != 'dev':
            raise ValueError('external notifications require APP_ENV=dev')
        if self.ntfy_base_url:
            url = urlsplit(self.ntfy_base_url)
            if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError('NTFY_BASE_URL must be HTTPS without credentials or query')
        if self.twilio_account_sid:
            import re
            if not re.fullmatch(r'AC[0-9a-fA-F]{32}', self.twilio_account_sid):
                raise ValueError('Invalid Twilio account SID')
        if self.app_env == "demo" and (not self.demo_data or self.provider_mode != "mock"):
            raise ValueError("demo requires fictional data and mock providers")
        if self.app_env == "test" and self.provider_mode != "mock":
            raise ValueError("test requires mock providers")
        if self.llm_provider != "mock":
            if self.app_env != "dev":
                raise ValueError("real LLM requires APP_ENV=dev")
            if not all(value and value.strip() for value in (self.llm_api_key, self.llm_base_url, self.llm_model)):
                raise ValueError("real LLM requires LLM_API_KEY, LLM_BASE_URL and LLM_MODEL")
            url = urlsplit(self.llm_base_url)
            if (url.scheme != "https" or not url.hostname or url.username or url.password
                    or url.query or url.fragment):
                raise ValueError("LLM_BASE_URL must be an HTTPS API base without credentials or query")
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
