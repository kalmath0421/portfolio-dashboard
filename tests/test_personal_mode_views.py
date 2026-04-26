"""personal 모드에서 법인 전용 패널/캡션이 숨겨지는지 검증."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def reload_views(monkeypatch):
    """profile_config + 관련 view 모듈을 환경변수에 맞춰 다시 로드."""
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
        from src.views import summary  # noqa: WPS433
        importlib.reload(summary)
        return profile_config, summary

    return _reload


class TestFyTaxPanelGating:
    """_fy_tax_panel 은 personal 모드에서 무조건 early return."""

    def test_personal_skips_even_with_data(self, reload_views, monkeypatch):
        _, summary = reload_views({"DASHBOARD_PROFILE": "personal"})

        # _fy_tax_panel 안에서 호출되는 streamlit 함수는 호출되지 않아야 한다.
        # st.subheader / st.columns / st.metric / st.caption 어떤 것도 호출 ❌
        called = {"subheader": 0, "columns": 0, "metric": 0, "caption": 0}

        def _track(name):
            def _fn(*args, **kwargs):
                called[name] += 1
                # 각 함수가 반환해야 할 객체를 적당히 흉내냄
                return [_FakeCol(), _FakeCol(), _FakeCol(), _FakeCol()]
            return _fn

        monkeypatch.setattr(summary.st, "subheader", _track("subheader"))
        monkeypatch.setattr(summary.st, "columns", _track("columns"))
        monkeypatch.setattr(summary.st, "metric", _track("metric"))
        monkeypatch.setattr(summary.st, "caption", _track("caption"))

        # fy_summary 와 expected_tax 가 둘 다 truthy 라도 personal 이면 스킵
        s = {"fy_summary": object(), "expected_tax": {"net_additional_after_credit": 0}}
        summary._fy_tax_panel(s)

        assert called == {"subheader": 0, "columns": 0, "metric": 0, "caption": 0}

    def test_corp_proceeds_when_data_present(self, reload_views, monkeypatch):
        _, summary = reload_views()  # 기본 corp

        called = {"subheader": 0}
        monkeypatch.setattr(
            summary.st, "subheader",
            lambda *a, **k: called.__setitem__("subheader", called["subheader"] + 1),
        )
        # 나머지는 no-op 으로 통과시킴
        monkeypatch.setattr(summary.st, "columns", lambda n: [_FakeCol()] * n)
        monkeypatch.setattr(summary.st, "metric", lambda *a, **k: None)
        monkeypatch.setattr(summary.st, "caption", lambda *a, **k: None)

        s = {
            "fy_summary": _FakeFy(),
            "expected_tax": {"net_additional_after_credit": 0},
        }
        summary._fy_tax_panel(s)

        assert called["subheader"] == 1


class _FakeCol:
    """`with col:` context manager 흉내."""
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _FakeFy:
    fiscal_year = 2026
    dividend_taxable_krw = 0
    realized_gain_taxable_krw = 0
    foreign_tax_paid_krw = 0
