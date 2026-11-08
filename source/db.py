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
        is_external NUMERIC,
        is_income NUMERIC
    )
    """
    # Create net_p_l table
    net_p_l_table = """
    CREATE TABLE IF NOT EXISTS net_p_l (
        date TEXT,
        Symbol TEXT,
        Market TEXT,
        Currency TEXT,
        Net_P_L NUMERIC,
        PRIMARY KEY(date, Symbol, Market, Currency)
    )
    """
    # Buy/Sell audit ledger (derived from historical_orders)
    transactions_table = """
    CREATE TABLE IF NOT EXISTS transactions (
        Order_ID TEXT PRIMARY KEY,
        date_time TEXT,
        Symbol TEXT,
        Name TEXT,
        Market TEXT,
        Buy_Sell TEXT,
        Quantity NUMERIC,
        Fill_Price NUMERIC,
        Multiplier NUMERIC,
        Gross_Amount NUMERIC,
        Currency TEXT
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

    # Create per-symbol price history table (individual holdings, same schema
    # as benchmark_history; kept separate so the two exports stay clean)
    symbol_price_history_table = """
    CREATE TABLE IF NOT EXISTS symbol_price_history (
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
        cursor.execute(transactions_table)
        cursor.execute(benchmark_history_table)
        cursor.execute(symbol_price_history_table)
        _ensure_cashflow_income_column(conn)
        _migrate_net_p_l(conn)

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
        
def prev_nav_units(before_date: str = None):
    """Latest nav/units, optionally strictly BEFORE a date ('YYYY-MM-DD').

    calc_nav_units passes today's date: on a same-day re-run today's row is
    already in the table, and using it as 'previous' drifts NAV whenever net
    cash flow is non-zero (units would compound on every rerun).
    """
    if before_date:
        query = f"SELECT nav, units FROM portfolio_snapshots WHERE date < '{before_date}' ORDER BY date DESC LIMIT 1"
    else:
        query = "SELECT nav, units FROM portfolio_snapshots ORDER BY date DESC LIMIT 1"
    prev_df = read_db(query)
    if prev_df.empty:
        return 0, 0
    return prev_df.loc[0, 'nav'], prev_df.loc[0, 'units']


def net_cashflow(start_date_exclusive: str, end_date: str):
    """Net EXTERNAL cash flow (converted to SGD) in (start_date_exclusive, end_date].

    calc_nav_units passes (previous snapshot date, today): flows that landed on
    days WITHOUT a snapshot (weekends, batch outages) must be captured here --
    the old same-date-only lookup silently dropped them forever, polluting
    NAV/units. Flows ON the start date are excluded: they were already counted
    in that snapshot's own units (no double count)."""
    query = (
        f"SELECT cashflow_id, Date, Currency, Amount FROM cashflow "
        f"WHERE Date > '{start_date_exclusive}' AND Date <= '{end_date}' "
        f"AND is_external = 1"
    )
    cf_df = read_db(query)
    if not cf_df.empty:
        cf_df['Amount'] = cf_df.apply(lambda x: convert_currency(x['Amount'], x['Currency'], 'SGD'), axis=1)
        return float(cf_df['Amount'].sum())
    return 0.0


def prev_snapshot_date(before_date: str):
    """Latest snapshot date STRICTLY BEFORE before_date ('YYYY-MM-DD'), or None."""
    df = read_db(f"SELECT MAX(date) AS d FROM portfolio_snapshots WHERE date < '{before_date}'")
    if not df.empty and pd.notna(df.iloc[0]['d']):
        return df.iloc[0]['d']
    return None


def last_cashflow_date():
    """Latest cashflow clearing date in the DB (None when the table is empty)."""
    df = read_db("SELECT MAX(Date) AS d FROM cashflow")
    if not df.empty and pd.notna(df.iloc[0]['d']):
        return df.iloc[0]['d']
    return None

def calc_nav_units(current_date: datetime, snapshot_df: pd.DataFrame):
    total_assets = snapshot_df.loc[0, 'total_assets']
    # Based on cash flow since the previous snapshot, DO the NAV calculation
    date_str = current_date.strftime('%Y-%m-%d')
    prev_date = prev_snapshot_date(date_str)
    prev_nav, prev_units = prev_nav_units(date_str)
    if prev_units == 0 or prev_date is None:
        # First entry
        new_units = 1000.0
        new_nav = total_assets / new_units
        net_cf = 0.0
    else:
        # ALL external flows since the previous snapshot adjust NAV *units* at
        # today's NAV (daily-granularity TWR treatment). Flows that landed on
        # days without a snapshot are picked up by the window, not lost.
        net_cf = net_cashflow(prev_date, date_str)
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
    dfs = [df for df in [historical_orders_p_l, positions_mv] if not df.empty]
    if dfs:
        net_P_L = pd.concat(dfs, ignore_index=True)
    else:
        # Return empty dataframe with correct columns if both are empty
        net_P_L = historical_orders_p_l

    net_P_L = net_P_L.groupby(['Symbol', 'Market', 'Currency'])[['Net_P_L']].sum().reset_index()
    # Date-stamp the snapshot so P/L history is preserved (not overwritten) day to day.
    net_P_L['date'] = today_date.strftime('%Y-%m-%d')
    return net_P_L

# Helper to get the latest available date in portfolio_snapshots table
def get_latest_db_date(today_date: datetime):
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
    # auto_adjust pinned: yfinance's default flipped over versions -- with
    # False an 'Adj Close' column appears and insert_dataframe would INSERT a
    # column the history tables don't have, killing the daily job mid-run.
    data = yf.download(ticker, period= period, interval=interval,multi_level_index=False, auto_adjust=True)
    data.reset_index(inplace=True)
    # Normalize Date to plain YYYY-MM-DD strings: PK upserts are exact-string
    # matches, so timestamp/timezone drift would duplicate calendar days.
    data['Date'] = pd.to_datetime(data['Date']).dt.strftime('%Y-%m-%d')
    data['Symbol'] = ticker
    return data
def update_indices(index_name: str,today_date = datetime.combine(date.today(), datetime.min.time())):
    if indices_exists(index_name):
        data = historical_close_prices(index_name, period='1mo',interval='1d')
        insert_dataframe(data,'benchmark_history')
    else: 
        data = historical_close_prices(index_name, period='max',interval='1d')
        insert_dataframe(data,'benchmark_history')

def indices_dict():
    indices_dict = {
        'SP500': '^GSPC',
        'NASDAQ': '^IXIC',
        'Russell 2000': '^RUT',
        'FTSE 100': '^FTSE',
        'Euro Stoxx 50': '^STOXX50E',
        'HSI': '^HSI',
        'Nikkei 225': '^N225',
        'STI': '^STI'
    }
    return indices_dict


def symbols_exists(symbol: str):
    query = "SELECT EXISTS (SELECT 1 FROM symbol_price_history WHERE Symbol = ?)"
    try:
        with db_contextmanager() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (symbol,))
            result = cursor.fetchone()
            return result[0] == 1 if result else False
    except Exception as e:
        print(f"Database error checking symbol {symbol}: {e}")
        return False


def position_stock_symbols():
    """Distinct non-option symbols ever held, from the positions table.
    Option contracts (OCC format: root + YYMMDD + C/P + strike, e.g.
    GRAB270115C5000) are excluded: yfinance has no usable daily history for
    them, and options correlation is a separate question from equity price
    correlation."""
    df = read_db("SELECT DISTINCT Symbol FROM positions")
    occ = re.compile(r'^[A-Z]{1,6}\d{6}[CP]\d{4,}$')
    return sorted(s for s in df['Symbol'].tolist() if not occ.match(s))


def update_symbol_price(symbol: str, ticker: str = None):
    """Fetch/refresh daily price history for one held symbol into
    symbol_price_history. First sighting backfills period='max'; afterwards
    a 1mo window tops up (same pattern as update_indices). Ticker resolution
    mirrors export_powerbi._ticker_candidates: bare symbol first, '.SI'
    suffix when the position traded on SG, BRK -> BRK-B variant."""
    if ticker is None:
        candidates = [symbol]
        if symbol in ("BRK",):
            candidates = ["BRK-B", symbol]
        elif symbol.isalnum() and 2 <= len(symbol) <= 4:
            with db_contextmanager() as conn:
                row = conn.execute(
                    "SELECT Market FROM positions WHERE Symbol = ? LIMIT 1",
                    (symbol,)).fetchone()
            if row and (row[0] or "").upper().startswith("SG"):
                candidates = [f"{symbol}.SI", symbol]
            else:
                candidates = [symbol, f"{symbol}.SI"]
    else:
        candidates = [ticker]

    data = None
    used = None
    for cand in candidates:
        try:
            df = historical_close_prices(cand, period='max' if not symbols_exists(symbol) else '1mo', interval='1d')
            if df is not None and not df.empty:
                data = df
                used = cand
                break
        except Exception as e:
            print(f"  {symbol}: candidate {cand} failed ({e})")
    if data is None or data.empty:
        print(f"  {symbol}: no price data from any candidate ({candidates}) - skipped")
        return
    if used != symbol:
        data['Symbol'] = symbol  # store under portfolio symbol, not yahoo ticker
    insert_dataframe(data, 'symbol_price_history')


def update_symbol_prices_for_positions():
    """Daily entry point: look at ALL symbols ever held, backfill/top up each."""
    syms = position_stock_symbols()
    print(f"Updating price history for {len(syms)} held symbols...")
    for s in syms:
        update_symbol_price(s)
    print("Symbol price history update complete.")







def _ensure_cashflow_income_column(conn):
    """Add the is_income column to an existing cashflow table (schema migration)."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(cashflow)")]
    if "is_income" not in cols:
        conn.execute("ALTER TABLE cashflow ADD COLUMN is_income NUMERIC")
        print("Migrated: added is_income column to cashflow table.")


def reclassify_cashflow():
    """Recompute is_external / is_income for ALL existing cashflow rows using the
    current classification rules in cleanup.classify_cashflow.

    Run once to backfill the corrected flags (e.g. old Coupon rows that were
    mislabelled as external capital flows). Idempotent -- safe to rerun.
    """
    from source.cleanup import classify_cashflow
    with db_contextmanager() as conn:
        _ensure_cashflow_income_column(conn)
        rows = conn.execute("SELECT cashflow_id, Type, Remark FROM cashflow").fetchall()
        for cid, ctype, remark in rows:
            ext, inc = classify_cashflow(ctype, remark)
            conn.execute(
                "UPDATE cashflow SET is_external = ?, is_income = ? WHERE cashflow_id = ?",
                (1 if ext else 0, 1 if inc else 0, cid),
            )
    print(f"Reclassified {len(rows)} cashflow rows.")


def get_inception_date():
    """Return the first (earliest) recorded snapshot date -- the tracking inception.

    This is the natural TWR reference point: performance is measured from when data
    recording began, regardless of when the account was opened.
    """
    df = read_db("SELECT MIN(date) AS min_date FROM portfolio_snapshots")
    if not df.empty and pd.notna(df.iloc[0]["min_date"]):
        return datetime.strptime(df.iloc[0]["min_date"], "%Y-%m-%d")
    return None


def income_by_date(to_currency: str = "SGD"):
    """Aggregate dividend/coupon/interest income per day, converted to to_currency.

    Returns a DataFrame with columns [Date, Amount, Cumulative]. Amount is net income
    (dividends in, minus withholding tax / fees). Cumulative is the running total.
    """
    df = read_db("SELECT Date, Currency, Amount FROM cashflow WHERE is_income = 1")
    if df.empty:
        return pd.DataFrame(columns=["Date", "Amount", "Cumulative"])
    df["Amount"] = df.apply(
        lambda x: convert_currency(x["Amount"], x["Currency"], to_currency), axis=1
    )
    df = df.groupby("Date")["Amount"].sum().reset_index().sort_values("Date").reset_index(drop=True)
    df["Cumulative"] = df["Amount"].cumsum().round(2)
    return df



OPTION_PATTERN = r'[A-Z]+\d{6}[CP]\d+'


def _migrate_net_p_l(conn):
    """Migrate the net_p_l table to include a date column (preserve P/L history).

    SQLite cannot alter a primary key in place, so the table is rebuilt. Existing
    rows are backfilled with the latest recorded snapshot date -- they are derived
    (regenerable) data, so nothing of value is lost.
    """
    cols = [r[1] for r in conn.execute("PRAGMA table_info(net_p_l)")]
    if "date" in cols:
        return
    latest = conn.execute("SELECT MAX(date) FROM portfolio_snapshots").fetchone()[0]
    date_col = latest or datetime.now().strftime("%Y-%m-%d")
    conn.execute("ALTER TABLE net_p_l RENAME TO net_p_l_old")
    conn.execute(
        """
        CREATE TABLE net_p_l (
            date TEXT,
            Symbol TEXT,
            Market TEXT,
            Currency TEXT,
            Net_P_L NUMERIC,
            PRIMARY KEY(date, Symbol, Market, Currency)
        )
        """
    )
    conn.execute(
        "INSERT INTO net_p_l (date, Symbol, Market, Currency, Net_P_L) "
        "SELECT ?, Symbol, Market, Currency, Net_P_L FROM net_p_l_old",
        (date_col,),
    )
    conn.execute("DROP TABLE net_p_l_old")
    print("Migrated: net_p_l is now date-stamped (realized P/L history preserved).")


def option_multiplier(symbol: str) -> int:
    """Return the contract multiplier: 100 for options, 1 for stocks/ETFs."""
    return 100 if re.search(OPTION_PATTERN, str(symbol)) else 1


def transaction_gross_amount(symbol, side, quantity, fill_price):
    """Signed, multiplier-aware notional for one fill (pure logic, testable).

    sign: BUY / BUY_BACK = -1 (cash out), SELL / SELL_SHORT = +1 (cash in).
    multiplier: 100 for options, 1 for stocks/ETFs.
    """
    mult = option_multiplier(symbol)
    sign = -1 if str(side).strip().upper() in ("BUY", "BUY_BACK") else 1
    return round(quantity * fill_price * mult * sign, 2)


def sync_transactions():
    """(Re)build the buy/sell audit `transactions` ledger from historical_orders.

    Each filled order becomes one row with a multiplier-aware, sign-conventioned
    Gross_Amount: SELL / SELL_SHORT = + (cash in), BUY / BUY_BACK = - (cash out).
    Idempotent -- ordered by Order_ID, safe to re-run on every update.
    """
    df = read_db("SELECT * FROM historical_orders")
    if df.empty:
        print("No historical orders to sync into transactions ledger.")
        return
    df = df.copy()
    df["Multiplier"] = df["Symbol"].apply(option_multiplier)
    df["Gross_Amount"] = [
        transaction_gross_amount(s, b, q, p)
        for s, b, q, p in zip(df["Symbol"], df["Buy_Sell"], df["Quantity"], df["Current_Price"])
    ]
    df = df.rename(columns={"Current_Price": "Fill_Price"})
    df = df[["Order_ID", "date_time", "Symbol", "Name", "Market", "Buy_Sell",
             "Quantity", "Fill_Price", "Multiplier", "Gross_Amount", "Currency"]]
    insert_dataframe(df, "transactions")
    print(f"Synced {len(df)} rows into the transactions (audit) ledger.")


def main():
    return 0

if __name__ == "__main__":
    main()