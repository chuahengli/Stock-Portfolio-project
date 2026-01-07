import sqlite3
import pandas as pd

def init_db():
    conn = sqlite3.connect('moomoo_portfolio.db')
    cursor = conn.cursor()

    # Create portfolio_snapshots table
    portfolio_snapshots_table ="""
    CREATE TABLE IF NOT EXISTS portfolio_snapshots (
        date_time TEXT PRIMARY KEY,
        total_assets REAL,
        stocks REAL,
        options REAL,
        cash REAL,
        nav REAL,
        units REAL
    )
    """
    # Create the Positions table
    positions_table = """
    CREATE TABLE IF NOT EXISTS positions (
        Symbol TEXT,
        Name TEXT,
        Market TEXT,
        Quantity REAL,
        Diluted_Cost REAL,
        Market_Value REAL,
        Current_Price REAL,
        P_L_Percent REAL,
        P_L REAL,
        Today_s_P_L REAL,
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
        Quantity REAL,
        Current_Price REAL,
        Currency TEXT,
        date_time TEXT
    )
    """
    # Create cashflow table
    cashflow_table = """
    CREATE TABLE IF NOT EXISTS cashflow (
        Date TEXT,
        Currency TEXT,
        Type TEXT,
        in_out TEXT,
        Amount REAL,
        Remark TEXT
    )
    """
    cursor.execute(portfolio_snapshots_table)
    cursor.execute(positions_table)
    cursor.execute(historical_orders_table)
    cursor.execute(cashflow_table)




    conn.commit()
    conn.close()

def insert_dataframe(df:pd.DataFrame, table_name:str):
    conn = sqlite3.connect('moomoo_portfolio.db')
    df.to_sql(table_name, conn, if_exists='append', index=False)
    conn.close()