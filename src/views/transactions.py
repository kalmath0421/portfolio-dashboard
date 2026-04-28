"""거래 입력 화면 — 초기보유 / 매매 / 분배금 수동 입력 (증권사 무관 통일 폼)."""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from src import db, profile_config, tax
from src.views import holdings_admin


_TAX_RULES_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "tax_rules.yaml"


def _current_fiscal_year_label() -> str:
    """현재 사업연도 라벨 (예: '2026 사업연도 (2026-01-01 이후)')."""
    try:
        rules = tax.TaxRules.from_yaml(_TAX_RULES_PATH)
        fy = tax.fiscal_year_of(date.today(), rules.fiscal_year_end_month)
        start, _ = tax.fiscal_year_bounds(fy, rules.fiscal_year_end_month)
        return f"{fy} 사업연도 ({start.isoformat()} 이후)"
    except Exception:
        return f"{date.today().year} 사업연도"


def _account_options() -> list[sqlite3.Row]:
    return db.list_accounts(active_only=True)


def _holdings_for_account(account_id: int) -> list[sqlite3.Row]:
    return db.list_holdings(active_only=True, account_id=account_id)


def _suggested_fx_rate(trade_date: date) -> float | None:
    """해당 날짜의 USDKRW 스냅샷이 있으면 추천 환율로 사용."""
    iso = trade_date.isoformat()
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT usdkrw FROM fx_snapshots WHERE snapshot_date <= ? ORDER BY snapshot_date DESC LIMIT 1",
            (iso,),
        ).fetchone()
    return float(row["usdkrw"]) if row else None


def _combined_new_holding_form() -> None:
    """종목 마스터 + 초기 보유분(BUY 거래)을 한 화면에서 동시에 등록.

    매수 한 번으로 종목 마스터 + 첫 BUY 거래를 동시에 등록.
    이미 등록된 종목이면 통화 일치 시 거래만 추가.
    """
    accounts = _account_options()
    if not accounts:
        st.warning("활성 계좌가 없습니다. 먼저 '🏦 계좌 관리'에서 계좌를 추가하세요.")
        return

    st.subheader("🆕 새 종목 + 초기 보유분 동시 등록")
    st.caption(
        "신규 종목을 한 번에 등록 + 초기 보유분 입력. "
        "이미 등록된 종목이면 통화가 일치할 때만 거래가 추가됩니다."
    )

    # 계좌·카테고리는 폼 밖에서 선택 — 카테고리에 따라 통화가 결정되므로
    # USD 종목일 때만 환율 필드를 보이게 하기 위해 폼 진입 전에 결정.
    c_acct, c_cat = st.columns(2)
    with c_acct:
        acct_id = st.selectbox(
            "계좌",
            options=[a["account_id"] for a in accounts],
            format_func=lambda i: next(
                f"{a['name']} ({db.KINDS[a['kind']]})"
                for a in accounts if a["account_id"] == i
            ),
            key="combined_acct",
        )
    with c_cat:
        category = st.selectbox(
            "카테고리",
            options=list(db.CATEGORIES.keys()),
            format_func=lambda x: db.CATEGORIES[x],
            key="combined_category",
            help=(
                "카테고리에 따라 통화는 자동 결정 — 미국주식=USD, "
                "그 외(국내·국내상장 ETF·MMF성)=KRW. KRW 종목은 환율 입력란이 사라집니다."
            ),
        )
    currency = db.default_currency_for_category(category)
    st.caption(f"💱 자동 결정된 통화: **{currency}**")

    acct = next(a for a in accounts if a["account_id"] == acct_id)
    fee_rate = float(acct["default_fee_rate"] or 0)
    if fee_rate > 0:
        st.caption(
            f"💡 수수료 자동 계산 ON — 이 계좌 기본 매매 수수료율 "
            f"**{fee_rate:.4g}%**. 저장 시 `수량 × 단가 × {fee_rate:.4g}%"
            f"{' × 환율' if currency == 'USD' else ''}`로 "
            "자동 적용 (수수료 직접 입력 시 덮어씀)."
        )

    with st.form("combined_new_holding_form", clear_on_submit=True):
        # --- 종목 마스터 정보 ---
        st.markdown("**1. 종목 정보**")
        c1, c2 = st.columns(2)
        with c1:
            ticker = st.text_input(
                "티커 *",
                key="combined_ticker",
                help="자동으로 대문자로 변환되어 저장됩니다 (amzn → AMZN).",
            )
        with c2:
            name = st.text_input("종목명 *", key="combined_name")

        st.divider()

        # --- 초기 보유분 정보 ---
        st.markdown("**2. 초기 보유분**")
        # 통화별 단가 자릿수 — KRW 정수 / USD 2자리.
        price_format = "%.0f" if currency == "KRW" else "%.2f"
        price_step = 1.0 if currency == "KRW" else 0.01

        c4, c5, c6 = st.columns(3)
        with c4:
            quantity = st.number_input(
                "보유 수량 *", min_value=0.0, step=1.0, format="%.0f",
                key="combined_qty",
                help="소수점 매매한 USD 종목이면 직접 입력 (보통 정수).",
            )
        with c5:
            avg_price = st.number_input(
                f"평균 매입가 ({currency}) *",
                min_value=0.0, step=price_step, format=price_format,
                key="combined_price",
            )
        with c6:
            base_date_val = st.date_input(
                "기준일",
                value=date.today(),
                key="combined_date",
                help="단일 BUY 거래의 거래일자로 기록됩니다.",
            )

        # USD 일 때만 환율 입력란을 보여줌 — KRW 종목엔 의미 없음.
        if currency == "USD":
            c7, c8, c9 = st.columns(3)
            with c7:
                avg_fx = st.number_input(
                    "평균 매입 환율 (USDKRW) *",
                    min_value=0.0, step=1.0, format="%.2f",
                    key="combined_fx",
                    help="USD 거래의 매입 시점 평균 환율.",
                )
            with c8:
                fee_override = st.number_input(
                    "수수료 직접 입력 (선택, 원화)",
                    min_value=0.0, step=100.0, value=0.0, format="%.0f",
                    key="combined_fee",
                    help="0이면 계좌 기본 율로 자동 계산. 다른 값을 직접 넣으면 그 값으로 덮어씀.",
                )
            with c9:
                note = st.text_input(
                    "메모 (선택)", value="", key="combined_note",
                )
        else:
            avg_fx = None
            c8, c9 = st.columns(2)
            with c8:
                fee_override = st.number_input(
                    "수수료 직접 입력 (선택, 원화)",
                    min_value=0.0, step=100.0, value=0.0, format="%.0f",
                    key="combined_fee",
                    help="0이면 계좌 기본 율로 자동 계산. 다른 값을 직접 넣으면 그 값으로 덮어씀.",
                )
            with c9:
                note = st.text_input(
                    "메모 (선택)", value="", key="combined_note",
                )

        submitted = st.form_submit_button(
            "저장 (종목 등록 + 거래 추가)", type="primary"
        )
        if submitted:
            # 검증
            if not ticker.strip() or not name.strip():
                st.error("티커와 종목명은 필수입니다.")
                return
            if quantity <= 0 or avg_price <= 0:
                st.error("수량과 평균단가는 0보다 커야 합니다.")
                return
            if currency == "USD" and (avg_fx is None or avg_fx <= 0):
                st.error("USD 종목은 평균 매입 환율이 필수입니다.")
                return

            # 수수료: 직접입력 > 자동계산
            if fee_override > 0:
                final_fee = float(fee_override)
                fee_msg = f"수수료 {final_fee:,.0f}원 (직접 입력)"
            else:
                final_fee = db.compute_auto_fee(
                    quantity=quantity,
                    price=avg_price,
                    fee_rate_pct=fee_rate,
                    currency=currency,
                    fx_rate=avg_fx if currency == "USD" else None,
                )
                fee_msg = (
                    f"수수료 {final_fee:,.0f}원 (자동: {fee_rate:.4g}%)"
                    if final_fee > 0
                    else "수수료 0원"
                )

            try:
                created, tx_id = db.add_holding_with_initial_position(
                    account_id=acct_id,
                    ticker=ticker,
                    name=name,
                    category=category,
                    currency=currency,
                    quantity=quantity,
                    avg_price=avg_price,
                    avg_fx_rate=avg_fx if currency == "USD" else None,
                    base_date=base_date_val.isoformat(),
                    note=note or None,
                    fee=final_fee,
                )
                if created:
                    st.success(
                        f"✅ 종목 {ticker.upper()} 등록 + 초기 보유분 거래 #{tx_id} 추가 — {fee_msg}"
                    )
                else:
                    st.success(
                        f"✅ 기존 종목 {ticker.upper()} 에 거래 #{tx_id} 추가 (마스터는 그대로) — {fee_msg}"
                    )
                st.rerun()
            except sqlite3.IntegrityError:
                st.error(
                    "❌ 같은 (날짜, 계좌, 티커, BUY, 수량, 단가) 조합이 이미 있습니다. "
                    "이미 등록했거나, 기준일을 다른 날짜로 변경해 주세요."
                )
            except ValueError as e:
                st.error(f"❌ {e}")


def _trade_form() -> None:
    accounts = _account_options()
    if not accounts:
        st.warning("활성 계좌가 없습니다. 먼저 '🏦 계좌 관리'에서 계좌를 추가하세요.")
        return

    st.subheader("➕ 매매 거래 입력")
    st.caption(
        "매수·매도 시점에 한 줄씩 입력하면 평균단가·실현손익이 자동 누적됩니다."
    )

    # 계좌 선택은 form 밖에서 (티커 목록 동적 변경 위해)
    acct_id = st.selectbox(
        "계좌",
        options=[a["account_id"] for a in accounts],
        format_func=lambda i: next(
            f"{a['name']} ({db.KINDS[a['kind']]})"
            for a in accounts if a["account_id"] == i
        ),
        key="tx_acct",
    )

    holdings = _holdings_for_account(acct_id)
    if not holdings:
        st.warning(
            "이 계좌에 등록된 종목이 없습니다. 위 '🆕 새 종목 첫 매수' 탭에서 "
            "첫 매수를 입력하면 종목이 자동으로 등록됩니다."
        )
        return

    # 종목 선택을 폼 밖으로 — 통화에 따라 number_input 자릿수를 다르게 주려면
    # 폼 진입 전에 currency 가 결정되어야 함 (form 안 widget 은 동적 재렌더 X).
    ticker = st.selectbox(
        "종목",
        options=[h["ticker"] for h in holdings],
        format_func=lambda t: next(
            f"{t} — {h['name']}" for h in holdings if h["ticker"] == t
        ),
        key="tx_ticker",
    )
    ticker_currency = next(h["currency"] for h in holdings if h["ticker"] == ticker)

    # 계좌 기본 수수료율 — 매번 거래 입력 시 fee 자동 계산에 사용.
    acct = next(a for a in accounts if a["account_id"] == acct_id)
    fee_rate = float(acct["default_fee_rate"] or 0)
    if fee_rate > 0:
        st.caption(
            f"💡 수수료 자동 계산 ON — 이 계좌 기본 매매 수수료율 "
            f"**{fee_rate:.4g}%**. 거래 저장 시 `수량 × 단가 × {fee_rate:.4g}%"
            f"{' × 환율' if ticker_currency == 'USD' else ''}`로 자동 적용 "
            "(수수료 직접 입력 시 덮어씀)."
        )
    else:
        st.caption(
            "💡 이 계좌 수수료율이 0% 입니다. '🏦 계좌 관리' 에서 기본 율을 "
            "설정하면 거래마다 자동 계산됩니다."
        )

    # 통화별 number_input 포맷 — KRW 정수 / USD 2자리.
    price_format = "%.0f" if ticker_currency == "KRW" else "%.2f"
    price_step = 1.0 if ticker_currency == "KRW" else 0.01

    with st.form("trade_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            trade_date_val = st.date_input("거래일", value=date.today())
            side = st.radio(
                "구분", options=["BUY", "SELL"],
                format_func=lambda s: "매수" if s == "BUY" else "매도",
                horizontal=True,
            )
        with c2:
            quantity = st.number_input(
                "수량", min_value=0.0, step=1.0, format="%.0f",
                help="소수점 매매를 한 경우만 직접 수정 (보통 정수).",
            )
            price = st.number_input(
                f"단가 ({ticker_currency})",
                min_value=0.0, step=price_step, format=price_format,
            )
        with c3:
            if ticker_currency == "USD":
                suggested = _suggested_fx_rate(trade_date_val)
                fx_rate = st.number_input(
                    "거래 시점 환율 (USDKRW) *",
                    min_value=0.0, step=1.0,
                    value=float(suggested) if suggested else 0.0,
                    format="%.2f",
                    help="해당 일자의 매매기준율 등을 입력. 시세 갱신 후 자동 추천값이 채워짐.",
                )
            else:
                fx_rate = None
            fee_override = st.number_input(
                "수수료 직접 입력 (선택, 원화)",
                min_value=0.0, step=100.0, value=0.0, format="%.0f",
                help="0이면 계좌 기본 율로 자동 계산. 다른 값을 직접 넣으면 그 값으로 덮어씀.",
            )

        note = st.text_input("메모 (선택)")
        st.caption(f"통화: **{ticker_currency}**")

        submitted = st.form_submit_button("저장", type="primary")
        if submitted:
            # 수수료 결정: 사용자가 직접 입력한 값(>0)이 있으면 그대로,
            # 0 이면 계좌 기본 율로 자동 계산.
            if fee_override > 0:
                final_fee = float(fee_override)
                fee_msg = f"수수료 {final_fee:,.0f}원 (직접 입력)"
            else:
                final_fee = db.compute_auto_fee(
                    quantity=quantity,
                    price=price,
                    fee_rate_pct=fee_rate,
                    currency=ticker_currency,
                    fx_rate=fx_rate,
                )
                fee_msg = (
                    f"수수료 {final_fee:,.0f}원 (자동: {fee_rate:.4g}%)"
                    if final_fee > 0
                    else "수수료 0원 (계좌 기본 율 0% 또는 USD 환율 미입력)"
                )
            try:
                tx_id = db.add_transaction(
                    trade_date=trade_date_val.isoformat(),
                    account_id=acct_id,
                    ticker=ticker,
                    side=side,
                    quantity=quantity,
                    price=price,
                    currency=ticker_currency,
                    fx_rate=fx_rate if ticker_currency == "USD" else None,
                    fee=final_fee,
                    note=note or None,
                )
                st.success(f"✅ 거래 등록 (#{tx_id}) — {fee_msg}")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error(
                    "❌ 같은 (날짜, 계좌, 티커, 구분, 수량, 단가) 조합이 이미 있습니다."
                )
            except ValueError as e:
                st.error(f"❌ {e}")


def _dividend_form() -> None:
    accounts = _account_options()
    if not accounts:
        return

    st.subheader("💵 분배금/배당금 입력")
    if profile_config.is_personal():
        st.caption(
            "분배금이 입금되면 한 줄씩 입력. 세전·원천징수·입금액을 함께 기록."
        )
    else:
        st.caption(
            "분배금이 입금되면 한 줄씩 입력. 세전·원천징수·입금액을 함께 기록해 "
            "법인세 신고 시 외국납부세액 공제에 활용."
        )
    st.info(
        f"💡 **{_current_fiscal_year_label()} 분배금만 입력**하시면 됩니다. "
        "작년 이전 분배금은 이미 결산 완료된 영역이라 입력 불필요."
    )

    acct_id = st.selectbox(
        "계좌",
        options=[a["account_id"] for a in accounts],
        format_func=lambda i: next(
            f"{a['name']} ({db.KINDS[a['kind']]})"
            for a in accounts if a["account_id"] == i
        ),
        key="div_acct",
    )

    holdings = _holdings_for_account(acct_id)
    if not holdings:
        st.warning("이 계좌에 등록된 종목이 없습니다.")
        return

    with st.form("dividend_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            pay_date_val = st.date_input("지급일", value=date.today(), key="div_date")
            ticker = st.selectbox(
                "종목",
                options=[h["ticker"] for h in holdings],
                format_func=lambda t: next(
                    f"{t} — {h['name']}" for h in holdings if h["ticker"] == t
                ),
                key="div_ticker",
            )
        with c2:
            gross = st.number_input(
                "세전 금액 (현지통화)", min_value=0.0, step=1.0, format="%.4f"
            )
            withholding = st.number_input(
                "원천징수 (현지통화)", min_value=0.0, step=1.0, format="%.4f",
                help="미국 배당의 경우 보통 15%",
            )
        with c3:
            net = st.number_input(
                "실입금액 (현지통화) — 세후",
                min_value=0.0, step=1.0, format="%.4f",
            )
            ticker_currency = next(
                h["currency"] for h in holdings if h["ticker"] == ticker
            )
            fx_rate = None
            if ticker_currency == "USD":
                suggested = _suggested_fx_rate(pay_date_val)
                fx_rate = st.number_input(
                    "환율 (USDKRW)",
                    min_value=0.0, step=1.0,
                    value=float(suggested) if suggested else 0.0,
                    key="div_fx",
                )

        note = st.text_input("메모 (선택)", key="div_note")
        st.caption(f"통화: **{ticker_currency}**")

        submitted = st.form_submit_button("저장", type="primary")
        if submitted:
            try:
                div_id = db.add_dividend(
                    pay_date=pay_date_val.isoformat(),
                    account_id=acct_id,
                    ticker=ticker,
                    gross_amount=gross,
                    net_amount=net,
                    currency=ticker_currency,
                    withholding_tax=withholding,
                    fx_rate=fx_rate if ticker_currency == "USD" else None,
                    note=note or None,
                )
                st.success(f"✅ 분배금 등록 (#{div_id})")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("❌ 동일 항목이 이미 있습니다.")
            except ValueError as e:
                st.error(f"❌ {e}")


def _recent_transactions_panel(key_prefix: str = "") -> None:
    st.subheader("📋 최근 매매 거래 (최대 50건)")
    rows = db.list_transactions(limit=50)
    if not rows:
        st.info("아직 입력된 거래가 없습니다.")
        return
    df = pd.DataFrame([dict(r) for r in rows])
    df = df[[
        "id", "trade_date", "account_name", "ticker", "ticker_name",
        "side", "quantity", "price", "currency", "fx_rate", "fee", "note",
    ]]
    df["side"] = df["side"].map({"BUY": "🟢 매수", "SELL": "🔴 매도"})
    st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("🗑 거래 삭제 (잘못 입력했을 때)"):
        del_id = st.number_input("삭제할 거래 ID", min_value=0, step=1, key=f"del_tx_id_{key_prefix}")
        confirm = st.checkbox("정말 삭제", key=f"del_tx_confirm_{key_prefix}")
        if confirm and st.button("삭제 실행", key=f"del_tx_btn_{key_prefix}") and del_id > 0:
            db.delete_transaction(int(del_id))
            st.success(f"거래 #{del_id} 삭제됨")
            st.rerun()


def _recent_dividends_panel() -> None:
    st.subheader("📋 최근 분배금 (최대 50건)")
    rows = db.list_dividends(limit=50)
    if not rows:
        st.info("아직 입력된 분배금이 없습니다.")
        return
    df = pd.DataFrame([dict(r) for r in rows])
    df = df[[
        "id", "pay_date", "account_name", "ticker", "ticker_name",
        "gross_amount", "withholding_tax", "net_amount", "currency",
        "fx_rate", "gross_krw", "net_krw", "note",
    ]]
    st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("🗑 분배금 삭제"):
        del_id = st.number_input("삭제할 분배금 ID", min_value=0, step=1, key="del_div_id")
        confirm = st.checkbox("정말 삭제", key="del_div_confirm")
        if confirm and st.button("삭제 실행", key="del_div_btn") and del_id > 0:
            db.delete_dividend(int(del_id))
            st.success(f"분배금 #{del_id} 삭제됨")
            st.rerun()


def render() -> None:
    st.header("📦 종목 + 거래")
    st.caption(
        "거래 입력과 보유 종목 관리를 한 페이지에서. "
        "새 종목을 매수하면 자동으로 보유 종목 목록에 추가됩니다."
    )

    tab_trade, tab_combined, tab_div = st.tabs([
        "💱 기존 종목 매매",
        "🆕 새 종목 첫 매수",
        "💵 분배금/배당금",
    ])
    with tab_trade:
        _trade_form()
        st.divider()
        _recent_transactions_panel(key_prefix="trade")
    with tab_combined:
        _combined_new_holding_form()
        st.divider()
        _recent_transactions_panel(key_prefix="combined")
    with tab_div:
        _dividend_form()
        st.divider()
        _recent_dividends_panel()

    # --- 종목 마스터 (보유 종목 표 + 추가/편집/일괄 등록) ---
    st.divider()
    st.subheader("📋 보유 종목")
    st.caption(
        "보유 종목 마스터 — 위 탭에서 매수하면 자동으로 추가됩니다. "
        "이 패널에서는 직접 종목을 추가하거나 편집·비활성화할 수도 있습니다."
    )
    holdings_admin.render_inline()
