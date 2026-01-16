import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date, timedelta
import matplotlib.pyplot as plt
import mplcyberpunk
import atexit

# Import existing project modules
from source import dashboard, db, moomoo_api
from config import settings
import main  # To access upload_to_db logic

# Register cleanup function to stop OpenD when the script exits (Ctrl+C)
atexit.register(moomoo_api.stop_opend)

# --- Page Configuration ---
st.set_page_config(
    page_title="Moomoo Portfolio Tracker",
    layout="wide",
    page_icon="📈",
    initial_sidebar_state="auto"
)

# --- Sidebar: Actions ---
with st.sidebar:
    st.title("Controls")
    st.write("Manage your portfolio data.")
    # --- Live Mode Toggle ---
    live_mode = st.toggle("🔴 Live Mode", value=False, help="Keeps OpenD running and auto-refreshes data.")
    
    if live_mode:
        refresh_rate = st.slider("Refresh Rate (Seconds)", 10, 300, 60)
        st.caption(f"Auto-refreshing every {refresh_rate}s...")
        
        # Auto-Update Logic
        with st.spinner("Fetching live data..."):
            try:
                today_date = datetime.combine(date.today(), datetime.min.time())
                # For live updates, we only need today's data (Fast)
                main.upload_to_db(today_date, today_date, keep_opend_alive=True)
            except Exception as e:
                st.error(f"Live update failed: {e}")
    
    # Manual Update Button (Only show if not in live mode to avoid conflict)
    elif st.button("🔄 Update Data from API", type="primary"):
        with st.spinner("Starting OpenD and fetching data..."):
            try:
                # Logic replicated from main.py
                today_date = datetime.combine(date.today(), datetime.min.time())
                # Update from 30 days ago to ensure coverage, or just today
                start_date = today_date - timedelta(days=5)
                
                # Call the existing update function
                main.upload_to_db(today_date, start_date, keep_opend_alive=True)
                st.success("Database updated successfully!")
                st.rerun() # Refresh the page to show new data
            except Exception as e:
                st.error(f"Error during update: {e}")

# --- Main Dashboard ---
st.title("📈 Moomoo Portfolio Dashboard", text_alignment = 'center')


# Setup styles
dashboard.setup()

# Helper to get the latest available date in DB
def get_latest_db_date():
    conn = sqlite3.connect(str(settings.MOOMOO_PORTFOLIO_DB_PATH))
    try:
        query = "SELECT date FROM portfolio_snapshots ORDER BY date DESC LIMIT 1"
        df = pd.read_sql_query(query, conn)
        if not df.empty:
            return datetime.strptime(df.iloc[0]['date'], '%Y-%m-%d')
        return None
    finally:
        conn.close()

latest_date = get_latest_db_date()
previous_date = latest_date - timedelta(days=1)


if latest_date:
    # --- Top Metrics Row ---
    conn = sqlite3.connect(str(settings.MOOMOO_PORTFOLIO_DB_PATH))
    snapshot_df = pd.read_sql_query(f"SELECT * FROM portfolio_snapshots WHERE date = '{latest_date.strftime('%Y-%m-%d')}'", conn)
    prev_snapshot_df = pd.read_sql_query(f"SELECT * FROM portfolio_snapshots WHERE date = '{previous_date.strftime('%Y-%m-%d')}'", conn)
    conn.close()

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
        prev = prev_snapshot_df.iloc[0]
        def get_metric_delta(curr, prev, column_name: str):
            return curr[column_name], round(curr[column_name] - prev[column_name],2)
        col1_metric = curr['stocks']+curr['cash']+curr['options']
        col1_delta = round(col1_metric - prev['stocks']-prev['cash']-prev['options'],2)
        col2_metric, col2_delta = get_metric_delta(curr, prev, 'stocks')
        col3_metric, col3_delta = get_metric_delta(curr, prev, 'options')
        col4_metric, col4_delta = get_metric_delta(curr, prev, 'cash')
        col5_metric, col5_delta = get_metric_delta(curr, prev, 'nav')
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.metric("Total Assets (SGD)", f"${col1_metric:,.2f}",delta=col1_delta)
        col2.metric("Stocks", f"${col2_metric:,.2f}", delta=col2_delta)
        col3.metric("Options", f"${col3_metric:,.2f}", delta=col3_delta)
        col4.metric("Cash Balance", f"${col4_metric:,.2f}", delta=col4_delta)
        col5.metric("NAV", f"{col5_metric:.4f}",delta=col5_delta)
        col6.metric("Last Updated", datetime.strptime(curr['date'],"%Y-%m-%d").strftime("%b %d, %Y"))
        

    # --- Tabs for different views ---
    tab1, tab2, tab3 = st.tabs(["📊 Overview", "📋 Positions", "💰 P/L Analysis"])

    with tab1:
        # col_left, col_right = st.columns(2)
        
        
        #st.subheader("Asset Allocation",text_alignment = 'center')
        _, col1, _ = st.columns([0.2,0.6,0.2])
        # Get allocation data for the specific date
        alloc_df = dashboard.asset_allocation_data(latest_date)
        with col1:
            if not alloc_df.empty:
                fig_alloc = dashboard.plot_asset_allocation(alloc_df)
                st.pyplot(fig_alloc)
            else:
                st.warning("No allocation data for this date.")

        col2, col3 = st.columns(2)
        with col2:
            #st.subheader("Asset Trend")
            trend_df = dashboard.asset_trend_data()
            fig_trend = dashboard.plot_asset_trend(trend_df)
            st.pyplot(fig_trend)
        with col3:
            #st.subheader("Time Weighted Returns (TWR)")
            twr_df = dashboard.twr_data()
            fig_twr = dashboard.plot_twr(twr_df)
            st.pyplot(fig_twr)
        # _, col3, _ = st.columns([0.2,0.6,0.2])
        
        

    with tab2:
        st.subheader(f"Positions as of {latest_date.strftime('%b %d, %Y')}")
        conn = sqlite3.connect(str(settings.MOOMOO_PORTFOLIO_DB_PATH))
        pos_df = pd.read_sql_query(f"SELECT * FROM positions WHERE date = '{latest_date.strftime('%Y-%m-%d')}'", conn)
        conn.close()
        st.dataframe(pos_df, use_container_width=True)

    with tab3:
        st.subheader("Net P/L by Market")
        col_us, col_sg = st.columns(2)
        with col_us:
            st.write("**🇺🇸 US Market**")
            st.dataframe(dashboard.market_p_l_type('US'), use_container_width=True)
        with col_sg:
            st.write("**🇸🇬 SG Market**")
            st.dataframe(dashboard.market_p_l_type('SG'), use_container_width=True)

else:
    st.info("No data found in database. Please click 'Update Data from API' in the sidebar to initialize.")
