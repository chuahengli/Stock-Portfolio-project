import moomoo_api
import preprocessing_to_db
from datetime import datetime
import database

def main():
    trade_obj, process = moomoo_api.start_opend_headless()
    acc_list = moomoo_api.account_list(trade_obj)
    acc_info = moomoo_api.account_info(trade_obj)
    positions = moomoo_api.get_positions(trade_obj)
    cashflow = moomoo_api.historical_account_cashflow(trade_obj)
    historical_orders = moomoo_api.get_historical_orders(trade_obj)
    trade_obj.close()
    process.terminate()

    acc_info = preprocessing_to_db.cleanup_acc_info(acc_info)
    positions = preprocessing_to_db.cleanup_positions(positions)
    preprocessing_to_db.update_portfolio_percentage(positions, preprocessing_to_db.get_total_assets(acc_info))
    historical_orders = preprocessing_to_db.cleanup_historical_orders(historical_orders)
    cashflow = preprocessing_to_db.cleanup_cashflow(cashflow)

    print(acc_info)
    print ("Total Assets: ",preprocessing_to_db.get_total_assets(acc_info))
    print ("Securities: ",preprocessing_to_db.get_securities(acc_info))
    print ("Cash: ",preprocessing_to_db.get_cash(acc_info))
    print ("Bonds: ",preprocessing_to_db.get_bonds(acc_info))
    print(positions)
    print(historical_orders)
    print(cashflow)

    shares = preprocessing_to_db.shares_df(positions)
    options = preprocessing_to_db.options_df(positions)
    print(shares)
    print(options)
    shares_mv = preprocessing_to_db.sum_of_mv(shares)
    options_mv = preprocessing_to_db.sum_of_mv(options)
    print("Shares Market Value (SGD): ", shares_mv)
    print("Options Market Value (SGD): ", options_mv)
    cash = preprocessing_to_db.get_cash(acc_info)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    initial_snapshot_df = preprocessing_to_db.initial_portfolio_snapshot_df(
        current_time,
        preprocessing_to_db.get_total_assets(acc_info),
        shares_mv,
        options_mv,
        cash
    )
    initial_positions_df = preprocessing_to_db.initial_positions_df(positions, current_time)

    print("Cash (SGD): ", cash)
    print(initial_snapshot_df)
    print(initial_positions_df)

    database.init_db()
    database.insert_dataframe(initial_snapshot_df, 'portfolio_snapshots')
    database.insert_dataframe(initial_positions_df, 'positions')
    database.insert_dataframe(historical_orders, 'historical_orders')
    database.insert_dataframe(cashflow, 'cashflow')
    return 0


    

if __name__ == "__main__":
    main()

