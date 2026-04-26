"""세금 추적 화면 — 사업연도 누적 과세대상금액 + 예상 추가 법인세."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from src import db, exports, tax


TAX_RULES_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "tax_rules.yaml"


def _format_krw(amount: Decimal | int | float) -> str:
    n = int(Decimal(str(amount)))
    return f"{n:,} 원"


def render() -> None:
    st.header("💰 세금 추적")
    st.caption("법인세 신고 대비 — 사업연도 누적 과세대상금액 모니터링")

    st.warning(
        "⚠️ 본 화면은 **모니터링 보조 도구**입니다. "
        "실제 법인세 신고는 반드시 세무사 검토를 거치십시오."
    )

    if not TAX_RULES_PATH.exists():
        st.error(f"세금 규칙 파일이 없습니다: {TAX_RULES_PATH}")
        return

    try:
        rules = tax.TaxRules.from_yaml(TAX_RULES_PATH)
    except (ValueError, KeyError) as e:
        st.error(f"tax_rules.yaml 파싱 오류: {e}")
        return

    today = date.today()
    current_fy = tax.fiscal_year_of(today, rules.fiscal_year_end_month)

    c1, c2 = st.columns([1, 2])
    with c1:
        fy = st.number_input(
            "사업연도", value=current_fy, step=1, min_value=2020, max_value=2100,
        )
    with c2:
        other_income = st.number_input(
            "투자 외 본업(학원) 과세소득 (KRW) — 누진세 한계효과 추정용",
            value=0, step=10_000_000, min_value=0,
            help="대략적인 사업소득을 입력하면 누진세 효과를 반영해 추가세액을 계산합니다."
        )

    summary = tax.aggregate_taxable_for_fy(int(fy), rules)

    st.subheader(f"📅 {summary.fiscal_year} 사업연도 ({summary.period_start} ~ {summary.period_end})")

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("분배금/배당 합계 (세전)", _format_krw(summary.dividend_taxable_krw))
    with m2:
        st.metric("실현 매매차익", _format_krw(summary.realized_gain_taxable_krw))
    with m3:
        st.metric("환차손익", _format_krw(summary.fx_gain_taxable_krw))
    with m4:
        st.metric("외국납부세액 (공제 대상)", _format_krw(summary.foreign_tax_paid_krw))

    st.divider()
    st.subheader("📊 누진세 적용 결과")
    expected = tax.expected_corporate_tax(summary, rules, other_income)

    e1, e2, e3 = st.columns(3)
    with e1:
        st.metric("투자 외 기준 법인세", _format_krw(expected["base_tax"]))
    with e2:
        st.metric("투자 포함 총 법인세", _format_krw(expected["total_tax"]))
    with e3:
        st.metric(
            "투자에 따른 추가세액",
            _format_krw(expected["additional_tax"]),
            delta=_format_krw(-expected["foreign_tax_credit"])
            if expected["foreign_tax_credit"] > 0 else None,
            delta_color="inverse",
        )

    st.metric(
        "외국납부세액 공제 후 순추가세액",
        _format_krw(expected["net_additional_after_credit"]),
    )

    st.caption(
        f"한계세율 (현재 소득 기준): "
        f"{tax.marginal_rate_at(other_income + summary.total_taxable_krw, rules.corporate_tax_brackets):.0%}"
    )

    if summary.total_taxable_krw == 0 and summary.foreign_tax_paid_krw == 0:
        st.info(
            "이 사업연도에는 아직 세금 이벤트가 없습니다. "
            "Phase 2에서 거래 CSV를 임포트하면 분배금·실현손익이 자동 누적됩니다."
        )

    st.divider()
    with st.expander("📋 현재 적용 중인 세금 규칙 (config/tax_rules.yaml)"):
        with TAX_RULES_PATH.open(encoding="utf-8") as f:
            st.json(yaml.safe_load(f))

    st.divider()
    st.subheader("📦 세무사 전달용 CSV 내보내기")
    st.caption(
        f"{summary.fiscal_year} 사업연도 데이터를 CSV로 내려받아 세무사에게 전달. "
        "한국어 엑셀에서 바로 열림 (UTF-8 BOM)."
    )

    csv_div = exports.export_dividends_csv(
        summary.fiscal_year, rules.fiscal_year_end_month
    )
    csv_tx = exports.export_transactions_csv(
        summary.fiscal_year, rules.fiscal_year_end_month
    )
    csv_ft = exports.export_foreign_tax_csv(
        summary.fiscal_year, rules.fiscal_year_end_month
    )

    fy = summary.fiscal_year
    cols = st.columns(3)
    with cols[0]:
        n_lines = csv_div.count("\n") - 1
        st.download_button(
            f"📥 분배금 내역 CSV ({n_lines}건)",
            data=exports.to_excel_bytes(csv_div),
            file_name=f"분배금_{fy}.csv",
            mime="text/csv",
            use_container_width=True,
            disabled=n_lines <= 0,
        )
    with cols[1]:
        n_lines = csv_tx.count("\n") - 1
        st.download_button(
            f"📥 매매 내역 CSV ({n_lines}건)",
            data=exports.to_excel_bytes(csv_tx),
            file_name=f"매매내역_{fy}.csv",
            mime="text/csv",
            use_container_width=True,
            disabled=n_lines <= 0,
        )
    with cols[2]:
        n_lines = csv_ft.count("\n") - 1
        st.download_button(
            f"📥 외국납부세액 CSV ({n_lines}건)",
            data=exports.to_excel_bytes(csv_ft),
            file_name=f"외국납부세액_{fy}.csv",
            mime="text/csv",
            use_container_width=True,
            disabled=n_lines <= 0,
        )
