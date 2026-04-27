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


class TestDeleteHolding:
    def test_delete_clean_holding(self, corp_account):
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="USD",
        )
        assert db.get_holding("AMZN", corp_account) is not None
        db.delete_holding("AMZN", corp_account)
        assert db.get_holding("AMZN", corp_account) is None

    def test_delete_releases_pk_for_reinsert(self, corp_account):
        """삭제 후 같은 (ticker, account_id) 재등록이 가능해야 — 통화 바꿔서 다시 넣는 케이스."""
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="KRW",  # 잘못된 통화
        )
        db.delete_holding("AMZN", corp_account)
        # 다시 USD 로 등록 가능해야 함
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="USD",
        )
        h = db.get_holding("AMZN", corp_account)
        assert h["currency"] == "USD"

    def test_delete_blocked_when_has_transactions(self, corp_account):
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="USD",
        )
        db.add_transaction(
            trade_date="2026-04-27", account_id=corp_account, ticker="AMZN",
            side="BUY", quantity=10, price=200.0, currency="USD", fx_rate=1400.0,
        )
        with pytest.raises(ValueError, match="종속 데이터"):
            db.delete_holding("AMZN", corp_account)

    def test_holding_has_data_false_when_clean(self, corp_account):
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="USD",
        )
        assert db.holding_has_data("AMZN", corp_account) is False

    def test_holding_has_data_true_when_tx(self, corp_account):
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="USD",
        )
        db.add_transaction(
            trade_date="2026-04-27", account_id=corp_account, ticker="AMZN",
            side="BUY", quantity=10, price=200.0, currency="USD", fx_rate=1400.0,
        )
        assert db.holding_has_data("AMZN", corp_account) is True


class TestUpdateHoldingCurrency:
    def test_change_currency_when_clean(self, corp_account):
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="KRW",  # 잘못 입력
        )
        db.update_holding(
            ticker="AMZN", account_id=corp_account, currency="USD"
        )
        h = db.get_holding("AMZN", corp_account)
        assert h["currency"] == "USD"

    def test_change_currency_blocked_when_has_data(self, corp_account):
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="KRW",
        )
        db.add_transaction(
            trade_date="2026-04-27", account_id=corp_account, ticker="AMZN",
            side="BUY", quantity=10, price=200.0, currency="KRW",
        )
        with pytest.raises(ValueError, match="통화는 변경할 수 없습니다"):
            db.update_holding(
                ticker="AMZN", account_id=corp_account, currency="USD"
            )
        # 원본 통화 유지
        assert db.get_holding("AMZN", corp_account)["currency"] == "KRW"

    def test_same_currency_does_not_check_data(self, corp_account):
        """동일 통화로 '변경'하는 건 종속 데이터 체크를 건너뛰어 영향 없음."""
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="USD",
        )
        db.add_transaction(
            trade_date="2026-04-27", account_id=corp_account, ticker="AMZN",
            side="BUY", quantity=10, price=200.0, currency="USD", fx_rate=1400.0,
        )
        # USD → USD 는 OK (실제 변경 사항 없음)
        db.update_holding(
            ticker="AMZN", account_id=corp_account, currency="USD",
            name="Amazon Inc.",
        )
        assert db.get_holding("AMZN", corp_account)["name"] == "Amazon Inc."

    def test_invalid_currency_rejected(self, corp_account):
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="USD",
        )
        with pytest.raises(ValueError, match="invalid currency"):
            db.update_holding(
                ticker="AMZN", account_id=corp_account, currency="JPY"
            )


class TestTickerNormalization:
    """티커는 .strip().upper() 로 정규화되어 저장·조회된다."""

    def test_lowercase_normalized_on_add(self, corp_account):
        db.add_holding(
            ticker="amzn", account_id=corp_account, name="Amazon",
            category="us_stock", currency="USD",
        )
        # 대문자로 저장되어 있어야 함
        h = db.get_holding("AMZN", corp_account)
        assert h is not None
        assert h["ticker"] == "AMZN"

    def test_lookup_case_insensitive(self, corp_account):
        """대문자로 등록한 종목을 소문자로 조회해도 찾을 수 있어야."""
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="USD",
        )
        assert db.get_holding("amzn", corp_account) is not None
        assert db.get_holding("AmZn", corp_account) is not None

    def test_whitespace_trimmed(self, corp_account):
        db.add_holding(
            ticker="  amzn  ", account_id=corp_account, name="Amazon",
            category="us_stock", currency="USD",
        )
        h = db.get_holding("AMZN", corp_account)
        assert h is not None
        assert h["ticker"] == "AMZN"

    def test_duplicate_different_case_blocked(self, corp_account):
        """동일 종목을 다른 case 로 두 번 등록하면 두 번째는 IntegrityError."""
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="USD",
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.add_holding(
                ticker="amzn", account_id=corp_account, name="Amazon Lower",
                category="us_stock", currency="USD",
            )

    def test_korean_numeric_ticker_unaffected(self, corp_account):
        """한국 ETF 티커(숫자)는 .upper() 영향 없음 — 그대로 저장."""
        db.add_holding(
            ticker="292150", account_id=corp_account, name="TIGER 코리아TOP10",
            category="domestic_equity_etf", currency="KRW",
        )
        h = db.get_holding("292150", corp_account)
        assert h is not None
        assert h["ticker"] == "292150"

    def test_transaction_ticker_normalized(self, corp_account):
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="USD",
        )
        tx_id = db.add_transaction(
            trade_date="2026-04-27", account_id=corp_account,
            ticker="amzn",  # 소문자 입력
            side="BUY", quantity=10, price=200.0,
            currency="USD", fx_rate=1400.0,
        )
        rows = db.list_transactions()
        match = [r for r in rows if r["id"] == tx_id]
        assert len(match) == 1
        assert match[0]["ticker"] == "AMZN"  # 정규화되어 저장

    def test_initial_position_ticker_normalized(self, corp_account):
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="USD",
        )
        db.add_initial_position(
            account_id=corp_account, ticker="amzn",  # 소문자
            quantity=10, avg_price=200.0, avg_fx_rate=1400.0,
        )
        rows = db.list_transactions()
        assert all(r["ticker"] == "AMZN" for r in rows)

    def test_delete_holding_works_with_lowercase(self, corp_account):
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="USD",
        )
        db.delete_holding("amzn", corp_account)  # 소문자로 삭제 시도
        assert db.get_holding("AMZN", corp_account) is None


class TestAddHoldingWithInitialPosition:
    """종목 마스터 + 초기 보유분 BUY 거래를 한 번에 등록하는 헬퍼."""

    def test_creates_holding_and_transaction(self, corp_account):
        created, tx_id = db.add_holding_with_initial_position(
            account_id=corp_account,
            ticker="AMZN", name="Amazon",
            category="us_stock", currency="USD",
            quantity=10, avg_price=200.0, avg_fx_rate=1400.0,
            base_date="2026-04-27",
        )
        assert created is True
        assert tx_id > 0
        h = db.get_holding("AMZN", corp_account)
        assert h is not None and h["currency"] == "USD"
        rows = db.list_transactions()
        assert any(r["id"] == tx_id and r["ticker"] == "AMZN" for r in rows)

    def test_existing_holding_skips_master_adds_transaction(self, corp_account):
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="USD",
        )
        created, tx_id = db.add_holding_with_initial_position(
            account_id=corp_account,
            ticker="AMZN", name="Amazon Inc.",  # 다른 이름이지만 마스터는 안 바꿈
            category="us_stock", currency="USD",
            quantity=5, avg_price=210.0, avg_fx_rate=1410.0,
            base_date="2026-04-27",
        )
        assert created is False  # 마스터 새로 안 만듦
        assert tx_id > 0
        h = db.get_holding("AMZN", corp_account)
        # 마스터의 이름은 처음 등록한 'Amazon' 그대로
        assert h["name"] == "Amazon"

    def test_currency_mismatch_rejected(self, corp_account):
        db.add_holding(
            ticker="AMZN", account_id=corp_account, name="Amazon",
            category="us_stock", currency="USD",
        )
        with pytest.raises(ValueError, match="통화"):
            db.add_holding_with_initial_position(
                account_id=corp_account,
                ticker="AMZN", name="Amazon",
                category="us_stock", currency="KRW",  # 통화 불일치
                quantity=5, avg_price=300000.0,
                base_date="2026-04-27",
            )

    def test_lowercase_ticker_normalized(self, corp_account):
        created, tx_id = db.add_holding_with_initial_position(
            account_id=corp_account,
            ticker="amzn",  # 소문자
            name="Amazon",
            category="us_stock", currency="USD",
            quantity=10, avg_price=200.0, avg_fx_rate=1400.0,
            base_date="2026-04-27",
        )
        assert created is True
        assert db.get_holding("AMZN", corp_account) is not None


class TestCategoryDefaultCurrency:
    """카테고리에서 통화 자동 도출."""

    def test_us_stock_defaults_to_usd(self):
        assert db.default_currency_for_category("us_stock") == "USD"

    def test_kr_stock_defaults_to_krw(self):
        assert db.default_currency_for_category("kr_stock") == "KRW"

    def test_domestic_etf_defaults_to_krw(self):
        assert db.default_currency_for_category("domestic_equity_etf") == "KRW"

    def test_overseas_kr_listed_etf_defaults_to_krw(self):
        # TIGER 미국나스닥100 같은 국내 상장 해외 ETF — 거래 통화는 KRW
        assert db.default_currency_for_category("overseas_equity_etf_kr_listed") == "KRW"

    def test_money_market_etf_defaults_to_krw(self):
        assert db.default_currency_for_category("money_market_etf") == "KRW"

    def test_invalid_category_rejected(self):
        with pytest.raises(ValueError, match="invalid category"):
            db.default_currency_for_category("crypto")


class TestAutoCurrencyOnInsert:
    """add_holding / add_holding_with_initial_position 가 카테고리에서 통화 자동 도출."""

    def test_add_holding_without_currency_uses_category(self, corp_account):
        db.add_holding(
            ticker="NVDA", account_id=corp_account, name="NVIDIA",
            category="us_stock",
            # currency 인자 생략 — 카테고리에서 자동 도출
        )
        h = db.get_holding("NVDA", corp_account)
        assert h["currency"] == "USD"

    def test_add_holding_explicit_currency_still_works(self, corp_account):
        # 명시값이 있으면 그대로 사용 (legacy compatibility)
        db.add_holding(
            ticker="005930", account_id=corp_account, name="삼성전자",
            category="kr_stock", currency="KRW",
        )
        h = db.get_holding("005930", corp_account)
        assert h["currency"] == "KRW"

    def test_combined_form_without_currency(self, corp_account):
        created, tx_id = db.add_holding_with_initial_position(
            account_id=corp_account,
            ticker="MSFT", name="Microsoft",
            category="us_stock",
            quantity=10, avg_price=400.0, avg_fx_rate=1400.0,
            base_date="2026-04-27",
            # currency 생략 — us_stock 이라 USD 자동
        )
        assert created is True
        h = db.get_holding("MSFT", corp_account)
        assert h["currency"] == "USD"
