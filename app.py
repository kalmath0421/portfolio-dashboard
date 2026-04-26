"""법인 투자 포트폴리오 대시보드 - Streamlit 진입점."""
from __future__ import annotations

import streamlit as st

from src import db, style
from src.views import (
    accounts_admin,
    charts,
    corp_etf,
    holdings_admin,
    stocks,
    summary,
    tax_view,
    transactions,
)


PAGE_REGISTRY = {
    "📊 요약": summary.render,
    "🏢 법인 계좌": corp_etf.render,
    "📈 개인 계좌": stocks.render,
    "💰 세금 추적": tax_view.render,
    "📉 차트": charts.render,
    "📝 거래 입력": transactions.render,
    "🏦 계좌 관리": accounts_admin.render,
    "⚙️ 종목 관리": holdings_admin.render,
}

# 관리·입력성 화면은 공통 헤더 생략
PAGES_WITHOUT_HEADER = {"🏦 계좌 관리", "⚙️ 종목 관리", "📝 거래 입력"}


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


def _sidebar() -> str:
    st.sidebar.title("📂 포트폴리오 대시보드")
    st.sidebar.caption("법인 투자 모니터링 (모니터링 보조 도구)")
    st.sidebar.divider()

    selected = st.sidebar.radio(
        "메뉴",
        options=list(PAGE_REGISTRY.keys()),
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
    st.sidebar.caption("Phase 4: 세금 모듈 ✅ tax.py 작성됨")

    return selected


def main() -> None:
    st.set_page_config(
        page_title="법인 포트폴리오 대시보드",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    style.apply_theme()

    _bootstrap()

    selected = _sidebar()

    if selected not in PAGES_WITHOUT_HEADER:
        summary.render_header()
        st.divider()

    PAGE_REGISTRY[selected]()


if __name__ == "__main__":
    main()
