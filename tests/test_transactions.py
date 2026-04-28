"""거래 / 분배금 수동 입력 CRUD 테스트."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src import db


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.initialize()


@pytest.fixture
def corp_with_holding(fresh_db) -> tuple[int, str]:
    acct = db.add_account(name="법인", broker="IBK", kind=db.KIND_CORP)
    db.add_holding(
        ticker="292150", account_id=acct, name="TIGER",
        category="domestic_equity_etf", currency="KRW",
    )
    return acct, "292150"


@pytest.fixture
def personal_with_usd(fresh_db) -> tuple[int, str]:
    acct = db.add_account(name="개인", broker="농협", kind=db.KIND_PERSONAL)
    db.add_holding(
        ticker="NVDA", account_id=acct, name="NVIDIA",
        category="us_stock", currency="USD",
    )
    return acct, "NVDA"


class TestAddTransaction:
    def test_buy_krw(self, corp_with_holding):
        acct, ticker = corp_with_holding
        tx_id = db.add_transaction(
            trade_date="2026-04-26", account_id=acct, ticker=ticker,
            side="BUY", quantity=100, price=18000, currency="KRW",
        )
        assert tx_id > 0
        rows = db.list_transactions(account_id=acct)
        assert len(rows) == 1
        assert rows[0]["side"] == "BUY"
        assert rows[0]["quantity"] == 100

    def test_buy_usd_requires_fx(self, personal_with_usd):
        acct, ticker = personal_with_usd
        with pytest.raises(ValueError, match="USD"):
            db.add_transaction(
                trade_date="2026-04-26", account_id=acct, ticker=ticker,
                side="BUY", quantity=10, price=180, currency="USD",
            )

    def test_buy_usd_with_fx_ok(self, personal_with_usd):
        acct, ticker = personal_with_usd
        tx_id = db.add_transaction(
            trade_date="2026-04-26", account_id=acct, ticker=ticker,
            side="BUY", quantity=10, price=180, currency="USD", fx_rate=1410,
        )
        assert tx_id > 0

    def test_unregistered_ticker_rejected(self, corp_with_holding):
        acct, _ = corp_with_holding
        with pytest.raises(ValueError, match="종목 마스터에 없는"):
            db.add_transaction(
                trade_date="2026-04-26", account_id=acct, ticker="ZZZZ",
                side="BUY", quantity=1, price=1000, currency="KRW",
            )

    def test_invalid_side(self, corp_with_holding):
        acct, ticker = corp_with_holding
        with pytest.raises(ValueError):
            db.add_transaction(
                trade_date="2026-04-26", account_id=acct, ticker=ticker,
                side="HOLD", quantity=1, price=100, currency="KRW",
            )

    def test_zero_quantity_rejected(self, corp_with_holding):
        acct, ticker = corp_with_holding
        with pytest.raises(ValueError):
            db.add_transaction(
                trade_date="2026-04-26", account_id=acct, ticker=ticker,
                side="BUY", quantity=0, price=1000, currency="KRW",
            )

    def test_duplicate_rejected(self, corp_with_holding):
        acct, ticker = corp_with_holding
        kw = dict(trade_date="2026-04-26", account_id=acct, ticker=ticker,
                  side="BUY", quantity=10, price=18000, currency="KRW")
        db.add_transaction(**kw)
        with pytest.raises(sqlite3.IntegrityError):
            db.add_transaction(**kw)


class TestListAndDeleteTransactions:
    def test_list_orders_by_date_desc(self, corp_with_holding):
        acct, ticker = corp_with_holding
        for d in ["2026-04-20", "2026-04-26", "2026-04-23"]:
            db.add_transaction(
                trade_date=d, account_id=acct, ticker=ticker,
                side="BUY", quantity=10, price=18000, currency="KRW",
            )
        rows = db.list_transactions(account_id=acct)
        # SQLite는 PARSE_DECLTYPES 옵션으로 DATE 컬럼을 datetime.date로 반환
        actual = [str(r["trade_date"]) for r in rows]
        assert actual == ["2026-04-26", "2026-04-23", "2026-04-20"]

    def test_delete(self, corp_with_holding):
        acct, ticker = corp_with_holding
        tx_id = db.add_transaction(
            trade_date="2026-04-26", account_id=acct, ticker=ticker,
            side="BUY", quantity=10, price=18000, currency="KRW",
        )
        db.delete_transaction(tx_id)
        assert db.list_transactions(account_id=acct) == []


class TestDividends:
    def test_add_krw_dividend(self, corp_with_holding):
        acct, ticker = corp_with_holding
        div_id = db.add_dividend(
            pay_date="2026-04-26", account_id=acct, ticker=ticker,
            gross_amount=87000, net_amount=87000, currency="KRW",
        )
        assert div_id > 0
        rows = db.list_dividends()
        assert rows[0]["gross_krw"] == 87000

    def test_add_usd_dividend_converts_krw(self, personal_with_usd):
        acct, ticker = personal_with_usd
        # 세전 $12, 원천징수 $1.8 (15%), 입금 $10.2, 환율 1400
        div_id = db.add_dividend(
            pay_date="2026-04-26", account_id=acct, ticker=ticker,
            gross_amount=12.0, withholding_tax=1.8, net_amount=10.2,
            currency="USD", fx_rate=1400,
        )
        rows = db.list_dividends()
        assert rows[0]["gross_krw"] == pytest.approx(16800)
        assert rows[0]["net_krw"] == pytest.approx(14280)

    def test_usd_requires_fx(self, personal_with_usd):
        acct, ticker = personal_with_usd
        with pytest.raises(ValueError, match="USD"):
            db.add_dividend(
                pay_date="2026-04-26", account_id=acct, ticker=ticker,
                gross_amount=10, net_amount=8.5, currency="USD",
            )

    def test_unregistered_ticker_rejected(self, corp_with_holding):
        acct, _ = corp_with_holding
        with pytest.raises(ValueError):
            db.add_dividend(
                pay_date="2026-04-26", account_id=acct, ticker="ZZZ",
                gross_amount=1000, net_amount=850, currency="KRW",
            )

    def test_delete(self, corp_with_holding):
        acct, ticker = corp_with_holding
        div_id = db.add_dividend(
            pay_date="2026-04-26", account_id=acct, ticker=ticker,
            gross_amount=1000, net_amount=1000, currency="KRW",
        )
        db.delete_dividend(div_id)
        assert db.list_dividends() == []


class TestInitialPosition:
    def test_krw_initial_position(self, corp_with_holding):
        from src import analytics
        acct, ticker = corp_with_holding
        tx_id = db.add_initial_position(
            account_id=acct, ticker=ticker,
            quantity=300, avg_price=18500, base_date="2026-01-01",
        )
        assert tx_id > 0
        states = analytics.load_states_from_db(account_id=acct)
        s = states[(acct, ticker)]
        assert s.quantity == 300
        assert s.avg_cost_local == 18500

    def test_usd_initial_position_requires_fx(self, personal_with_usd):
        acct, ticker = personal_with_usd
        with pytest.raises(ValueError, match="USD"):
            db.add_initial_position(
                account_id=acct, ticker=ticker,
                quantity=30, avg_price=130, base_date="2026-01-01",
            )

    def test_usd_initial_position_with_fx(self, personal_with_usd):
        from src import analytics
        acct, ticker = personal_with_usd
        db.add_initial_position(
            account_id=acct, ticker=ticker,
            quantity=30, avg_price=130, avg_fx_rate=1350,
            base_date="2026-01-01",
        )
        states = analytics.load_states_from_db(account_id=acct)
        s = states[(acct, ticker)]
        assert s.quantity == 30
        assert s.avg_cost_local == 130
        assert s.avg_cost_fx == 1350

    def test_unregistered_ticker_rejected(self, fresh_db):
        acct = db.add_account(name="X", broker="Y", kind=db.KIND_CORP)
        with pytest.raises(ValueError, match="종목 마스터에 없"):
            db.add_initial_position(
                account_id=acct, ticker="ZZZ",
                quantity=100, avg_price=1000,
            )

    def test_initial_then_subsequent_buy_recomputes_avg(self, corp_with_holding):
        """초기 보유분 등록 후 새 매수 발생 시 가중평균 재계산되는지."""
        from src import analytics
        acct, ticker = corp_with_holding
        # 초기 100주 @18000
        db.add_initial_position(
            account_id=acct, ticker=ticker,
            quantity=100, avg_price=18000, base_date="2026-01-01",
        )
        # 새 매수 100주 @20000
        db.add_transaction(
            trade_date="2026-04-26", account_id=acct, ticker=ticker,
            side="BUY", quantity=100, price=20000, currency="KRW",
        )
        states = analytics.load_states_from_db(account_id=acct)
        s = states[(acct, ticker)]
        assert s.quantity == 200
        # (100*18000 + 100*20000) / 200 = 19000
        assert s.avg_cost_local == 19000


class TestComputeAutoFee:
    """compute_auto_fee 의 산식 검증 — UI 가 의존하는 핵심 로직."""

    def test_krw_basic(self):
        # 100주 × 18000원 × 0.015% = 270원
        fee = db.compute_auto_fee(
            quantity=100, price=18000, fee_rate_pct=0.015, currency="KRW",
        )
        assert fee == pytest.approx(270.0)

    def test_usd_with_fx(self):
        # 10주 × 130 USD × 0.25% × 1350원 = 4387.5원
        fee = db.compute_auto_fee(
            quantity=10, price=130, fee_rate_pct=0.25, currency="USD",
            fx_rate=1350,
        )
        assert fee == pytest.approx(10 * 130 * 0.0025 * 1350)

    def test_zero_rate_returns_zero(self):
        # 율이 0 이면 자동 OFF
        assert db.compute_auto_fee(
            quantity=100, price=18000, fee_rate_pct=0, currency="KRW",
        ) == 0.0

    def test_negative_rate_returns_zero(self):
        # 비정상 입력 방어
        assert db.compute_auto_fee(
            quantity=100, price=18000, fee_rate_pct=-1, currency="KRW",
        ) == 0.0

    def test_zero_quantity_returns_zero(self):
        assert db.compute_auto_fee(
            quantity=0, price=18000, fee_rate_pct=0.015, currency="KRW",
        ) == 0.0

    def test_usd_without_fx_returns_zero(self):
        # USD 인데 환율이 없으면 잘못된 원가가 박히지 않도록 0
        assert db.compute_auto_fee(
            quantity=10, price=130, fee_rate_pct=0.25, currency="USD",
            fx_rate=None,
        ) == 0.0
        assert db.compute_auto_fee(
            quantity=10, price=130, fee_rate_pct=0.25, currency="USD",
            fx_rate=0,
        ) == 0.0


class TestIntegrationWithAnalytics:
    """수동 입력한 거래가 analytics.replay_positions로 반영되는지 검증."""

    def test_buys_accumulate_to_position(self, corp_with_holding):
        from src import analytics
        acct, ticker = corp_with_holding
        db.add_transaction(
            trade_date="2026-04-01", account_id=acct, ticker=ticker,
            side="BUY", quantity=100, price=18000, currency="KRW",
        )
        db.add_transaction(
            trade_date="2026-04-15", account_id=acct, ticker=ticker,
            side="BUY", quantity=100, price=20000, currency="KRW",
        )
        states = analytics.load_states_from_db(account_id=acct)
        s = states[(acct, ticker)]
        assert s.quantity == 200
        # 가중평균 = (100*18000 + 100*20000) / 200 = 19000
        assert s.avg_cost_local == 19000
