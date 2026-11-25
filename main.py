"""Entry point: fetch from the broker, clean, and store one day's snapshot."""
from source import moomoo_api, cleanup, db
from source.export_powerbi import fetch_symbol_meta_bulk, load_meta
from config import settings
from datetime import date, datetime, timedelta
import os
import pandas as pd


def _summarize_frame(name, df, extra=""):
    """Log a row/column summary instead of dumping the frame (keeps the log small)."""
    if df is None:
        print(f"{name}: None")
    elif hasattr(df, "shape"):
        print(f"{name}: {df.shape[0]} row(s) x {df.shape[1]} col(s){extra}")
    else:
        print(f"{name}: present{extra}")


def get_api_data(current_date: datetime, end_date: datetime, keep_opend_alive: bool = False):
    ## Handle API
    # Initialize variables to None 
    acc_info, positions, cashflow, historical_orders = None, None, None, None
    try:
        with moomoo_api.opend_session(keep_alive=keep_opend_alive) as trade_ctx:
            # Record down raw data from api
            acc_info = moomoo_api.account_info(trade_ctx)
            positions = moomoo_api.get_positions(trade_ctx)
            cashflow = moomoo_api.account_cashflow(trade_ctx, current_date, end_date)
            historical_orders = moomoo_api.get_historical_orders(trade_ctx)
    except Exception as e:
        print(f"API Error: {e}")
    
    _summarize_frame("Acc_info", acc_info)
    _summarize_frame("Positions", positions)
    _summarize_frame("Cashflow", cashflow)
    _summarize_frame("Historical Orders", historical_orders)

    return acc_info, positions, cashflow, historical_orders

def cleanup_data(acc_info: pd.DataFrame, positions: pd.DataFrame, cashflow: pd.DataFrame, historical_orders: pd.DataFrame,current_date: datetime):
    ## Cleanup to upload to db
    print("Cleaning up data...")
    acc_info = cleanup.cleanup_acc_info(acc_info)
    positions = cleanup.cleanup_positions(positions)
    cleanup.update_portfolio_percentage(positions, cleanup.get_total_assets(acc_info))
    historical_orders = cleanup.cleanup_historical_orders(historical_orders)
    cashflow = cleanup.cleanup_cashflow(cashflow)

    _summarize_frame("Acc_info", acc_info)
    _summarize_frame("Positions", positions)
    _summarize_frame("Cashflow", cashflow)
    _summarize_frame("Historical Orders", historical_orders)

    # Split shares and options positions into separate dataframes
    shares, options = cleanup.separate_assets(positions)
    _summarize_frame("Shares Dataframe", shares)
    _summarize_frame("Options Dataframe", options)
    # Calculate Market Value of Shares and Options
    shares_mv = cleanup.sum_of_mv(shares)
    options_mv = cleanup.sum_of_mv(options)
    print("Shares Market Value (SGD): ", shares_mv)
    print("Options Market Value (SGD): ", options_mv)
    # Calculate Cash position
    cash = cleanup.get_cash(acc_info)
    print("Cash (SGD): ", cash)
    # Set up snapshot dataframe
    date_str = current_date.strftime("%Y-%m-%d")
    # Set up snapshot_df and positions_df to place into db
    snapshot_df = cleanup.portfolio_snapshot_table(
        date_str,
        shares_mv,
        options_mv,
        cash
    )
    # Set up positions dataframe
    positions_df = cleanup.positions_table(positions, date_str)
    
    _summarize_frame("snapshot dataframe", snapshot_df)
    _summarize_frame("positions dataframe", positions_df)

    return snapshot_df, positions_df, cashflow, historical_orders

def update_db(snapshot_df: pd.DataFrame, positions_df: pd.DataFrame, cashflow: pd.DataFrame, historical_orders: pd.DataFrame,
              current_date: datetime):
    """Write one day's data.

    Order is enforced by the FK on positions.date -> portfolio_snapshots.date,
    so the snapshot must be written before its positions. cashflow precedes
    calc_nav_units, which reads it.
    """
    db.init_db()

    # Store the USD->SGD rate the batch used, so the 10s live poller can
    # revalue holdings without a yfinance round-trip. Best-effort: a failed FX
    # fetch must not abort the batch.
    try:
        rate = cleanup.get_exchange_rate(
            "USD", "SGD", current_date.strftime("%Y-%m-%d-%H")
        )
        db.store_fx_rate(rate, "USD", "SGD")
        print(f"Stored FX rate USD->SGD: {rate}")
    except Exception as e:
        print(f"FX rate unavailable ({e}); live poller will fall back to stored rate.")

    if cashflow.empty:
        print("Skipping cashflow database update due to empty results.")
    else:
        db.insert_dataframe(cashflow, 'cashflow')
    db.insert_dataframe(historical_orders, 'historical_orders')
    db.sync_transactions()

    nav, units = db.calc_nav_units(current_date, snapshot_df)
    snapshot_df.loc[0, 'nav'] = nav
    snapshot_df.loc[0, 'units'] = units

    # Parent before child, or the FK rejects the positions rows.
    db.insert_dataframe(snapshot_df, 'portfolio_snapshots')
    db.insert_dataframe(positions_df, 'positions')

    db.insert_dataframe(db.net_p_l(current_date), 'net_p_l')

    # Static classification for the dashboard. Best-effort and gated to once a
    # day: it never fails the batch and never runs on the 10s render loop.
    if db.get_meta("last_symbol_meta_update") != current_date.strftime('%Y-%m-%d'):
        try:
            refresh_symbol_meta(allow_network=True)
            db.set_meta("last_symbol_meta_update", current_date.strftime('%Y-%m-%d'))
        except Exception as e:
            print(f"symbol_meta refresh skipped ({e}).")

    # Index + per-symbol price history: ~57 yfinance downloads per pass, so it
    # is gated to once per calendar day via an app_meta flag. A same-day re-run
    # of main.py only backfills symbols seen for the first time.
    if not db.prices_updated_today():
        indices_dict = db.indices_dict()
        for index_name, ticker in indices_dict.items():
            db.update_indices(ticker)

        # Price history for every stock ever held (backfills on first sighting,
        # tops up 1mo afterwards) -- feeds the correlation work in Power BI.
        db.update_symbol_prices_for_positions()
        db.set_meta("last_symbol_prices_update", date.today().strftime("%Y-%m-%d"))
    else:
        for s in db.missing_price_symbols():
            db.update_symbol_price(s)

    return 0


def refresh_symbol_meta(allow_network: bool = True) -> int:
    """Persist static classification (sector/industry/country/market cap) for
    every underlier ever held, into `symbol_meta`. The dashboard reads this
    table on every 10s tick instead of calling yfinance. Best-effort: a failed
    fetch still writes the cached Sector/Industry/Country so the charts render.
    """
    from datetime import date as _date
    syms = db.position_stock_symbols()
    # Options map to their underlying root; only equities have classification.
    import re
    occ = re.compile(r'^([A-Z]{1,6})\d{6}[CP]\d{4,}$')
    roots = sorted({occ.match(s).group(1) if occ.match(s) else s for s in syms})
    if not roots:
        return 0
    venues = {}
    try:
        for s, mkt in db.read_db(
            "SELECT DISTINCT Symbol, Market FROM positions WHERE Market IS NOT NULL"
        ).itertuples(index=False):
            venues[s] = (mkt or "").strip().upper()
    except Exception:
        pass
    try:
        existing = {r["Symbol"]: r for r in
                    db.read_symbol_meta().to_dict("records")}
    except Exception:
        existing = {}
    meta = fetch_symbol_meta_bulk(roots, venues=venues,
                                  allow_network=allow_network, existing=existing)
    now = _date.today().strftime("%Y-%m-%d")
    rows = [
        {"Symbol": t, "Sector": v["Sector"], "Industry": v["Industry"],
         "Country": v["Country"], "Market_Cap": v["Market_Cap"], "Updated_At": now}
        for t, v in meta.items()
    ]
    n = db.upsert_symbol_meta(rows)
    print(f"symbol_meta refreshed: {n} symbols (network={'on' if allow_network else 'off'}).")
    return n


def upload_to_db(current_date: datetime, end_date: datetime, keep_opend_alive: bool = False):
    acc_info, positions, cashflow, historical_orders = get_api_data(current_date, end_date, keep_opend_alive)
    if acc_info is None or positions is None:
        print("API returned no data. Skipping database update for this tick.")
        return 1
    snapshot_df, positions_df, cashflow, historical_orders = cleanup_data(acc_info, positions, cashflow, historical_orders,current_date)
    update_db(snapshot_df, positions_df, cashflow, historical_orders, current_date)
    print("Database updated successfully.")
    return 0


def cashflow_start_date(today_date: datetime) -> datetime:
    """Start of the cashflow fetch window: 30 days back, EXTENDED to just past
    the last recorded cashflow row when a batch outage created a bigger gap
    (a fixed window permanently misses rows once it is down longer than the
    window). The 30-day base stays: the API filters by clearing_date, so
    late-posted rows with older clearing dates are only caught by a wide
    window. Clamped to START_DATE so a wiped DB still fetches full history."""
    start = today_date - timedelta(days=30)
    last = db.last_cashflow_date()
    if last is not None:
        start = min(start, datetime.strptime(last, '%Y-%m-%d') - timedelta(days=2))
    return max(start, settings.START_DATE)


def main():
    today_date = datetime.combine(date.today(), datetime.min.time())
    beginning_date = settings.START_DATE

    # --- Database Update Logic ---
    if not os.path.exists(settings.MOOMOO_PORTFOLIO_DB_PATH) or db.get_latest_db_date() is None:
        print("Database not found or empty. Initializing and fetching all historical data...")
        rc = upload_to_db(today_date, beginning_date, keep_opend_alive=False)
    else:
        rc = upload_to_db(today_date, cashflow_start_date(today_date), keep_opend_alive=False)

    if rc == 0:
        print("Database initialized successfully.")
    return rc

if __name__ == "__main__":
    raise SystemExit(main())
