"""app._build_page_registry 가 프로파일에 따라 메뉴를 다르게 구성하는지 검증."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def reload_app(monkeypatch):
    """매 케이스마다 profile_config + app 모듈을 환경변수에 맞춰 다시 import."""
    def _reload(env: dict | None = None):
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
        import app  # noqa: WPS433

        importlib.reload(app)
        return app

    return _reload


class TestBuildPageRegistry:
    def test_corp_includes_corporate_and_tax(self, reload_app):
        app = reload_app()  # 기본 corp
        registry = app._build_page_registry()
        keys = list(registry.keys())
        assert "🏢 법인 계좌" in keys
        assert "💰 세금 추적" in keys
        # 핵심 페이지는 모두 포함 (종목 관리 + 거래 입력은 한 페이지로 통합).
        for required in ("📊 요약", "📈 개인 계좌", "📉 차트", "📦 종목 + 거래",
                         "🏦 계좌 관리"):
            assert required in keys
        # 통합 후 별도 메뉴는 제거됨.
        assert "⚙️ 종목 관리" not in keys
        assert "📝 거래 입력" not in keys

    def test_personal_hides_corporate_and_tax(self, reload_app):
        app = reload_app({"DASHBOARD_PROFILE": "personal"})
        registry = app._build_page_registry()
        keys = list(registry.keys())
        assert "🏢 법인 계좌" not in keys
        assert "💰 세금 추적" not in keys
        # 그 외 핵심 페이지는 그대로 노출
        for required in ("📊 요약", "📈 개인 계좌", "📉 차트", "📦 종목 + 거래",
                         "🏦 계좌 관리"):
            assert required in keys
        assert "⚙️ 종목 관리" not in keys
        assert "📝 거래 입력" not in keys

    def test_personal_keeps_summary_first(self, reload_app):
        app = reload_app({"DASHBOARD_PROFILE": "personal"})
        registry = app._build_page_registry()
        # 요약이 첫 메뉴
        assert next(iter(registry.keys())) == "📊 요약"
