"""개인 계좌 화면 — 통화별(USD/KRW) 수익률 분리 + 계좌 합계 + 환율 영향 분리."""
from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st

from src import analytics, db, prices


D = Decimal


def _format_krw(amount: Decimal | None) -> str:
    if amount is None:
        return "—"
    return f"{int(amount):,} 원"


def _format_usd(amount: Decimal | None) -> str:
    if amount is None:
        return "—"
    return f"$ {float(amount):,.2f}"


def _format_pct(pct: Decimal | None) -> str:
    if pct is None:
        return "—"
    return f"{float(pct):+.2f}%"


def _account_holdings_table(
    holdings, valuations_by_ticker: dict[str, analytics.HoldingValuation]
) -> pd.DataFrame:
    """계좌의 종목 목록을 USD 수익률 / KRW 수익률 함께 표시."""
    rows = []
    for h in holdings:
        v = valuations_by_ticker.get(h["ticker"])
        if v is None:
            rows.append({
                "ticker": h["ticker"],
                "name": h["name"],
                "category": db.CATEGORIES.get(h["category"], h["category"]),
                "currency": h["currency"],
                "보유수량": "—",
                "평균단가": "—",
                "현재가": "—",
                "평가(현지)": "—",
                "USD/현지 수익률": "—",
                "원화 수익률": "—",
            })
            continue

        if v.currency == "USD":
            avg_str = _format_usd(v.avg_cost_local) if v.avg_cost_local > 0 else "—"
            cur_str = _format_usd(v.current_price_local)
            mv_str = _format_usd(v.market_value_local)
        else:
            avg_str = (
                f"{int(v.avg_cost_local):,} 원" if v.avg_cost_local > 0 else "—"
            )
            cur_str = (
                f"{int(v.current_price_local):,} 원"
                if v.current_price_local is not None else "—"
            )
            mv_str = _format_krw(v.market_value_local)

        rows.append({
            "ticker": h["ticker"],
            "name": h["name"],
            "category": db.CATEGORIES.get(h["category"], h["category"]),
            "currency": h["currency"],
            "보유수량": (
                f"{float(v.quantity):g}" if v.quantity > 0 else "—"
            ),
            "평균단가": avg_str,
            "현재가": cur_str + (" ⚠️" if v.is_price_stale else ""),
            "평가(현지)": mv_str,
            "USD/현지 수익률": _format_pct(v.return_pct_local),
            "원화 수익률": _format_pct(v.return_pct_krw),
        })
    return pd.DataFrame(rows)


def _account_metrics(account_id: int, agg: dict) -> None:
    """계좌별 합계 메트릭 — USD 평가 + KRW 환산 분리 표시."""
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        usd_mv = agg["market_value_usd"]
        st.metric(
            "USD 평가금액",
            _format_usd(usd_mv) if usd_mv > 0 else "—",
            help="이 계좌의 USD 종목 평가금액 합 (현지통화 그대로)",
        )
    with c2:
        krw_mv = agg["market_value_krw_only"]
        st.metric(
            "KRW 평가금액",
            _format_krw(krw_mv) if krw_mv > 0 else "—",
            help="이 계좌의 KRW 종목 평가금액 합",
        )
    with c3:
        total_krw = agg["market_value_krw"]
        st.metric(
            "총 평가금액 (KRW 환산)",
            _format_krw(total_krw) if total_krw > 0 else "—",
            help="USD 종목을 현재 환율로 환산해 합산한 총액",
        )
    with c4:
        unreal = agg["unrealized_pnl_krw"]
        cost = agg["cost_basis_krw"]
        ret_pct = (
            (unreal / cost * D(100)).quantize(D("0.01"))
            if cost and cost > 0 else None
        )
        st.metric(
            "미실현 손익 (KRW)",
            _format_krw(unreal) if unreal != 0 else "—",
            delta=_format_pct(ret_pct) if ret_pct is not None else None,
        )


def _fx_attribution_panel(
    valuations: list, states: dict
) -> None:
    """USD 종목의 환율 영향 분리 — 가격 효과 vs 환율 효과."""
    rows = analytics.fx_attribution_table(valuations, states)
    if not rows:
        return
    with st.expander("💱 환율 영향 분리 (USD 종목별, KRW 단위)", expanded=False):
        st.caption(
            "미실현 손익을 **가격 변동 효과**와 **환율 변동 효과**, "
            "그리고 두 변수가 함께 움직인 **교차항**으로 분해합니다. "
            "세 값의 합은 미실현 손익(KRW)과 일치합니다."
        )
        df = pd.DataFrame(rows)
        df_view = pd.DataFrame({
            "티커": df["ticker"],
            "가격 효과 (KRW)": df["price_effect_krw"].astype(float).map("{:,.0f}".format),
            "환율 효과 (KRW)": df["fx_effect_krw"].astype(float).map("{:,.0f}".format),
            "교차항 (KRW)": df["cross_term_krw"].astype(float).map("{:,.0f}".format),
            "미실현 손익 합 (KRW)": df["total_unrealized_krw"].astype(float).map("{:,.0f}".format),
        })
        st.dataframe(df_view, use_container_width=True, hide_index=True)


def _load_market_data(holdings) -> tuple[dict, prices.FxResult | None]:
    """현재가·환율 조회.

    세션당 한 번 자동 라이브 갱신 — 오늘자 스냅샷이 없는 종목만 호출.
    이미 오늘자 데이터가 있으면 외부 호출 없이 빠르게 표시.
    """
    if not st.session_state.get("auto_refresh_done"):
        with st.spinner("🌐 시세·환율 자동 갱신 중... (오늘 첫 진입)"):
            st.session_state["price_cache"] = prices.auto_refresh_prices(holdings)
            st.session_state["fx_cache"] = prices.auto_refresh_fx()
            st.session_state["auto_refresh_done"] = True
    else:
        # 이후 페이지 이동에서는 캐시 그대로
        if "price_cache" not in st.session_state or not st.session_state["price_cache"]:
            st.session_state["price_cache"] = prices.load_cached_prices(holdings)
        if "fx_cache" not in st.session_state or st.session_state["fx_cache"] is None:
            st.session_state["fx_cache"] = prices.load_cached_fx()

    return st.session_state["price_cache"], st.session_state["fx_cache"]


def _refresh_button(holdings) -> None:
    if st.button("🔄 시세 갱신", key="stocks_refresh"):
        with st.spinner("시세·환율 조회 중..."):
            price_cache: dict = {}
            for h in holdings:
                key = (h["ticker"], h["currency"])
                if key in price_cache:
                    continue
                result = prices.get_price(h["ticker"], h["currency"])
                price_cache[key] = result
            fx_result = prices.get_usdkrw()
            st.session_state["price_cache"] = price_cache
            st.session_state["fx_cache"] = fx_result
        st.rerun()


def render() -> None:
    st.header("📈 개인 계좌")
    st.caption(
        "개인 종류 계좌의 모든 활성 종목 — 미국 / 국내 분리 + 통화별 수익률 + 환율 영향 분리"
    )

    accounts = db.list_accounts(active_only=True, kind=db.KIND_PERSONAL)
    if not accounts:
        st.warning("활성 개인 계좌가 없습니다. '🏦 계좌 관리'에서 추가하세요.")
        return

    all_holdings = db.list_holdings(active_only=True, kind=db.KIND_PERSONAL)
    _refresh_button(all_holdings)

    price_cache, fx_cache = _load_market_data(all_holdings)
    states = analytics.load_states_from_db()

    # 모든 종목 valuation 미리 계산
    valuations: list[analytics.HoldingValuation] = []
    for h in all_holdings:
        key = (h["account_id"], h["ticker"])
        state = states.get(key) or analytics.PositionState(
            ticker=h["ticker"], account_id=h["account_id"],
            currency=h["currency"],
        )
        price_result = price_cache.get((h["ticker"], h["currency"]))
        cur_price = price_result.price if price_result else None
        is_stale = price_result.is_stale if price_result else False
        cur_fx = fx_cache.rate if (h["currency"] == "USD" and fx_cache) else None
        v = analytics.value_position(state, cur_price, cur_fx, is_price_stale=is_stale)
        valuations.append(v)

    aggregates = analytics.aggregate_by_account(valuations)

    if fx_cache:
        st.caption(
            f"💱 적용 환율 USD/KRW = {fx_cache.rate:,.2f} "
            f"({fx_cache.as_of}, {fx_cache.source}"
            f"{', stale' if fx_cache.is_stale else ''})"
        )

    for acct in accounts:
        with st.container(border=True):
            st.subheader(f"📂 {acct['name']}")
            st.caption(
                f"증권사: {acct['broker']}"
                + (f" · {acct['note']}" if acct["note"] else "")
            )

            agg = aggregates.get(
                acct["account_id"],
                {k: D(0) for k in (
                    "market_value_usd", "market_value_krw_only",
                    "market_value_krw", "cost_basis_krw", "unrealized_pnl_krw",
                )},
            )
            _account_metrics(acct["account_id"], agg)

            holdings = [h for h in all_holdings if h["account_id"] == acct["account_id"]]
            if not holdings:
                st.info("이 계좌에 등록된 종목이 없습니다.")
                continue

            v_by_ticker = {
                v.ticker: v for v in valuations if v.account_id == acct["account_id"]
            }

            us_holdings = [h for h in holdings if h["currency"] == "USD"]
            kr_holdings = [h for h in holdings if h["currency"] == "KRW"]

            tab_us, tab_kr = st.tabs([
                f"🇺🇸 미국 ({len(us_holdings)})",
                f"🇰🇷 국내 ({len(kr_holdings)})",
            ])
            with tab_us:
                if us_holdings:
                    df = _account_holdings_table(us_holdings, v_by_ticker)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.caption("(없음)")
            with tab_kr:
                if kr_holdings:
                    df = _account_holdings_table(kr_holdings, v_by_ticker)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.caption("(없음)")

            acct_valuations = [v for v in valuations if v.account_id == acct["account_id"]]
            _fx_attribution_panel(acct_valuations, states)

    if all(v.market_value_krw is None for v in valuations):
        st.info(
            "💡 거래 데이터가 없거나 시세를 아직 조회하지 않았습니다. "
            "위 '🔄 시세 갱신' 버튼을 누르면 yfinance·pykrx로 현재가/환율을 가져옵니다. "
            "거래 내역은 Phase 2(CSV 임포트)에서 자동 누적됩니다."
        )
