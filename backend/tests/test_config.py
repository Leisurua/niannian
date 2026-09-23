from pathlib import Path

import pytest
from pydantic import ValidationError

from app.platform.config import Environment, Settings, load_settings


@pytest.mark.parametrize("environment", ["dev", "test", "demo"])
def test_profile_loads_with_typed_safe_defaults(environment: Environment, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("PROVIDER_MODE", "DEMO_DATA", "LLM_API_KEY", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    settings = load_settings(environment)

    assert settings.app_env == environment
    assert settings.provider_mode == "mock"
    assert settings.provider_label == "Mock"
    assert settings.demo_data is (environment == "demo")
    assert settings.data_label == ("Demo Data" if environment == "demo" else "Local Data")
    assert settings.llm_api_key is None
    assert "@" not in settings.database_url


def test_demo_rejects_real_provider_and_nonfictional_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PROVIDER_MODE", raising=False)
    monkeypatch.delenv("DEMO_DATA", raising=False)
    override = tmp_path / "local.env"
    override.write_text("PROVIDER_MODE=real\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="demo requires fictional data and mock providers"):
        load_settings("demo", local_env_file=override)

    override.write_text("DEMO_DATA=false\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="demo requires fictional data and mock providers"):
        load_settings("demo", local_env_file=override)


def test_real_provider_has_explicit_label() -> None:
    settings = Settings(app_env="dev", provider_mode="real")
    assert settings.provider_label == "Real"
    assert "fixture-secret" not in repr(Settings(llm_api_key="fixture-secret"))
    assert "local-password" not in repr(Settings(database_url="postgresql+psycopg://user:local-password@localhost/db"))


def test_test_environment_rejects_real_provider() -> None:
    with pytest.raises(ValidationError, match="test requires mock providers"):
        Settings(app_env="test", provider_mode="real")
