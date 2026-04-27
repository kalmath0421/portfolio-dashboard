"""auth 모듈 — 비밀번호 게이트 검증."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def reload_auth(monkeypatch):
    """매 테스트마다 환경변수 정리 + auth 모듈 다시 import."""
    def _reload(env: dict | None = None):
        env = env or {}
        monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        from src import auth  # noqa: WPS433
        importlib.reload(auth)
        return auth

    return _reload


class TestIsGateEnabled:
    def test_disabled_when_env_missing(self, reload_auth):
        auth = reload_auth()
        assert auth.is_gate_enabled() is False

    def test_disabled_when_env_empty(self, reload_auth):
        auth = reload_auth({"DASHBOARD_PASSWORD": ""})
        assert auth.is_gate_enabled() is False

    def test_disabled_when_env_whitespace_only(self, reload_auth):
        auth = reload_auth({"DASHBOARD_PASSWORD": "   "})
        assert auth.is_gate_enabled() is False

    def test_enabled_when_env_set(self, reload_auth):
        auth = reload_auth({"DASHBOARD_PASSWORD": "swordfish"})
        assert auth.is_gate_enabled() is True


class TestVerifyPassword:
    def test_correct_password_passes(self, reload_auth):
        auth = reload_auth({"DASHBOARD_PASSWORD": "swordfish"})
        assert auth.verify_password("swordfish") is True

    def test_wrong_password_rejected(self, reload_auth):
        auth = reload_auth({"DASHBOARD_PASSWORD": "swordfish"})
        assert auth.verify_password("salmon") is False

    def test_empty_input_rejected_when_gate_enabled(self, reload_auth):
        auth = reload_auth({"DASHBOARD_PASSWORD": "swordfish"})
        assert auth.verify_password("") is False

    def test_whitespace_trimmed_on_compare(self, reload_auth):
        """앞뒤 공백은 자동 제거 — 모바일 자동 입력에서 흔한 케이스."""
        auth = reload_auth({"DASHBOARD_PASSWORD": "swordfish"})
        assert auth.verify_password("  swordfish  ") is True

    def test_case_sensitive(self, reload_auth):
        auth = reload_auth({"DASHBOARD_PASSWORD": "SwordFish"})
        assert auth.verify_password("swordfish") is False
        assert auth.verify_password("SwordFish") is True

    def test_no_env_means_anything_passes(self, reload_auth):
        """환경변수 미설정 = 게이트 비활성 → 어떤 입력이든 통과."""
        auth = reload_auth()
        assert auth.verify_password("anything") is True
        assert auth.verify_password("") is True

    def test_unicode_password(self, reload_auth):
        auth = reload_auth({"DASHBOARD_PASSWORD": "한글비번123"})
        assert auth.verify_password("한글비번123") is True
        assert auth.verify_password("한글비번") is False
