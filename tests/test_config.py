"""Secrets → environment → settings, and Supabase key safety checks."""

from __future__ import annotations

import base64
import json

import pytest

import config
from auth import AuthError, build_auth_service
from config import Settings, apply_secrets, get_settings


@pytest.fixture(autouse=True)
def clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEY", "AUTH_MODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "_INJECTED", {})
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_secrets_added_after_start_are_picked_up() -> None:
    assert not get_settings().supabase_configured  # first run: no secrets yet (cached)
    changed = apply_secrets({"SUPABASE_URL": "https://abc.supabase.co/rest/v1/ ", "SUPABASE_KEY": " sb_publishable_x"})
    assert changed
    settings = get_settings()
    assert settings.supabase_url == "https://abc.supabase.co"
    assert settings.supabase_key == "sb_publishable_x"
    assert not apply_secrets({"SUPABASE_URL": "https://abc.supabase.co/rest/v1/ ", "SUPABASE_KEY": " sb_publishable_x"})


def test_sections_and_lowercase_keys() -> None:
    apply_secrets({"supabase": {"url": "https://abc.supabase.co", "publishable_key": "sb_publishable_y"}})
    assert get_settings().supabase_configured


def test_external_environment_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://from-shell.supabase.co")
    apply_secrets({"SUPABASE_URL": "https://from-secrets.supabase.co"})
    assert get_settings().supabase_url == "https://from-shell.supabase.co"


def _jwt(role: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{payload}.sig"


@pytest.mark.parametrize("key", ["sb_secret_abc", _jwt("service_role")])
def test_privileged_keys_are_refused(key: str) -> None:
    with pytest.raises(AuthError, match="clé secrète"):
        build_auth_service(Settings(anthropic_api_key=None, supabase_url="https://a.supabase.co", supabase_key=key))


def test_missing_secrets_are_named() -> None:
    with pytest.raises(AuthError, match="SUPABASE_KEY"):
        build_auth_service(Settings(anthropic_api_key=None, supabase_url="https://a.supabase.co"))


def test_anon_jwt_and_publishable_keys_are_accepted() -> None:
    for key in ("sb_publishable_abc", _jwt("anon")):
        service = build_auth_service(
            Settings(anthropic_api_key=None, supabase_url="https://a.supabase.co", supabase_key=key)
        )
        assert service.mode == "supabase"
