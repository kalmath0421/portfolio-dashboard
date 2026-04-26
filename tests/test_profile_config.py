"""profile_config 환경변수 분기 검증."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def reload_profile(monkeypatch):
    """매 케이스마다 profile_config 를 깨끗이 다시 import."""
    def _reload(env: dict | None = None) -> "module":  # type: ignore[name-defined]
        env = env or {}
        for key in (
            "DASHBOARD_PROFILE",
            "DASHBOARD_TITLE",
            "DASHBOARD_SUBTITLE",
        ):
            monkeypatch.delenv(key, raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        from src import profile_config  # noqa: WPS433
        importlib.reload(profile_config)
        return profile_config

    return _reload


class TestGetProfile:
    def test_default_is_corp(self, reload_profile):
        pc = reload_profile()
        assert pc.get_profile() == "corp"
        assert pc.is_corp() is True
        assert pc.is_personal() is False

    def test_personal_when_env_set(self, reload_profile):
        pc = reload_profile({"DASHBOARD_PROFILE": "personal"})
        assert pc.get_profile() == "personal"
        assert pc.is_personal() is True
        assert pc.is_corp() is False

    def test_unknown_value_falls_back_to_corp(self, reload_profile):
        pc = reload_profile({"DASHBOARD_PROFILE": "garbage"})
        assert pc.get_profile() == "corp"
        assert pc.is_corp() is True

    def test_case_insensitive_and_trimmed(self, reload_profile):
        pc = reload_profile({"DASHBOARD_PROFILE": "  PERSONAL  "})
        assert pc.is_personal() is True


class TestGetPageTitle:
    def test_default_corp_title(self, reload_profile):
        pc = reload_profile()
        assert pc.get_page_title() == "법인 포트폴리오 대시보드"

    def test_default_personal_title(self, reload_profile):
        pc = reload_profile({"DASHBOARD_PROFILE": "personal"})
        assert pc.get_page_title() == "포트폴리오 대시보드"

    def test_custom_title_wins(self, reload_profile):
        pc = reload_profile(
            {
                "DASHBOARD_PROFILE": "personal",
                "DASHBOARD_TITLE": "아란의 포트폴리오",
            }
        )
        assert pc.get_page_title() == "아란의 포트폴리오"

    def test_custom_title_in_corp_mode(self, reload_profile):
        pc = reload_profile({"DASHBOARD_TITLE": "회사 대시보드"})
        assert pc.get_page_title() == "회사 대시보드"


class TestGetSubtitle:
    def test_default_corp(self, reload_profile):
        pc = reload_profile()
        assert "법인 투자" in pc.get_subtitle()

    def test_default_personal(self, reload_profile):
        pc = reload_profile({"DASHBOARD_PROFILE": "personal"})
        assert "개인 투자" in pc.get_subtitle()

    def test_custom_subtitle_wins(self, reload_profile):
        pc = reload_profile(
            {"DASHBOARD_SUBTITLE": "맞춤 부제"},
        )
        assert pc.get_subtitle() == "맞춤 부제"
