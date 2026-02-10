import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date, timedelta
import matplotlib.pyplot as plt
import mplcyberpunk
import atexit
import plotly.express as px

# Import existing project modules
from source import dashboard, db, moomoo_api
from config import settings
import main  # To access upload_to_db logic

atexit.register(moomoo_api.stop_opend)

@st.cache_resource
def persistent_opend():
    """Return True if OpenD is ready, False otherwise. Cache so that it's only checked once."""
    return moomoo_api.ensure_opend_is_ready()



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
live_mode = st.toggle("🔴 Live Mode", value=True, help="Auto-refresh data every 10 seconds.")
refresh_rate = 10
if live_mode:
        st.caption(f"Auto-refreshing every {refresh_rate}s...")

    

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




@st.fragment(run_every=refresh_rate if live_mode else None)
def live_update_db():
    try:
        today_date = datetime.combine(date.today(), datetime.min.time())
        main.upload_to_db(today_date, today_date, keep_opend_alive=True)
    except Exception as e:
        print(f"Error updating database: {e}")

@st.fragment(run_every=refresh_rate if live_mode else None)
def render_live():
    current_time = datetime.now().strftime('%b %d, %Y %H:%M:%S')
    latest_date = db.get_latest_db_date(datetime.combine(date.today(), datetime.min.time()))
    
    if not latest_date:
        st.info("No data found in database. Please click 'Update Data from API' in the sidebar.")
        return
    
    previous_date = latest_date - timedelta(days=1)
    portfolio_snapshots_df = combined_data('portfolio_snapshots')
    benchmark_df = combined_data('benchmark_history')                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               
    pos_df = db.read_db(f"SELECT * FROM positions WHERE date = '{latest_date.strftime('%Y-%m-%d')}'")
    pos_df=dashboard.display_pos(pos_df)

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
        prev = prev_snapshot_df.iloc[0]
        def get_metric_delta(curr, prev, column_name: str):
            change = round(curr[column_name] - prev[column_name],2)
            percentage_change = (curr[column_name] - prev[column_name]) / prev[column_name]
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
        #col5.metric("NAV", f"{col5_metric:.4f}",delta=col5_delta)
        col6.metric("Last Updated", current_time)
    # --- Tabs for different views ---
    overview, positions, p_l_analysis = st.tabs(["📊 Overview", "📋 Positions", "💰 P/L Analysis"])

    with overview:
        # col_left, col_right = st.columns(2)
        
        
        #st.subheader("Asset Allocation",text_alignment = 'center')
        # Get allocation data for the specific date
        returns_str = dashboard.get_twr(portfolio_snapshots_df, datetime.strptime('2026-01-12', '%Y-%m-%d'), latest_date)
        
        alloc_df = snapshot_df.loc[:,['stocks','options','cash']]
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
            sign = "+" if float(returns_str.replace('%', '')) >= 0 else ""
            if float(returns_str.replace('%', '')) >= 0:
                st.markdown(
                    f"<span style='font-size:24px;'>Time Weighted Returns: </span>"
                    f"<span style='color:green; font-size:24px;'>{sign}{returns_str}</span>", 
                    unsafe_allow_html=True
                )
                #st.markdown(f"<span style='color:green; font-size:24px;'>{sign}{returns_str}</span>", unsafe_allow_html=True)
                
            else:
                #st.markdown(f"<span style='font-size:24px;'>Portfolio Return:</span>", unsafe_allow_html=True)
                #st.markdown(f"<span style='color:red; font-size:24px;'>{sign}{returns_str}</span>", unsafe_allow_html=True)
                st.markdown(
                    f"<span style='font-size:24px;'>Time Weighted Returns: </span>"
                    f"<span style='color:red; font-size:24px;'>{sign}{returns_str}</span>", 
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

render_live()  
persistent_opend()
live_update_db()
