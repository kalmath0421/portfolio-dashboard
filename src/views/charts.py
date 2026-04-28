"""차트 화면 — 평가금액 추이 / 분배금 월별 / 비중 분석."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import analytics, db


D = Decimal

PALETTE = [
    "#F5A623", "#FF7A45", "#FF4D4F", "#EB2F96", "#9254DE",
    "#597EF7", "#13C2C2", "#52C41A", "#FAAD14", "#FA8C16",
    "#A0D911", "#1890FF", "#722ED1", "#FF6F61", "#36CFC9",
]

PERIOD_OPTIONS = {
    "1M": 30,
    "3M": 90,
    "6M": 180,
    "YTD": None,   # 올해 1월 1일부터
    "전체": None,  # 전체
}


def _plotly_layout(**overrides) -> dict:
    base = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E6E9EF", family="Pretendard"),
        margin=dict(l=10, r=10, t=30, b=20),
        xaxis=dict(gridcolor="#1F2531", zerolinecolor="#1F2531"),
        yaxis=dict(gridcolor="#1F2531", zerolinecolor="#1F2531"),
        legend=dict(orientation="h", y=-0.15),
    )
    base.update(overrides)
    return base


def _value_history_chart(period: str) -> None:
    today = date.today()
    if period == "전체":
        start = None
    elif period == "YTD":
        start = date(today.year, 1, 1).isoformat()
    else:
        days = PERIOD_OPTIONS[period]
        start = (today - timedelta(days=days)).isoformat()

    history = analytics.value_history(start_date=start)
    if not history or len(history) < 2:
        st.info(
            f"💡 {period} 기간의 시계열 데이터가 부족합니다. "
            "매일 시세 갱신이 누적되면 추이 그래프가 풍부해집니다."
        )
        return

    df = pd.DataFrame([
        {
            "date": h["date"],
            "평가금액": float(h["value_krw"]),
            "투자원금": float(h["cost_krw"]),
        }
        for h in history
    ])
    df["date"] = pd.to_datetime(df["date"])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["평가금액"], name="평가금액",
        mode="lines", line=dict(color="#F5A623", width=2.5),
        fill="tozeroy", fillcolor="rgba(245, 166, 35, 0.08)",
        hovertemplate="%{x|%Y-%m-%d}<br>평가 %{y:,.0f}원<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["투자원금"], name="투자원금",
        mode="lines", line=dict(color="#94A3B8", width=1.5, dash="dot"),
        hovertemplate="%{x|%Y-%m-%d}<br>원가 %{y:,.0f}원<extra></extra>",
    ))
    fig.update_layout(**_plotly_layout(
        height=380, hovermode="x unified",
        yaxis=dict(gridcolor="#1F2531", tickformat=",.0f", ticksuffix=" 원"),
    ))
    st.plotly_chart(fig, use_container_width=True)

    latest = df.iloc[-1]
    first = df.iloc[0]
    delta_value = latest["평가금액"] - first["평가금액"]
    delta_pct = (delta_value / first["평가금액"] * 100) if first["평가금액"] > 0 else 0
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("기간 시작", f"{int(first['평가금액']):,} 원",
                  help=f"{first['date'].date()}")
    with c2:
        st.metric("현재", f"{int(latest['평가금액']):,} 원",
                  help=f"{latest['date'].date()}")
    with c3:
        st.metric("기간 변동", f"{int(delta_value):+,} 원",
                  delta=f"{delta_pct:+.2f}%")


def _dividend_monthly_chart() -> None:
    monthly = analytics.dividend_monthly()
    if not monthly:
        st.info("💡 분배금 데이터가 없습니다. '📦 종목 + 거래' → 분배금 탭에서 입력하세요.")
        return

    df = pd.DataFrame([
        {
            "month": m["month"],
            "세전": float(m["gross_krw"]),
            "세후": float(m["net_krw"]),
        }
        for m in monthly
    ])

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["month"], y=df["세전"], name="세전",
        marker_color="#F5A623", opacity=0.95,
        hovertemplate="%{x}<br>세전 %{y:,.0f}원<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=df["month"], y=df["세후"], name="세후 (실입금)",
        marker_color="#FF7A45", opacity=0.95,
        hovertemplate="%{x}<br>세후 %{y:,.0f}원<extra></extra>",
    ))
    fig.update_layout(**_plotly_layout(
        height=360, barmode="group",
        yaxis=dict(gridcolor="#1F2531", tickformat=",.0f", ticksuffix=" 원"),
    ))
    st.plotly_chart(fig, use_container_width=True)

    total_gross = df["세전"].sum()
    total_net = df["세후"].sum()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("누적 세전", f"{int(total_gross):,} 원")
    with c2:
        st.metric("누적 세후", f"{int(total_net):,} 원")
    with c3:
        diff = total_gross - total_net
        st.metric("원천징수 합계", f"{int(diff):,} 원")


def _share_donut(values: list[tuple[str, float]], title: str) -> None:
    if not values:
        st.caption("(데이터 없음)")
        return
    df = pd.DataFrame(values, columns=["label", "value"]).sort_values(
        "value", ascending=False
    )
    fig = go.Figure(data=[go.Pie(
        labels=df["label"],
        values=df["value"],
        hole=0.55,
        textinfo="label+percent",
        textposition="inside",
        marker=dict(
            colors=PALETTE * (len(df) // len(PALETTE) + 1),
            line=dict(color="#0F1218", width=2),
        ),
    )])
    fig.update_layout(**_plotly_layout(
        height=320, showlegend=False, margin=dict(l=0, r=0, t=30, b=0),
        title=dict(text=title, font=dict(size=14, color="#E6E9EF")),
    ))
    st.plotly_chart(fig, use_container_width=True)


def _allocation_panels() -> None:
    """통화별 / 카테고리별 / 계좌별 비중 도넛 3종."""
    holdings = db.list_holdings(active_only=True)
    states = analytics.load_states_from_db()
    price_cache = st.session_state.get("price_cache", {})
    fx_cache = st.session_state.get("fx_cache")

    valuations = []
    for h in holdings:
        key = (h["account_id"], h["ticker"])
        state = states.get(key) or analytics.PositionState(
            ticker=h["ticker"], account_id=h["account_id"], currency=h["currency"],
        )
        pr = price_cache.get((h["ticker"], h["currency"]))
        cur_price = pr.price if pr else None
        cur_fx = fx_cache.rate if (h["currency"] == "USD" and fx_cache) else None
        v = analytics.value_position(state, cur_price, cur_fx)
        valuations.append((v, h))

    if not any(v.market_value_krw for v, _ in valuations):
        st.info("💡 평가금액 데이터가 없어 비중 분석을 표시할 수 없습니다.")
        return

    by_currency: dict[str, float] = {}
    by_category: dict[str, float] = {}
    by_account: dict[str, float] = {}

    accounts = {a["account_id"]: a for a in db.list_accounts()}

    for v, h in valuations:
        if v.market_value_krw is None or v.market_value_krw <= 0:
            continue
        amount = float(v.market_value_krw)
        by_currency[v.currency] = by_currency.get(v.currency, 0) + amount

        cat_label = db.CATEGORIES.get(h["category"], h["category"])
        by_category[cat_label] = by_category.get(cat_label, 0) + amount

        acct = accounts.get(h["account_id"])
        acct_name = acct["name"] if acct else f"#{h['account_id']}"
        by_account[acct_name] = by_account.get(acct_name, 0) + amount

    c1, c2, c3 = st.columns(3)
    with c1:
        _share_donut(list(by_currency.items()), "💵 통화별")
    with c2:
        _share_donut(list(by_category.items()), "🗂 카테고리별")
    with c3:
        _share_donut(list(by_account.items()), "🏦 계좌별")


def render() -> None:
    st.header("📉 차트")
    st.caption("평가금액 추이 · 분배금 월별 · 비중 분석")

    has_holdings = bool(db.list_holdings(active_only=True))
    if not has_holdings:
        st.info(
            "💡 차트에 표시할 데이터가 없습니다. "
            "먼저 계좌·종목 등록 후 거래를 입력하세요."
        )
        return

    # 1. 평가금액 추이
    st.subheader("📈 평가금액 추이")
    period = st.radio(
        "기간",
        options=list(PERIOD_OPTIONS.keys()),
        horizontal=True,
        label_visibility="collapsed",
        key="chart_period",
    )
    _value_history_chart(period)

    st.divider()

    # 2. 분배금 월별
    st.subheader("💵 분배금 월별 추이")
    _dividend_monthly_chart()

    st.divider()

    # 3. 비중 분석 (3종 도넛)
    st.subheader("🥯 비중 분석")
    _allocation_panels()
