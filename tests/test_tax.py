"""tax.py 단위 테스트."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.tax import (
    D,
    TaxBracket,
    TaxRules,
    TaxableSummary,
    calc_corporate_tax,
    expected_corporate_tax,
    fiscal_year_bounds,
    fiscal_year_of,
    marginal_rate_at,
    realized_gain_krw,
)


# 명세서 값 그대로
SPEC_BRACKETS = [
    TaxBracket(D("200000000"), D("0.09")),
    TaxBracket(D("20000000000"), D("0.19")),
    TaxBracket(D("300000000000"), D("0.21")),
    TaxBracket(None, D("0.24")),
]


class TestCorporateTaxCalculation:
    def test_zero_or_negative_income_is_zero_tax(self):
        assert calc_corporate_tax(0, SPEC_BRACKETS) == D(0)
        assert calc_corporate_tax(-1000, SPEC_BRACKETS) == D(0)

    def test_within_first_bracket(self):
        # 1억원 → 9%
        assert calc_corporate_tax(D("100000000"), SPEC_BRACKETS) == D("9000000")

    def test_at_first_bracket_top(self):
        # 정확히 2억원 → 1800만원
        assert calc_corporate_tax(D("200000000"), SPEC_BRACKETS) == D("18000000")

    def test_crosses_first_to_second_bracket(self):
        # 3억원 → 2억까지 9% (1800만) + 1억에 19% (1900만) = 3700만
        assert calc_corporate_tax(D("300000000"), SPEC_BRACKETS) == D("37000000")

    def test_crosses_into_third_bracket(self):
        # 250억원 → 2억(9%)+198억(19%)+50억(21%)
        # = 18,000,000 + 3,762,000,000 + 1,050,000,000
        # = 4,830,000,000
        assert calc_corporate_tax(D("25000000000"), SPEC_BRACKETS) == D("4830000000")

    def test_into_top_bracket(self):
        # 4000억 → 2억(9%)+198억(19%)+2800억(21%)+1000억(24%)
        # 18,000,000 + 3,762,000,000 + 58,800,000,000 + 24,000,000,000 = 86,580,000,000
        assert calc_corporate_tax(D("400000000000"), SPEC_BRACKETS) == D("86580000000")

    def test_marginal_rate(self):
        assert marginal_rate_at(D("100000000"), SPEC_BRACKETS) == D("0.09")
        assert marginal_rate_at(D("199999999"), SPEC_BRACKETS) == D("0.09")
        assert marginal_rate_at(D("200000000"), SPEC_BRACKETS) == D("0.19")
        assert marginal_rate_at(D("500000000"), SPEC_BRACKETS) == D("0.19")
        assert marginal_rate_at(D("999999999999"), SPEC_BRACKETS) == D("0.24")


class TestFiscalYear:
    def test_december_year_end(self):
        # 12월 결산 → 그냥 그 해
        assert fiscal_year_of(date(2026, 1, 1), 12) == 2026
        assert fiscal_year_of(date(2026, 4, 25), 12) == 2026
        assert fiscal_year_of(date(2026, 12, 31), 12) == 2026

    def test_march_year_end(self):
        # 3월 결산 → 4~3월이 한 사업연도. 종료월(3월)이 속한 해가 라벨.
        assert fiscal_year_of(date(2026, 3, 31), 3) == 2026
        assert fiscal_year_of(date(2026, 4, 1), 3) == 2027
        assert fiscal_year_of(date(2026, 12, 31), 3) == 2027
        assert fiscal_year_of(date(2027, 3, 1), 3) == 2027

    def test_bounds_december(self):
        start, end = fiscal_year_bounds(2026, 12)
        assert start == date(2026, 1, 1)
        assert end == date(2026, 12, 31)

    def test_bounds_march(self):
        # 2027 사업연도(3월결산) → 2026-04-01 ~ 2027-03-31
        start, end = fiscal_year_bounds(2027, 3)
        assert start == date(2026, 4, 1)
        assert end == date(2027, 3, 31)

    def test_invalid_month(self):
        with pytest.raises(ValueError):
            fiscal_year_of(date(2026, 1, 1), 0)
        with pytest.raises(ValueError):
            fiscal_year_of(date(2026, 1, 1), 13)


class TestExpectedCorporateTax:
    def test_no_other_income_just_investment(self):
        summary = TaxableSummary(
            fiscal_year=2026,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            dividend_taxable_krw=D("50000000"),
            realized_gain_taxable_krw=D("0"),
            fx_gain_taxable_krw=D("0"),
            foreign_tax_paid_krw=D("0"),
        )
        result = expected_corporate_tax(summary, _rules(), other_taxable_income_krw=0)
        # 5천만 → 9%만 적용
        assert result["base_tax"] == D(0)
        assert result["total_tax"] == D("4500000")
        assert result["additional_tax"] == D("4500000")

    def test_with_other_income_marginal_effect(self):
        # 본업 1.5억 + 투자 1억 = 2.5억
        # base: 1.5억 * 9% = 1350만
        # total: 2억 * 9% (1800만) + 0.5억 * 19% (950만) = 2750만
        # additional: 2750만 - 1350만 = 1400만 (마지막 5천만은 19% 적용됨)
        summary = TaxableSummary(
            fiscal_year=2026,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            dividend_taxable_krw=D("50000000"),
            realized_gain_taxable_krw=D("50000000"),
            fx_gain_taxable_krw=D("0"),
            foreign_tax_paid_krw=D("0"),
        )
        result = expected_corporate_tax(
            summary, _rules(), other_taxable_income_krw=D("150000000")
        )
        assert result["base_tax"] == D("13500000")
        assert result["total_tax"] == D("27500000")
        assert result["additional_tax"] == D("14000000")

    def test_foreign_tax_credit_capped(self):
        summary = TaxableSummary(
            fiscal_year=2026,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            dividend_taxable_krw=D("10000000"),
            realized_gain_taxable_krw=D("0"),
            fx_gain_taxable_krw=D("0"),
            foreign_tax_paid_krw=D("5000000"),  # 추가세액보다 많음
        )
        # 1천만 * 9% = 90만 추가세액. 외국납부 500만이지만 90만까지만 공제
        result = expected_corporate_tax(summary, _rules(), other_taxable_income_krw=0)
        assert result["additional_tax"] == D("900000")
        assert result["foreign_tax_credit"] == D("900000")
        assert result["net_additional_after_credit"] == D("0")


class TestRealizedGain:
    def test_krw_simple_profit(self):
        # 100주 매수 1만원, 매도 1.2만원 → 차익 20만원
        gain = realized_gain_krw(
            sell_quantity=100,
            sell_price=12000,
            sell_fx_rate=None,
            avg_cost=10000,
            avg_cost_fx_rate=None,
            currency="KRW",
        )
        assert gain == D("200000")

    def test_krw_with_fee(self):
        gain = realized_gain_krw(
            sell_quantity=100,
            sell_price=12000,
            sell_fx_rate=None,
            avg_cost=10000,
            avg_cost_fx_rate=None,
            currency="KRW",
            fee_krw=5000,
        )
        assert gain == D("195000")

    def test_usd_with_fx_appreciation(self):
        # 10주 매수 $100 (1100원), 매도 $110 (1300원)
        # 매도가 KRW = 10 * 110 * 1300 = 1,430,000
        # 매수가 KRW = 10 * 100 * 1100 = 1,100,000
        # 차익 = 330,000 (가격+환율 합산)
        gain = realized_gain_krw(
            sell_quantity=10,
            sell_price=110,
            sell_fx_rate=1300,
            avg_cost=100,
            avg_cost_fx_rate=1100,
            currency="USD",
        )
        assert gain == D("330000")

    def test_usd_loss(self):
        gain = realized_gain_krw(
            sell_quantity=10,
            sell_price=90,
            sell_fx_rate=1100,
            avg_cost=100,
            avg_cost_fx_rate=1100,
            currency="USD",
        )
        assert gain == D("-110000")

    def test_usd_requires_fx(self):
        with pytest.raises(ValueError):
            realized_gain_krw(
                sell_quantity=10, sell_price=110, sell_fx_rate=None,
                avg_cost=100, avg_cost_fx_rate=None, currency="USD",
            )


class TestTaxRulesYaml:
    def test_load_default_yaml(self):
        rules = TaxRules.from_yaml()
        assert rules.fiscal_year_end_month == 12
        assert rules.us_dividend_withholding_rate == D("0.15")
        assert len(rules.corporate_tax_brackets) >= 4
        # 첫 구간이 2억 9%인지
        first = rules.corporate_tax_brackets[0]
        assert first.up_to_krw == D("200000000")
        assert first.rate == D("0.09")
        # 마지막은 무한대
        assert rules.corporate_tax_brackets[-1].up_to_krw is None


# --- 테스트 헬퍼 ---

def _rules() -> TaxRules:
    return TaxRules(
        fiscal_year_end_month=12,
        corporate_tax_brackets=SPEC_BRACKETS,
        us_dividend_withholding_rate=D("0.15"),
        etf_taxation={},
        fx_gain_recognition="on_realization",
    )
