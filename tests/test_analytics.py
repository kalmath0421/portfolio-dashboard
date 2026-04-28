"""analytics.py - 평균단가, 실현손익, 환차분리 테스트."""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.analytics import (
    aggregate_by_account,
    contribution_breakdown,
    fx_attribution_table,
    fx_attribution_usd,
    replay_positions,
    total_market_value,
    total_unrealized,
    value_position,
)


D = Decimal


def _tx(**kw):
    base = {"trade_date": "2026-01-01", "account_id": 1, "ticker": "X",
            "side": "BUY", "quantity": 10, "price": 100, "currency": "KRW",
            "fx_rate": None, "fee": 0}
    base.update(kw)
    return base


def _div(**kw):
    base = {"pay_date": "2026-02-01", "account_id": 1, "ticker": "X",
            "currency": "KRW", "gross_krw": 0, "net_krw": 0}
    base.update(kw)
    return base


class TestKrwAveraging:
    def test_two_buys_weighted_average(self):
        states = replay_positions([
            _tx(trade_date="2026-01-01", quantity=10, price=1000),
            _tx(trade_date="2026-01-02", quantity=10, price=1500),
        ])
        s = states[(1, "X")]
        assert s.quantity == D(20)
        # (10*1000 + 10*1500) / 20 = 1250
        assert s.avg_cost_local == D(1250)

    def test_buy_then_sell_realized(self):
        states = replay_positions([
            _tx(trade_date="2026-01-01", quantity=10, price=1000),
            _tx(trade_date="2026-01-02", quantity=10, price=1500),
            _tx(trade_date="2026-01-03", side="SELL", quantity=5, price=2000),
        ])
        s = states[(1, "X")]
        # 평균 1250, 5주 매도 @2000 → (2000-1250)*5 = 3750
        assert s.realized_pnl_krw == D(3750)
        assert s.quantity == D(15)
        # 매도 후 평균단가는 그대로 (이동평균법)
        assert s.avg_cost_local == D(1250)

    def test_full_sell_resets_avg(self):
        states = replay_positions([
            _tx(trade_date="2026-01-01", quantity=10, price=1000),
            _tx(trade_date="2026-01-02", side="SELL", quantity=10, price=1200),
        ])
        s = states[(1, "X")]
        assert s.quantity == D(0)
        assert s.avg_cost_local == D(0)
        assert s.realized_pnl_krw == D(2000)


class TestUsdAveraging:
    def test_usd_two_buys_track_fx_average(self):
        states = replay_positions([
            _tx(currency="USD", quantity=10, price=100, fx_rate=1100),
            _tx(currency="USD", trade_date="2026-01-02",
                quantity=10, price=120, fx_rate=1300),
        ])
        s = states[(1, "X")]
        # 가격 평균: (10*100 + 10*120)/20 = 110
        assert s.avg_cost_local == D(110)
        # 환율 평균: (10*1100 + 10*1300)/20 = 1200
        assert s.avg_cost_fx == D(1200)

    def test_usd_sell_includes_fx_gain(self):
        states = replay_positions([
            _tx(currency="USD", quantity=10, price=100, fx_rate=1100),
            _tx(currency="USD", trade_date="2026-01-02", side="SELL",
                quantity=10, price=110, fx_rate=1300),
        ])
        s = states[(1, "X")]
        # 매수 KRW: 10*100*1100 = 1,100,000
        # 매도 KRW: 10*110*1300 = 1,430,000
        # 차익 330,000
        assert s.realized_pnl_krw == D(330000)


class TestValuation:
    def test_unrealized_krw(self):
        states = replay_positions([
            _tx(quantity=10, price=1000),
        ])
        s = states[(1, "X")]
        v = value_position(s, current_price_local=1500, current_fx=None)
        assert v.market_value_krw == D(15000)
        assert v.unrealized_pnl_krw == D(5000)
        # KRW 종목은 현지=원화이므로 양쪽 동일
        assert v.market_value_local == D(15000)
        assert v.unrealized_pnl_local == D(5000)
        assert v.return_pct_local == D("50.00")
        assert v.return_pct_krw == D("50.00")

    def test_unrealized_usd_split_currencies(self):
        states = replay_positions([
            _tx(currency="USD", quantity=10, price=100, fx_rate=1100),
        ])
        s = states[(1, "X")]
        v = value_position(s, current_price_local=120, current_fx=1300)
        # 현지(USD): 평가 1200, 원가 1000, 손익 200, 수익률 20%
        assert v.market_value_local == D(1200)
        assert v.cost_basis_local == D(1000)
        assert v.unrealized_pnl_local == D(200)
        assert v.return_pct_local == D("20.00")
        # 원화: 평가 1,560,000 / 원가 1,100,000 / 손익 460,000
        assert v.market_value_krw == D(1560000)
        assert v.cost_basis_krw == D(1100000)
        assert v.unrealized_pnl_krw == D(460000)
        # 원화 수익률: 460000 / 1100000 = 41.82%
        assert v.return_pct_krw == D("41.82")

    def test_buy_fee_included_in_cost_basis_krw(self):
        states = replay_positions([
            _tx(quantity=10, price=1000, fee=500),
        ])
        s = states[(1, "X")]
        v = value_position(s, current_price_local=1000, current_fx=None)
        # 원가 = 10*1000 + 500 = 10,500
        assert v.cost_basis_krw == D(10500)
        # 평가금액 = 10*1000 = 10,000 (수수료 무관)
        assert v.market_value_krw == D(10000)
        # 미실현 손익 = 10,000 - 10,500 = -500
        assert v.unrealized_pnl_krw == D(-500)

    def test_usd_buy_fee_added_to_krw_cost(self):
        states = replay_positions([
            _tx(currency="USD", quantity=10, price=100, fx_rate=1100, fee=3000),
        ])
        s = states[(1, "X")]
        v = value_position(s, current_price_local=100, current_fx=1100)
        # USD 원가는 수수료 미포함 (수수료가 KRW이므로)
        assert v.cost_basis_local == D(1000)
        # KRW 원가 = 10*100*1100 + 3000 = 1,103,000
        assert v.cost_basis_krw == D(1103000)
        assert v.market_value_krw == D(1100000)
        assert v.unrealized_pnl_krw == D(-3000)

    def test_partial_sell_consumes_buy_fee_proportionally(self):
        states = replay_positions([
            _tx(trade_date="2026-01-01", quantity=10, price=1000, fee=500),
            _tx(trade_date="2026-01-02", side="SELL", quantity=4, price=1000, fee=0),
        ])
        s = states[(1, "X")]
        # 매도 시점: 4/10 = 40% 매수수수료 소진 = 200원 차감
        # 실현손익 = (4*1000 - 4*1000) - 200 = -200
        assert s.realized_pnl_krw == D(-200)
        # 잔량 6주에 귀속되는 매수수수료 = 300원 남음
        assert s.cumulative_buy_fee_krw == D(300)
        v = value_position(s, current_price_local=1000, current_fx=None)
        # 잔량 원가 = 6*1000 + 300 = 6,300
        assert v.cost_basis_krw == D(6300)

    def test_usd_no_price_yet_keeps_cost_basis(self):
        """현재가 없어도 매수원가는 산출돼야 한다."""
        states = replay_positions([
            _tx(currency="USD", quantity=10, price=100, fx_rate=1100),
        ])
        s = states[(1, "X")]
        v = value_position(s, current_price_local=None, current_fx=None)
        assert v.cost_basis_local == D(1000)
        assert v.cost_basis_krw == D(1100000)
        assert v.market_value_local is None
        assert v.return_pct_krw is None


class TestDailyChange:
    """value_position 의 일일 변동(시장 직전 거래일 종가 대비) 산출."""

    def test_krw_basic(self):
        # 10주 보유, 어제 1000 → 오늘 1100. 변동 +1000원, +10%.
        states = replay_positions([_tx(quantity=10, price=900)])
        s = states[(1, "X")]
        v = value_position(
            s, current_price_local=1100, current_fx=None,
            previous_price_local=1000,
        )
        assert v.daily_change_local == D(1000)
        assert v.daily_change_krw == D(1000)
        assert v.daily_change_pct == D("10.00")

    def test_krw_negative(self):
        # 직전 거래일보다 떨어진 케이스 — 부호 음수.
        states = replay_positions([_tx(quantity=5, price=1000)])
        s = states[(1, "X")]
        v = value_position(
            s, current_price_local=950, current_fx=None,
            previous_price_local=1000,
        )
        assert v.daily_change_local == D(-250)
        assert v.daily_change_pct == D("-5.00")

    def test_usd_uses_current_fx_for_krw_translation(self):
        # 10주 USD, 어제 100 → 오늘 110, 환율 1300. 변동 USD 100, KRW 130000.
        states = replay_positions([
            _tx(currency="USD", quantity=10, price=90, fx_rate=1100),
        ])
        s = states[(1, "X")]
        v = value_position(
            s, current_price_local=110, current_fx=1300,
            previous_price_local=100,
        )
        assert v.daily_change_local == D(100)
        assert v.daily_change_krw == D(130000)
        assert v.daily_change_pct == D("10.00")

    def test_no_previous_close_yields_none(self):
        states = replay_positions([_tx(quantity=10, price=1000)])
        s = states[(1, "X")]
        v = value_position(
            s, current_price_local=1100, current_fx=None,
            previous_price_local=None,
        )
        assert v.daily_change_local is None
        assert v.daily_change_krw is None
        assert v.daily_change_pct is None

    def test_zero_quantity_yields_none(self):
        # 전량 매도된 종목은 일일 변동도 없음.
        states = replay_positions([
            _tx(quantity=10, price=1000),
            _tx(side="SELL", quantity=10, price=1100, trade_date="2026-02-01"),
        ])
        s = states[(1, "X")]
        v = value_position(
            s, current_price_local=1200, current_fx=None,
            previous_price_local=1100,
        )
        assert v.daily_change_local is None
        assert v.daily_change_krw is None
        assert v.daily_change_pct is None

    def test_usd_without_current_fx_local_only(self):
        # USD 종목인데 환율이 없으면 KRW 변동은 산출 불가, 현지 변동은 가능.
        states = replay_positions([
            _tx(currency="USD", quantity=10, price=90, fx_rate=1100),
        ])
        s = states[(1, "X")]
        v = value_position(
            s, current_price_local=110, current_fx=None,
            previous_price_local=100,
        )
        assert v.daily_change_local == D(100)
        assert v.daily_change_krw is None
        assert v.daily_change_pct == D("10.00")


class TestFxAttribution:
    def test_split_into_price_fx_cross(self):
        states = replay_positions([
            _tx(currency="USD", quantity=10, price=100, fx_rate=1100),
        ])
        s = states[(1, "X")]
        attr = fx_attribution_usd(s, current_price_local=120, current_fx=1300)
        # price_effect: 10 * 20 * 1100 = 220,000
        # fx_effect:    10 * 100 * 200 = 200,000
        # cross_term:   10 * 20 * 200 = 40,000
        # total: 460,000 (미실현과 일치)
        assert attr["price_effect"] == D(220000)
        assert attr["fx_effect"] == D(200000)
        assert attr["cross_term"] == D(40000)
        assert attr["price_effect"] + attr["fx_effect"] + attr["cross_term"] == D(460000)


class TestContributionAndAggregates:
    def test_total_market_value(self):
        states = replay_positions([
            _tx(ticker="A", quantity=10, price=100),
            _tx(ticker="B", quantity=5, price=200),
        ])
        v_a = value_position(states[(1, "A")], 150, None)
        v_b = value_position(states[(1, "B")], 250, None)
        assert total_market_value([v_a, v_b]) == D(2750)

    def test_contribution_breakdown_signed(self):
        states = replay_positions([
            _tx(ticker="GAIN", quantity=10, price=100),
            _tx(ticker="LOSS", quantity=10, price=200),
        ])
        v_gain = value_position(states[(1, "GAIN")], 150, None)
        v_loss = value_position(states[(1, "LOSS")], 100, None)
        breakdown = contribution_breakdown([v_gain, v_loss])
        # GAIN: +500, LOSS: -1000, abs_sum=1500
        # 가장 좋은 게 먼저 (양수 우선)
        assert breakdown[0]["ticker"] == "GAIN"
        assert breakdown[0]["unrealized_pnl_krw"] == D(500)
        assert breakdown[1]["ticker"] == "LOSS"
        assert breakdown[1]["unrealized_pnl_krw"] == D(-1000)


class TestAccountAggregation:
    def test_currency_separation(self):
        states = replay_positions([
            _tx(account_id=1, ticker="NVDA", currency="USD",
                quantity=10, price=100, fx_rate=1100),
            _tx(account_id=1, ticker="005930", currency="KRW",
                quantity=100, price=70000),
        ])
        v_usd = value_position(states[(1, "NVDA")], 120, 1300)
        v_krw = value_position(states[(1, "005930")], 80000, None)
        agg = aggregate_by_account([v_usd, v_krw])[1]

        # USD 종목: 평가 USD 1200, KRW 환산 1,560,000
        assert agg["market_value_usd"] == D(1200)
        # KRW 종목: 평가 8,000,000 (현지=원화)
        assert agg["market_value_krw_only"] == D(8000000)
        # 전체 KRW 환산: 1,560,000 + 8,000,000
        assert agg["market_value_krw"] == D(9560000)


class TestFxAttributionTable:
    def test_table_only_includes_usd(self):
        states = replay_positions([
            _tx(ticker="A", currency="USD", quantity=10, price=100, fx_rate=1100),
            _tx(ticker="B", currency="KRW", quantity=10, price=1000),
        ])
        v_a = value_position(states[(1, "A")], 120, 1300)
        v_b = value_position(states[(1, "B")], 1500, None)
        rows = fx_attribution_table([v_a, v_b], states)
        assert len(rows) == 1
        assert rows[0]["ticker"] == "A"
        # price + fx + cross 합 = 미실현 손익(KRW)
        assert (
            rows[0]["price_effect_krw"]
            + rows[0]["fx_effect_krw"]
            + rows[0]["cross_term_krw"]
            == v_a.unrealized_pnl_krw
        )

    def test_skips_when_no_price(self):
        states = replay_positions([
            _tx(currency="USD", quantity=10, price=100, fx_rate=1100),
        ])
        v = value_position(states[(1, "X")], None, None)
        assert fx_attribution_table([v], states) == []


class TestDividends:
    def test_dividends_accumulate(self):
        states = replay_positions(
            [_tx(quantity=10, price=100)],
            dividends=[
                _div(pay_date="2026-02-01", gross_krw=1000, net_krw=850),
                _div(pay_date="2026-03-01", gross_krw=1500, net_krw=1275),
            ],
        )
        s = states[(1, "X")]
        assert s.cumulative_dividend_gross_krw == D(2500)
        assert s.cumulative_dividend_net_krw == D(2125)
