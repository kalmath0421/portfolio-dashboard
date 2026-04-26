"""세금 계산 로직.

명세서 9장 원칙: 모든 금액 계산은 Decimal 기반 (float 누적 오차 방지).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable

import yaml

from src import db


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TAX_RULES_PATH = PROJECT_ROOT / "config" / "tax_rules.yaml"

D = Decimal


@dataclass(frozen=True)
class TaxBracket:
    """누진세 구간. up_to_krw=None 은 무한대를 의미."""

    up_to_krw: Decimal | None
    rate: Decimal


@dataclass(frozen=True)
class TaxRules:
    fiscal_year_end_month: int
    corporate_tax_brackets: list[TaxBracket]
    us_dividend_withholding_rate: Decimal
    etf_taxation: dict[str, dict[str, bool]]
    fx_gain_recognition: str

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> TaxRules:
        rules_path = path or TAX_RULES_PATH
        if not rules_path.exists():
            raise FileNotFoundError(
                f"tax_rules.yaml 파일이 없습니다: {rules_path}"
            )
        with rules_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)

        brackets = [
            TaxBracket(
                up_to_krw=D(str(b["up_to_krw"])) if b["up_to_krw"] is not None else None,
                rate=D(str(b["rate"])),
            )
            for b in data["corporate_tax_brackets"]
        ]
        # 무한대 구간이 마지막에 있어야 함
        for b in brackets[:-1]:
            if b.up_to_krw is None:
                raise ValueError("무한대 구간(up_to_krw=null)은 마지막에만 위치해야 합니다.")
        if not brackets or brackets[-1].up_to_krw is not None:
            raise ValueError("마지막 구간은 up_to_krw=null 이어야 합니다.")

        return cls(
            fiscal_year_end_month=int(data["fiscal_year_end_month"]),
            corporate_tax_brackets=brackets,
            us_dividend_withholding_rate=D(str(data["us_dividend_withholding_rate"])),
            etf_taxation=data["etf_taxation"],
            fx_gain_recognition=data["fx_gain_recognition"],
        )


# --- 누진세 계산 ---

def calc_corporate_tax(
    taxable_income_krw: Decimal | int | float,
    brackets: Iterable[TaxBracket],
) -> Decimal:
    """과세표준에 대해 누진세율 적용.

    각 구간의 상한까지의 소득에 해당 세율을 적용한 뒤 합산.
    음수 또는 0 입력 시 0 반환.
    """
    income = D(str(taxable_income_krw))
    if income <= 0:
        return D(0)

    tax = D(0)
    prev_top = D(0)
    for b in brackets:
        if b.up_to_krw is None:
            # 무한대 구간 — 남은 소득 전부에 적용
            tax += (income - prev_top) * b.rate
            return tax.quantize(D("1"), rounding=ROUND_HALF_UP)

        if income <= b.up_to_krw:
            tax += (income - prev_top) * b.rate
            return tax.quantize(D("1"), rounding=ROUND_HALF_UP)
        else:
            tax += (b.up_to_krw - prev_top) * b.rate
            prev_top = b.up_to_krw

    return tax.quantize(D("1"), rounding=ROUND_HALF_UP)


def marginal_rate_at(
    taxable_income_krw: Decimal | int | float,
    brackets: Iterable[TaxBracket],
) -> Decimal:
    """주어진 소득의 한계세율(다음 1원에 적용될 세율) 반환."""
    income = D(str(taxable_income_krw))
    for b in brackets:
        if b.up_to_krw is None or income < b.up_to_krw:
            return b.rate
    # brackets가 비어 있는 경우는 from_yaml에서 검증됨
    return D(0)


# --- 사업연도 계산 ---

def fiscal_year_of(d: date, fiscal_year_end_month: int) -> int:
    """주어진 날짜가 속한 사업연도 라벨 (사업연도 종료 월 기준).

    예: fiscal_year_end_month=12 (12월 결산)
        2026-04-25 → 2026 (1~12월이 2026년 사업연도)
    예: fiscal_year_end_month=3 (3월 결산)
        2026-04-25 → 2027 (4~3월이 2027년 사업연도; 종료월이 속한 해)
        2026-02-15 → 2026
    """
    if not (1 <= fiscal_year_end_month <= 12):
        raise ValueError("fiscal_year_end_month must be 1..12")
    if fiscal_year_end_month == 12:
        return d.year
    if d.month <= fiscal_year_end_month:
        return d.year
    return d.year + 1


def fiscal_year_bounds(
    fiscal_year: int, fiscal_year_end_month: int
) -> tuple[date, date]:
    """사업연도의 시작일과 종료일 반환."""
    if fiscal_year_end_month == 12:
        return date(fiscal_year, 1, 1), date(fiscal_year, 12, 31)
    # 종료월이 fiscal_year에 속한 해의 (fiscal_year_end_month) 마지막 일
    end = _last_day_of_month(fiscal_year, fiscal_year_end_month)
    # 시작: 종료월 다음 달 1일, 전년도
    start_year = fiscal_year - 1
    start_month = fiscal_year_end_month + 1
    if start_month > 12:
        start_month = 1
        start_year = fiscal_year
    return date(start_year, start_month, 1), end


def _last_day_of_month(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    from datetime import timedelta
    return date(year, month + 1, 1) - timedelta(days=1)


# --- 과세대상금액 집계 (DB 기반) ---

@dataclass
class TaxableSummary:
    fiscal_year: int
    period_start: date
    period_end: date
    dividend_taxable_krw: Decimal
    realized_gain_taxable_krw: Decimal
    fx_gain_taxable_krw: Decimal
    foreign_tax_paid_krw: Decimal

    @property
    def total_taxable_krw(self) -> Decimal:
        return (
            self.dividend_taxable_krw
            + self.realized_gain_taxable_krw
            + self.fx_gain_taxable_krw
        )


def aggregate_taxable_for_fy(
    fiscal_year: int, rules: TaxRules
) -> TaxableSummary:
    """tax_events 테이블에서 사업연도 기준 합계 집계."""
    start, end = fiscal_year_bounds(fiscal_year, rules.fiscal_year_end_month)

    sql_sum = """
        SELECT
            COALESCE(SUM(CASE WHEN event_type = 'dividend' THEN taxable_amount_krw ELSE 0 END), 0)
              AS dividend_total,
            COALESCE(SUM(CASE WHEN event_type = 'realized_gain' THEN taxable_amount_krw ELSE 0 END), 0)
              AS realized_total,
            COALESCE(SUM(CASE WHEN event_type = 'fx_gain' THEN taxable_amount_krw ELSE 0 END), 0)
              AS fx_total,
            COALESCE(SUM(foreign_tax_paid_krw), 0) AS foreign_tax_total
        FROM tax_events
        WHERE fiscal_year = ?
    """
    with db.transaction() as conn:
        row = conn.execute(sql_sum, (fiscal_year,)).fetchone()

    return TaxableSummary(
        fiscal_year=fiscal_year,
        period_start=start,
        period_end=end,
        dividend_taxable_krw=D(str(row["dividend_total"])),
        realized_gain_taxable_krw=D(str(row["realized_total"])),
        fx_gain_taxable_krw=D(str(row["fx_total"])),
        foreign_tax_paid_krw=D(str(row["foreign_tax_total"])),
    )


def expected_corporate_tax(
    summary: TaxableSummary,
    rules: TaxRules,
    other_taxable_income_krw: Decimal | int | float = 0,
) -> dict:
    """투자에 따른 추가 법인세 추정.

    other_taxable_income_krw: 투자 외 본업(학원) 과세소득. 누진세 한계 효과 반영.
    Returns dict: base_tax(투자 외만), total_tax(투자 포함), additional(차이),
                 net_after_foreign_credit(외국납부세액 공제 후 추가세액).
    """
    other = D(str(other_taxable_income_krw))
    investment = summary.total_taxable_krw

    base_tax = calc_corporate_tax(other, rules.corporate_tax_brackets)
    total_tax = calc_corporate_tax(other + investment, rules.corporate_tax_brackets)
    additional = total_tax - base_tax

    # 외국납부세액공제 한도: 단순 추정 — 추가 법인세 한도 내에서만 공제
    creditable = min(summary.foreign_tax_paid_krw, additional)
    net_additional = additional - creditable

    return {
        "base_tax": base_tax,
        "total_tax": total_tax,
        "additional_tax": additional,
        "foreign_tax_credit": creditable,
        "net_additional_after_credit": net_additional,
    }


# --- 매도 시 실현손익 계산 보조 ---

def realized_gain_krw(
    sell_quantity: Decimal | float,
    sell_price: Decimal | float,
    sell_fx_rate: Decimal | float | None,
    avg_cost: Decimal | float,
    avg_cost_fx_rate: Decimal | float | None,
    currency: str,
    fee_krw: Decimal | float = 0,
) -> Decimal:
    """매도 1건의 원화 실현손익 계산.

    USD 종목은 매수·매도 시점 환율 모두 반영하여 환차손익까지 포함.
    이동평균법 기준 평균단가를 입력으로 받음.
    """
    qty = D(str(sell_quantity))
    sp = D(str(sell_price))
    ac = D(str(avg_cost))
    fee = D(str(fee_krw))

    if currency == "USD":
        if sell_fx_rate is None or avg_cost_fx_rate is None:
            raise ValueError("USD 종목은 매도/매수 환율이 필요합니다.")
        sell_krw = qty * sp * D(str(sell_fx_rate))
        cost_krw = qty * ac * D(str(avg_cost_fx_rate))
    elif currency == "KRW":
        sell_krw = qty * sp
        cost_krw = qty * ac
    else:
        raise ValueError(f"unsupported currency: {currency}")

    return (sell_krw - cost_krw - fee).quantize(D("1"), rounding=ROUND_HALF_UP)
