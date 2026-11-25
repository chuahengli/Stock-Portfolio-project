"""Streamlit dashboard. Read-only -- main.py is the only database writer."""
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import subprocess
import sys
from pathlib import Path

from source import dashboard, db, live

PROJECT_ROOT = Path(__file__).resolve().parent


def run_batch_subprocess() -> tuple[bool, str]:
    """Run main.py as a separate process so the UI never holds a broker session."""
    try:
        proc = subprocess.run(
            [sys.executable, "main.py"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=900,
        )
        ok = proc.returncode == 0
        tail = (proc.stdout or "")[-2000:] + (proc.stderr or "")[-2000:]
        return ok, tail
    except subprocess.TimeoutExpired:
        return False, "Batch timed out after 900s."
    except Exception as e:  # pragma: no cover - environment dependent
        return False, f"Failed to launch batch: {e}"




# --- Page Configuration ---
st.set_page_config(
    page_title="Moomoo Portfolio Tracker",
    layout="wide",
    page_icon="📈",
    initial_sidebar_state="auto"
)
    
    

# --- Main Dashboard ---
st.title("📈 Moomoo Portfolio Dashboard", text_alignment = 'center')
# --- Live Mode Toggle ---
refresh_rate = 10
live_mode = st.toggle(
    "🔴 Live Mode", value=True,
    help="Re-read the database every 10 seconds and poll moomoo quotes into "
         "the live layer. The nightly batch remains the only writer of record.",
)
poller = live.LivePoller.get(refresh_rate)

# A previous app process may have been killed without running cleanup. Wipe
# its stale quotes and "connected" flag ONCE per Streamlit session (session
# state survives fragment reruns, so this does not run on every 10s tick).
if "live_session_initialised" not in st.session_state:
    st.session_state["live_session_initialised"] = True
    try:
        db.clear_live_layer()
    except Exception:
        pass

if live_mode:
    poller.start()
else:
    poller.stop()

# --- Manual refresh: the ONE way the UI can cause a write ---
with st.sidebar:
    st.subheader("Data")
    latest_meta = db.get_meta("last_symbol_prices_update", "never")
    st.caption(f"Last price update: {latest_meta}")
    if st.button("Refresh from broker", help="Runs main.py as a separate process, then reloads. Takes ~60s."):
        with st.spinner("Running the daily batch..."):
            ok, detail = run_batch_subprocess()
        if ok:
            st.success("Batch completed. Reloading...")
            st.rerun()
        else:
            st.error("Batch failed. See logs/daily_log.txt")
            with st.expander("Output"):
                st.code(detail or "(no output)")

    

@st.cache_data(scope = 'session')
def past_data(today_str: str,table_name: str):
    with db.db_contextmanager() as conn:
        past_data_df = pd.read_sql_query(f"SELECT * FROM {table_name} WHERE date < ?", conn, params=(today_str,))
    return past_data_df
# cache to store for refresh rate so that any calls to the function use the stored value instead before next run
@st.cache_data(ttl=refresh_rate)
def live_data(today_str: str,table_name: str):
    with db.db_contextmanager() as conn:
        live_data_df = pd.read_sql_query(f"SELECT * FROM {table_name} WHERE date = ?", conn, params=(today_str,))
    return live_data_df

def combined_data(table_name: str):
    if table_name == 'portfolio_snapshots':
        today_str = date.today().strftime('%Y-%m-%d')
        sort_col = 'date'
    elif table_name == 'benchmark_history':
        today_str = datetime.combine(date.today(), datetime.min.time())
        sort_col = 'Date'
    
    p_data = past_data(today_str, table_name)
    l_data = live_data(today_str, table_name)
    
    # Filter out empty dataframes to avoid FutureWarning about concatenation with empty/NA entries
    dfs = [df for df in [p_data, l_data] if not df.empty]
    
    full_df = pd.concat(dfs) if dfs else p_data
    full_df = full_df.sort_values(sort_col, ascending=True).reset_index(drop=True)
    return full_df


def render_live_status():
    """Show what the 10s cycle actually does, and the age of the broker data."""
    state, detail = db.get_live_status()
    # The batch date is the last nightly snapshot, not the internal
    # symbol_meta flag (which is a maintenance detail).
    try:
        d = db.get_latest_db_date()
        batch_asof = d.strftime('%Y-%m-%d') if d else "never"
    except Exception:
        batch_asof = "never"
    label = {"connected": "connected", "starting": "starting",
             "disconnected": "reconnecting", "error": "quote error",
             "idle": "off"}.get(state, state)
    colour = {"connected": "#4CAF50", "error": "#E57373",
              "disconnected": "#D4AF37"}.get(state, "#9A9A9A")
    st.markdown(
        f"<span style='font-size:0.85rem;color:#9A9A9A;'>"
        f"Live poll: <span style='color:{colour};'>{label}</span> · "
        f"batch: {batch_asof} · re-reading every {refresh_rate}s</span>",
        unsafe_allow_html=True,
    )
    if state == "error" and detail:
        with st.expander("Quote error detail"):
            st.code(detail)




@st.fragment(run_every=refresh_rate)
def render_live():
    render_live_status()
    current_time = datetime.now().strftime('%b %d, %Y %H:%M:%S')
    latest_date = db.get_latest_db_date(datetime.combine(date.today(), datetime.min.time()))
    
    if not latest_date:
        st.info("No data found in database. Run `python main.py`, or use 'Refresh from broker' in the sidebar.")
        return
    
    previous_date = latest_date - timedelta(days=1)
    portfolio_snapshots_df = combined_data('portfolio_snapshots')
    benchmark_df = combined_data('benchmark_history')
    # Live layer: when a fresh moomoo quote snapshot exists, overlay it on the
    # batch's positions (same schema). The batch-owned tables are never written
    # from this render loop.
    live_acct = db.read_live_account()
    live_q = db.read_live_quotes()
    use_live = (not live_acct.empty and not live_q.empty
                and 'as_of' in live_acct.columns
                and str(live_acct.iloc[0].get('as_of') or '')[:10]
                    == date.today().strftime('%Y-%m-%d'))
    if use_live:
        pos_df = live_q.copy()
        st.caption(f"Live moomoo quotes · {live_acct.iloc[0]['as_of']}")
    else:
        pos_df = db.read_db(
            f"SELECT * FROM positions WHERE date = '{latest_date.strftime('%Y-%m-%d')}'"
        )
    pos_df = dashboard.display_pos(pos_df)

    # --- Top Metrics Row ---
    snapshot_df = portfolio_snapshots_df.loc[portfolio_snapshots_df['date'] == latest_date.strftime('%Y-%m-%d')]
    
    prev_snapshot_df = portfolio_snapshots_df.loc[portfolio_snapshots_df['date'] < latest_date.strftime('%Y-%m-%d')].tail(1)

    st.markdown("""
    <style>
    [data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        text-align: left !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 1.2rem !important;
        text-align: left !important;
        display: block !important;
    }
    [data-testid="stMetricDelta"] {
        justify-content: center !important;
    }
    </style>
    """, unsafe_allow_html=True)
    if not snapshot_df.empty:
        curr = snapshot_df.iloc[0]
        if prev_snapshot_df.empty:
            prev = curr  # first-ever snapshot: no prior day exists, deltas read as zero
        else:
            prev = prev_snapshot_df.iloc[0]
        def get_metric_delta(curr, prev, column_name: str):
            change = round(curr[column_name] - prev[column_name],2)
            prev_val = prev[column_name]
            if pd.isna(prev_val) or prev_val == 0:
                # % change is undefined against a zero base (e.g. options were
                # 0 the day before and re-opened) -- show the absolute change
                # instead of crashing the metrics row with ZeroDivisionError.
                return curr[column_name], f"{change} (n/a)"
            percentage_change = (curr[column_name] - prev_val) / prev_val
            delta = f"{change} ({percentage_change:.2%})" if percentage_change != 0 else f"{change} (0.0%)"
            return curr[column_name], delta
        
        col1_metric,col1_delta = get_metric_delta(curr, prev, 'total_assets')
        col2_metric, col2_delta = get_metric_delta(curr, prev, 'stocks')
        col3_metric, col3_delta = get_metric_delta(curr, prev, 'options')
        col4_metric, col4_delta = get_metric_delta(curr, prev, 'cash')
        col1, col2, col3, col4, col6 = st.columns(5)
        col1.metric("Total Assets (SGD)", f"${col1_metric:,.2f}",delta=col1_delta)
        col2.metric("Stocks", f"${col2_metric:,.2f}", delta=col2_delta)
        col3.metric("Options", f"${col3_metric:,.2f}", delta=col3_delta)
        col4.metric("Cash Balance", f"${col4_metric:,.2f}", delta=col4_delta)
        col6.metric("Refreshed", current_time)
    # --- Tabs for different views ---
    overview, positions, p_l_analysis, ledger = st.tabs(["📊 Overview", "📋 Positions", "💰 P/L Analysis", "Trade Ledger"])

    with overview:
        # Get allocation data for the specific date
        inception_date = db.get_inception_date()
        returns_str = dashboard.get_twr(portfolio_snapshots_df, inception_date, latest_date)
        
        alloc_df = snapshot_df.loc[:,['stocks','options','cash']]
        if alloc_df.empty:
            # Race guard: this fragment can render before the first upload of a
            # new day lands in the cached queries -- skip this tick.
            return
        total_assets = alloc_df.sum(axis=1).values[0]
        

        asset_trend, twr_trend,asset_alloc = st.columns([4,4,2])
        with asset_trend:
            st.markdown(
                    f"<span style='font-size:24px;'>Total Assets(SGD): ${total_assets:,.2f}</span>",
                    unsafe_allow_html=True
                )
            fig_trend = dashboard.plot_asset_trend(portfolio_snapshots_df)
            st.plotly_chart(fig_trend)
        with twr_trend:
            try:
                twr_val = float(returns_str.replace('%', ''))
            except ValueError:
                twr_val = None  # 'N/A' (e.g. render tick before today's snapshot is cached)
            if twr_val is None:
                st.markdown(
                    f"<span style='font-size:24px;'>Time Weighted Returns: {returns_str}</span>",
                    unsafe_allow_html=True
                )
            else:
                sign = "+" if twr_val >= 0 else ""
                colour = "green" if twr_val >= 0 else "red"
                st.markdown(
                    f"<span style='font-size:24px;'>Time Weighted Returns: </span>"
                    f"<span style='color:{colour}; font-size:24px;'>{sign}{returns_str}</span>",
                    unsafe_allow_html=True
                )
            comparison = dashboard.comparison_df(portfolio_snapshots_df, benchmark_df)
            fig_comparison = dashboard.plt_performance_comparison(dashboard.comparison_percent(comparison))
            st.plotly_chart(fig_comparison)

        with asset_alloc:
            if not alloc_df.empty:
                fig_alloc = dashboard.plot_asset_allocation(alloc_df)
                st.plotly_chart(fig_alloc)
            else:
                st.warning("No allocation data for this date.")
            
        
        portfolio_characteristics,pos_overview = st.columns([6.5,3.5])
        with portfolio_characteristics:
            st.plotly_chart(dashboard.plot_portfolio_characteristics(pos_df))
        
        with pos_overview:
            st.dataframe(dashboard.positions_overview(pos_df), hide_index=True,
                        column_config={'Market_Value': st.column_config.NumberColumn('Market Value',
                                                                                    format="localized"),
                                        'Current_Price': st.column_config.NumberColumn('Current Price',
                                                                                    format="%.2f"),
                                        'P_L_Percent': st.column_config.NumberColumn('P/L %',
                                                                                  format="percent"),
                                        'P_L': st.column_config.NumberColumn('P/L',
                                                                                    format="%+.2f"),
                                        'Today_s_P_L': st.column_config.NumberColumn('Today\'s P/L',
                                                                                    format="%+.2f"),
                                        'Ticker_Total_Val': st.column_config.NumberColumn('Portfolio %',
                                                                                    format="%.2f %%")
                                        } 
                        )

        
        

    
    

        # --- Dividend / Coupon Income Attribution ---
        st.markdown("#### Dividend / Coupon Income")
        _income_df = db.income_by_date()
        inc_chart, inc_metric = st.columns([4, 1])
        with inc_chart:
            st.plotly_chart(dashboard.plot_income_trend(_income_df), width='stretch')
        with inc_metric:
            if not _income_df.empty:
                total_inc = _income_df['Cumulative'].iloc[-1]
                last_inc = _income_df['Amount'].iloc[-1]
                st.metric("Net Income (cumulative, SGD)", f"${total_inc:,.2f}")
                st.metric("Latest (SGD)", f"${last_inc:,.2f}")
            else:
                st.info("No dividend/coupon income recorded yet.")
        st.divider()

    with positions:
        st.subheader(f"Positions as of {latest_date.strftime('%b %d, %Y')}")
        pos_df_styled = dashboard.style_pos(pos_df)
        st.table(pos_df_styled)
        
        




    with p_l_analysis:
        st.subheader("Net P/L by Market")
        col_us, col_sg = st.columns(2)
        with col_us:
            st.write("**🇺🇸 US Market**")
            us_p_l = dashboard.market_p_l_type('US').sort_values(by='Total_Net_P_L', ascending=False)
            subset_cols = [col for col in ['Stock', 'Option', 'Total_Net_P_L'] if col in us_p_l.columns]
            us_p_l = us_p_l.style.map(dashboard.style_negative_red_positive_green, subset=subset_cols)
            st.dataframe(us_p_l.format("{:+,.2f}", subset=subset_cols),
                        column_config={
                                        'Stock': st.column_config.NumberColumn('Stock'),
                                        'Option': st.column_config.NumberColumn('Option'),
                                        'Total_Net_P_L': st.column_config.NumberColumn('Net P/L')
                                        }
                        )
            
        with col_sg:
            st.write("**🇸🇬 SG Market**")
            sg_p_l = dashboard.market_p_l_type('SG').sort_values(by='Total_Net_P_L', ascending=False)
            subset_cols = [col for col in ['Stock', 'Option', 'Total_Net_P_L'] if col in sg_p_l.columns]
            sg_p_l = sg_p_l.style.map(dashboard.style_negative_red_positive_green, subset=subset_cols)
            st.dataframe(sg_p_l.format("{:+,.2f}", subset=subset_cols),
                        column_config={
                                        'Stock': st.column_config.NumberColumn('Stock'),
                                        'Total_Net_P_L': st.column_config.NumberColumn('Net P/L')
                                        }
                        )

    with ledger:
        st.subheader("Trade Ledger (Buy/Sell Audit)")
        ledger_data = dashboard.trade_ledger()
        if ledger_data.empty:
            st.info("No transaction records yet. Run a daily update to build the ledger.")
        else:
            mkt_opts = ["All"] + sorted(ledger_data["Market"].dropna().unique().tolist())
            sel_mkt = st.selectbox("Market", mkt_opts, key="ledger_mkt")
            view = ledger_data if sel_mkt == "All" else ledger_data[ledger_data["Market"] == sel_mkt]
            total_cf = view["Gross_Amount"].sum()
            st.metric("Net Realised Cash Flow (as-traded)", f"{total_cf:+,.2f}")
            st.dataframe(
                view[["date_time", "Symbol", "Name", "Market", "Buy_Sell",
                      "Quantity", "Fill_Price", "Multiplier", "Gross_Amount", "Currency"]]
                .reset_index(drop=True),
                width='stretch',
                height=420,
                column_config={
                    "date_time": "Date/Time",
                    "Buy_Sell": "Side",
                    "Fill_Price": st.column_config.NumberColumn("Fill Price"),
                    "Multiplier": st.column_config.NumberColumn("Mult"),
                    "Gross_Amount": st.column_config.NumberColumn("Cash Flow ($)"),
                },
            )
            st.caption(
                "Signed Cash Flow: SELL / SELL_SHORT = + (cash in), BUY / BUY_BACK = - (cash out). "
                "Options use the x100 contract multiplier. Amounts are in the as-traded currency (USD/SGD)."
            )
            with st.expander("Net Cash Flow by Symbol"):
                summary = dashboard.ledger_summary(sel_mkt if sel_mkt != "All" else None)
                if not summary.empty:
                    st.dataframe(summary, width='stretch')

render_live()
