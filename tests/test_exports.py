"""CSV 내보내기 단위 테스트."""
from __future__ import annotations

from pathlib import Path

import pytest

from src import db, exports


@pytest.fixture
def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.initialize()


@pytest.fixture
def populated_db(fresh_db) -> tuple[int, int]:
    """법인 + 개인 계좌 + 종목 + 거래 + 분배금까지 채운 DB."""
    corp = db.add_account(name="법인 A", broker="IBK", kind=db.KIND_CORP)
    personal = db.add_account(name="개인 A", broker="농협", kind=db.KIND_PERSONAL)
    db.add_holding(ticker="292150", account_id=corp, name="TIGER 코리아TOP10",
                   category="domestic_equity_etf", currency="KRW")
    db.add_holding(ticker="NVDA", account_id=personal, name="NVIDIA",
                   category="us_stock", currency="USD")
    # 거래
    db.add_transaction(
        trade_date="2026-02-15", account_id=corp, ticker="292150",
        side="BUY", quantity=100, price=18000, currency="KRW",
    )
    db.add_transaction(
        trade_date="2026-03-20", account_id=personal, ticker="NVDA",
        side="BUY", quantity=10, price=180, currency="USD", fx_rate=1410,
    )
    # 작년 거래 (2026 사업연도 외)
    db.add_transaction(
        trade_date="2025-08-01", account_id=corp, ticker="292150",
        side="BUY", quantity=50, price=15000, currency="KRW",
    )
    # 분배금
    db.add_dividend(
        pay_date="2026-03-15", account_id=corp, ticker="292150",
        gross_amount=87000, net_amount=87000, currency="KRW",
    )
    db.add_dividend(
        pay_date="2026-04-15", account_id=personal, ticker="NVDA",
        gross_amount=12.0, net_amount=10.2, currency="USD",
        withholding_tax=1.8, fx_rate=1400,
    )
    # 작년 분배금 (제외돼야 함)
    db.add_dividend(
        pay_date="2025-12-15", account_id=corp, ticker="292150",
        gross_amount=50000, net_amount=50000, currency="KRW",
    )
    return corp, personal


class TestDividendsCsv:
    def test_header_korean(self, fresh_db):
        csv = exports.export_dividends_csv(2026)
        first_line = csv.split("\n")[0]
        assert "지급일" in first_line
        assert "세전금액(현지)" in first_line
        assert "세전금액(KRW)" in first_line

    def test_filters_by_fiscal_year(self, populated_db):
        csv_2026 = exports.export_dividends_csv(2026)
        # 헤더 + 2건 (2025-12 분배금은 제외)
        assert csv_2026.count("\n") == 3  # 헤더 1줄 + 데이터 2줄 (각 \n 포함)
        assert "2026-03-15" in csv_2026
        assert "2026-04-15" in csv_2026
        assert "2025-12-15" not in csv_2026

    def test_includes_2025_when_filtering_2025(self, populated_db):
        csv_2025 = exports.export_dividends_csv(2025)
        assert "2025-12-15" in csv_2025
        assert "2026-03-15" not in csv_2025

    def test_usd_dividend_includes_fx(self, populated_db):
        csv = exports.export_dividends_csv(2026)
        assert "USD" in csv
        assert "1400.00" in csv  # 환율
        assert "16800" in csv     # 세전 KRW = 12 * 1400 (정수)
        # 10.2 × 1400 은 부동소수점에서 14279.999... 가 되어 14279로 절삭
        assert "14279" in csv or "14280" in csv

    def test_empty_when_no_data(self, fresh_db):
        csv = exports.export_dividends_csv(2026)
        # 헤더만
        assert csv.count("\n") == 1


class TestTransactionsCsv:
    def test_header(self, fresh_db):
        csv = exports.export_transactions_csv(2026)
        first_line = csv.split("\n")[0]
        assert "거래일" in first_line
        assert "구분" in first_line
        assert "단가(현지)" in first_line

    def test_buy_sell_korean(self, populated_db):
        csv = exports.export_transactions_csv(2026)
        assert "매수" in csv  # BUY → 매수
        # 매도 거래는 없으므로 "매도" 없음

    def test_filters_by_fiscal_year(self, populated_db):
        csv_2026 = exports.export_transactions_csv(2026)
        assert "2026-02-15" in csv_2026
        assert "2026-03-20" in csv_2026
        # 2025-08 거래는 제외
        assert "2025-08-01" not in csv_2026

    def test_includes_category_korean(self, populated_db):
        csv = exports.export_transactions_csv(2026)
        assert "국내주식ETF" in csv
        assert "미국주식" in csv


class TestForeignTaxCsv:
    def test_only_usd_with_withholding(self, populated_db):
        csv = exports.export_foreign_tax_csv(2026)
        # NVDA 분배금만 (USD + 원천징수>0)
        assert "NVDA" in csv
        # KRW 분배금(292150)은 외국납부세액 없으므로 제외
        assert "292150" not in csv

    def test_calculates_krw_withholding(self, populated_db):
        csv = exports.export_foreign_tax_csv(2026)
        # 1.8 USD * 1400 KRW = 2520 KRW
        assert "2520" in csv

    def test_empty_when_no_usd_dividends(self, fresh_db):
        corp = db.add_account(name="X", broker="Y", kind=db.KIND_CORP)
        db.add_holding(ticker="005930", account_id=corp, name="삼성전자",
                       category="kr_stock", currency="KRW")
        db.add_dividend(
            pay_date="2026-03-15", account_id=corp, ticker="005930",
            gross_amount=10000, net_amount=10000, currency="KRW",
        )
        csv = exports.export_foreign_tax_csv(2026)
        # 헤더만
        assert csv.count("\n") == 1


class TestExcelBytes:
    def test_utf8_bom_attached(self):
        out = exports.to_excel_bytes("a,b\n1,2\n")
        # BOM = EF BB BF
        assert out[:3] == b"\xef\xbb\xbf"

    def test_korean_round_trip(self):
        text = "지급일,종목\n2026-04-15,삼성전자\n"
        out = exports.to_excel_bytes(text)
        # BOM 제거하고 UTF-8 디코드 → 원래 문자열
        decoded = out.decode("utf-8-sig")
        assert decoded == text
