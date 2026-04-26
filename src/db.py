"""SQLite 연결, 스키마 초기화, 시드 데이터 관리.

다중 계좌 지원:
- accounts 테이블이 모든 계좌를 보유
- holdings/transactions/dividends/positions_snapshot/tax_events는 account_id로 참조
- 계좌는 kind('corp'/'personal')로 법인/개인 구분
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "portfolio.db"

KIND_CORP = "corp"
KIND_PERSONAL = "personal"
KINDS = {KIND_CORP: "법인", KIND_PERSONAL: "개인"}

CATEGORIES = {
    "domestic_equity_etf": "국내주식ETF",
    "overseas_equity_etf_kr_listed": "국내상장 해외ETF",
    "money_market_etf": "MMF성ETF",
    "us_stock": "미국주식",
    "kr_stock": "국내주식",
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    broker TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('corp', 'personal')),
    is_active INTEGER NOT NULL DEFAULT 1,
    note TEXT,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS holdings (
    ticker TEXT NOT NULL,
    account_id INTEGER NOT NULL REFERENCES accounts(account_id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN (
        'domestic_equity_etf',
        'overseas_equity_etf_kr_listed',
        'money_market_etf',
        'us_stock',
        'kr_stock'
    )),
    currency TEXT NOT NULL CHECK (currency IN ('KRW', 'USD')),
    is_active INTEGER NOT NULL DEFAULT 1,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    note TEXT,
    PRIMARY KEY (ticker, account_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date DATE NOT NULL,
    account_id INTEGER NOT NULL REFERENCES accounts(account_id) ON DELETE RESTRICT,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    currency TEXT NOT NULL,
    fx_rate REAL,
    fee REAL DEFAULT 0,
    realized_pnl_krw REAL,
    note TEXT,
    UNIQUE(trade_date, account_id, ticker, side, quantity, price)
);

CREATE TABLE IF NOT EXISTS dividends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pay_date DATE NOT NULL,
    account_id INTEGER NOT NULL REFERENCES accounts(account_id) ON DELETE RESTRICT,
    ticker TEXT NOT NULL,
    gross_amount REAL NOT NULL,
    withholding_tax REAL DEFAULT 0,
    net_amount REAL NOT NULL,
    currency TEXT NOT NULL,
    fx_rate REAL,
    gross_krw REAL,
    net_krw REAL,
    note TEXT,
    UNIQUE(pay_date, account_id, ticker, gross_amount)
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    snapshot_date DATE NOT NULL,
    ticker TEXT NOT NULL,
    close_price REAL NOT NULL,
    currency TEXT NOT NULL,
    PRIMARY KEY (snapshot_date, ticker)
);

CREATE TABLE IF NOT EXISTS fx_snapshots (
    snapshot_date DATE PRIMARY KEY,
    usdkrw REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS positions_snapshot (
    snapshot_date DATE NOT NULL,
    account_id INTEGER NOT NULL REFERENCES accounts(account_id) ON DELETE RESTRICT,
    ticker TEXT NOT NULL,
    quantity REAL NOT NULL,
    avg_cost REAL,
    market_value_krw REAL,
    PRIMARY KEY (snapshot_date, account_id, ticker)
);

CREATE TABLE IF NOT EXISTS tax_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date DATE NOT NULL,
    fiscal_year INTEGER NOT NULL,
    account_id INTEGER NOT NULL REFERENCES accounts(account_id) ON DELETE RESTRICT,
    ticker TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'dividend', 'realized_gain', 'fx_gain'
    )),
    taxable_amount_krw REAL NOT NULL,
    foreign_tax_paid_krw REAL DEFAULT 0,
    note TEXT
);

CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(trade_date);
CREATE INDEX IF NOT EXISTS idx_tx_acct_ticker ON transactions(account_id, ticker);
CREATE INDEX IF NOT EXISTS idx_div_date ON dividends(pay_date);
CREATE INDEX IF NOT EXISTS idx_div_acct_ticker ON dividends(account_id, ticker);
CREATE INDEX IF NOT EXISTS idx_holdings_acct ON holdings(account_id);
CREATE INDEX IF NOT EXISTS idx_tax_fy ON tax_events(fiscal_year);
"""


# 명세서 3.2의 기본 종목 — '시드' 가 아니라 '템플릿'.
# 사용자가 계좌를 만들고 본인이 원하면 일괄 등록 가능.
DEFAULT_CORP_HOLDINGS: list[dict] = [
    {"ticker": "292150", "name": "TIGER 코리아TOP10",
     "category": "domestic_equity_etf", "currency": "KRW"},
    {"ticker": "458730", "name": "TIGER 미국배당다우존스",
     "category": "overseas_equity_etf_kr_listed", "currency": "KRW"},
    {"ticker": "486290", "name": "TIGER 미국나스닥100 타겟데일리커버드콜",
     "category": "overseas_equity_etf_kr_listed", "currency": "KRW"},
    {"ticker": "498410", "name": "KODEX 금융고배당TOP10타겟위클리커버드콜",
     "category": "domestic_equity_etf", "currency": "KRW"},
    {"ticker": "498400", "name": "KODEX 200타겟위클리커버드콜",
     "category": "domestic_equity_etf", "currency": "KRW"},
    # KODEX CD금리액티브는 사용자가 티커를 직접 입력 (3.2 명세 참조)
]

DEFAULT_PERSONAL_HOLDINGS: list[dict] = [
    # 미국
    {"ticker": "NVDA", "name": "NVIDIA", "category": "us_stock", "currency": "USD"},
    {"ticker": "MSFT", "name": "Microsoft", "category": "us_stock", "currency": "USD"},
    {"ticker": "TSLA", "name": "Tesla", "category": "us_stock", "currency": "USD"},
    {"ticker": "AMZN", "name": "Amazon", "category": "us_stock", "currency": "USD"},
    {"ticker": "GOOGL", "name": "Alphabet (Class A)", "category": "us_stock", "currency": "USD"},
    {"ticker": "XLU", "name": "Utilities Select Sector SPDR Fund",
     "category": "us_stock", "currency": "USD"},
    {"ticker": "QQQJ", "name": "Invesco NASDAQ Next Gen 100 ETF",
     "category": "us_stock", "currency": "USD"},
    {"ticker": "SPYM", "name": "SPDR Portfolio S&P 500 ETF",
     "category": "us_stock", "currency": "USD"},
    # 국내
    {"ticker": "005930", "name": "삼성전자", "category": "kr_stock", "currency": "KRW"},
    {"ticker": "316140", "name": "우리금융지주", "category": "kr_stock", "currency": "KRW"},
    {"ticker": "402340", "name": "SK스퀘어", "category": "kr_stock", "currency": "KRW"},
]


def default_holdings_for_kind(kind: str) -> list[dict]:
    if kind == KIND_CORP:
        return list(DEFAULT_CORP_HOLDINGS)
    if kind == KIND_PERSONAL:
        return list(DEFAULT_PERSONAL_HOLDINGS)
    raise ValueError(f"unknown kind: {kind}")


def get_db_path() -> Path:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema() -> None:
    with transaction() as conn:
        conn.executescript(SCHEMA_SQL)


def has_money_market_etf() -> bool:
    """MMF성 ETF가 어떤 활성 법인 계좌에라도 등록돼 있는지 확인."""
    with transaction() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM holdings h
            JOIN accounts a ON a.account_id = h.account_id
            WHERE h.category = 'money_market_etf' AND a.is_active = 1
            LIMIT 1
            """
        ).fetchone()
        return row is not None


def initialize() -> dict:
    """앱 시작 시 호출. 스키마만 보장 (자동 계좌·종목 시드는 하지 않음).

    계좌 생성·종목 등록은 사용자가 UI에서 직접 진행한다.
    """
    init_schema()
    return {
        "has_accounts": account_count() > 0,
        "has_holdings": holding_count() > 0,
    }


def account_count() -> int:
    with transaction() as conn:
        return conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]


def holding_count() -> int:
    with transaction() as conn:
        return conn.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]


# --- 계좌 CRUD ---

def list_accounts(active_only: bool = False, kind: str | None = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM accounts WHERE 1=1"
    params: list = []
    if active_only:
        sql += " AND is_active = 1"
    if kind is not None:
        sql += " AND kind = ?"
        params.append(kind)
    sql += " ORDER BY kind, name"
    with transaction() as conn:
        return conn.execute(sql, params).fetchall()


def get_account(account_id: int) -> sqlite3.Row | None:
    with transaction() as conn:
        return conn.execute(
            "SELECT * FROM accounts WHERE account_id = ?", (account_id,)
        ).fetchone()


def add_account(name: str, broker: str, kind: str, note: str | None = None) -> int:
    if kind not in KINDS:
        raise ValueError(f"invalid kind: {kind}")
    if not name.strip() or not broker.strip():
        raise ValueError("name and broker are required")
    with transaction() as conn:
        cur = conn.execute(
            "INSERT INTO accounts (name, broker, kind, note) VALUES (?, ?, ?, ?)",
            (name.strip(), broker.strip(), kind, note),
        )
        return cur.lastrowid


def update_account(
    account_id: int,
    name: str | None = None,
    broker: str | None = None,
    kind: str | None = None,
    note: str | None = None,
) -> None:
    sets, params = [], []
    if name is not None:
        sets.append("name = ?")
        params.append(name.strip())
    if broker is not None:
        sets.append("broker = ?")
        params.append(broker.strip())
    if kind is not None:
        if kind not in KINDS:
            raise ValueError(f"invalid kind: {kind}")
        sets.append("kind = ?")
        params.append(kind)
    if note is not None:
        sets.append("note = ?")
        params.append(note)
    if not sets:
        return
    params.append(account_id)
    with transaction() as conn:
        conn.execute(
            f"UPDATE accounts SET {', '.join(sets)} WHERE account_id = ?", params
        )


def set_account_active(account_id: int, active: bool) -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE accounts SET is_active = ? WHERE account_id = ?",
            (1 if active else 0, account_id),
        )


def account_has_data(account_id: int) -> bool:
    """계좌에 거래/잔고/배당/세금이벤트가 하나라도 있으면 True (삭제 방지용)."""
    with transaction() as conn:
        for table in ("transactions", "dividends", "positions_snapshot", "tax_events"):
            row = conn.execute(
                f"SELECT 1 FROM {table} WHERE account_id = ? LIMIT 1", (account_id,)
            ).fetchone()
            if row:
                return True
        row = conn.execute(
            "SELECT 1 FROM holdings WHERE account_id = ? LIMIT 1", (account_id,)
        ).fetchone()
        return bool(row)


def delete_account(account_id: int) -> None:
    """계좌 삭제. 종속 데이터가 있으면 거부."""
    if account_has_data(account_id):
        raise ValueError(
            "계좌에 종속 데이터(종목/거래/배당 등)가 존재해 삭제할 수 없습니다. "
            "비활성화를 사용하세요."
        )
    with transaction() as conn:
        conn.execute("DELETE FROM accounts WHERE account_id = ?", (account_id,))


# --- 종목 마스터 CRUD ---

def list_holdings(
    active_only: bool = False,
    account_id: int | None = None,
    kind: str | None = None,
) -> list[sqlite3.Row]:
    sql = """
        SELECT h.*, a.name AS account_name, a.broker AS broker, a.kind AS kind
        FROM holdings h
        JOIN accounts a ON a.account_id = h.account_id
        WHERE 1=1
    """
    params: list = []
    if active_only:
        sql += " AND h.is_active = 1 AND a.is_active = 1"
    if account_id is not None:
        sql += " AND h.account_id = ?"
        params.append(account_id)
    if kind is not None:
        sql += " AND a.kind = ?"
        params.append(kind)
    sql += " ORDER BY a.kind, a.name, h.category, h.ticker"
    with transaction() as conn:
        return conn.execute(sql, params).fetchall()


def get_holding(ticker: str, account_id: int) -> sqlite3.Row | None:
    with transaction() as conn:
        return conn.execute(
            "SELECT * FROM holdings WHERE ticker = ? AND account_id = ?",
            (ticker, account_id),
        ).fetchone()


def add_holding(
    ticker: str,
    account_id: int,
    name: str,
    category: str,
    currency: str,
    note: str | None = None,
) -> None:
    if category not in CATEGORIES:
        raise ValueError(f"invalid category: {category}")
    if currency not in ("KRW", "USD"):
        raise ValueError(f"invalid currency: {currency}")
    if not ticker.strip() or not name.strip():
        raise ValueError("ticker and name are required")
    with transaction() as conn:
        if not conn.execute(
            "SELECT 1 FROM accounts WHERE account_id = ?", (account_id,)
        ).fetchone():
            raise ValueError(f"account_id {account_id} not found")
        conn.execute(
            """
            INSERT INTO holdings (ticker, account_id, name, category, currency, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ticker.strip(), account_id, name.strip(), category, currency, note),
        )


def update_holding(
    ticker: str,
    account_id: int,
    name: str | None = None,
    category: str | None = None,
    note: str | None = None,
) -> None:
    sets, params = [], []
    if name is not None:
        sets.append("name = ?")
        params.append(name.strip())
    if category is not None:
        if category not in CATEGORIES:
            raise ValueError(f"invalid category: {category}")
        sets.append("category = ?")
        params.append(category)
    if note is not None:
        sets.append("note = ?")
        params.append(note)
    if not sets:
        return
    params.extend([ticker, account_id])
    with transaction() as conn:
        conn.execute(
            f"UPDATE holdings SET {', '.join(sets)} WHERE ticker = ? AND account_id = ?",
            params,
        )


def set_holding_active(ticker: str, account_id: int, active: bool) -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE holdings SET is_active = ? WHERE ticker = ? AND account_id = ?",
            (1 if active else 0, ticker, account_id),
        )


def bulk_add_holdings(
    account_id: int, holdings: list[dict], skip_existing: bool = True
) -> int:
    """여러 종목을 한 계좌에 일괄 등록. 추가된 개수 반환.

    holdings: [{ticker, name, category, currency, note?}, ...]
    skip_existing=True면 이미 (ticker, account_id) 조합이 있는 항목은 건너뜀.
    """
    if not holdings:
        return 0
    inserted = 0
    with transaction() as conn:
        if not conn.execute(
            "SELECT 1 FROM accounts WHERE account_id = ?", (account_id,)
        ).fetchone():
            raise ValueError(f"account_id {account_id} not found")

        for h in holdings:
            category = h["category"]
            currency = h["currency"]
            if category not in CATEGORIES:
                raise ValueError(f"invalid category: {category}")
            if currency not in ("KRW", "USD"):
                raise ValueError(f"invalid currency: {currency}")

            existing = conn.execute(
                "SELECT 1 FROM holdings WHERE ticker = ? AND account_id = ?",
                (h["ticker"], account_id),
            ).fetchone()
            if existing:
                if skip_existing:
                    continue
                raise sqlite3.IntegrityError(
                    f"already exists: {h['ticker']} in account {account_id}"
                )
            conn.execute(
                """
                INSERT INTO holdings
                    (ticker, account_id, name, category, currency, note)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    h["ticker"].strip(),
                    account_id,
                    h["name"].strip(),
                    category,
                    currency,
                    h.get("note"),
                ),
            )
            inserted += 1
    return inserted


def add_default_holdings_to_account(account_id: int) -> int:
    """계좌의 kind에 맞는 기본 종목 목록을 일괄 등록. 추가 개수 반환."""
    acct = get_account(account_id)
    if acct is None:
        raise ValueError(f"account_id {account_id} not found")
    return bulk_add_holdings(
        account_id, default_holdings_for_kind(acct["kind"]), skip_existing=True
    )


# --- 거래 내역 CRUD ---

def add_transaction(
    trade_date: str,
    account_id: int,
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    currency: str,
    fx_rate: float | None = None,
    fee: float = 0,
    note: str | None = None,
) -> int:
    if side not in ("BUY", "SELL"):
        raise ValueError(f"invalid side: {side}")
    if currency not in ("KRW", "USD"):
        raise ValueError(f"invalid currency: {currency}")
    if quantity <= 0 or price <= 0:
        raise ValueError("quantity and price must be > 0")
    if currency == "USD" and (fx_rate is None or fx_rate <= 0):
        raise ValueError("USD 거래는 환율이 필요합니다")
    with transaction() as conn:
        if not conn.execute(
            "SELECT 1 FROM accounts WHERE account_id = ?", (account_id,)
        ).fetchone():
            raise ValueError(f"account_id {account_id} not found")
        if not conn.execute(
            "SELECT 1 FROM holdings WHERE ticker = ? AND account_id = ?",
            (ticker, account_id),
        ).fetchone():
            raise ValueError(
                f"종목 마스터에 없는 티커입니다: {ticker} (계좌 {account_id}). "
                f"먼저 '종목 관리'에서 등록하세요."
            )
        cur = conn.execute(
            """
            INSERT INTO transactions
                (trade_date, account_id, ticker, side, quantity, price,
                 currency, fx_rate, fee, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (trade_date, account_id, ticker, side, quantity, price,
             currency, fx_rate, fee, note),
        )
        return cur.lastrowid


def add_initial_position(
    account_id: int,
    ticker: str,
    quantity: float,
    avg_price: float,
    avg_fx_rate: float | None = None,
    base_date: str | None = None,
    note: str | None = None,
) -> int:
    """초기 보유분(누적 평균단가)을 단일 BUY 거래로 등록.

    종목 마스터에서 통화를 가져와 자동 사용. USD면 avg_fx_rate 필수.
    내부적으로 add_transaction()을 호출하므로 평균단가·평가손익 계산이
    그대로 작동.
    """
    if base_date is None:
        from datetime import date as _date
        base_date = _date.today().isoformat()

    holding = get_holding(ticker, account_id)
    if holding is None:
        raise ValueError(
            f"종목 마스터에 없습니다: {ticker} (계좌 {account_id}). "
            "먼저 '종목 관리'에서 등록하세요."
        )
    currency = holding["currency"]

    return add_transaction(
        trade_date=base_date,
        account_id=account_id,
        ticker=ticker,
        side="BUY",
        quantity=quantity,
        price=avg_price,
        currency=currency,
        fx_rate=avg_fx_rate if currency == "USD" else None,
        fee=0,
        note=note or "초기 보유분 (평균단가 기준)",
    )


def list_transactions(
    account_id: int | None = None, limit: int = 100
) -> list[sqlite3.Row]:
    sql = """
        SELECT t.*, a.name AS account_name, h.name AS ticker_name
        FROM transactions t
        JOIN accounts a ON a.account_id = t.account_id
        LEFT JOIN holdings h ON h.account_id = t.account_id AND h.ticker = t.ticker
        WHERE 1=1
    """
    params: list = []
    if account_id is not None:
        sql += " AND t.account_id = ?"
        params.append(account_id)
    sql += " ORDER BY t.trade_date DESC, t.id DESC LIMIT ?"
    params.append(limit)
    with transaction() as conn:
        return conn.execute(sql, params).fetchall()


def delete_transaction(transaction_id: int) -> None:
    with transaction() as conn:
        conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))


# --- 분배금/배당금 CRUD ---

def add_dividend(
    pay_date: str,
    account_id: int,
    ticker: str,
    gross_amount: float,
    net_amount: float,
    currency: str,
    withholding_tax: float = 0,
    fx_rate: float | None = None,
    note: str | None = None,
) -> int:
    if currency not in ("KRW", "USD"):
        raise ValueError(f"invalid currency: {currency}")
    if gross_amount <= 0:
        raise ValueError("gross_amount must be > 0")
    if currency == "USD" and (fx_rate is None or fx_rate <= 0):
        raise ValueError("USD 분배금은 환율이 필요합니다")

    if currency == "USD":
        gross_krw = gross_amount * fx_rate
        net_krw = net_amount * fx_rate
    else:
        gross_krw = gross_amount
        net_krw = net_amount

    with transaction() as conn:
        if not conn.execute(
            "SELECT 1 FROM accounts WHERE account_id = ?", (account_id,)
        ).fetchone():
            raise ValueError(f"account_id {account_id} not found")
        if not conn.execute(
            "SELECT 1 FROM holdings WHERE ticker = ? AND account_id = ?",
            (ticker, account_id),
        ).fetchone():
            raise ValueError(
                f"종목 마스터에 없는 티커입니다: {ticker} (계좌 {account_id})"
            )
        cur = conn.execute(
            """
            INSERT INTO dividends
                (pay_date, account_id, ticker, gross_amount, withholding_tax,
                 net_amount, currency, fx_rate, gross_krw, net_krw, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (pay_date, account_id, ticker, gross_amount, withholding_tax,
             net_amount, currency, fx_rate, gross_krw, net_krw, note),
        )
        return cur.lastrowid


def list_dividends(
    account_id: int | None = None, limit: int = 100
) -> list[sqlite3.Row]:
    sql = """
        SELECT d.*, a.name AS account_name, h.name AS ticker_name
        FROM dividends d
        JOIN accounts a ON a.account_id = d.account_id
        LEFT JOIN holdings h ON h.account_id = d.account_id AND h.ticker = d.ticker
        WHERE 1=1
    """
    params: list = []
    if account_id is not None:
        sql += " AND d.account_id = ?"
        params.append(account_id)
    sql += " ORDER BY d.pay_date DESC, d.id DESC LIMIT ?"
    params.append(limit)
    with transaction() as conn:
        return conn.execute(sql, params).fetchall()


def delete_dividend(dividend_id: int) -> None:
    with transaction() as conn:
        conn.execute("DELETE FROM dividends WHERE id = ?", (dividend_id,))


def find_unregistered_tickers(
    tickers: list[str], account_id: int
) -> list[str]:
    """특정 계좌 기준으로 등록되지 않은 티커 목록 반환 (CSV 임포트용)."""
    if not tickers:
        return []
    placeholders = ",".join("?" * len(tickers))
    with transaction() as conn:
        rows = conn.execute(
            f"""
            SELECT ticker FROM holdings
            WHERE account_id = ? AND ticker IN ({placeholders})
            """,
            [account_id, *tickers],
        ).fetchall()
        registered = {r["ticker"] for r in rows}
    return [t for t in tickers if t not in registered]
