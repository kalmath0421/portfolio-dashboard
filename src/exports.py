"""세무사 전달용 CSV 내보내기 — 분배금 / 매매 / 외국납부세액."""
from __future__ import annotations

import csv
import io
from datetime import date

from src import db, tax


def _norm_date(d) -> str:
    if isinstance(d, date):
        return d.isoformat()
    return str(d)


def _to_date(d) -> date:
    if isinstance(d, date):
        return d
    return date.fromisoformat(_norm_date(d))


def _fy_filter(rows: list[dict], fy: int, fy_end_month: int, date_field: str) -> list[dict]:
    """사업연도 범위 내 행만 필터."""
    start, end = tax.fiscal_year_bounds(fy, fy_end_month)
    out = []
    for r in rows:
        d = _to_date(r[date_field])
        if start <= d <= end:
            out.append(r)
    return out


def export_dividends_csv(fy: int, fy_end_month: int = 12) -> str:
    sql = """
        SELECT d.*, a.name AS account_name, a.kind AS account_kind, a.broker,
               h.name AS ticker_name
        FROM dividends d
        JOIN accounts a ON a.account_id = d.account_id
        LEFT JOIN holdings h ON h.account_id = d.account_id AND h.ticker = d.ticker
        ORDER BY d.pay_date
    """
    with db.transaction() as conn:
        rows = [dict(r) for r in conn.execute(sql).fetchall()]
    rows = _fy_filter(rows, fy, fy_end_month, "pay_date")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "지급일", "계좌명", "계좌종류", "증권사", "티커", "종목명",
        "통화", "세전금액(현지)", "원천징수(현지)", "입금액(현지)",
        "환율", "세전금액(KRW)", "입금액(KRW)", "메모",
    ])
    for r in rows:
        writer.writerow([
            _norm_date(r["pay_date"]),
            r.get("account_name") or "",
            db.KINDS.get(r.get("account_kind"), ""),
            r.get("broker") or "",
            r["ticker"],
            r.get("ticker_name") or "",
            r["currency"],
            f"{float(r['gross_amount'] or 0):.4f}",
            f"{float(r['withholding_tax'] or 0):.4f}",
            f"{float(r['net_amount'] or 0):.4f}",
            f"{float(r['fx_rate']):.2f}" if r.get("fx_rate") else "",
            int(r["gross_krw"] or 0),
            int(r["net_krw"] or 0),
            r.get("note") or "",
        ])
    return buf.getvalue()


def export_transactions_csv(fy: int, fy_end_month: int = 12) -> str:
    sql = """
        SELECT t.*, a.name AS account_name, a.kind AS account_kind, a.broker,
               h.name AS ticker_name, h.category
        FROM transactions t
        JOIN accounts a ON a.account_id = t.account_id
        LEFT JOIN holdings h ON h.account_id = t.account_id AND h.ticker = t.ticker
        ORDER BY t.trade_date, t.id
    """
    with db.transaction() as conn:
        rows = [dict(r) for r in conn.execute(sql).fetchall()]
    rows = _fy_filter(rows, fy, fy_end_month, "trade_date")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "거래일", "계좌명", "계좌종류", "증권사", "티커", "종목명", "카테고리",
        "통화", "구분", "수량", "단가(현지)", "환율", "수수료(KRW)",
        "실현손익(KRW)", "메모",
    ])
    for r in rows:
        realized = r.get("realized_pnl_krw")
        writer.writerow([
            _norm_date(r["trade_date"]),
            r.get("account_name") or "",
            db.KINDS.get(r.get("account_kind"), ""),
            r.get("broker") or "",
            r["ticker"],
            r.get("ticker_name") or "",
            db.CATEGORIES.get(r.get("category"), ""),
            r["currency"],
            "매수" if r["side"] == "BUY" else "매도",
            f"{float(r['quantity']):.4f}",
            f"{float(r['price']):.4f}",
            f"{float(r['fx_rate']):.2f}" if r.get("fx_rate") else "",
            int(r["fee"] or 0),
            int(realized) if realized is not None else "",
            r.get("note") or "",
        ])
    return buf.getvalue()


def export_foreign_tax_csv(fy: int, fy_end_month: int = 12) -> str:
    """외국납부세액 — USD 종목 + 원천징수 > 0 분배금만 추출."""
    sql = """
        SELECT d.*, a.name AS account_name, h.name AS ticker_name
        FROM dividends d
        JOIN accounts a ON a.account_id = d.account_id
        LEFT JOIN holdings h ON h.account_id = d.account_id AND h.ticker = d.ticker
        WHERE d.currency = 'USD' AND d.withholding_tax > 0
        ORDER BY d.pay_date
    """
    with db.transaction() as conn:
        rows = [dict(r) for r in conn.execute(sql).fetchall()]
    rows = _fy_filter(rows, fy, fy_end_month, "pay_date")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "지급일", "계좌명", "티커", "종목명",
        "세전금액(USD)", "원천징수(USD)", "환율",
        "세전금액(KRW)", "원천징수(KRW)",
    ])
    for r in rows:
        wh_local = float(r["withholding_tax"] or 0)
        fx = float(r["fx_rate"] or 0)
        wh_krw = int(wh_local * fx) if fx > 0 else 0
        writer.writerow([
            _norm_date(r["pay_date"]),
            r.get("account_name") or "",
            r["ticker"],
            r.get("ticker_name") or "",
            f"{float(r['gross_amount'] or 0):.4f}",
            f"{wh_local:.4f}",
            f"{fx:.2f}" if fx > 0 else "",
            int(r["gross_krw"] or 0),
            wh_krw,
        ])
    return buf.getvalue()


def to_excel_bytes(csv_text: str) -> bytes:
    """한국어 엑셀에서 깨지지 않도록 UTF-8 BOM 부착."""
    return ("\ufeff" + csv_text).encode("utf-8")
