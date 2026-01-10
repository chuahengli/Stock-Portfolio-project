import sqlite3
import pandas as pd
from datetime import datetime
from preprocessing_to_db import convert_currency,get_exchange_rate

def init_db():
    conn = sqlite3.connect('moomoo_portfolio.db')
    cursor = conn.cursor()

    # Create portfolio_snapshots table
    portfolio_snapshots_table ="""
    CREATE TABLE IF NOT EXISTS portfolio_snapshots (
        date_time TEXT PRIMARY KEY,
        total_assets NUMERIC,
        stocks NUMERIC,
        options NUMERIC,
        cash NUMERIC,
        nav NUMERIC,
        units NUMERIC
    )
    """
    # Create the Positions table
    positions_table = """
    CREATE TABLE IF NOT EXISTS positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        Symbol TEXT,
        Name TEXT,
        Market TEXT,
        Quantity NUMERIC,
        Diluted_Cost NUMERIC,
        Market_Value NUMERIC,
        Current_Price NUMERIC,
        P_L_Percent NUMERIC,
        P_L NUMERIC,
        Today_s_P_L NUMERIC,
        Currency TEXT,
        Portfolio_Percent REAL,
        date_time TEXT,
        FOREIGN KEY (date_time) REFERENCES portfolio_snapshots (date_time)
    )
    """
    # Create historical_orders table
    historical_orders_table = """
    CREATE TABLE IF NOT EXISTS historical_orders (
        Symbol TEXT,
        Name TEXT,
        Market TEXT,
        Buy_Sell TEXT,
        Quantity NUMERIC,
        Order_ID TEXT PRIMARY KEY,
        Current_Price NUMERIC,
        Currency TEXT,
        date_time TEXT
    )
    """
    # Create cashflow table
    cashflow_table = """
    CREATE TABLE IF NOT EXISTS cashflow (
        cashflow_id TEXT PRIMARY KEY,
        Date TEXT,
        Currency TEXT,
        Type TEXT,
        in_out TEXT,
        Amount NUMERIC,
        Remark TEXT
    )
    """
    cursor.execute(portfolio_snapshots_table)
    cursor.execute(positions_table)
    cursor.execute(historical_orders_table)
    cursor.execute(cashflow_table)
    conn.commit()
    conn.close()

def table_empty(table_name:str):
    conn = sqlite3.connect('moomoo_portfolio.db')
    cursor = conn.cursor()
    query = f"SELECT EXISTS (SELECT 1 FROM {table_name}) AS result;"
    # 0 if empty, 1 if not empty
    cursor.execute(query)
    count = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return count == 0

def insert_dataframe(df:pd.DataFrame, table_name:str):
    if table_empty(table_name):
        conn = sqlite3.connect('moomoo_portfolio.db')
        df.to_sql(table_name, conn, if_exists='append', index=False)
        conn.commit()
        conn.close()
    elif not table_empty(table_name):
        conn = sqlite3.connect('moomoo_portfolio.db')
        # Upload DataFrame to a staging table
        df.to_sql('temp_staging', conn, if_exists='replace', index=False)
        # Define columns in df to place in columns in sql db table
        cols = ",".join(df.columns)
        # Transfer data to the main table with "Replace" logic
        conn.execute(f"""
            INSERT OR REPLACE INTO {table_name} ({cols})
            SELECT {cols} FROM temp_staging
        """)
        conn.execute("DROP TABLE temp_staging")
        conn.commit()
        conn.close()
def prev_nav_units():
    conn = sqlite3.connect('moomoo_portfolio.db')
    query = "SELECT nav, units FROM portfolio_snapshots ORDER BY date_time DESC LIMIT 1"
    prev_df = pd.read_sql_query(query, conn)
    conn.commit()
    conn.close()
    if prev_df.empty:
        return 0, 0
    return prev_df.loc[0, 'nav'], prev_df.loc[0, 'units']


def net_cashflow(date_str: str):
    conn = sqlite3.connect('moomoo_portfolio.db')
    query = f"SELECT cashflow_id, Date, Currency, Amount FROM cashflow where Date = '{date_str}'"
    today_cf_df = pd.read_sql_query(query, conn)
    if not today_cf_df.empty:
        today_cf_df['Amount'] = today_cf_df.apply(lambda x: convert_currency(x['Amount'], x['Currency'], 'SGD'), axis=1)
    conn.commit()
    conn.close()
    net_cash_flow = today_cf_df['Amount'].sum() if not today_cf_df.empty else 0.0
    return net_cash_flow

def calc_nav_units(current_time: datetime, snapshot_df: pd.DataFrame):
    total_assets = snapshot_df.loc[0, 'total_assets']
    # Based on today's cash flow, DO the NAV calculation
    date_str = current_time.strftime('%Y-%m-%d')
    net_cf = net_cashflow(date_str)
    prev_nav, prev_units = prev_nav_units()
    if prev_units == 0:
        # First entry
        new_units = 1000.0
        new_nav = total_assets / new_units
    else:
        # New NAV = (Ending Value - Net Cash Flow) / Previous Units
        # NAV only changed with market movement, not cash flow in/out
        new_nav = (total_assets - net_cf) / prev_units
        new_units = prev_units + (net_cf / new_nav)
    print(f"Update Complete. New NAV: {new_nav:.4f}, Net CF: {net_cf:.2f}, New Units: {new_units:.4f}")
    return new_nav, new_units


def run(snapshot_df: pd.DataFrame, positions_df: pd.DataFrame, historical_orders: pd.DataFrame, cashflow: pd.DataFrame, current_time: datetime):
    init_db()
    insert_dataframe(positions_df, 'positions')
    insert_dataframe(historical_orders, 'historical_orders')
    if cashflow.empty:
        print("Skipping cashflow database update due to empty results.")
    else:
        insert_dataframe(cashflow, 'cashflow')

    nav, units = calc_nav_units(current_time, snapshot_df)
    snapshot_df.loc[0, 'nav'] = nav
    snapshot_df.loc[0, 'units'] = units

    insert_dataframe(snapshot_df, 'portfolio_snapshots')
    return 0

def main():
    return 0

if __name__ == "__main__":
    main()