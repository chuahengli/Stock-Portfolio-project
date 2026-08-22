"""Export the local portfolio SQLite DB into the star-schema CSV folder for Power BI.

Contract: powerbi/POWERBI_ROADMAP.md + AGENTS.md (the export contract is the single
source of truth for file names and columns -- KEEP THEM STABLE, the user's Power BI
work depends on them). This script implements that contract.

Usage (from the project root):
    pipenv run python -m source.export_powerbi              # full run (tries Yahoo enrichment)
    pipenv run python -m source.export_powerbi --no-enrich  # offline-safe, cache only

Output: powerbi/export/{dim_date,dim_symbol,fact_snapshots,fact_positions,
fact_cashflow,fact_trades,fact_benchmark}.csv  (7 files, utf-8-sig/BOM)

Why this file exists:
    Power BI Desktop connects to these CSVs (Get Data > Text/CSV, one file at a
    time). The user does ALL Power Query / DAX / modeling work by hand -- this
    script only produces the clean(ish) data layer: windowed benchmark, classified
    cashflow, option-aware symbol dimension. Deliberately left messy on purpose:
    Portfolio_Percent stays TEXT like "6.93%" (first Power Query exercise).
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from datetime import date
from pathlib import Path

import pandas as pd

from config import settings

EXPORT_DIR = settings.BASE_DIR / "powerbi" / "export"
META_PATH = settings.BASE_DIR / "powerbi" / "symbol_meta.json"

# Moomoo option symbol format: <UNDERLYING><YYMMDD><C|P><STRIKEx1000>
# e.g. AMZN260918C250000 -> AMZN, 2026-09-18, Call, 250.00
OPTION_RE = re.compile(r"^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d+)$")

CONTRACT_FILES = [
    "dim_date", "dim_symbol", "fact_snapshots", "fact_positions",
    "fact_cashflow", "fact_trades", "fact_benchmark",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _norm_date(v) -> str:
    """Normalise a date-ish value to YYYY-MM-DD (handles '2026-08-14 00:00:00')."""
    return str(v).strip()[:10]


def build_date_dim(inception: str, end: str) -> pd.DataFrame:
    start_dt = pd.Timestamp(inception)
    end_dt = pd.Timestamp(end)
    days = pd.date_range(start_dt, end_dt, freq="D")
    df = pd.DataFrame({
        "Date": [d.strftime("%Y-%m-%d") for d in days],
        "Year": days.year,
        "Quarter": days.quarter,
        "Month": days.month,
        "MonthName": days.strftime("%b"),
        "Day": days.day,
        "Weekday": days.dayofweek,          # Monday = 0 (Power Query convention)
        "WeekdayName": days.strftime("%a"),
        "IsWeekend": (days.dayofweek >= 5).astype(int),
    })
    df.insert(3, "QuarterLabel", "Q" + df["Quarter"].astype(str))
    return df


def parse_option_symbol(symbol: str) -> dict | None:
    """Parse an option symbol into parts; None if not an option."""
    m = OPTION_RE.match(symbol or "")
    if not m:
        return None
    under, yy, mm, dd, typ, strike_raw = m.groups()
    return {
        "Underlying": under,
        "Expiry": f"20{yy}-{mm}-{dd}",
        "Option_Type": "Call" if typ == "C" else "Put",
        "Strike": int(strike_raw) / 1000.0,
    }


# ---------------------------------------------------------------------------
# enrichment cache (sector / industry), network best-effort
# ---------------------------------------------------------------------------

def load_meta() -> dict:
    if META_PATH.exists():
        try:
            return json.loads(META_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_meta(meta: dict) -> None:
    META_PATH.parent.mkdir(parents=True, exist_ok=True)
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def enrich(tickers: list[str], meta: dict, allow_network: bool) -> dict:
    """Fill Sector/Industry for tickers missing from the cache.
    Network is best-effort (never fails the export); cache survives reruns.
    Legacy cache files used lowercase keys - read both spellings."""
    missing = sorted({t for t in tickers if t not in meta})
    if missing and allow_network:
        try:
            import yfinance as yf
            for t in missing:
                try:
                    info = (yf.Ticker(t).info) or {}
                    meta[t] = {
                        "Sector": (info.get("Sector") or info.get("sector") or "").strip(),
                        "Industry": (info.get("Industry") or info.get("industry") or "").strip(),
                    }
                except Exception:
                    meta[t] = {"Sector": "", "Industry": ""}
                time.sleep(0.1)
        except Exception:
            pass  # offline: export must never fail
    for t in missing:
        meta.setdefault(t, {"Sector": "", "Industry": ""})
    return meta


def build_dim_symbol(conn: sqlite3.Connection, allow_network: bool) -> pd.DataFrame:
    cur = conn.cursor()

    symbols: set[str] = set()
    for tbl, col in [("positions", "Symbol"), ("net_p_l", "Symbol"),
                     ("transactions", "Symbol"), ("historical_orders", "Symbol")]:
        try:
            for (s,) in cur.execute(f'SELECT DISTINCT "{col}" FROM "{tbl}"'):
                if s and not s.startswith("^"):   # benchmarks live in fact_benchmark only
                    symbols.add(s)
        except Exception:
            pass

    # Most-recent names (positions latest day first, then any other table).
    name_lk: dict[str, str] = {}
    latest = cur.execute("SELECT MAX(date) FROM positions").fetchone()[0]
    if latest:
        for s, n in cur.execute(
            "SELECT Symbol, Name FROM positions WHERE date = ? AND Name IS NOT NULL AND Name != ''",
            (latest,),
        ):
            name_lk.setdefault(s, n)
    for tbl, col in [("transactions", "Name"), ("historical_orders", "Name")]:
        try:
            for s, n in cur.execute(f'SELECT Symbol, "{col}" FROM "{tbl}" '
                                    f'WHERE "{col}" IS NOT NULL AND "{col}" != ""'):
                name_lk.setdefault(s, n)
        except Exception:
            pass

    market_lk: dict[str, str] = {}
    ccy_lk: dict[str, str] = {}
    if latest:
        for s, m, c in cur.execute(
            "SELECT Symbol, Market, Currency FROM positions WHERE date = ?", (latest,),
        ):
            market_lk.setdefault(s, m or "")
            ccy_lk.setdefault(s, c or "")

    rows = []
    stock_tickers: set[str] = set()
    for sym in sorted(symbols):
        opt = parse_option_symbol(sym)
        if opt:
            is_option = 1
            underlying = opt["Underlying"]
            multiplier = 100
            stock_tickers.add(underlying)
        else:
            is_option = 0
            underlying = ""
            multiplier = 1
            stock_tickers.add(sym)
        rows.append({
            "Symbol": sym,
            "AssetClass": "Option" if is_option else "Stock",
            "IsOption": is_option,
            "Underlying": underlying,
            "Multiplier": multiplier,
            "Name": name_lk.get(sym, sym),
            "Market": market_lk.get(sym, ""),
            "Currency": ccy_lk.get(sym, ""),
        })

    meta = enrich(list(stock_tickers), load_meta(), allow_network)
    save_meta(meta)
    for r in rows:
        parent = r["Underlying"] or r["Symbol"]
        info = meta.get(parent) or {}
        r["Sector"] = info.get("Sector") or info.get("sector") or ""
        r["Industry"] = info.get("Industry") or info.get("industry") or ""

    cols = ["Symbol", "AssetClass", "IsOption", "Underlying", "Multiplier",
            "Name", "Market", "Currency", "Sector", "Industry"]
    return pd.DataFrame(rows)[cols]


# ---------------------------------------------------------------------------
# fact builders
# ---------------------------------------------------------------------------

def build_fact_snapshots(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT date AS Date, total_assets, stocks, options, cash, nav, units "
        "FROM portfolio_snapshots ORDER BY date", conn,
    )


def build_fact_positions(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT date AS Date, Symbol, Name, Market, Quantity, Market_Value, "
        "Diluted_Cost, Current_Price, P_L_Percent, P_L, Today_s_P_L, Currency, "
        "Portfolio_Percent FROM positions ORDER BY date, Symbol", conn,
    )
    # Portfolio_Percent is intentionally kept as TEXT ("6.9%") - the user's first
    # Power Query exercise (do NOT pre-clean it here).
    return df


def build_fact_cashflow(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT cashflow_id, substr(Date,1,10) AS Date, Currency, Type, "
        "in_out, Amount, Remark, is_external, is_income FROM cashflow "
        "ORDER BY Date", conn,
    )

    def _flow(r):
        if r["is_external"]:
            return "External Capital"
        if r["is_income"]:
            return "Investment Income"
        return "Internal"
    df["CashflowCategory"] = df.apply(_flow, axis=1)
    return df


def build_fact_trades(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT Order_ID, date_time, substr(date_time,1,10) AS Date, Symbol, Name, "
        "Market, Buy_Sell, Quantity, Fill_Price, Multiplier, Gross_Amount, Currency "
        "FROM transactions ORDER BY date_time", conn,
    )
    return df


def build_fact_benchmark(conn: sqlite3.Connection, inception: str) -> pd.DataFrame:
    # Window the benchmark to the tracked period only (was ~98k rows back to 1927).
    df = pd.read_sql_query(
        "SELECT Symbol, substr(Date,1,10) AS Date, Close FROM benchmark_history "
        "WHERE substr(Date,1,10) >= ? ORDER BY Date, Symbol",
        conn, params=(inception,),
    )
    return df[["Date", "Symbol", "Close"]]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run(allow_network: bool = True) -> int:
    if not settings.MOOMOO_PORTFOLIO_DB_PATH.exists():
        print("No database found - run `pipenv run python main.py` first.")
        return 1

    conn = sqlite3.connect(settings.MOOMOO_PORTFOLIO_DB_PATH)
    inception = conn.execute("SELECT MIN(date) FROM portfolio_snapshots").fetchone()[0]
    last_snap = conn.execute("SELECT MAX(date) FROM portfolio_snapshots").fetchone()[0]
    if not inception:
        print("No snapshots in the database - run `pipenv run python main.py` first.")
        return 1

    today = date.today().isoformat()
    end = max(last_snap, today)

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    tables = {
        "dim_date": build_date_dim(inception, end),
        "dim_symbol": build_dim_symbol(conn, allow_network),
        "fact_snapshots": build_fact_snapshots(conn),
        "fact_positions": build_fact_positions(conn),
        "fact_cashflow": build_fact_cashflow(conn),
        "fact_trades": build_fact_trades(conn),
        "fact_benchmark": build_fact_benchmark(conn, inception),
    }

    for name in CONTRACT_FILES:
        path = EXPORT_DIR / f"{name}.csv"
        tables[name].to_csv(path, index=False, encoding="utf-8-sig")

    print(f"Power BI export complete. Last DB snapshot: {last_snap}.")
    print(f"Export folder: {EXPORT_DIR}")
    for name in CONTRACT_FILES:
        print(f"  {name}.csv: {len(tables[name]):>7} rows")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Export star-schema CSVs for Power BI.")
    ap.add_argument("--no-enrich", action="store_true",
                    help="Skip network sector/industry lookup (cache only).")
    return run(allow_network=not ap.parse_args().no_enrich)


if __name__ == "__main__":
    raise SystemExit(main())