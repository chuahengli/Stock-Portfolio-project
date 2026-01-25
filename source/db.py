from source.cleanup import convert_currency,get_exchange_rate
from config import settings 

import sqlite3
import pandas as pd
from datetime import datetime, date
import re
import numpy as np
from contextlib import contextmanager
import yfinance as yf
import functools

# Manage the open and close of database
@contextmanager
def db_contextmanager():
    conn = sqlite3.connect(str(settings.MOOMOO_PORTFOLIO_DB_PATH),check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        yield conn
    finally:
        conn.commit()
        conn.close()


def init_db():
    # Create portfolio_snapshots table
    portfolio_snapshots_table ="""
    CREATE TABLE IF NOT EXISTS portfolio_snapshots (
        date TEXT PRIMARY KEY,
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
        date TEXT,
        FOREIGN KEY (date) REFERENCES portfolio_snapshots (date),
        PRIMARY KEY(Symbol, date) 
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
        Remark TEXT,
        is_external NUMERIC
    )
    """
    # Create net_p_l table
    net_p_l_table = """
    CREATE TABLE IF NOT EXISTS net_p_l (
        Symbol TEXT,
        Market TEXT,
        Currency TEXT,
        Net_P_L NUMERIC,
        PRIMARY KEY(Symbol, Market, Currency)
    )
    """

    # Create benchmark indices table
    benchmark_history_table = """
    CREATE TABLE IF NOT EXISTS benchmark_history (
        Date TEXT,
        Close NUMERIC,
        High NUMERIC,
        Low NUMERIC,
        Open NUMERIC,
        Volume NUMERIC,
        Symbol TEXT,
        PRIMARY KEY (Date, Symbol)
    )
    """

    with db_contextmanager() as conn:
        cursor = conn.cursor()
        cursor.execute(portfolio_snapshots_table)
        cursor.execute(positions_table)
        cursor.execute(historical_orders_table)
        cursor.execute(cashflow_table)
        cursor.execute(net_p_l_table)
        cursor.execute(benchmark_history_table)

def table_empty(table_name:str):
    with db_contextmanager() as conn:
        cursor = conn.cursor()
        query = f"SELECT EXISTS (SELECT 1 FROM {table_name}) AS result;"
        # 0 if empty, 1 if not empty
        cursor.execute(query)
        count = cursor.fetchone()[0]
        return count == 0

def insert_dataframe(df:pd.DataFrame, table_name:str):
    with db_contextmanager() as conn:
        # Upload DataFrame to a staging table
        df.to_sql('temp_staging', conn, if_exists='replace', index=False)
        # Define columns in df to place in columns in sql db table
        cols = ",".join(df.columns)
        # Transfer data to the main table using INSERT OR REPLACE for an "upsert" operation
        conn.execute(f"""
            INSERT OR REPLACE INTO {table_name} ({cols})
            SELECT {cols} FROM temp_staging
        """)
        conn.execute("DROP TABLE temp_staging")

def read_db(query:str):
    with db_contextmanager() as conn:
        df = pd.read_sql_query(query, conn)
    return df
        
def prev_nav_units():
    query = "SELECT nav, units FROM portfolio_snapshots ORDER BY date DESC LIMIT 1"
    prev_df = read_db(query)
    if prev_df.empty:
        return 0, 0
    return prev_df.loc[0, 'nav'], prev_df.loc[0, 'units']


def net_cashflow(date_str: str):
    query = f"SELECT cashflow_id, Date, Currency, Amount FROM cashflow where Date = '{date_str}' AND is_external = 1"
    today_cf_df = read_db(query)
    if not today_cf_df.empty:
        today_cf_df['Amount'] = today_cf_df.apply(lambda x: convert_currency(x['Amount'], x['Currency'], 'SGD'), axis=1)
    net_cash_flow = today_cf_df['Amount'].sum() if not today_cf_df.empty else 0.0
    return net_cash_flow

def calc_nav_units(current_date: datetime, snapshot_df: pd.DataFrame):
    total_assets = snapshot_df.loc[0, 'total_assets']
    # Based on today's cash flow, DO the NAV calculation
    date_str = current_date.strftime('%Y-%m-%d')
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


# Get historical orders dataframe
def historical_orders_data():
    query = f"SELECT * FROM historical_orders "
    df = read_db(query)
    return df

# Calculate P/L for historical orders dataframe
def calculate_change(row):
        option_pattern = r'[A-Z]+\d{6}[CP]\d+'
        # Determine multiplier: 100 for options, 1 for stocks
        is_option = re.search(option_pattern, str(row['Symbol']))
        multiplier = 100 if is_option else 1
        amount = row['Quantity'] * row['Current_Price'] * multiplier
        
        side = str(row['Buy_Sell']).upper()
        if 'BUY' in side:
            return amount * -1
        elif 'SELL' in side:
            return amount
        return 0.0

# Get relevant information from positions table as dataframe to calculate P/L
def unrealised_p_l(today_date: datetime):
    query = f"SELECT Symbol, Market, Market_Value, P_L, Currency FROM positions WHERE date = '{today_date.strftime('%Y-%m-%d')}'"
    df = read_db(query)
    return df


def net_p_l(today_date: datetime):
    # Regex to identify options (Standard: Root + 6 digits + C/P + 8 digits)
    option_pattern = r'[A-Z]+\d{6}[CP]\d+'
    historical_orders_p_l = historical_orders_data()

    # Calculate 'Change'
    # BUY = Negative (Cost), SELL = Positive(Revenue)
    historical_orders_p_l['Change'] = historical_orders_p_l.apply(calculate_change, axis=1)

    # Group by columns and sum up those of the same symbol to get net P/L (Excluding those in current positions/hodlings)
    historical_orders_p_l = historical_orders_p_l.groupby(['Symbol', 'Market', 'Currency'])[['Change']].sum().reset_index().rename(columns={'Change': 'Net_P_L'})
    
    # Get current positions market value and unrealised P/L to calculate net P/L
    positions_mv = unrealised_p_l(today_date)
    # Define condition if is option, if option use P_L, otherwise use Market_Vaue 
    condition = positions_mv['Symbol'].astype(str).str.contains(option_pattern, regex=True)
    positions_mv['Net_P_L'] = np.where(
        condition, 
        positions_mv['P_L'],          # Use value from 'P_L' column
        positions_mv['Market_Value']  # Use value from 'Market_Value' column
    )
    
    positions_mv.drop(['Market_Value','P_L'], axis=1, inplace=True) 
    # Concat, then do the same group by and sum to get true net P/L
    net_P_L = pd.concat([historical_orders_p_l,positions_mv],ignore_index=True)
    net_P_L = net_P_L.groupby(['Symbol', 'Market', 'Currency'])[['Net_P_L']].sum().reset_index()
    return net_P_L

@functools.lru_cache()
# Helper to get the latest available date in portfolio_snapshots table
def get_latest_db_date(today_date = datetime.combine(date.today(), datetime.min.time())):
    query = "SELECT date FROM portfolio_snapshots ORDER BY date DESC LIMIT 1"
    df = read_db(query)
    if not df.empty:
        return datetime.strptime(df.iloc[0]['date'], '%Y-%m-%d')
    return None

        

def indices_exists(index_name: str):
    query = "SELECT EXISTS (SELECT 1 FROM benchmark_history WHERE Symbol LIKE ?)"
    search_term = f"%{index_name}%"
    try:
        with db_contextmanager() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (search_term,))
            result = cursor.fetchone()
            
            return result[0] == 1 if result else False
            
    except Exception as e:
        print(f"Database error checking index {index_name}: {e}")
        return False 
        
def historical_close_prices(ticker: str,period: str, interval: str):
    data = yf.download(ticker, period= period, interval=interval,multi_level_index=False)
    data.reset_index(inplace=True)
    data['Symbol'] = ticker
    return data
@functools.lru_cache(maxsize=10)
def update_indices(index_name: str,today_date = datetime.combine(date.today(), datetime.min.time())):
    if indices_exists(index_name):
        data = historical_close_prices(index_name, period='1mo',interval='1d')
        insert_dataframe(data,'benchmark_history')
    else: 
        data = historical_close_prices(index_name, period='max',interval='1d')
        insert_dataframe(data,'benchmark_history')






def main():
    return 0

if __name__ == "__main__":
    main()