import moomoo_api
import preprocessing_to_db
from datetime import date, datetime,timedelta
import database
import os

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

def initialise(current_time: datetime, current_date: datetime, end_date: datetime):
        
    acc_info, positions, cashflow, historical_orders = moomoo_api.run(current_date, end_date)


    snapshot_df, positions_df, historical_orders, cashflow = preprocessing_to_db.run(acc_info, positions, cashflow, historical_orders, current_time)

    database.run(snapshot_df, positions_df, historical_orders, cashflow, current_time)

    print("Database initialized successfully.")
    return 0

def update(current_time: datetime, current_date: datetime, end_date: datetime):
    acc_info, positions, cashflow, historical_orders = moomoo_api.run(current_date, end_date)


    snapshot_df, positions_df, historical_orders, cashflow = preprocessing_to_db.run(acc_info, positions, cashflow, historical_orders, current_time)
    database.run(snapshot_df, positions_df, historical_orders, cashflow, current_time)
    print("Database updated successfully.")
    return 0

def main():
    if not os.path.exists('moomoo_portfolio.db'):
        initialise((datetime.now() - timedelta(days=30))
                    , datetime.combine(date.today(), datetime.min.time()) - timedelta(days=30)
                    , datetime.combine(date.today(), datetime.min.time()) - timedelta(days=60))
    else:
        print("Database already exists. Initialization skipped.")
        update(datetime.now(),
               datetime.combine(date.today(), datetime.min.time()),
               datetime.combine(date.today(), datetime.min.time()) - timedelta(days=30))

    return 0


    

if __name__ == "__main__":
    main()

