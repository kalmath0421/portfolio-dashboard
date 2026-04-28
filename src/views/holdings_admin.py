"""종목 관리 화면 - 추가/편집/비활성화/재활성화 (다중 계좌 지원)."""
from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from src import analytics, db, prices, profile_config


CATEGORY_OPTIONS = list(db.CATEGORIES.keys())
CURRENCY_OPTIONS = ["KRW", "USD"]


def _holdings_dataframe(
    active_only: bool, account_id: int | None
) -> pd.DataFrame:
    rows = db.list_holdings(active_only=active_only, account_id=account_id)
    if not rows:
        return pd.DataFrame(
            columns=[
                "ticker", "name", "account_name", "category", "currency",
                "is_active", "added_at", "note",
            ]
        )
    df = pd.DataFrame([dict(r) for r in rows])
    df["category"] = df["category"].map(db.CATEGORIES).fillna(df["category"])
    df["is_active"] = df["is_active"].map({1: "✅ 활성", 0: "⏸ 비활성"})
    return df[["ticker", "name", "account_name", "category", "currency",
               "is_active", "added_at", "note"]]


def _valued_holdings_dataframe(
    active_only: bool,
    account_id: int | None,
    show_zero_qty: bool,
) -> tuple[pd.DataFrame, int]:
    """보유 종목 + 라이브 가치(보유수량/현재가/평가금액/수익률) 결합 표.

    Args:
        active_only: 비활성 종목 제외 여부
        account_id: 특정 계좌 필터 (None=전체)
        show_zero_qty: 보유수량 0 종목도 포함할지 (False면 매도 완료 종목 숨김)

    Returns: (DataFrame, 0주로 인해 숨겨진 row 개수)
    """
    holdings = db.list_holdings(active_only=active_only, account_id=account_id)
    if not holdings:
        return pd.DataFrame(), 0

    states = analytics.load_states_from_db(account_id=account_id)

    # summary 와 같은 캐시 키 — 한 세션 내에서 재사용해 라이브 호출 비용 절감
    if not st.session_state.get("price_cache"):
        st.session_state["price_cache"] = prices.load_cached_prices(holdings)
    if st.session_state.get("fx_cache") is None:
        st.session_state["fx_cache"] = prices.load_cached_fx()
    price_cache = st.session_state["price_cache"]
    fx_cache = st.session_state["fx_cache"]

    rows: list[dict] = []
    hidden_zero = 0
    for h in holdings:
        key = (h["account_id"], h["ticker"])
        state = states.get(key) or analytics.PositionState(
            ticker=h["ticker"],
            account_id=h["account_id"],
            currency=h["currency"],
        )

        # 매도로 0주가 된 종목은 기본적으로 숨김 — 마스터는 DB 에 그대로 남음
        if state.quantity <= 0 and not show_zero_qty:
            hidden_zero += 1
            continue

        pr = price_cache.get((h["ticker"], h["currency"]))
        cur_price = pr.price if pr else None
        is_stale = pr.is_stale if pr else False
        cur_fx = fx_cache.rate if (h["currency"] == "USD" and fx_cache) else None
        v = analytics.value_position(
            state, cur_price, cur_fx, is_price_stale=is_stale
        )

        if cur_price is None:
            price_status = "—"
        elif is_stale:
            price_status = "⚠️ 갱신필요"
        else:
            price_status = "🟢"

        rows.append({
            "티커": h["ticker"],
            "종목명": h["name"],
            "계좌": h["account_name"],
            "통화": h["currency"],
            "보유수량": float(state.quantity) if state.quantity > 0 else 0.0,
            "평균단가": (
                float(state.avg_cost_local)
                if state.quantity > 0 else None
            ),
            "현재가": float(cur_price) if cur_price is not None else None,
            "평가금액(₩)": (
                float(v.market_value_krw)
                if v.market_value_krw is not None else None
            ),
            "미실현손익(₩)": (
                float(v.unrealized_pnl_krw)
                if v.unrealized_pnl_krw is not None else None
            ),
            "수익률(%)": (
                float(v.return_pct_krw)
                if v.return_pct_krw is not None else None
            ),
            "상태": "✅" if h["is_active"] else "⏸",
            "시세": price_status,
        })

    # 평가금액 큰 순으로 정렬 (None 은 뒤로)
    rows.sort(
        key=lambda r: (
            r["평가금액(₩)"] if r["평가금액(₩)"] is not None else -1
        ),
        reverse=True,
    )
    df = pd.DataFrame(rows)
    return df, hidden_zero


def _money_market_ticker_prompt(corp_accounts: list[sqlite3.Row]) -> None:
    """KODEX CD금리액티브 정확한 티커를 묻는 폼."""
    if not corp_accounts:
        st.error("법인 계좌가 없습니다. 먼저 '🏦 계좌 관리'에서 법인 계좌를 추가하세요.")
        return

    st.warning(
        "**KODEX CD금리액티브** 종목이 아직 등록되지 않았습니다.\n\n"
        "정확한 6자리 티커를 입력해 주세요. "
        "(한국거래소 또는 IBK WINGS 화면에서 확인 가능)"
    )
    with st.form("mm_etf_form", clear_on_submit=False):
        c1, c2, c3 = st.columns([1, 2, 2])
        with c1:
            ticker = st.text_input("티커 (6자리)", max_chars=6, key="mm_etf_ticker")
        with c2:
            name = st.text_input("종목명", value="KODEX CD금리액티브", key="mm_etf_name")
        with c3:
            acct_id = st.selectbox(
                "등록할 계좌",
                options=[a["account_id"] for a in corp_accounts],
                format_func=lambda i: next(
                    a["name"] for a in corp_accounts if a["account_id"] == i
                ),
                key="mm_etf_account",
            )
        submitted = st.form_submit_button("등록", type="primary")
        if submitted:
            if not ticker or not ticker.strip().isdigit() or len(ticker.strip()) != 6:
                st.error("티커는 6자리 숫자여야 합니다.")
                return
            try:
                db.add_holding(
                    ticker=ticker.strip(),
                    account_id=acct_id,
                    name=name,
                    category="money_market_etf",
                    currency="KRW",
                    note="첫 실행 시 사용자 입력",
                )
                st.success(f"✅ {name} ({ticker}) 등록 완료")
                st.rerun()
            except sqlite3.IntegrityError as e:
                st.error(f"등록 실패 (중복?): {e}")


def _add_form(accounts: list[sqlite3.Row]) -> None:
    if not accounts:
        st.warning("등록된 계좌가 없습니다. '🏦 계좌 관리'에서 먼저 계좌를 추가하세요.")
        return

    with st.expander("➕ 새 종목 추가", expanded=False):
        with st.form("add_holding_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                ticker = st.text_input(
                    "티커",
                    help="국내: 6자리 숫자(예: 005930), 미국: 알파벳(예: NVDA)",
                )
                name = st.text_input("종목명")
                acct_id = st.selectbox(
                    "계좌",
                    options=[a["account_id"] for a in accounts],
                    format_func=lambda i: next(
                        f"{a['name']} ({db.KINDS[a['kind']]})"
                        for a in accounts if a["account_id"] == i
                    ),
                )
            with c2:
                category = st.selectbox(
                    "카테고리",
                    options=CATEGORY_OPTIONS,
                    format_func=lambda x: db.CATEGORIES[x],
                    help=(
                        "카테고리에 따라 통화는 자동 결정됩니다 — "
                        "미국주식=USD, 그 외(국내·국내상장 ETF·MMF성)=KRW"
                    ),
                )
                # 통화는 카테고리에서 자동 도출. UI에 표시만 (read-only).
                derived_currency = db.default_currency_for_category(category)
                st.text_input(
                    "통화 (자동 결정)",
                    value=derived_currency,
                    disabled=True,
                    help="카테고리에 따라 자동 결정됨",
                )
                note = st.text_input("메모 (선택)")

            submitted = st.form_submit_button("저장", type="primary")
            if submitted:
                try:
                    db.add_holding(
                        ticker=ticker,
                        account_id=acct_id,
                        name=name,
                        category=category,
                        # currency 생략 → 카테고리에서 자동 도출
                        note=note or None,
                    )
                    st.success(f"✅ {name} ({ticker}) 추가 완료 ({derived_currency})")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"❌ 같은 계좌에 이미 등록된 티커: {ticker}")
                except ValueError as e:
                    st.error(f"❌ {e}")


def _edit_panel() -> None:
    rows = db.list_holdings(active_only=False)
    if not rows:
        return

    with st.expander("✏️ 종목 편집 / 활성·비활성 토글", expanded=False):
        key_to_row = {f"{r['account_id']}::{r['ticker']}": r for r in rows}
        selected_key = st.selectbox(
            "편집할 종목 선택",
            options=list(key_to_row.keys()),
            format_func=lambda k: (
                f"{key_to_row[k]['ticker']} — {key_to_row[k]['name']} "
                f"@ {key_to_row[k]['account_name']}"
            ),
            key="edit_holding_select",
        )
        if not selected_key:
            return
        row = key_to_row[selected_key]
        ticker = row["ticker"]
        account_id = row["account_id"]

        has_data = db.holding_has_data(ticker, account_id)

        c1, c2 = st.columns(2)
        with c1:
            new_name = st.text_input("종목명", value=row["name"], key=f"edit_name_{selected_key}")
            new_category = st.selectbox(
                "카테고리",
                options=CATEGORY_OPTIONS,
                index=CATEGORY_OPTIONS.index(row["category"])
                if row["category"] in CATEGORY_OPTIONS else 0,
                format_func=lambda x: db.CATEGORIES[x],
                key=f"edit_cat_{selected_key}",
            )
            # 통화 — 종속 데이터가 없을 때만 변경 허용
            cur_index = (
                CURRENCY_OPTIONS.index(row["currency"])
                if row["currency"] in CURRENCY_OPTIONS else 0
            )
            new_currency = st.selectbox(
                "통화",
                options=CURRENCY_OPTIONS,
                index=cur_index,
                disabled=has_data,
                key=f"edit_cur_{selected_key}",
                help=(
                    "거래/배당/잔고 스냅샷이 있는 종목은 통화를 바꿀 수 없습니다. "
                    "종속 데이터를 먼저 삭제하세요."
                    if has_data
                    else "USD ↔ KRW 변경 가능. 가격 단위가 달라지므로 종속 데이터 없을 때만 허용."
                ),
            )
            new_note = st.text_input(
                "메모", value=row["note"] or "", key=f"edit_note_{selected_key}"
            )

        with c2:
            currently_active = bool(row["is_active"])
            st.write("")
            st.write(f"계좌: {row['account_name']}")
            st.write(f"현재 상태: {'✅ 활성' if currently_active else '⏸ 비활성'}")
            st.write(
                f"종속 데이터: {'있음 (삭제 불가)' if has_data else '없음 (삭제 가능)'}"
            )

            b1, b2 = st.columns(2)
            with b1:
                if st.button("💾 저장", key=f"save_{selected_key}", type="primary"):
                    try:
                        db.update_holding(
                            ticker=ticker,
                            account_id=account_id,
                            name=new_name,
                            category=new_category,
                            currency=new_currency,
                            note=new_note,
                        )
                        st.success("저장됨")
                        st.rerun()
                    except ValueError as e:
                        st.error(f"❌ {e}")
            with b2:
                if currently_active:
                    if st.button("⏸ 비활성화", key=f"deact_{selected_key}"):
                        db.set_holding_active(ticker, account_id, False)
                        st.rerun()
                else:
                    if st.button("✅ 재활성화", key=f"react_{selected_key}"):
                        db.set_holding_active(ticker, account_id, True)
                        st.rerun()

            if not has_data:
                st.divider()
                st.caption(
                    "⚠️ 영구 삭제는 되돌릴 수 없습니다. 종속 데이터가 없을 때만 가능."
                )
                confirm_del = st.checkbox(
                    "영구 삭제 확인", key=f"del_holding_confirm_{selected_key}"
                )
                if confirm_del and st.button(
                    "🗑 영구 삭제",
                    key=f"del_holding_btn_{selected_key}",
                    type="secondary",
                ):
                    try:
                        db.delete_holding(ticker, account_id)
                        st.success(f"종목 {ticker} 삭제됨")
                        st.rerun()
                    except ValueError as e:
                        st.error(f"❌ {e}")


def _bulk_seed_form(accounts: list[sqlite3.Row]) -> None:
    """선택한 계좌에 명세서 기본 종목을 일괄 등록."""
    if not accounts:
        return
    with st.expander("💡 명세서 기본 종목을 특정 계좌에 일괄 등록", expanded=False):
        if profile_config.is_personal():
            st.caption(
                "NVDA·MSFT·TSLA·AMZN·GOOGL·XLU·QQQJ·SPYM(미국) + "
                "삼성전자·우리금융지주·SK스퀘어(국내). "
                "이미 등록된 티커는 건너뜁니다."
            )
        else:
            st.caption(
                "법인 계좌: TIGER 코리아TOP10 외 4종 ETF · "
                "개인 계좌: NVDA·MSFT·TSLA·AMZN·GOOGL·XLU·QQQJ·SPYM(미국) + 삼성전자·우리금융지주·SK스퀘어(국내). "
                "이미 등록된 티커는 건너뜁니다."
            )
        with st.form("bulk_seed_form", clear_on_submit=False):
            c1, c2 = st.columns([3, 1])
            with c1:
                acct_id = st.selectbox(
                    "대상 계좌",
                    options=[a["account_id"] for a in accounts],
                    format_func=lambda i: next(
                        f"{a['name']} ({db.KINDS[a['kind']]})"
                        for a in accounts if a["account_id"] == i
                    ),
                )
            with c2:
                st.write("")
                submitted = st.form_submit_button("일괄 등록", type="primary")
            if submitted and acct_id:
                added = db.add_default_holdings_to_account(acct_id)
                if added > 0:
                    st.success(f"✅ {added}개 종목 등록 완료")
                else:
                    st.info("이미 모든 기본 종목이 이 계좌에 등록되어 있습니다.")
                st.rerun()


def render() -> None:
    st.header("⚙️ 종목 관리")
    st.caption(
        "보유 종목 마스터 — UI에서 추가/편집/비활성화. "
        "비활성화된 종목도 과거 거래 기록은 보존됩니다. "
        "동일 티커를 여러 계좌에 등록할 수 있습니다."
    )
    render_inline()


def render_inline() -> None:
    """헤더 없이 종목 목록 + 추가/편집 panel 만 렌더 — 다른 페이지 하단 임베드용."""
    accounts = db.list_accounts(active_only=True)

    if not accounts:
        if profile_config.is_personal():
            st.warning(
                "👋 활성 계좌가 없습니다. 먼저 사이드바 **🏦 계좌 관리** 메뉴에서 "
                "계좌를 추가하세요. 계좌명은 자유롭게 정할 수 있습니다."
            )
        else:
            st.warning(
                "👋 활성 계좌가 없습니다. 먼저 사이드바 **🏦 계좌 관리** 메뉴에서 "
                "법인/개인 계좌를 추가하세요. 계좌명은 자유롭게 정할 수 있습니다."
            )
        return

    corp_accounts = [a for a in accounts if a["kind"] == db.KIND_CORP]

    if corp_accounts and not db.has_money_market_etf():
        _money_market_ticker_prompt(corp_accounts)
        st.divider()

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        all_accounts = db.list_accounts(active_only=False)
        filter_options = [None] + [a["account_id"] for a in all_accounts]
        filter_acct = st.selectbox(
            "계좌 필터",
            options=filter_options,
            format_func=lambda i: "전체 계좌"
            if i is None
            else next(a["name"] for a in all_accounts if a["account_id"] == i),
            key="hold_filter_acct",
        )
    with c2:
        show_inactive = st.toggle(
            "비활성 종목 표시", value=False, key="hold_show_inactive"
        )
    with c3:
        show_zero_qty = st.toggle(
            "0주 종목 표시",
            value=False,
            key="hold_show_zero_qty",
            help=(
                "전량 매도되어 0주가 된 종목은 기본적으로 숨겨집니다. "
                "켜면 거래 이력 보존 차원에서 함께 표시 (마스터는 DB 에 항상 남아 있음)."
            ),
        )

    df, hidden_zero = _valued_holdings_dataframe(
        active_only=not show_inactive,
        account_id=filter_acct,
        show_zero_qty=show_zero_qty,
    )

    if df.empty:
        if hidden_zero > 0:
            st.info(
                f"전량 매도된 종목 {hidden_zero}개가 숨겨져 있습니다. "
                "위 '0주 종목 표시' 토글을 켜면 보입니다."
            )
        else:
            st.info("등록된 종목이 없습니다. 아래 '새 종목 추가' 폼으로 시작하세요.")
    else:
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "티커": st.column_config.TextColumn("티커", width="small"),
                "종목명": st.column_config.TextColumn("종목명"),
                "계좌": st.column_config.TextColumn("계좌"),
                "통화": st.column_config.TextColumn("통화", width="small"),
                "보유수량": st.column_config.NumberColumn("보유수량", format="%.4f"),
                "평균단가": st.column_config.NumberColumn("평균단가", format="%.2f"),
                "현재가": st.column_config.NumberColumn("현재가", format="%.2f"),
                "평가금액(₩)": st.column_config.NumberColumn("평가금액(₩)", format="%,.0f"),
                "미실현손익(₩)": st.column_config.NumberColumn("미실현손익(₩)", format="%,.0f"),
                "수익률(%)": st.column_config.NumberColumn("수익률(%)", format="%+.2f"),
                "상태": st.column_config.TextColumn("상태", width="small"),
                "시세": st.column_config.TextColumn("시세", width="small"),
            },
        )
        if hidden_zero > 0:
            st.caption(f"💡 전량 매도된 종목 {hidden_zero}개 숨김.")
        st.caption(
            "수익률은 원화 기준 (USD 종목은 매수환율 vs 현재환율 차이도 반영). "
            "현재가가 비어 있으면 사이드바의 시세 갱신 버튼을 눌러 주세요."
        )

    st.divider()
    _add_form(accounts)
    _bulk_seed_form(accounts)
    _edit_panel()
