from source import moomoo_api, cleanup, db, dashboard
from config import settings
from datetime import date, datetime,timedelta
import matplotlib.pyplot as plt
import os
import subprocess
import pandas as pd


def _summarize_frame(name, df, extra=""):
    """Log a concise summary of a dataframe instead of dumping its full contents
    (keeps daily_log.txt small -- the file used to grow to tens of MB)."""
    if df is None:
        print(f"{name}: None")
    elif hasattr(df, "shape"):
        print(f"{name}: {df.shape[0]} row(s) x {df.shape[1]} col(s){extra}")
    else:
        print(f"{name}: present{extra}")



'''
TESTING PURPOSES ONLY

current_date = [
                datetime.combine(date.today(), datetime.min.time()),
                datetime.combine(date.today(), datetime.min.time()) - timedelta(days=30),
                datetime.combine(date.today(), datetime.min.time()) - timedelta(days=60),
                datetime.combine(date.today(), datetime.min.time()) - timedelta(days=90),
                datetime.strptime('2023-08-07', '%Y-%m-%d')
                ]
                
'''
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
    '''
    print ("Total Assets: ",cleanup.get_total_assets(acc_info))
    print ("Securities assets: ",cleanup.get_securities_assets(acc_info))
    print ("Cash: ",cleanup.get_cash(acc_info))
    print ("Bonds: ",cleanup.get_bonds(acc_info))
    '''

    
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
    ## Initialise and upload dataframes to db
    db.init_db()
    db.insert_dataframe(positions_df, 'positions')
    db.insert_dataframe(historical_orders, 'historical_orders')
    db.sync_transactions()
    # Check if cashflow dataframe is empty
    if cashflow.empty:
        print("Skipping cashflow database update due to empty results.")
    else:
        db.insert_dataframe(cashflow, 'cashflow')
    # Calculate and update nav for Time Weighted Returns(TWR)
    nav, units = db.calc_nav_units(current_date, snapshot_df)
    snapshot_df.loc[0, 'nav'] = nav
    snapshot_df.loc[0, 'units'] = units

    db.insert_dataframe(snapshot_df, 'portfolio_snapshots')
    db.insert_dataframe(db.net_p_l(current_date),'net_p_l')

    
    # Index + per-symbol price history: ~57 yfinance downloads per pass. The
    # Streamlit live fragment calls update_db every 10 seconds, so this is
    # gated to once per calendar day (app_meta flag); a same-day re-run only
    # backfills symbols seen for the first time.
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
    if not os.path.exists(settings.MOOMOO_PORTFOLIO_DB_PATH):
        print("Database not found. Initializing and fetching all historical data...")
        upload_to_db(today_date, beginning_date,keep_opend_alive=False)

    else:
        upload_to_db(today_date, cashflow_start_date(today_date), keep_opend_alive=False)
    
    print("Database initialized successfully.")
    return 0

if __name__ == "__main__":
    main()
