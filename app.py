"""포트폴리오 대시보드 - Streamlit 진입점.

DASHBOARD_PROFILE 환경변수에 따라 corp(기본) / personal 모드로 동작.
"""
from __future__ import annotations

import streamlit as st

from src import auth, db, profile_config, style
from src.views import (
    accounts_admin,
    charts,
    corp_etf,
    stocks,
    summary,
    tax_view,
    transactions,
)


def _build_page_registry() -> dict:
    """현재 프로파일에 맞는 메뉴 dict를 반환.

    personal 모드에서는 법인 계좌·세금 추적 페이지를 숨긴다.
    """
    registry = {
        "📊 요약": summary.render,
    }
    if profile_config.is_corp():
        registry["🏢 법인 계좌"] = corp_etf.render
    registry["📈 개인 계좌"] = stocks.render
    if profile_config.is_corp():
        registry["💰 세금 추적"] = tax_view.render
    registry["📉 차트"] = charts.render
    # 종목 관리 + 거래 입력은 한 페이지로 통합 (매수하면 보유 종목이 아래에 자동 등록).
    registry["📦 종목 + 거래"] = transactions.render
    registry["🏦 계좌 관리"] = accounts_admin.render
    return registry


# 관리·입력성 화면은 공통 헤더 생략
PAGES_WITHOUT_HEADER = {"🏦 계좌 관리", "📦 종목 + 거래"}


def _bootstrap() -> None:
    """첫 실행 시 한 번만 — 스키마 보장. 계좌·종목 시드는 사용자 UI에서 직접."""
    if "bootstrapped" in st.session_state:
        return
    info = db.initialize()
    st.session_state["bootstrapped"] = True
    if not info["has_accounts"]:
        st.toast(
            "👋 환영합니다! '🏦 계좌 관리'에서 첫 계좌를 추가하세요.",
            icon="🚀",
        )


def _sidebar(page_registry: dict) -> str:
    st.sidebar.title(f"📂 {profile_config.get_page_title()}")
    st.sidebar.caption(profile_config.get_subtitle())
    st.sidebar.divider()

    selected = st.sidebar.radio(
        "메뉴",
        options=list(page_registry.keys()),
        label_visibility="collapsed",
    )

    st.sidebar.divider()

    accounts = db.list_accounts(active_only=True)
    corp_n = sum(1 for a in accounts if a["kind"] == db.KIND_CORP)
    personal_n = sum(1 for a in accounts if a["kind"] == db.KIND_PERSONAL)

    if not accounts:
        st.sidebar.warning(
            "👋 등록된 계좌가 없습니다. **🏦 계좌 관리**에서 추가해주세요."
        )
    else:
        if profile_config.is_personal():
            st.sidebar.caption(f"활성 계좌: {personal_n}개")
        else:
            st.sidebar.caption(f"활성 계좌: 법인 {corp_n} · 개인 {personal_n}")
            if corp_n > 0 and not db.has_money_market_etf():
                st.sidebar.warning(
                    "⚠️ MMF성 ETF(예: KODEX CD금리액티브) 미등록 — "
                    "'⚙️ 종목 관리'에서 추가하세요."
                )

    st.sidebar.divider()
    st.sidebar.caption("**Phase 1 (현재)**: 다중 계좌 + 종목 관리")
    st.sidebar.caption("Phase 2: CSV 임포트 + 시세 (보류)")
    st.sidebar.caption("Phase 3: 화면 구현 (시세 후)")
    if profile_config.is_corp():
        st.sidebar.caption("Phase 4: 세금 모듈 ✅ tax.py 작성됨")

    # 비밀번호 변경 / 로그아웃
    auth.render_sidebar_change_password()

    return selected


def main() -> None:
    st.set_page_config(
        page_title=profile_config.get_page_title(),
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="auto",
    )
    style.apply_theme()

    # 스키마 우선 보장 — auth 테이블 등 필요. require_auth 가 DB 를 참조하기 때문.
    _bootstrap()

    # 비밀번호 게이트 — DB 미등록이면 등록, 등록 후엔 로그인. 통과 못 하면 st.stop.
    auth.require_auth()

    page_registry = _build_page_registry()
    selected = _sidebar(page_registry)

    if selected not in PAGES_WITHOUT_HEADER:
        summary.render_header()
        st.divider()

    page_registry[selected]()


if __name__ == "__main__":
    main()
