from pathlib import Path

import pytest
from pydantic import ValidationError

from app.platform import config
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


@pytest.mark.parametrize("environment", ["dev", "test", "demo"])
def test_app_env_selects_checked_in_profile(
    environment: Environment, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    isolated_root = tmp_path / "backend"
    (isolated_root / "config").mkdir(parents=True)
    for name in ("dev", "test", "demo"):
        source = config._BACKEND_ROOT / "config" / f"{name}.env"
        (isolated_root / "config" / f"{name}.env").write_bytes(source.read_bytes())
    monkeypatch.setattr(config, "_BACKEND_ROOT", isolated_root)
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setenv("APP_ENV", environment)
    config.get_settings.cache_clear()
    try:
        settings = config.get_settings()
        assert settings.app_env == environment
        assert settings.provider_mode == "mock"
        assert settings.demo_data is (environment == "demo")
    finally:
        config.get_settings.cache_clear()


def test_local_override_changes_dev_mode_but_invalid_mode_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PROVIDER_MODE", raising=False)
    override = tmp_path / "local.env"
    override.write_text("PROVIDER_MODE=real\n", encoding="utf-8")
    assert load_settings("dev", local_env_file=override).provider_label == "Real"

    override.write_text("PROVIDER_MODE=unsupported\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_settings("dev", local_env_file=override)


def test_invalid_app_env_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    config.get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="APP_ENV must be dev, test, or demo"):
            config.get_settings()
    finally:
        config.get_settings.cache_clear()
