"""포트폴리오 분석 — 평균단가, 실현/미실현 손익, 분배수익률, 기여도.

이동평균법으로 매수 시점마다 평균단가 갱신, 매도 시 평균단가 기준 실현손익 계산.
USD 종목은 매수·매도 시점 환율을 별도 가중평균으로 추적해 환차손익 분리 가능.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Iterable

from src import db


D = Decimal


@dataclass
class PositionState:
    """이동평균법 기준 종목 상태."""

    ticker: str
    account_id: int
    currency: str
    quantity: Decimal = D(0)
    avg_cost_local: Decimal = D(0)        # 현지 통화 기준 평균 매수단가
    avg_cost_fx: Decimal = D(0)           # USD 종목의 매수 시점 가중평균 환율
    cumulative_buy_fee_krw: Decimal = D(0)  # 보유 잔량에 귀속되는 매수 수수료 (KRW)
    realized_pnl_krw: Decimal = D(0)
    cumulative_dividend_gross_krw: Decimal = D(0)
    cumulative_dividend_net_krw: Decimal = D(0)


def _empty_state(ticker: str, account_id: int, currency: str) -> PositionState:
    return PositionState(ticker=ticker, account_id=account_id, currency=currency)


def replay_positions(
    transactions: Iterable[dict],
    dividends: Iterable[dict] | None = None,
    on_sell: Callable[[dict, Decimal], None] | None = None,
) -> dict[tuple[int, str], PositionState]:
    """거래내역을 시간순으로 재생해 종목별 (account_id, ticker) 상태 산출.

    - transactions: 'trade_date', 'account_id', 'ticker', 'side', 'quantity',
                    'price', 'currency', 'fx_rate', 'fee' (KRW)
    - dividends: 'pay_date', 'account_id', 'ticker', 'gross_krw', 'net_krw'
    - on_sell: 매도 거래마다 (tx_dict, realized_pnl_krw) 로 호출되는 콜백.
               거래목록에 거래별 P/L 컬럼 표시할 때 사용.
    """
    states: dict[tuple[int, str], PositionState] = {}

    sorted_tx = sorted(
        transactions,
        key=lambda t: (str(t["trade_date"]), t.get("id") or 0),
    )

    for tx in sorted_tx:
        key = (tx["account_id"], tx["ticker"])
        state = states.setdefault(
            key, _empty_state(tx["ticker"], tx["account_id"], tx["currency"])
        )
        qty = D(str(tx["quantity"]))
        price = D(str(tx["price"]))
        fx = D(str(tx["fx_rate"])) if tx.get("fx_rate") else D(0)
        fee = D(str(tx.get("fee") or 0))

        if tx["side"] == "BUY":
            new_qty = state.quantity + qty
            if new_qty <= 0:
                # 데이터 이상 — 무시하지 말고 그대로 누적
                state.quantity = new_qty
                continue
            # 가중평균 매수단가 갱신
            state.avg_cost_local = (
                (state.avg_cost_local * state.quantity + price * qty) / new_qty
            )
            if state.currency == "USD":
                state.avg_cost_fx = (
                    (state.avg_cost_fx * state.quantity + fx * qty) / new_qty
                )
            state.quantity = new_qty
            # 매수 수수료(KRW)는 잔량에 누적 — 매도 시 비례 소진
            state.cumulative_buy_fee_krw += fee
        elif tx["side"] == "SELL":
            if qty > state.quantity:
                # 매도 수량이 보유보다 많으면 보유분만큼만 매도된 것으로 처리
                qty = state.quantity
            # 매도 비율만큼 누적 매수 수수료 소진 (실현손익에 차감)
            consumed_buy_fee = D(0)
            if state.quantity > 0:
                sold_ratio = qty / state.quantity
                consumed_buy_fee = state.cumulative_buy_fee_krw * sold_ratio
                state.cumulative_buy_fee_krw -= consumed_buy_fee
            if state.currency == "USD":
                if state.avg_cost_fx <= 0 or fx <= 0:
                    realized = D(0)
                else:
                    sell_krw = qty * price * fx
                    cost_krw = qty * state.avg_cost_local * state.avg_cost_fx
                    realized = sell_krw - cost_krw - consumed_buy_fee - fee
            else:
                sell_krw = qty * price
                cost_krw = qty * state.avg_cost_local
                realized = sell_krw - cost_krw - consumed_buy_fee - fee
            state.realized_pnl_krw += realized
            state.quantity -= qty
            if state.quantity == 0:
                state.avg_cost_local = D(0)
                state.avg_cost_fx = D(0)
                state.cumulative_buy_fee_krw = D(0)
            if on_sell is not None:
                on_sell(tx, realized)
        else:
            raise ValueError(f"unknown side: {tx['side']}")

    if dividends:
        for div in sorted(dividends, key=lambda d: str(d["pay_date"])):
            key = (div["account_id"], div["ticker"])
            state = states.setdefault(
                key,
                _empty_state(div["ticker"], div["account_id"], div.get("currency", "KRW")),
            )
            state.cumulative_dividend_gross_krw += D(str(div.get("gross_krw") or 0))
            state.cumulative_dividend_net_krw += D(str(div.get("net_krw") or 0))

    return states


@dataclass
class HoldingValuation:
    ticker: str
    account_id: int
    currency: str
    quantity: Decimal
    avg_cost_local: Decimal
    avg_cost_fx: Decimal | None
    current_price_local: Decimal | None
    current_fx: Decimal | None
    # 현지통화 기준
    cost_basis_local: Decimal | None        # 현지통화 매수원가
    market_value_local: Decimal | None      # 현지통화 평가금액
    unrealized_pnl_local: Decimal | None    # 현지통화 미실현 손익
    return_pct_local: Decimal | None        # 현지통화 수익률 (%)
    # 원화 기준
    cost_basis_krw: Decimal | None
    market_value_krw: Decimal | None
    unrealized_pnl_krw: Decimal | None
    return_pct_krw: Decimal | None          # 원화 수익률 (%)
    # 일일 변동 (시장 캘린더 기준 직전 거래일 종가 대비)
    previous_price_local: Decimal | None = None
    daily_change_local: Decimal | None = None      # qty × (cur - prev)
    daily_change_krw: Decimal | None = None        # 위에 현재 환율 곱 (USD)
    daily_change_pct: Decimal | None = None        # (cur - prev) / prev × 100
    # 누적
    realized_pnl_krw: Decimal = Decimal(0)
    cumulative_dividend_gross_krw: Decimal = Decimal(0)
    cumulative_dividend_net_krw: Decimal = Decimal(0)
    is_price_stale: bool = False


def _safe_pct(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator <= 0:
        return None
    return (numerator / denominator * D(100)).quantize(D("0.01"))


def value_position(
    state: PositionState,
    current_price_local: Decimal | float | None,
    current_fx: Decimal | float | None,
    is_price_stale: bool = False,
    previous_price_local: Decimal | float | None = None,
) -> HoldingValuation:
    """현재가 + 환율로 손익·수익률(현지/원화 양쪽)을 계산해 HoldingValuation 생성.

    ``previous_price_local`` 이 주어지면 일일 변동(시장 직전 거래일 대비)도 계산.
    USD 종목은 KRW 환산에 ``current_fx`` 를 씀 (어제 환율은 일단 무시 — 일일 P&L
    표시 목적상 가격 변동을 깨끗이 보여주는 게 우선).
    """
    cp = D(str(current_price_local)) if current_price_local is not None else None
    fx = D(str(current_fx)) if current_fx is not None else None
    pp = (
        D(str(previous_price_local))
        if previous_price_local is not None else None
    )

    cost_local: Decimal | None = None
    mv_local: Decimal | None = None
    pnl_local: Decimal | None = None
    ret_local: Decimal | None = None
    cost_krw: Decimal | None = None
    mv_krw: Decimal | None = None
    pnl_krw: Decimal | None = None
    ret_krw: Decimal | None = None

    if state.quantity > 0:
        # 현지통화 매수원가는 항상 산출 가능 (현재가 없어도)
        cost_local = state.quantity * state.avg_cost_local
        if state.currency == "USD" and state.avg_cost_fx > 0:
            cost_krw = (
                state.quantity * state.avg_cost_local * state.avg_cost_fx
                + state.cumulative_buy_fee_krw
            )
        elif state.currency == "KRW":
            cost_local = cost_local + state.cumulative_buy_fee_krw
            cost_krw = cost_local

        if cp is not None:
            mv_local = state.quantity * cp
            pnl_local = mv_local - cost_local
            ret_local = _safe_pct(pnl_local, cost_local)

            if state.currency == "USD":
                if fx is not None and state.avg_cost_fx > 0:
                    mv_krw = state.quantity * cp * fx
                    pnl_krw = mv_krw - cost_krw
                    ret_krw = _safe_pct(pnl_krw, cost_krw)
            else:  # KRW
                mv_krw = mv_local
                pnl_krw = pnl_local
                ret_krw = ret_local

    # 일일 변동 — 보유분에 한해 (current - previous) × qty.
    daily_local: Decimal | None = None
    daily_krw: Decimal | None = None
    daily_pct: Decimal | None = None
    if state.quantity > 0 and cp is not None and pp is not None and pp > 0:
        diff = cp - pp
        daily_local = state.quantity * diff
        daily_pct = (diff / pp * D(100)).quantize(D("0.01"))
        if state.currency == "USD":
            if fx is not None and fx > 0:
                daily_krw = state.quantity * diff * fx
        else:  # KRW
            daily_krw = daily_local

    return HoldingValuation(
        ticker=state.ticker,
        account_id=state.account_id,
        currency=state.currency,
        quantity=state.quantity,
        avg_cost_local=state.avg_cost_local,
        avg_cost_fx=state.avg_cost_fx if state.currency == "USD" else None,
        current_price_local=cp,
        current_fx=fx if state.currency == "USD" else None,
        cost_basis_local=cost_local,
        market_value_local=mv_local,
        unrealized_pnl_local=pnl_local,
        return_pct_local=ret_local,
        cost_basis_krw=cost_krw,
        market_value_krw=mv_krw,
        unrealized_pnl_krw=pnl_krw,
        return_pct_krw=ret_krw,
        previous_price_local=pp,
        daily_change_local=daily_local,
        daily_change_krw=daily_krw,
        daily_change_pct=daily_pct,
        realized_pnl_krw=state.realized_pnl_krw,
        cumulative_dividend_gross_krw=state.cumulative_dividend_gross_krw,
        cumulative_dividend_net_krw=state.cumulative_dividend_net_krw,
        is_price_stale=is_price_stale,
    )


# --- 기여도 / 집계 ---

def total_market_value(valuations: Iterable[HoldingValuation]) -> Decimal:
    return sum(
        (v.market_value_krw for v in valuations if v.market_value_krw is not None),
        D(0),
    )


def total_unrealized(valuations: Iterable[HoldingValuation]) -> Decimal:
    return sum(
        (v.unrealized_pnl_krw for v in valuations if v.unrealized_pnl_krw is not None),
        D(0),
    )


def contribution_breakdown(
    valuations: Iterable[HoldingValuation],
) -> list[dict]:
    """각 종목의 미실현손익 기여도 (총합 대비 %).

    음/양 모두 포함. 절대값 합으로 비율 계산.
    """
    items = [v for v in valuations if v.unrealized_pnl_krw is not None]
    if not items:
        return []
    abs_sum = sum((abs(v.unrealized_pnl_krw) for v in items), D(0))
    out = []
    for v in items:
        share = (
            (v.unrealized_pnl_krw / abs_sum * D(100)) if abs_sum > 0 else D(0)
        )
        out.append(
            {
                "ticker": v.ticker,
                "account_id": v.account_id,
                "unrealized_pnl_krw": v.unrealized_pnl_krw,
                "contribution_pct": share,
            }
        )
    out.sort(key=lambda d: d["unrealized_pnl_krw"], reverse=True)
    return out


def fx_attribution_usd(
    state: PositionState,
    current_price_local: Decimal | float,
    current_fx: Decimal | float,
) -> dict[str, Decimal]:
    """USD 종목의 손익을 가격 변동분 vs 환율 변동분으로 분해.

    - price_effect: 환율 고정(매수환율) 가정 시 가격 변동에 의한 KRW 손익
    - fx_effect: 가격 고정(매수가) 가정 시 환율 변동에 의한 KRW 손익
    - cross_term: 두 변수 모두 변동에서 오는 잔차 (작지만 분리해 표시)
    """
    if state.currency != "USD" or state.quantity <= 0:
        return {"price_effect": D(0), "fx_effect": D(0), "cross_term": D(0)}

    cp = D(str(current_price_local))
    fx = D(str(current_fx))
    qty = state.quantity
    p0 = state.avg_cost_local
    fx0 = state.avg_cost_fx

    if fx0 <= 0:
        return {"price_effect": D(0), "fx_effect": D(0), "cross_term": D(0)}

    price_effect = qty * (cp - p0) * fx0
    fx_effect = qty * p0 * (fx - fx0)
    cross_term = qty * (cp - p0) * (fx - fx0)

    return {
        "price_effect": price_effect,
        "fx_effect": fx_effect,
        "cross_term": cross_term,
    }


# --- DB 통합 헬퍼 ---

def realized_pnl_by_tx_id() -> dict[int, Decimal]:
    """전 종목 거래 replay 후 매도 거래 id → 실현손익(KRW) 매핑.

    거래 목록 테이블에 거래별 P/L 컬럼을 표시하기 위해 사용.
    """
    sql_tx = """
        SELECT id, trade_date, account_id, ticker, side, quantity, price,
               currency, fx_rate, fee
        FROM transactions
    """
    with db.transaction() as conn:
        tx_rows = [dict(r) for r in conn.execute(sql_tx).fetchall()]

    pnl_by_id: dict[int, Decimal] = {}

    def _record(tx: dict, realized: Decimal) -> None:
        if tx.get("id") is not None:
            pnl_by_id[int(tx["id"])] = realized

    replay_positions(tx_rows, on_sell=_record)
    return pnl_by_id


def load_states_from_db(account_id: int | None = None) -> dict[tuple[int, str], PositionState]:
    """DB의 transactions/dividends를 읽어 현재 포지션 상태 산출."""
    sql_tx = """
        SELECT id, trade_date, account_id, ticker, side, quantity, price,
               currency, fx_rate, fee
        FROM transactions
    """
    sql_div = """
        SELECT pay_date, account_id, ticker, currency, gross_krw, net_krw
        FROM dividends
    """
    params_tx: list = []
    params_div: list = []
    if account_id is not None:
        sql_tx += " WHERE account_id = ?"
        sql_div += " WHERE account_id = ?"
        params_tx.append(account_id)
        params_div.append(account_id)

    with db.transaction() as conn:
        tx_rows = [dict(r) for r in conn.execute(sql_tx, params_tx).fetchall()]
        div_rows = [dict(r) for r in conn.execute(sql_div, params_div).fetchall()]

    return replay_positions(tx_rows, div_rows)


def value_history(
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """일별 총 평가금액 시계열.

    - 각 날짜에 대해 그날까지의 거래내역 누적 → 보유수량
    - 그날의 price_snapshot + fx_snapshot 으로 KRW 평가금액 산출
    - 시세 스냅샷이 있는 날짜만 시계열에 포함됨 (사용자가 매일 갱신할수록 풍부해짐)

    Returns: [{"date": "YYYY-MM-DD", "value_krw": Decimal, "cost_krw": Decimal}, ...]
    """
    sql_tx = "SELECT * FROM transactions"
    sql_price = "SELECT * FROM price_snapshots"
    sql_fx = "SELECT * FROM fx_snapshots"
    params_p: list = []
    params_f: list = []
    where_p = []
    where_f = []
    if start_date:
        where_p.append("snapshot_date >= ?")
        params_p.append(start_date)
        where_f.append("snapshot_date >= ?")
        params_f.append(start_date)
    if end_date:
        where_p.append("snapshot_date <= ?")
        params_p.append(end_date)
        where_f.append("snapshot_date <= ?")
        params_f.append(end_date)
    if where_p:
        sql_price += " WHERE " + " AND ".join(where_p)
        sql_fx += " WHERE " + " AND ".join(where_f)
    sql_price += " ORDER BY snapshot_date"
    sql_fx += " ORDER BY snapshot_date"
    sql_tx += " ORDER BY trade_date, id"

    with db.transaction() as conn:
        tx_rows = [dict(r) for r in conn.execute(sql_tx).fetchall()]
        price_rows = [dict(r) for r in conn.execute(sql_price, params_p).fetchall()]
        fx_rows = [dict(r) for r in conn.execute(sql_fx, params_f).fetchall()]

    if not price_rows:
        return []

    def _norm_date(d) -> str:
        return d if isinstance(d, str) else d.isoformat()

    # 날짜별 가격 맵
    prices_by_date: dict[str, dict[str, tuple[float, str]]] = {}
    for p in price_rows:
        d = _norm_date(p["snapshot_date"])
        prices_by_date.setdefault(d, {})[p["ticker"]] = (
            float(p["close_price"]), p["currency"],
        )

    fx_by_date: dict[str, float] = {
        _norm_date(f["snapshot_date"]): float(f["usdkrw"]) for f in fx_rows
    }

    sorted_dates = sorted(prices_by_date.keys())
    out: list[dict] = []

    # 거래 내역을 날짜 오름차순으로 보면서 보유수량/원가 누적
    tx_idx = 0
    sorted_tx = sorted(tx_rows, key=lambda t: (_norm_date(t["trade_date"]), t["id"]))
    holdings: dict[tuple[int, str], dict] = {}

    for d in sorted_dates:
        # d 이전 또는 같은 날짜 거래 모두 반영
        while tx_idx < len(sorted_tx) and _norm_date(sorted_tx[tx_idx]["trade_date"]) <= d:
            tx = sorted_tx[tx_idx]
            tx_idx += 1
            key = (tx["account_id"], tx["ticker"])
            h = holdings.setdefault(key, {
                "qty": D(0), "cost_local": D(0), "cost_fx": D(0),
                "currency": tx["currency"],
            })
            qty = D(str(tx["quantity"]))
            price = D(str(tx["price"]))
            fx = D(str(tx["fx_rate"])) if tx.get("fx_rate") else D(0)
            if tx["side"] == "BUY":
                new_qty = h["qty"] + qty
                if new_qty > 0:
                    h["cost_local"] = (h["cost_local"] * h["qty"] + price * qty) / new_qty
                    if h["currency"] == "USD":
                        h["cost_fx"] = (h["cost_fx"] * h["qty"] + fx * qty) / new_qty
                h["qty"] = new_qty
            else:  # SELL
                if qty > h["qty"]:
                    qty = h["qty"]
                h["qty"] -= qty
                if h["qty"] == 0:
                    h["cost_local"] = D(0)
                    h["cost_fx"] = D(0)

        # 평가금액·원가 KRW 합산
        total_value = D(0)
        total_cost = D(0)
        for (acct, ticker), h in holdings.items():
            if h["qty"] <= 0:
                continue
            price_info = prices_by_date[d].get(ticker)
            if price_info is None:
                continue
            close, cur = price_info
            close_d = D(str(close))
            if cur == "USD":
                fx = D(str(fx_by_date.get(d, 0)))
                if fx <= 0 or h["cost_fx"] <= 0:
                    continue
                total_value += h["qty"] * close_d * fx
                total_cost += h["qty"] * h["cost_local"] * h["cost_fx"]
            else:
                total_value += h["qty"] * close_d
                total_cost += h["qty"] * h["cost_local"]

        out.append({
            "date": d,
            "value_krw": total_value,
            "cost_krw": total_cost,
        })

    return out


def dividend_monthly(account_id: int | None = None) -> list[dict]:
    """월별 분배금 합계 (KRW)."""
    sql = """
        SELECT pay_date, gross_krw, net_krw
        FROM dividends
        WHERE 1=1
    """
    params: list = []
    if account_id is not None:
        sql += " AND account_id = ?"
        params.append(account_id)
    sql += " ORDER BY pay_date"
    with db.transaction() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    if not rows:
        return []

    monthly: dict[str, dict[str, Decimal]] = {}
    for r in rows:
        d = r["pay_date"] if isinstance(r["pay_date"], str) else r["pay_date"].isoformat()
        ym = d[:7]
        agg = monthly.setdefault(ym, {"gross": D(0), "net": D(0)})
        agg["gross"] += D(str(r["gross_krw"] or 0))
        agg["net"] += D(str(r["net_krw"] or 0))
    return [
        {"month": ym, "gross_krw": v["gross"], "net_krw": v["net"]}
        for ym, v in sorted(monthly.items())
    ]


def aggregate_by_account(
    valuations: Iterable[HoldingValuation],
) -> dict[int, dict[str, Decimal]]:
    """계좌별 통화별 합계.

    KRW 환산 합계와 함께, 통화별 현지 합계도 분리해 반환.
    USD 종목 평가금액 합계와 KRW 환산을 별도 표시할 수 있도록.
    """
    out: dict[int, dict[str, Decimal]] = defaultdict(
        lambda: {
            # KRW 환산 (전체 합산)
            "cost_basis_krw": D(0),
            "market_value_krw": D(0),
            "unrealized_pnl_krw": D(0),
            "realized_pnl_krw": D(0),
            "dividend_gross_krw": D(0),
            "dividend_net_krw": D(0),
            # 일일 변동 (시장 직전 거래일 종가 대비) — prev_close 가 있는 종목만 합산
            "daily_change_krw": D(0),
            # 통화별 현지 합계
            "market_value_usd": D(0),
            "cost_basis_usd": D(0),
            "unrealized_pnl_usd": D(0),
            "market_value_krw_only": D(0),     # KRW 종목만의 합 (환산 아님, 그대로)
            "cost_basis_krw_only": D(0),
            "unrealized_pnl_krw_only": D(0),
        }
    )
    for v in valuations:
        agg = out[v.account_id]
        if v.cost_basis_krw is not None:
            agg["cost_basis_krw"] += v.cost_basis_krw
        if v.market_value_krw is not None:
            agg["market_value_krw"] += v.market_value_krw
        if v.unrealized_pnl_krw is not None:
            agg["unrealized_pnl_krw"] += v.unrealized_pnl_krw
        if v.daily_change_krw is not None:
            agg["daily_change_krw"] += v.daily_change_krw
        agg["realized_pnl_krw"] += v.realized_pnl_krw
        agg["dividend_gross_krw"] += v.cumulative_dividend_gross_krw
        agg["dividend_net_krw"] += v.cumulative_dividend_net_krw

        if v.currency == "USD":
            if v.market_value_local is not None:
                agg["market_value_usd"] += v.market_value_local
            if v.cost_basis_local is not None:
                agg["cost_basis_usd"] += v.cost_basis_local
            if v.unrealized_pnl_local is not None:
                agg["unrealized_pnl_usd"] += v.unrealized_pnl_local
        elif v.currency == "KRW":
            if v.market_value_local is not None:
                agg["market_value_krw_only"] += v.market_value_local
            if v.cost_basis_local is not None:
                agg["cost_basis_krw_only"] += v.cost_basis_local
            if v.unrealized_pnl_local is not None:
                agg["unrealized_pnl_krw_only"] += v.unrealized_pnl_local
    return dict(out)


def fx_attribution_table(
    valuations: Iterable[HoldingValuation],
    states: dict[tuple[int, str], PositionState],
) -> list[dict]:
    """USD 종목별 환율 영향 분리 (가격/환율/교차항). KRW 단위.

    명세서 6.3 — 가격 변동분 vs 환율 변동분.
    """
    rows: list[dict] = []
    for v in valuations:
        if v.currency != "USD" or v.quantity <= 0:
            continue
        if v.current_price_local is None or v.current_fx is None:
            continue
        state = states.get((v.account_id, v.ticker))
        if state is None:
            continue
        attr = fx_attribution_usd(state, v.current_price_local, v.current_fx)
        rows.append(
            {
                "ticker": v.ticker,
                "account_id": v.account_id,
                "price_effect_krw": attr["price_effect"],
                "fx_effect_krw": attr["fx_effect"],
                "cross_term_krw": attr["cross_term"],
                "total_unrealized_krw": (
                    attr["price_effect"] + attr["fx_effect"] + attr["cross_term"]
                ),
            }
        )
    return rows
