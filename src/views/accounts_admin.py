"""계좌 관리 화면 - 추가/편집/비활성화/삭제."""
from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from src import db


KIND_OPTIONS = list(db.KINDS.keys())


def _accounts_dataframe(active_only: bool) -> pd.DataFrame:
    rows = db.list_accounts(active_only=active_only)
    if not rows:
        return pd.DataFrame(
            columns=["account_id", "name", "broker", "kind", "is_active", "added_at", "note"]
        )
    df = pd.DataFrame([dict(r) for r in rows])
    df["kind"] = df["kind"].map(db.KINDS).fillna(df["kind"])
    df["is_active"] = df["is_active"].map({1: "✅ 활성", 0: "⏸ 비활성"})
    return df


def _add_form(expanded_default: bool = False) -> None:
    with st.expander("➕ 새 계좌 추가", expanded=expanded_default):
        with st.form("add_account_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input(
                    "계좌 표시명 *",
                    help='자유롭게 짓기. 예: "IBK WINGS 법인 #1", "키움 개인", "한투 ISA"',
                )
                broker = st.text_input(
                    "증권사 *",
                    help='예: "IBK WINGS", "농협 나무", "한국투자증권", "키움증권"',
                )
            with c2:
                kind = st.selectbox(
                    "계좌 종류 *",
                    options=KIND_OPTIONS,
                    format_func=lambda x: db.KINDS[x],
                    help="법인 유보금 계좌인지 개인 계좌인지 선택. 세금 계산에 영향.",
                )
                note = st.text_input("메모 (선택)")

            seed_default = st.checkbox(
                "💡 명세서 기본 종목을 이 계좌에 일괄 등록",
                value=False,
                help=(
                    "법인 선택 시: TIGER 코리아TOP10·미국배당다우존스·미국나스닥100 커버드콜 등 5종 (CD금리액티브는 별도 입력)\n"
                    "개인 선택 시: NVDA, MSFT, TSLA, AMZN, GOOGL, XLU, QQQJ, SPYM (미국) + 삼성전자, 우리금융지주, SK스퀘어 (국내)"
                ),
            )

            submitted = st.form_submit_button("저장", type="primary")
            if submitted:
                try:
                    new_id = db.add_account(name=name, broker=broker, kind=kind, note=note or None)
                    msg = f"✅ 계좌 추가 완료: {name}"
                    if seed_default:
                        added = db.add_default_holdings_to_account(new_id)
                        msg += f" / 기본 종목 {added}개 일괄 등록"
                    st.success(msg)
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("❌ 이미 존재하는 계좌 표시명입니다. 다른 이름을 사용하세요.")
                except ValueError as e:
                    st.error(f"❌ {e}")


def _edit_panel() -> None:
    rows = db.list_accounts(active_only=False)
    if not rows:
        return

    with st.expander("✏️ 계좌 편집 / 활성·비활성 / 삭제", expanded=False):
        id_to_row = {r["account_id"]: r for r in rows}
        selected_id = st.selectbox(
            "편집할 계좌 선택",
            options=list(id_to_row.keys()),
            format_func=lambda i: f"[{i}] {id_to_row[i]['name']}",
            key="edit_account_select",
        )
        if not selected_id:
            return
        row = id_to_row[selected_id]

        c1, c2 = st.columns(2)
        with c1:
            new_name = st.text_input(
                "계좌 표시명", value=row["name"], key=f"edit_acct_name_{selected_id}"
            )
            new_broker = st.text_input(
                "증권사", value=row["broker"], key=f"edit_acct_broker_{selected_id}"
            )
            new_kind = st.selectbox(
                "계좌 종류",
                options=KIND_OPTIONS,
                index=KIND_OPTIONS.index(row["kind"]),
                format_func=lambda x: db.KINDS[x],
                key=f"edit_acct_kind_{selected_id}",
            )
            new_note = st.text_input(
                "메모", value=row["note"] or "", key=f"edit_acct_note_{selected_id}"
            )

        with c2:
            currently_active = bool(row["is_active"])
            has_data = db.account_has_data(selected_id)
            st.write("")
            st.write(f"현재 상태: {'✅ 활성' if currently_active else '⏸ 비활성'}")
            st.write(f"종속 데이터: {'있음 (삭제 불가)' if has_data else '없음 (삭제 가능)'}")

            b1, b2 = st.columns(2)
            with b1:
                if st.button("💾 저장", key=f"save_acct_{selected_id}", type="primary"):
                    try:
                        db.update_account(
                            account_id=selected_id,
                            name=new_name,
                            broker=new_broker,
                            kind=new_kind,
                            note=new_note,
                        )
                        st.success("저장됨")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("❌ 계좌 표시명이 중복됩니다.")
                    except ValueError as e:
                        st.error(f"❌ {e}")
            with b2:
                if currently_active:
                    if st.button("⏸ 비활성화", key=f"deact_acct_{selected_id}"):
                        db.set_account_active(selected_id, False)
                        st.rerun()
                else:
                    if st.button("✅ 재활성화", key=f"react_acct_{selected_id}"):
                        db.set_account_active(selected_id, True)
                        st.rerun()

            if not has_data:
                st.divider()
                st.caption("⚠️ 아래 삭제는 되돌릴 수 없습니다. 종속 데이터가 없을 때만 가능.")
                confirm = st.checkbox("삭제 확인", key=f"del_confirm_{selected_id}")
                if confirm and st.button(
                    "🗑 영구 삭제", key=f"del_acct_{selected_id}", type="secondary"
                ):
                    try:
                        db.delete_account(selected_id)
                        st.success("삭제됨")
                        st.rerun()
                    except ValueError as e:
                        st.error(f"❌ {e}")


def render() -> None:
    st.header("🏦 계좌 관리")
    st.caption(
        "여러 증권사·계좌를 관리합니다. "
        "법인/개인 계좌를 각각 여러 개 등록 가능."
    )

    has_any = db.account_count() > 0

    show_inactive = st.toggle("비활성 계좌도 표시", value=False, key="acct_show_inactive")
    df = _accounts_dataframe(active_only=not show_inactive)

    if df.empty and has_any:
        st.info("표시할 활성 계좌가 없습니다. 위 토글로 비활성 계좌도 볼 수 있습니다.")
    elif df.empty:
        st.warning(
            "👋 아직 등록된 계좌가 없습니다. 아래 폼에서 첫 계좌를 추가하세요. "
            "법인/개인을 직접 선택하고 계좌명도 자유롭게 정할 수 있습니다."
        )
    else:
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "account_id": st.column_config.NumberColumn("ID", width="small"),
                "name": st.column_config.TextColumn("계좌명"),
                "broker": st.column_config.TextColumn("증권사"),
                "kind": st.column_config.TextColumn("종류", width="small"),
                "is_active": st.column_config.TextColumn("상태", width="small"),
                "added_at": st.column_config.DatetimeColumn("등록일", format="YYYY-MM-DD"),
                "note": st.column_config.TextColumn("메모"),
            },
        )

    st.divider()
    # 계좌가 없으면 추가 폼을 자동으로 펼침
    _add_form(expanded_default=not has_any)
    _edit_panel()
