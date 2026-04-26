"""db.py 종목·계좌 CRUD 단위 테스트.

isolated_db fixture로 임시 DB 파일을 만들어 모듈 전역 DB_PATH를 monkeypatch.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src import db


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """매 테스트마다 임시 DB로 격리. 자동 시드 없음 — 빈 상태로 시작."""
    test_db_path = tmp_path / "test_portfolio.db"
    monkeypatch.setattr(db, "DB_PATH", test_db_path)
    info = db.initialize()
    yield info


@pytest.fixture
def corp_account(isolated_db) -> int:
    return db.add_account(name="법인 계좌 A", broker="IBK WINGS", kind=db.KIND_CORP)


@pytest.fixture
def personal_account(isolated_db) -> int:
    return db.add_account(name="개인 계좌 A", broker="농협 나무", kind=db.KIND_PERSONAL)


class TestInitialize:
    def test_clean_init_has_no_accounts_or_holdings(self, isolated_db):
        """자동 시드 제거 — 초기 상태는 완전히 비어 있어야 함."""
        assert isolated_db["has_accounts"] is False
        assert isolated_db["has_holdings"] is False
        assert db.account_count() == 0
        assert db.holding_count() == 0

    def test_idempotent_initialize(self, isolated_db):
        # 두 번 호출해도 깨지지 않음
        info2 = db.initialize()
        assert info2["has_accounts"] is False


class TestDefaultHoldings:
    def test_default_for_corp(self):
        items = db.default_holdings_for_kind(db.KIND_CORP)
        # 명세서 3.2 기본 5종 (CD금리액티브 제외)
        assert len(items) == 5
        tickers = {h["ticker"] for h in items}
        assert "292150" in tickers
        assert "498400" in tickers
        # MMF는 사용자가 직접 입력
        assert all(h["category"] != "money_market_etf" for h in items)

    def test_default_for_personal(self):
        items = db.default_holdings_for_kind(db.KIND_PERSONAL)
        # 미국 8 + 국내 3 = 11
        assert len(items) == 11
        usd_tickers = {h["ticker"] for h in items if h["currency"] == "USD"}
        krw_tickers = {h["ticker"] for h in items if h["currency"] == "KRW"}
        assert "NVDA" in usd_tickers
        assert "005930" in krw_tickers

    def test_invalid_kind(self):
        with pytest.raises(ValueError):
            db.default_holdings_for_kind("foo")

    def test_add_default_to_corp_account(self, corp_account):
        added = db.add_default_holdings_to_account(corp_account)
        assert added == 5
        held = db.list_holdings(account_id=corp_account)
        assert {h["ticker"] for h in held} == {"292150", "458730", "486290", "498410", "498400"}

    def test_add_default_to_personal_account(self, personal_account):
        added = db.add_default_holdings_to_account(personal_account)
        assert added == 11

    def test_add_default_skips_existing(self, corp_account):
        first = db.add_default_holdings_to_account(corp_account)
        second = db.add_default_holdings_to_account(corp_account)
        assert first == 5
        assert second == 0
        assert db.holding_count() == 5

    def test_add_default_invalid_account(self, isolated_db):
        with pytest.raises(ValueError):
            db.add_default_holdings_to_account(99999)


class TestAccountCrud:
    def test_add_and_list(self, isolated_db):
        new_id = db.add_account(name="키움 법인", broker="키움증권", kind=db.KIND_CORP)
        assert new_id > 0
        assert len(db.list_accounts()) == 1

    def test_user_can_create_multiple_personal_accounts(self, isolated_db):
        """사용자 요청: 개인 계좌도 여러 개."""
        db.add_account(name="농협 나무 개인", broker="농협 나무", kind=db.KIND_PERSONAL)
        db.add_account(name="키움 개인", broker="키움증권", kind=db.KIND_PERSONAL)
        db.add_account(name="한투 ISA", broker="한국투자증권", kind=db.KIND_PERSONAL)
        personals = db.list_accounts(kind=db.KIND_PERSONAL)
        assert len(personals) == 3

    def test_user_can_create_multiple_corp_accounts(self, isolated_db):
        db.add_account(name="IBK 법인 A", broker="IBK WINGS", kind=db.KIND_CORP)
        db.add_account(name="삼성 법인 B", broker="삼성증권", kind=db.KIND_CORP)
        corps = db.list_accounts(kind=db.KIND_CORP)
        assert len(corps) == 2

    def test_duplicate_name_rejected(self, isolated_db):
        db.add_account(name="동일이름", broker="X", kind=db.KIND_CORP)
        with pytest.raises(sqlite3.IntegrityError):
            db.add_account(name="동일이름", broker="Y", kind=db.KIND_PERSONAL)

    def test_invalid_kind(self, isolated_db):
        with pytest.raises(ValueError):
            db.add_account(name="X", broker="Y", kind="invalid")

    def test_blank_name_rejected(self, isolated_db):
        with pytest.raises(ValueError):
            db.add_account(name="  ", broker="X", kind=db.KIND_CORP)

    def test_update(self, corp_account):
        db.update_account(corp_account, note="신규 메모", broker="새증권사")
        u = db.get_account(corp_account)
        assert u["note"] == "신규 메모"
        assert u["broker"] == "새증권사"

    def test_set_active(self, personal_account):
        db.set_account_active(personal_account, False)
        assert db.get_account(personal_account)["is_active"] == 0
        db.set_account_active(personal_account, True)
        assert db.get_account(personal_account)["is_active"] == 1

    def test_delete_with_holdings_blocked(self, corp_account):
        db.add_default_holdings_to_account(corp_account)
        with pytest.raises(ValueError):
            db.delete_account(corp_account)

    def test_delete_empty_account_ok(self, personal_account):
        db.delete_account(personal_account)
        assert db.get_account(personal_account) is None


class TestHoldingCrud:
    def test_add_to_specific_account(self, corp_account):
        db.add_holding(
            ticker="999999",
            account_id=corp_account,
            name="테스트 ETF",
            category="money_market_etf",
            currency="KRW",
        )
        assert len(db.list_holdings(account_id=corp_account)) == 1

    def test_same_ticker_allowed_in_different_accounts(self, isolated_db):
        a1 = db.add_account(name="개인 A", broker="농협", kind=db.KIND_PERSONAL)
        a2 = db.add_account(name="개인 B", broker="키움", kind=db.KIND_PERSONAL)
        for acct in (a1, a2):
            db.add_holding(
                ticker="NVDA", account_id=acct, name="NVIDIA",
                category="us_stock", currency="USD",
            )
        assert len([h for h in db.list_holdings() if h["ticker"] == "NVDA"]) == 2

    def test_same_ticker_same_account_rejected(self, corp_account):
        db.add_holding(
            ticker="292150", account_id=corp_account, name="TIGER",
            category="domestic_equity_etf", currency="KRW",
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.add_holding(
                ticker="292150", account_id=corp_account, name="중복",
                category="domestic_equity_etf", currency="KRW",
            )

    def test_invalid_category(self, corp_account):
        with pytest.raises(ValueError):
            db.add_holding(
                ticker="X", account_id=corp_account, name="X",
                category="invalid_cat", currency="KRW",
            )

    def test_invalid_account_id(self, isolated_db):
        with pytest.raises(ValueError):
            db.add_holding(
                ticker="X", account_id=99999, name="X",
                category="kr_stock", currency="KRW",
            )

    def test_update_holding(self, corp_account):
        db.add_holding(
            ticker="292150", account_id=corp_account, name="원본",
            category="domestic_equity_etf", currency="KRW",
        )
        db.update_holding(
            ticker="292150", account_id=corp_account,
            name="수정됨", note="rename",
        )
        h = db.get_holding("292150", corp_account)
        assert h["name"] == "수정됨"
        assert h["note"] == "rename"

    def test_deactivate_and_reactivate(self, corp_account):
        db.add_holding(
            ticker="292150", account_id=corp_account, name="X",
            category="domestic_equity_etf", currency="KRW",
        )
        db.set_holding_active("292150", corp_account, False)
        assert db.get_holding("292150", corp_account)["is_active"] == 0
        active = db.list_holdings(active_only=True, account_id=corp_account)
        assert "292150" not in {row["ticker"] for row in active}
        db.set_holding_active("292150", corp_account, True)
        assert db.get_holding("292150", corp_account)["is_active"] == 1

    def test_find_unregistered(self, corp_account):
        db.add_default_holdings_to_account(corp_account)
        result = db.find_unregistered_tickers(
            ["292150", "ZZZ", "498400"], corp_account
        )
        assert result == ["ZZZ"]

    def test_find_unregistered_per_account(self, isolated_db):
        corp = db.add_account(name="법인", broker="IBK", kind=db.KIND_CORP)
        personal = db.add_account(name="개인", broker="농협", kind=db.KIND_PERSONAL)
        db.add_default_holdings_to_account(personal)
        # NVDA는 personal에는 있지만 corp에는 없음
        result = db.find_unregistered_tickers(["NVDA"], corp)
        assert result == ["NVDA"]


class TestMoneyMarketDetection:
    def test_no_corp_no_mmf(self, isolated_db):
        assert db.has_money_market_etf() is False

    def test_corp_with_default_holdings_lacks_mmf(self, corp_account):
        # 명세서 기본 종목에는 MMF가 없음
        db.add_default_holdings_to_account(corp_account)
        assert db.has_money_market_etf() is False

    def test_after_user_adds_mmf(self, corp_account):
        db.add_holding(
            ticker="359240", account_id=corp_account, name="KODEX CD금리액티브",
            category="money_market_etf", currency="KRW",
        )
        assert db.has_money_market_etf() is True

    def test_inactive_account_mmf_does_not_count(self, corp_account):
        db.add_holding(
            ticker="359240", account_id=corp_account, name="KODEX CD금리액티브",
            category="money_market_etf", currency="KRW",
        )
        db.set_account_active(corp_account, False)
        assert db.has_money_market_etf() is False
