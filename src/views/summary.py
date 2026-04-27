"""상단 공통 헤더 + 요약 메인 페이지."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import analytics, db, prices, profile_config, tax


D = Decimal
_TAX_RULES_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "tax_rules.yaml"
)


def _format_krw(amount: Decimal | int | float | None) -> str:
    if amount is None:
        return "—"
    n = int(Decimal(str(amount)))
    if n == 0:
        return "—"
    return f"{n:,} 원"


def _format_pct(pct: Decimal | float | None) -> str:
    if pct is None:
        return "—"
    return f"{float(pct):+.2f}%"


def _gather() -> dict:
    """모든 활성 종목 valuation + 분배금 + 사업연도 세금 합산."""
    holdings = db.list_holdings(active_only=True)
    states = analytics.load_states_from_db()

    # 시세·환율 캐시 (없으면 DB 스냅샷에서 로드)
    if not st.session_state.get("price_cache"):
        st.session_state["price_cache"] = prices.load_cached_prices(holdings)
    if st.session_state.get("fx_cache") is None:
        st.session_state["fx_cache"] = prices.load_cached_fx()

    price_cache = st.session_state["price_cache"]
    fx_cache = st.session_state["fx_cache"]

    valuations: list[analytics.HoldingValuation] = []
    for h in holdings:
        key = (h["account_id"], h["ticker"])
        state = states.get(key) or analytics.PositionState(
            ticker=h["ticker"], account_id=h["account_id"],
            currency=h["currency"],
        )
        pr = price_cache.get((h["ticker"], h["currency"]))
        cur_price = pr.price if pr else None
        is_stale = pr.is_stale if pr else False
        cur_fx = fx_cache.rate if (h["currency"] == "USD" and fx_cache) else None
        v = analytics.value_position(state, cur_price, cur_fx, is_price_stale=is_stale)
        valuations.append(v)

    total_mv = sum(
        (v.market_value_krw for v in valuations if v.market_value_krw is not None),
        D(0),
    )
    total_cost = sum(
        (v.cost_basis_krw for v in valuations if v.cost_basis_krw is not None),
        D(0),
    )
    total_unreal = total_mv - total_cost if total_cost > 0 else D(0)
    return_pct = (
        (total_unreal / total_cost * D(100)).quantize(D("0.01"))
        if total_cost > 0 else None
    )

    # 누적 분배금 (전체 기간)
    div_gross = sum(
        (v.cumulative_dividend_gross_krw for v in valuations), D(0)
    )
    div_net = sum((v.cumulative_dividend_net_krw for v in valuations), D(0))

    # 사업연도 세금
    fy_summary = None
    expected_tax = None
    rules = None
    if _TAX_RULES_PATH.exists():
        try:
            rules = tax.TaxRules.from_yaml(_TAX_RULES_PATH)
            fy = tax.fiscal_year_of(date.today(), rules.fiscal_year_end_month)
            fy_summary = tax.aggregate_taxable_for_fy(fy, rules)
            expected_tax = tax.expected_corporate_tax(fy_summary, rules, 0)
        except Exception:
            pass

    return {
        "valuations": valuations,
        "holdings": holdings,
        "total_mv": total_mv,
        "total_cost": total_cost,
        "total_unreal": total_unreal,
        "return_pct": return_pct,
        "div_gross": div_gross,
        "div_net": div_net,
        "fy_summary": fy_summary,
        "expected_tax": expected_tax,
        "fx_cache": fx_cache,
    }


def render_header() -> None:
    """모든 페이지 상단 공통 메트릭. corp 모드는 4개, personal 모드는 3개."""
    s = _gather()
    is_personal = profile_config.is_personal()
    cols = st.columns(3 if is_personal else 4)
    with cols[0]:
        st.metric(
            "총 평가금액 (KRW)",
            _format_krw(s["total_mv"]),
            delta=_format_pct(s["return_pct"]),
            help="모든 활성 종목의 평가금액 합 (USD는 현재 환율로 환산)",
        )
    with cols[1]:
        st.metric(
            "투자원금 (KRW)",
            _format_krw(s["total_cost"]),
            help="평균단가 × 보유수량의 합 (USD는 매입 시점 환율)",
        )
    with cols[2]:
        delta_str = (
            f"세후 {_format_krw(s['div_net'])}" if s["div_gross"] > 0 else None
        )
        st.metric(
            "누적 분배금 (세전)",
            _format_krw(s["div_gross"]),
            delta=delta_str,
            help="입력된 분배금 합계",
        )
    if not is_personal:
        with cols[3]:
            if s["expected_tax"]:
                st.metric(
                    "사업연도 예상 추가 법인세",
                    _format_krw(s["expected_tax"]["net_additional_after_credit"]),
                    help="투자 외 본업 소득 0원 가정. '💰 세금 추적'에서 정밀 계산.",
                )
            else:
                st.metric("사업연도 예상 추가 법인세", "—")


def _account_cards(valuations: list[analytics.HoldingValuation]) -> None:
    aggregates = analytics.aggregate_by_account(valuations)
    accounts = db.list_accounts(active_only=True)
    if not accounts:
        return

    st.subheader("📂 계좌별 요약")
    cols = st.columns(min(len(accounts), 3) or 1)
    for i, acct in enumerate(accounts):
        agg = aggregates.get(acct["account_id"], {})
        with cols[i % len(cols)]:
            with st.container(border=True):
                st.markdown(f"### {acct['name']}")
                st.caption(f"{db.KINDS[acct['kind']]} · {acct['broker']}")
                mv = agg.get("market_value_krw", D(0))
                cost = agg.get("cost_basis_krw", D(0))
                pnl = agg.get("unrealized_pnl_krw", D(0))
                ret = (
                    (pnl / cost * D(100)).quantize(D("0.01"))
                    if cost > 0 else None
                )
                st.metric("평가금액", _format_krw(mv), delta=_format_pct(ret))
                st.caption(
                    f"원가 {_format_krw(cost)} · 미실현 {_format_krw(pnl)}"
                )

                # USD/KRW 분리
                usd_mv = agg.get("market_value_usd", D(0))
                krw_only = agg.get("market_value_krw_only", D(0))
                if usd_mv > 0 and krw_only > 0:
                    st.caption(
                        f"USD ${float(usd_mv):,.0f} · KRW {_format_krw(krw_only)}"
                    )


def _contribution_panel(valuations: list[analytics.HoldingValuation]) -> None:
    breakdown = analytics.contribution_breakdown(valuations)
    if not breakdown:
        return

    # 종목명 매핑
    name_map = {
        (v.account_id, v.ticker): v.ticker
        for v in valuations
    }
    holdings_lookup: dict[tuple[int, str], dict] = {}
    for h in db.list_holdings(active_only=True):
        holdings_lookup[(h["account_id"], h["ticker"])] = dict(h)

    def _label(b: dict) -> str:
        h = holdings_lookup.get((b["account_id"], b["ticker"]))
        if h:
            return f"{b['ticker']} ({h['name']})"
        return b["ticker"]

    st.subheader("🏆 손익 기여도")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**📈 상위 5종목**")
        top = breakdown[:5]
        df_top = pd.DataFrame([
            {
                "종목": _label(b),
                "손익 (KRW)": _format_krw(b["unrealized_pnl_krw"]),
                "기여도": f"{float(b['contribution_pct']):+.1f}%",
            }
            for b in top
        ])
        st.dataframe(df_top, use_container_width=True, hide_index=True)
    with col2:
        st.markdown("**📉 하위 5종목**")
        bot = breakdown[-5:][::-1]
        df_bot = pd.DataFrame([
            {
                "종목": _label(b),
                "손익 (KRW)": _format_krw(b["unrealized_pnl_krw"]),
                "기여도": f"{float(b['contribution_pct']):+.1f}%",
            }
            for b in bot
        ])
        st.dataframe(df_bot, use_container_width=True, hide_index=True)


def _allocation_donut(valuations: list[analytics.HoldingValuation]) -> None:
    chart_data = [
        (v.ticker, float(v.market_value_krw))
        for v in valuations
        if v.market_value_krw is not None and v.market_value_krw > 0
    ]
    if not chart_data:
        return

    st.subheader("🥯 종목별 비중")
    df = pd.DataFrame(chart_data, columns=["ticker", "market_value_krw"])
    df = df.sort_values("market_value_krw", ascending=False)

    fig = go.Figure(data=[go.Pie(
        labels=df["ticker"],
        values=df["market_value_krw"],
        hole=0.55,
        textinfo="label+percent",
        textposition="outside",
        marker=dict(
            colors=[
                "#F5A623", "#FF7A45", "#FF4D4F", "#EB2F96", "#9254DE",
                "#597EF7", "#13C2C2", "#52C41A", "#FAAD14", "#FA8C16",
                "#A0D911", "#1890FF", "#722ED1", "#EB2F96", "#FF6F61",
            ],
            line=dict(color="#0F1218", width=2),
        ),
    )])
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E6E9EF", family="Pretendard"),
        height=440,
        margin=dict(l=0, r=0, t=20, b=20),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def _fy_tax_panel(s: dict) -> None:
    # 법인세 패널 — personal 모드에서는 불필요하므로 스킵.
    if profile_config.is_personal():
        return
    if not s["fy_summary"] or not s["expected_tax"]:
        return
    fy = s["fy_summary"]
    et = s["expected_tax"]

    st.subheader(f"💰 {fy.fiscal_year} 사업연도 세금 누적")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("분배금/배당 (세전)", _format_krw(fy.dividend_taxable_krw))
    with c2:
        st.metric("실현 매매차익", _format_krw(fy.realized_gain_taxable_krw))
    with c3:
        st.metric("외국납부세액", _format_krw(fy.foreign_tax_paid_krw))
    with c4:
        st.metric(
            "예상 추가 법인세 (공제 후)",
            _format_krw(et["net_additional_after_credit"]),
        )
    st.caption(
        "⚠️ 본업 소득 0원 기준의 단순 추정. 정확한 분석은 '💰 세금 추적' 화면 참고."
    )


def _refresh_button(holdings) -> None:
    if st.button("🔄 시세 갱신", key="summary_refresh"):
        with st.spinner("시세·환율 조회 중..."):
            price_cache: dict = {}
            for h in holdings:
                key = (h["ticker"], h["currency"])
                if key in price_cache:
                    continue
                price_cache[key] = prices.get_price(h["ticker"], h["currency"])
            st.session_state["price_cache"] = price_cache
            st.session_state["fx_cache"] = prices.get_usdkrw()
        st.rerun()


def render() -> None:
    s = _gather()

    st.header("📊 요약")

    if s["total_mv"] == 0 and not s["holdings"]:
        st.info(
            "💡 거래 데이터가 없습니다.\n\n"
            "1️⃣ '🏦 계좌 관리'에서 계좌 추가\n"
            "2️⃣ '⚙️ 종목 관리'에서 종목 등록 (또는 일괄 등록)\n"
            "3️⃣ '📝 거래 입력' → '📦 초기 보유분'에서 평균단가·수량 입력"
        )
        return

    _refresh_button(s["holdings"])

    # 큰 메트릭 카드 2개
    c1, c2 = st.columns(2)
    with c1:
        delta = (
            f"{_format_krw(s['total_unreal'])} ({_format_pct(s['return_pct'])})"
            if s["total_cost"] > 0 else None
        )
        st.metric(
            "💰 총 평가금액",
            _format_krw(s["total_mv"]),
            delta=delta,
        )
    with c2:
        st.metric(
            "🌱 투자원금",
            _format_krw(s["total_cost"]),
        )

    # 분배금 포함 총수익 — 자본이득(미실현) + 누적 분배금(세후).
    # 수익률은 delta 에 함께 표기해 카드 한 개로 통합 (산만함 줄이기).
    if s["total_cost"] > 0:
        total_return = D(str(s["total_unreal"])) + D(str(s["div_net"]))
        total_return_pct = (
            total_return / D(str(s["total_cost"])) * D(100)
        ).quantize(D("0.01"))
        st.metric(
            "💎 총수익 (분배금 포함, 세후)",
            _format_krw(total_return),
            delta=(
                f"{_format_pct(total_return_pct)} · "
                f"미실현 {_format_krw(s['total_unreal'])} + 분배금 {_format_krw(s['div_net'])}"
            ),
            help=(
                "보유 종목의 미실현 손익 + 누적 분배금(원천징수 후) 합계. "
                "지금 모두 매도하면 통장에 남을 추정 금액에 가까움 (매도 수수료·세금 별도). "
                "수익률 = 총수익 / 매입원가 × 100."
            ),
        )

    if s["fx_cache"]:
        fx = s["fx_cache"]
        stale_note = " · ⚠️ 갱신 필요" if fx.is_stale else ""
        st.caption(
            f"💱 **환율 USD/KRW = {fx.rate:,.2f}원** "
            f"· 기준일 {fx.as_of} · 출처 {fx.source}{stale_note}"
        )

    st.divider()
    _account_cards(s["valuations"])

    st.divider()
    _contribution_panel(s["valuations"])

    st.divider()
    _allocation_donut(s["valuations"])

    st.divider()
    _fy_tax_panel(s)
