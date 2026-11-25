"""SQLite schema, upserts, NAV/unit maths, and price-history refresh."""
from source.cleanup import convert_currency,get_exchange_rate
from config import settings 

import sqlite3
import pandas as pd
from datetime import datetime, date
import re
import uuid
import numpy as np
from contextlib import contextmanager
import yfinance as yf
import functools

# Manage the open and close of database
@contextmanager
def db_contextmanager():
    """Open a connection; commit on success, roll back and re-raise on error."""
    conn = sqlite3.connect(str(settings.MOOMOO_PORTFOLIO_DB_PATH), check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        # FKs are unenforced in SQLite unless set per connection.
        conn.execute("PRAGMA foreign_keys=ON;")
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create all SQLite tables if they do not exist and apply idempotent schema migrations."""
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

    # Key/value flags shared by the daily batch and the Streamlit live
    # fragment (e.g. last daily price-update date).
    app_meta_table = """
    CREATE TABLE IF NOT EXISTS app_meta (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """

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

    # Per-symbol price history (individual holdings, same schema as
    # benchmark_history; kept separate so the two exports stay clean)
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

    # Static per-symbol classification (sector / industry / country / market cap).
    # Written by the batch (main.refresh_symbol_meta), read by the dashboard.
    # Keeping it in the DB means the 10s render loop never calls yfinance.
    symbol_meta_table = """
    CREATE TABLE IF NOT EXISTS symbol_meta (
        Symbol TEXT PRIMARY KEY,
        Sector TEXT,
        Industry TEXT,
        Country TEXT,
        Market_Cap NUMERIC,
        Updated_At TEXT
    )
    """

    # Live moomoo quote layer. Written ONLY by source.live.LivePoller (background
    # thread), read by the dashboard. Kept separate from the batch-owned
    # portfolio_snapshots/positions tables so a 10s quote tick can never race
    # the nightly batch's FK-ordered write or drift NAV/units.
    live_account_table = """
    CREATE TABLE IF NOT EXISTS live_account (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        total_assets NUMERIC,
        stocks NUMERIC,
        options NUMERIC,
        cash NUMERIC,
        as_of TEXT
    )
    """
    live_quotes_table = """
    CREATE TABLE IF NOT EXISTS live_quotes (
        Symbol TEXT PRIMARY KEY,
        Name TEXT,
        Market TEXT,
        Quantity NUMERIC,
        Diluted_Cost NUMERIC,
        Current_Price NUMERIC,
        Market_Value NUMERIC,
        P_L_Percent NUMERIC,
        P_L NUMERIC,
        Today_s_P_L NUMERIC,
        Currency TEXT,
        Portfolio_Percent REAL,
        date TEXT,
        as_of TEXT
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
        cursor.execute(symbol_meta_table)
        cursor.execute(live_account_table)
        cursor.execute(live_quotes_table)
        cursor.execute(app_meta_table)
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
    """Upsert a DataFrame into `table_name`.

    The staging table name is unique per call: a fixed name is shared global
    state, so two concurrent writers would clobber each other mid-upsert.
    """
    staging = f"temp_staging_{uuid.uuid4().hex}"
    with db_contextmanager() as conn:
        # Upload DataFrame to a staging table
        df.to_sql(staging, conn, if_exists='replace', index=False)
        # Define columns in df to place in columns in sql db table
        cols = ",".join(df.columns)
        # Transfer data to the main table using INSERT OR REPLACE for an "upsert" operation
        conn.execute(f"""
            INSERT OR REPLACE INTO {table_name} ({cols})
            SELECT {cols} FROM {staging}
        """)
        conn.execute(f"DROP TABLE {staging}")

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

    calc_nav_units passes (previous snapshot date, today) so flows that landed on
    days without a snapshot (weekends, batch outages) are included. Flows on the
    start date are excluded because they were already counted in that snapshot's units.
    """
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
    try:
        df = read_db("SELECT MAX(Date) AS d FROM cashflow")
    except Exception:
        return None
    if not df.empty and pd.notna(df.iloc[0]['d']):
        return df.iloc[0]['d']
    return None


def get_meta(key: str, default=None):
    try:
        with db_contextmanager() as conn:
            row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default
    except sqlite3.OperationalError:
        return default


def set_meta(key: str, value: str):
    with db_contextmanager() as conn:
        conn.execute("INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)", (key, str(value)))


def prices_updated_today() -> bool:
    """True once today's index + symbol price history pass has already run."""
    return get_meta("last_symbol_prices_update") == date.today().strftime("%Y-%m-%d")


def missing_price_symbols():
    """Held symbols with no rows yet in symbol_price_history (first sighting)."""
    held = set(position_stock_symbols())
    with db_contextmanager() as conn:
        have = {r[0] for r in conn.execute("SELECT DISTINCT Symbol FROM symbol_price_history")}
    return sorted(held - have)

def calc_nav_units(current_date: datetime, snapshot_df: pd.DataFrame):
    """Compute today's NAV and unit count (TWR unitisation).

    NAV per unit moves only with market performance. External cash flows change
    the number of units instead, so a deposit cannot flatter the return:

        new_nav   = (total_assets - net_external_cashflow) / previous_units
        new_units = previous_units + (net_external_cashflow / new_nav)

    The first snapshot seeds 1000 units at the opening NAV.
    """
    total_assets = snapshot_df.loc[0, 'total_assets']
    date_str = current_date.strftime('%Y-%m-%d')
    prev_date = prev_snapshot_date(date_str)
    prev_nav, prev_units = prev_nav_units(date_str)
    if prev_units == 0 or prev_date is None:
        # First entry: seed the fund at 1000 units.
        new_units = 1000.0
        new_nav = total_assets / new_units
        net_cf = 0.0
    else:
        # Every external flow since the previous snapshot adjusts units at
        # today's NAV. Flows landing on days without a snapshot are caught by
        # the window rather than dropped.
        net_cf = net_cashflow(prev_date, date_str)

        # NAV changed only with market movement, not cash flow in/out
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
    """Aggregate realised order cash flows plus current position values/P&L by symbol, market, and currency."""
    option_pattern = r'[A-Z]+\d{6}[CP]\d+'
    historical_orders_p_l = historical_orders_data()

    # BUY = Negative (Cost), SELL = Positive (Revenue)
    historical_orders_p_l['Change'] = historical_orders_p_l.apply(calculate_change, axis=1)

    historical_orders_p_l = historical_orders_p_l.groupby(['Symbol', 'Market', 'Currency'])[['Change']].sum().reset_index().rename(columns={'Change': 'Net_P_L'})
    
    positions_mv = unrealised_p_l(today_date)
    # Options contribute unrealised P_L; stocks contribute current Market_Value.
    condition = positions_mv['Symbol'].astype(str).str.contains(option_pattern, regex=True)
    positions_mv['Net_P_L'] = np.where(
        condition, 
        positions_mv['P_L'],
        positions_mv['Market_Value']
    )
    
    positions_mv.drop(['Market_Value','P_L'], axis=1, inplace=True) 
    dfs = [df for df in [historical_orders_p_l, positions_mv] if not df.empty]
    if dfs:
        net_P_L = pd.concat(dfs, ignore_index=True)
    else:
        net_P_L = historical_orders_p_l

    net_P_L = net_P_L.groupby(['Symbol', 'Market', 'Currency'])[['Net_P_L']].sum().reset_index()
    # date is part of the PK, so each run's P/L row is retained alongside previous runs.
    net_P_L['date'] = today_date.strftime('%Y-%m-%d')
    return net_P_L


def get_latest_db_date(today_date: datetime = None):
    """Latest snapshot date in portfolio_snapshots as a datetime, or None if empty."""
    query = "SELECT date FROM portfolio_snapshots ORDER BY date DESC LIMIT 1"
    try:
        df = read_db(query)
    except Exception:
        return None
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


# ---------------------------------------------------------------------------
# symbol_meta: static classification, written by the batch, read by the dashboard
# ---------------------------------------------------------------------------

def read_symbol_meta() -> pd.DataFrame:
    """All cached symbol classifications. Empty frame with the right columns when none."""
    cols = ["Symbol", "Sector", "Industry", "Country", "Market_Cap", "Updated_At"]
    try:
        df = read_db("SELECT Symbol, Sector, Industry, Country, Market_Cap, Updated_At FROM symbol_meta")
    except sqlite3.OperationalError:
        return pd.DataFrame(columns=cols)
    return df if not df.empty else pd.DataFrame(columns=cols)


def upsert_symbol_meta(rows: list[dict]) -> int:
    """Insert/replace static classification rows. Returns rows written."""
    if not rows:
        return 0
    df = pd.DataFrame(rows)[
        ["Symbol", "Sector", "Industry", "Country", "Market_Cap", "Updated_At"]
    ]
    insert_dataframe(df, "symbol_meta")
    return len(df)


# ---------------------------------------------------------------------------
# Stored FX rate: lets the 10s live snapshot revalue USD holdings without a
# yfinance round-trip. The batch refreshes it; the dashboard only reads it.
# ---------------------------------------------------------------------------

def get_stored_fx_rate(from_ccy: str = "USD", to_ccy: str = "SGD") -> float | None:
    """Last known rate, or None. Keyed by pair so a missing rate is explicit."""
    key = f"fx_{from_ccy.upper()}_{to_ccy.upper()}"
    val = get_meta(key)
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def store_fx_rate(rate: float, from_ccy: str = "USD", to_ccy: str = "SGD") -> None:
    set_meta(f"fx_{from_ccy.upper()}_{to_ccy.upper()}", f"{rate}")


def convert_currency_cached(value, from_ccy: str, to_ccy: str = "SGD"):
    """Convert using the stored rate; never hits the network. Raises on a
    missing rate -- a silent 1.0 would corrupt every downstream total."""
    fc, tc = str(from_ccy).strip().upper(), str(to_ccy).strip().upper()
    if fc == tc:
        return round(float(value), 2)
    rate = get_stored_fx_rate(fc, tc)
    if rate is None or rate <= 0:
        raise RuntimeError(f"no stored FX rate for {fc}->{tc}; run the batch first")
    return round(float(value) * rate, 2)


# ---------------------------------------------------------------------------
# Live moomoo quote layer (background poller writes, dashboard reads)
# ---------------------------------------------------------------------------

def write_live_snapshot(account: dict, quotes: list[dict]) -> None:
    """Atomically replace the live account row and the live quote rows.

    Called from the poller thread only. Never touches batch-owned tables.
    """
    acct = pd.DataFrame([{
        "id": 1,
        "total_assets": account.get("total_assets"),
        "stocks": account.get("stocks"),
        "options": account.get("options"),
        "cash": account.get("cash"),
        "as_of": account.get("as_of"),
    }])
    qdf = pd.DataFrame(quotes)
    with db_contextmanager() as conn:
        conn.execute("DELETE FROM live_quotes")
        acct.to_sql("tmp_live_acct", conn, if_exists="replace", index=False)
        conn.execute(
            "INSERT OR REPLACE INTO live_account "
            "(id,total_assets,stocks,options,cash,as_of) "
            "SELECT id,total_assets,stocks,options,cash,as_of FROM tmp_live_acct"
        )
        conn.execute("DROP TABLE tmp_live_acct")
        if not qdf.empty:
            cols = ["Symbol", "Name", "Market", "Quantity", "Diluted_Cost",
                    "Current_Price", "Market_Value", "P_L_Percent", "P_L",
                    "Today_s_P_L", "Currency", "Portfolio_Percent", "date", "as_of"]
            qdf = qdf.reindex(columns=cols)
            qdf.to_sql("tmp_live_quotes", conn, if_exists="replace", index=False)
            conn.execute(
                "INSERT OR REPLACE INTO live_quotes (" + ",".join(cols) + ") "
                "SELECT " + ",".join(cols) + " FROM tmp_live_quotes"
            )
            conn.execute("DROP TABLE tmp_live_quotes")


def read_live_account() -> pd.DataFrame:
    try:
        return read_db("SELECT * FROM live_account WHERE id = 1")
    except sqlite3.OperationalError:
        return pd.DataFrame()


def read_live_quotes() -> pd.DataFrame:
    try:
        return read_db("SELECT * FROM live_quotes")
    except sqlite3.OperationalError:
        return pd.DataFrame()


def set_live_status(state: str, detail: str = "") -> None:
    set_meta("live_poller_state", state)
    set_meta("live_poller_detail", detail)


def clear_live_layer() -> None:
    """Drop stale live rows and reset the status. Called at startup so a
    crashed previous session cannot leave the dashboard showing 'connected'
    quotes that no poller is refreshing."""
    try:
        with db_contextmanager() as conn:
            conn.execute("DELETE FROM live_quotes")
            conn.execute("DELETE FROM live_account")
    except sqlite3.OperationalError:
        pass
    set_live_status("idle", "Starting fresh session.")


def get_live_status() -> tuple[str, str]:
    return (get_meta("live_poller_state", "idle") or "idle",
            get_meta("live_poller_detail", "") or "")


def main():
    return 0

if __name__ == "__main__":
    main()