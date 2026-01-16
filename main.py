from source import moomoo_api, cleanup, db, dashboard
from config import settings
from datetime import date, datetime,timedelta
import matplotlib.pyplot as plt
import os
import subprocess
import pandas as pd

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
    
    print("Acc_info: \n", acc_info)
    print("Positions: \n", positions)
    print("Cashflow: \n", cashflow)
    print("Historical Orders: \n", historical_orders)

    return acc_info, positions, cashflow, historical_orders

def cleanup_data(acc_info: pd.DataFrame, positions: pd.DataFrame, cashflow: pd.DataFrame, historical_orders: pd.DataFrame,current_date: datetime):
    ## Cleanup to upload to db
    print("Cleaning up data...")
    acc_info = cleanup.cleanup_acc_info(acc_info)
    positions = cleanup.cleanup_positions(positions)
    cleanup.update_portfolio_percentage(positions, cleanup.get_total_assets(acc_info))
    historical_orders = cleanup.cleanup_historical_orders(historical_orders)
    cashflow = cleanup.cleanup_cashflow(cashflow)

    print("Acc_info: \n", acc_info)
    print("Positions: \n", positions)
    print("Cashflow: \n", cashflow)
    print("Historical Orders: \n", historical_orders)
    '''
    print ("Total Assets: ",cleanup.get_total_assets(acc_info))
    print ("Securities assets: ",cleanup.get_securities_assets(acc_info))
    print ("Cash: ",cleanup.get_cash(acc_info))
    print ("Bonds: ",cleanup.get_bonds(acc_info))
    '''

    
    # Split shares and options positions into separate dataframes
    shares, options = cleanup.separate_assets(positions)
    print("Shares Dataframe: \n", shares)
    print("Options Dataframe: \n", options)
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
        cleanup.get_total_assets(acc_info),
        shares_mv,
        options_mv,
        cash
    )
    # Set up positions dataframe
    positions_df = cleanup.positions_table(positions, date_str)
    
    print("snapshot dataframe: \n", snapshot_df)
    print("positions dataframe: \n", positions_df)

    return snapshot_df, positions_df, cashflow, historical_orders

def update_db(snapshot_df: pd.DataFrame, positions_df: pd.DataFrame, cashflow: pd.DataFrame, historical_orders: pd.DataFrame,current_date: datetime):
    ## Initialise and upload dataframes to db
    db.init_db()
    db.insert_dataframe(positions_df, 'positions')
    db.insert_dataframe(historical_orders, 'historical_orders')
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
    return 0


def upload_to_db(current_date: datetime, end_date: datetime, keep_opend_alive: bool = False):
    acc_info, positions, cashflow, historical_orders = get_api_data(current_date, end_date, keep_opend_alive)
    snapshot_df, positions_df, cashflow, historical_orders = cleanup_data(acc_info, positions, cashflow, historical_orders,current_date)
    update_db(snapshot_df, positions_df, cashflow, historical_orders, current_date)
    print("Database updated successfully.")
    return 0


def main():
    today_date = datetime.combine(date.today(), datetime.min.time())
    beginning_date = datetime.strptime('2023-08-07', '%Y-%m-%d')

    # --- Database Update Logic ---
    if not os.path.exists(settings.MOOMOO_PORTFOLIO_DB_PATH):
        print("Database not found. Initializing and fetching all historical data...")
        upload_to_db(today_date, beginning_date,keep_opend_alive=False)
        print("Database initialized successfully.")
    else:
        today_str = today_date.strftime("%Y-%m-%d")
        if not db.check_date_exists(today_str):
            print("Database found, but today's snapshot is missing. Updating...")
            upload_to_db(today_date, today_date - timedelta(days=30),keep_opend_alive=False)
            print("Database updated successfully.")
        else:
            print(f"Portfolio snapshot for {today_str} is already up-to-date. Skipping data update.")
    return 0

if __name__ == "__main__":
    main()
