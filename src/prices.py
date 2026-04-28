"""시세·환율 조회 모듈.

명세서 9장 원칙: 시세 조회 실패 시 마지막 스냅샷 사용 + 화면 경고. 임의 가격 생성 금지.

- 미국 주식/ETF: yfinance
- 국내 주식/ETF: pykrx
- USD/KRW: yfinance ('KRW=X' 또는 'USDKRW=X')
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from src import db


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PriceResult:
    ticker: str
    price: float
    currency: str
    as_of: date
    source: str  # "yfinance", "pykrx", "snapshot"
    is_stale: bool  # True면 라이브 조회 실패 → 마지막 스냅샷 사용
    # 시장 캘린더 기준 직전 거래일 종가 — 일일 P&L 계산용. 스냅샷 폴백 또는
    # 라이브 조회가 1행만 반환했을 때 None.
    previous_close: float | None = None


@dataclass(frozen=True)
class FxResult:
    rate: float
    as_of: date
    source: str
    is_stale: bool


# --- 마지막 스냅샷 폴백 ---

def _last_price_snapshot(
    ticker: str,
) -> tuple[float, str, date, float | None] | None:
    """반환: (close_price, currency, as_of, previous_close)."""
    with db.transaction() as conn:
        row = conn.execute(
            """
            SELECT close_price, currency, snapshot_date, previous_close
            FROM price_snapshots
            WHERE ticker = ?
            ORDER BY snapshot_date DESC
            LIMIT 1
            """,
            (ticker,),
        ).fetchone()
    if not row:
        return None
    snap_date = row["snapshot_date"]
    if isinstance(snap_date, str):
        snap_date = date.fromisoformat(snap_date)
    prev = row["previous_close"]
    return float(row["close_price"]), row["currency"], snap_date, (
        float(prev) if prev is not None else None
    )


def _last_fx_snapshot() -> tuple[float, date] | None:
    with db.transaction() as conn:
        row = conn.execute(
            """
            SELECT usdkrw, snapshot_date FROM fx_snapshots
            ORDER BY snapshot_date DESC LIMIT 1
            """
        ).fetchone()
    if not row:
        return None
    snap_date = row["snapshot_date"]
    if isinstance(snap_date, str):
        snap_date = date.fromisoformat(snap_date)
    return float(row["usdkrw"]), snap_date


def _save_price_snapshot(
    ticker: str,
    price: float,
    currency: str,
    as_of: date,
    previous_close: float | None = None,
) -> None:
    with db.transaction() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO price_snapshots
                (snapshot_date, ticker, close_price, currency, previous_close)
            VALUES (?, ?, ?, ?, ?)
            """,
            (as_of.isoformat(), ticker, price, currency, previous_close),
        )


def _save_fx_snapshot(rate: float, as_of: date) -> None:
    with db.transaction() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO fx_snapshots (snapshot_date, usdkrw)
            VALUES (?, ?)
            """,
            (as_of.isoformat(), rate),
        )


# --- 라이브 조회 (외부 의존) ---

def _fetch_us_price(
    ticker: str,
) -> tuple[float, date, float | None] | None:
    """yfinance로 미국 주식/ETF 종가 + 직전 거래일 종가 조회. 실패 시 None.

    Returns: (close, as_of, previous_close).
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance가 설치되지 않음 — pip install yfinance")
        return None
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d", interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            return None
        last_idx = hist.index[-1]
        close = float(hist["Close"].iloc[-1])
        as_of = last_idx.date() if hasattr(last_idx, "date") else date.today()
        prev: float | None = None
        if len(hist) >= 2:
            prev = float(hist["Close"].iloc[-2])
        return close, as_of, prev
    except Exception as e:  # 네트워크/포맷 오류 등
        logger.warning("yfinance fetch failed for %s: %s", ticker, e)
        return None


def _fetch_kr_price(
    ticker: str,
) -> tuple[float, date, float | None] | None:
    """pykrx로 국내 종목/ETF 종가 + 직전 거래일 종가 조회.

    Returns: (close, as_of, previous_close).
    """
    try:
        from pykrx import stock
    except ImportError:
        logger.warning("pykrx가 설치되지 않음")
        return None
    try:
        # 최근 ~10거래일 범위에서 마지막 두 거래일 종가
        today = date.today()
        start = (today - timedelta(days=10)).strftime("%Y%m%d")
        end = today.strftime("%Y%m%d")
        df = stock.get_market_ohlcv_by_date(start, end, ticker)
        if df is None or df.empty:
            # ETF 별도 함수
            df = stock.get_etf_ohlcv_by_date(start, end, ticker)
        if df is None or df.empty:
            return None
        close = float(df["종가"].iloc[-1])
        last_idx = df.index[-1]
        as_of = last_idx.date() if hasattr(last_idx, "date") else today
        prev: float | None = None
        if len(df) >= 2:
            prev = float(df["종가"].iloc[-2])
        return close, as_of, prev
    except Exception as e:
        logger.warning("pykrx fetch failed for %s: %s", ticker, e)
        return None


def _fetch_usdkrw() -> tuple[float, date] | None:
    """yfinance로 USDKRW 조회."""
    try:
        import yfinance as yf
    except ImportError:
        return None
    for symbol in ("KRW=X", "USDKRW=X"):
        try:
            hist = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=False)
            if hist is None or hist.empty:
                continue
            close = float(hist["Close"].iloc[-1])
            last_idx = hist.index[-1]
            as_of = last_idx.date() if hasattr(last_idx, "date") else date.today()
            return close, as_of
        except Exception as e:
            logger.warning("usdkrw fetch failed via %s: %s", symbol, e)
            continue
    return None


# --- Public API ---

def get_price(ticker: str, currency: str) -> PriceResult | None:
    """시세 조회. 라이브 → 실패 시 마지막 스냅샷 → 둘 다 없으면 None."""
    fetched: tuple[float, date, float | None] | None
    source: str
    if currency == "USD":
        fetched = _fetch_us_price(ticker)
        source = "yfinance"
    elif currency == "KRW":
        fetched = _fetch_kr_price(ticker)
        source = "pykrx"
    else:
        raise ValueError(f"unsupported currency: {currency}")

    if fetched is not None:
        price, as_of, prev_close = fetched
        _save_price_snapshot(ticker, price, currency, as_of, prev_close)
        return PriceResult(
            ticker=ticker, price=price, currency=currency,
            as_of=as_of, source=source, is_stale=False,
            previous_close=prev_close,
        )

    # 폴백: 마지막 스냅샷
    snap = _last_price_snapshot(ticker)
    if snap is None:
        logger.warning("No price available for %s", ticker)
        return None
    price, snap_currency, as_of, prev_close = snap
    return PriceResult(
        ticker=ticker, price=price, currency=snap_currency,
        as_of=as_of, source="snapshot", is_stale=True,
        previous_close=prev_close,
    )


def get_usdkrw() -> FxResult | None:
    fetched = _fetch_usdkrw()
    if fetched is not None:
        rate, as_of = fetched
        _save_fx_snapshot(rate, as_of)
        return FxResult(rate=rate, as_of=as_of, source="yfinance", is_stale=False)

    snap = _last_fx_snapshot()
    if snap is None:
        return None
    rate, as_of = snap
    return FxResult(rate=rate, as_of=as_of, source="snapshot", is_stale=True)


def snapshot_is_today(ticker: str) -> bool:
    today = date.today().isoformat()
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT 1 FROM price_snapshots WHERE ticker = ? AND snapshot_date = ?",
            (ticker, today),
        ).fetchone()
    return row is not None


def fx_snapshot_is_today() -> bool:
    today = date.today().isoformat()
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT 1 FROM fx_snapshots WHERE snapshot_date = ?", (today,)
        ).fetchone()
    return row is not None


def auto_refresh_prices(holdings) -> dict:
    """페이지 첫 진입용 — 오늘자 스냅샷이 없는 종목만 라이브 호출.

    이미 오늘자 데이터가 있으면 그대로 사용 (외부 호출 생략, 빠름).
    라이브 호출 실패 시 마지막 스냅샷으로 폴백 (is_stale=True).
    """
    cache: dict = {}
    seen: set[tuple[str, str]] = set()
    for h in holdings:
        key = (h["ticker"], h["currency"])
        if key in seen:
            continue
        seen.add(key)
        if snapshot_is_today(h["ticker"]):
            snap = _last_price_snapshot(h["ticker"])
            if snap:
                price, snap_currency, as_of, prev_close = snap
                cache[key] = PriceResult(
                    ticker=h["ticker"], price=price,
                    currency=snap_currency, as_of=as_of,
                    source="snapshot", is_stale=False,
                    previous_close=prev_close,
                )
                continue
        # 오늘자 없음 — 라이브 호출 (실패 시 폴백)
        result = get_price(h["ticker"], h["currency"])
        if result is not None:
            cache[key] = result
    return cache


def auto_refresh_fx() -> FxResult | None:
    """오늘자 환율이 이미 있으면 그대로, 없으면 라이브 호출."""
    if fx_snapshot_is_today():
        snap = _last_fx_snapshot()
        if snap:
            rate, as_of = snap
            return FxResult(rate=rate, as_of=as_of, source="snapshot", is_stale=False)
    return get_usdkrw()


def load_cached_prices(holdings) -> dict:
    """DB에 저장된 마지막 스냅샷만 빠르게 읽어 캐시 형태로 반환 (외부 호출 없음).

    화면 첫 로드 시 즉시 가격을 표시하기 위해 사용. 사용자가 '🔄 시세 갱신'
    버튼을 누르면 라이브 조회로 갱신된다.
    """
    cache: dict = {}
    seen: set[tuple[str, str]] = set()
    for h in holdings:
        key = (h["ticker"], h["currency"])
        if key in seen:
            continue
        seen.add(key)
        snap = _last_price_snapshot(h["ticker"])
        if snap is None:
            continue
        price, snap_currency, as_of, prev_close = snap
        cache[key] = PriceResult(
            ticker=h["ticker"],
            price=price,
            currency=snap_currency,
            as_of=as_of,
            source="snapshot",
            is_stale=True,
            previous_close=prev_close,
        )
    return cache


def load_cached_fx() -> FxResult | None:
    """DB에 저장된 마지막 환율 스냅샷만 읽음."""
    snap = _last_fx_snapshot()
    if snap is None:
        return None
    rate, as_of = snap
    return FxResult(rate=rate, as_of=as_of, source="snapshot", is_stale=True)


def refresh_all_active() -> dict:
    """모든 활성 종목 시세 + USDKRW 갱신. 결과 요약 반환."""
    holdings = db.list_holdings(active_only=True)
    seen: set[tuple[str, str]] = set()
    success: list[str] = []
    stale: list[str] = []
    failed: list[str] = []

    for h in holdings:
        key = (h["ticker"], h["currency"])
        if key in seen:
            continue
        seen.add(key)
        result = get_price(h["ticker"], h["currency"])
        if result is None:
            failed.append(h["ticker"])
        elif result.is_stale:
            stale.append(h["ticker"])
        else:
            success.append(h["ticker"])

    fx_result = get_usdkrw()
    fx_status = "fresh" if (fx_result and not fx_result.is_stale) else (
        "stale" if fx_result else "missing"
    )

    return {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "success": success,
        "stale": stale,
        "failed": failed,
        "fx_status": fx_status,
        "fx_rate": fx_result.rate if fx_result else None,
    }
