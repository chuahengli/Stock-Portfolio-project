from source import moomoo_api, cleanup, db
from config import settings
from datetime import date, datetime,timedelta
import os
import subprocess

'''
TESTING PURPOSES ONLY

current_date = [
                datetime.combine(date.today(), datetime.min.time()),
                datetime.combine(date.today(), datetime.min.time()) - timedelta(days=30),
                datetime.combine(date.today(), datetime.min.time()) - timedelta(days=60),
                datetime.combine(date.today(), datetime.min.time()) - timedelta(days=90),
                datetime.strptime('2023-08-07', '%Y-%m-%d')
                ]
current_time = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"),
                (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S"),
                (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S")
                ]
'''

def upload_to_db(current_date: datetime, end_date: datetime):

    ## Handle API
    # Check if running .exe and create process
    proc_handle, was_already_running = moomoo_api.manage_opend()
    trade_ctx = None
    # Initialize variables to None 
    acc_info, positions, cashflow, historical_orders = None, None, None, None
    try:
        trade_ctx = moomoo_api.configure_moomoo_api()
        acc_list = moomoo_api.account_list(trade_ctx)
        acc_info = moomoo_api.account_info(trade_ctx)
        positions = moomoo_api.get_positions(trade_ctx)
        cashflow = moomoo_api.account_cashflow(trade_ctx, current_date, end_date)
        historical_orders = moomoo_api.get_historical_orders(trade_ctx)

    except Exception as e:
        print(f"API Error: {e}")
    finally:
        if trade_ctx:
            trade_ctx.close()
        # KILL THE PROCESS
        # If we started it, OR if you want it dead regardless:
        if proc_handle:
            print("Shutting down OpenD...")
            proc_handle.terminate() # Gentle request to close
            
            # Wait 2 seconds, if still alive, kill it forcefully
            try:
                proc_handle.wait(timeout=2)
            except subprocess.TimeoutExpired:
                print("OpenD didn't close, forcing kill...")
                proc_handle.kill()

    print(acc_info)
    print(positions)
    print(cashflow)
    print(historical_orders)

    ## Cleanup to upload to db
    acc_info = cleanup.cleanup_acc_info(acc_info)
    positions = cleanup.cleanup_positions(positions)
    cleanup.update_portfolio_percentage(positions, cleanup.get_total_assets(acc_info))
    historical_orders = cleanup.cleanup_historical_orders(historical_orders)
    cashflow = cleanup.cleanup_cashflow(cashflow)

    print(acc_info)
    print ("Total Assets: ",cleanup.get_total_assets(acc_info))
    print ("Equity: ",cleanup.get_equity(acc_info))
    print ("Cash: ",cleanup.get_cash(acc_info))
    print ("Bonds: ",cleanup.get_bonds(acc_info))
    print(positions)
    print(historical_orders)
    print(cashflow)
    # Calculate shares, options and cash to place into portfolio snapshot
    shares, options = cleanup.separate_assets(positions)
    print(shares)
    print(options)
    shares_mv = cleanup.sum_of_mv(shares)
    options_mv = cleanup.sum_of_mv(options)
    print("Shares Market Value (SGD): ", shares_mv)
    print("Options Market Value (SGD): ", options_mv)
    cash = cleanup.get_cash(acc_info)
    date_str = current_date.strftime("%Y-%m-%d")
    # Set up snapshot_df and positions_df to place into db
    snapshot_df = cleanup.portfolio_snapshot_table(
        date_str,
        cleanup.get_total_assets(acc_info),
        shares_mv,
        options_mv,
        cash
    )
    positions_df = cleanup.positions_table(positions, date_str)

    print("Cash (SGD): ", cash)
    print(snapshot_df)
    print(positions_df)

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

    return 0



def main():
    if not os.path.exists(settings.MOOMOO_PORTFOLIO_DB_PATH):
        upload_to_db(datetime.combine(date.today(), datetime.min.time()) - timedelta(days=30)
                    , datetime.combine(date.today(), datetime.min.time()) - timedelta(days=60))
        print("Database initialized successfully.")
    else:
        print("Database already exists. Initialization skipped.")
        today_str = datetime.now().strftime("%Y-%m-%d")
        if db.check_date_exists(today_str):
            print(f"Portfolio snapshot for {today_str} already exists. Skipping run.")
            return 0

        upload_to_db(datetime.combine(date.today(), datetime.min.time()),
               datetime.combine(date.today(), datetime.min.time()) - timedelta(days=30))
        print("Database updated successfully.")

    return 0


    

if __name__ == "__main__":
    main()
