"""종목 관리 화면 - 추가/편집/비활성화/재활성화 (다중 계좌 지원)."""
from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from src import db, profile_config


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
                )
                currency = st.selectbox("통화", options=CURRENCY_OPTIONS)
                note = st.text_input("메모 (선택)")

            submitted = st.form_submit_button("저장", type="primary")
            if submitted:
                try:
                    db.add_holding(
                        ticker=ticker,
                        account_id=acct_id,
                        name=name,
                        category=category,
                        currency=currency,
                        note=note or None,
                    )
                    st.success(f"✅ {name} ({ticker}) 추가 완료")
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
            new_note = st.text_input(
                "메모", value=row["note"] or "", key=f"edit_note_{selected_key}"
            )

        with c2:
            currently_active = bool(row["is_active"])
            st.write("")
            st.write(f"계좌: {row['account_name']}")
            st.write(f"현재 상태: {'✅ 활성' if currently_active else '⏸ 비활성'}")

            b1, b2 = st.columns(2)
            with b1:
                if st.button("💾 저장", key=f"save_{selected_key}", type="primary"):
                    db.update_holding(
                        ticker=ticker,
                        account_id=account_id,
                        name=new_name,
                        category=new_category,
                        note=new_note,
                    )
                    st.success("저장됨")
                    st.rerun()
            with b2:
                if currently_active:
                    if st.button("⏸ 비활성화", key=f"deact_{selected_key}"):
                        db.set_holding_active(ticker, account_id, False)
                        st.rerun()
                else:
                    if st.button("✅ 재활성화", key=f"react_{selected_key}"):
                        db.set_holding_active(ticker, account_id, True)
                        st.rerun()


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

    c1, c2 = st.columns([2, 1])
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
        show_inactive = st.toggle("비활성 종목도 표시", value=False, key="hold_show_inactive")

    df = _holdings_dataframe(active_only=not show_inactive, account_id=filter_acct)

    if df.empty:
        st.info("등록된 종목이 없습니다. 아래 '새 종목 추가' 폼으로 시작하세요.")
    else:
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ticker": st.column_config.TextColumn("티커", width="small"),
                "name": st.column_config.TextColumn("종목명"),
                "account_name": st.column_config.TextColumn("계좌"),
                "category": st.column_config.TextColumn("카테고리"),
                "currency": st.column_config.TextColumn("통화", width="small"),
                "is_active": st.column_config.TextColumn("상태", width="small"),
                "added_at": st.column_config.DatetimeColumn("등록일", format="YYYY-MM-DD"),
                "note": st.column_config.TextColumn("메모"),
            },
        )

    st.divider()
    _add_form(accounts)
    _bulk_seed_form(accounts)
    _edit_panel()
