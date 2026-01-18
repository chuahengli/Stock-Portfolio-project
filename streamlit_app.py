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
    live_mode = st.toggle("🔴 Live Mode", value=True, help="Auto-refresh data every 10 seconds.")
    refresh_rate = 10

    if live_mode:
        st.caption(f"Auto-refreshing every {refresh_rate}s...")
    

# --- Main Dashboard ---
st.title("📈 Moomoo Portfolio Dashboard", text_alignment = 'center')


# Setup styles
dashboard.setup()
    

# Helper to get the latest available date in DB
@st.cache_data(scope = 'session')
def get_latest_db_date():
    query = "SELECT date FROM portfolio_snapshots ORDER BY date DESC LIMIT 1"
    df = db.read_db(query)
    if not df.empty:
        return datetime.strptime(df.iloc[0]['date'], '%Y-%m-%d')
    return None
# Style Pandas dataframe
def style_negative_red_positive_green(val):
            color = '#A52A2A' if val < 0 else '#4CAF50'
            return f'color: {color}'

@st.cache_data(scope = 'session')
def get_past_data(today_str: str):
    with db.db_contextmanager() as conn:
        portfolio_snapshots_df = pd.read_sql_query("SELECT * FROM portfolio_snapshots WHERE date < ?", conn, params=(today_str,))
        #positions_df = pd.read_sql_query("SELECT * FROM positions WHERE date < ?", conn, params=(today_str,))
        #cashflow_df = pd.read_sql_query(f"SELECT * FROM cashflow", conn)
        #historical_orders_df = pd.read_sql_query(f"SELECT * FROM historical_orders", conn)
        #net_p_l_df = pd.read_sql_query(f"SELECT * FROM net_p_l", conn)
    return portfolio_snapshots_df#, positions_df, cashflow_df, historical_orders_df
# cache to store for refresh rate so that any calls to the function use the stored value instead before next run
@st.cache_data(ttl=refresh_rate)
def get_live_data(today_str: str):
    with db.db_contextmanager() as conn:
        portfolio_snapshots_df = pd.read_sql_query("SELECT * FROM portfolio_snapshots WHERE date = ?", conn, params=(today_str,))
    return portfolio_snapshots_df
def get_combined_data():
    today_str = date.today().strftime('%Y-%m-%d')
    full_df = pd.concat([get_past_data(today_str), get_live_data(today_str)]).sort_values('date',ascending=True).reset_index(drop=True)
    return full_df




@st.fragment(run_every=refresh_rate if live_mode else None)
def live_update_db():
    try:
        today_date = datetime.combine(date.today(), datetime.min.time())
        main.upload_to_db(today_date, today_date, keep_opend_alive=True)
        print("Database updated successfully.")
    except Exception as e:
        print(f"Error updating database: {e}")

@st.fragment(run_every=refresh_rate if live_mode else None)
def render_live():
    latest_date = get_latest_db_date()
    
    if not latest_date:
        st.info("No data found in database. Please click 'Update Data from API' in the sidebar.")
        return
    
    previous_date = latest_date - timedelta(days=1)
    portfolio_snapshots_df = get_combined_data()

    # --- Top Metrics Row ---
    snapshot_df = portfolio_snapshots_df.loc[portfolio_snapshots_df['date'] == latest_date.strftime('%Y-%m-%d')]
    
    prev_snapshot_df = portfolio_snapshots_df.loc[portfolio_snapshots_df['date'] == previous_date.strftime('%Y-%m-%d')]

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
        #col5_metric, col5_delta = get_metric_delta(curr, prev, 'nav')
        col1, col2, col3, col4, col6 = st.columns(5)
        col1.metric("Total Assets (SGD)", f"${col1_metric:,.2f}",delta=col1_delta)
        col2.metric("Stocks", f"${col2_metric:,.2f}", delta=col2_delta)
        col3.metric("Options", f"${col3_metric:,.2f}", delta=col3_delta)
        col4.metric("Cash Balance", f"${col4_metric:,.2f}", delta=col4_delta)
        #col5.metric("NAV", f"{col5_metric:.4f}",delta=col5_delta)
        col6.metric("Last Updated", datetime.strptime(curr['date'],"%Y-%m-%d").strftime("%b %d, %Y"))
    # --- Tabs for different views ---
    tab1, tab2, tab3 = st.tabs(["📊 Overview", "📋 Positions", "💰 P/L Analysis"])

    with tab1:
        # col_left, col_right = st.columns(2)
        
        
        #st.subheader("Asset Allocation",text_alignment = 'center')
        _, col1, _ = st.columns([0.2,0.6,0.2])
        # Get allocation data for the specific date
        returns_str = dashboard.get_twr(portfolio_snapshots_df, datetime.strptime('2026-01-12', '%Y-%m-%d'), latest_date)
        
        alloc_df = snapshot_df.loc[:,['stocks','options','cash']]
        with col1:
            
            if not alloc_df.empty:
                fig_alloc = dashboard.plot_asset_allocation(alloc_df)
                st.pyplot(fig_alloc)
            else:
                st.warning("No allocation data for this date.")

        col2, col3 = st.columns(2)
        with col2:
            #st.subheader("Asset Trend")
            trend_df = portfolio_snapshots_df.loc[:,['date','total_assets']]
            fig_trend = dashboard.plot_asset_trend(trend_df)
            st.pyplot(fig_trend)
        with col3:
            #st.subheader("Time Weighted Returns")
            #st.text("Time Weighted Returns (TWR)")
            sign = "+" if float(returns_str.replace('%', '')) >= 0 else ""
            #col3.metric("Time Weighted Returns", f"{returns_str}")
            #st.markdown(f"**{returns_str}**")
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

            twr_df = portfolio_snapshots_df.loc[:,['date','nav']]
            fig_twr = dashboard.plot_twr(twr_df)
            st.pyplot(fig_twr)

        # _, col3, _ = st.columns([0.2,0.6,0.2])
    
    

    with tab2:
        st.subheader(f"Positions as of {latest_date.strftime('%b %d, %Y')}")
        
        pos_df = db.read_db(f"SELECT * FROM positions WHERE date = '{latest_date.strftime('%Y-%m-%d')}'")
        
        # Add column is option or not
        option_pattern = r'[A-Z]+\d{6}[CP]\d+'
        pos_df['Is_Option'] = pos_df['Symbol'].str.contains(option_pattern, regex=True)
        # Identify what Ticker, and if is option or stock
        pos_df['Ticker'] = pos_df.apply(lambda x: dashboard.get_base_ticker(x['Symbol'], x['Is_Option']), axis=1)
        pos_df['Asset_Type'] = pos_df['Is_Option'].map({True: 'Option', False: 'Stock'})

        # Grouping and Sorting: Calculate total portfolio % per ticker to sort groups by size
        # Convert 'Portfolio_Percent' (e.g., "12.5%") to float for calculation
        pos_df['Sort_Val'] = pos_df['Portfolio_Percent'].astype(str).str.rstrip('%').astype(float)
        # Create new dataframe with Ticker total value for each ticker sum it
        ticker_totals = pos_df.groupby('Ticker')['Sort_Val'].sum().reset_index(name='Ticker_Total_Val')
        # Merge onto Ticker column to match respective ticker, total ticker percentage on resepective ticker regardless option or stock
        pos_df = pos_df.merge(ticker_totals, on='Ticker')
        # Sort by Ticker Total (desc), then by individual position value (desc)
        pos_df = pos_df.sort_values(by=['Ticker_Total_Val', 'Sort_Val'], ascending=[False, False])
        
        # Reorder columns to show Ticker and Asset Type first
        cols_order = ['Ticker', 'Symbol', 'Asset_Type'] + [c for c in pos_df.columns if c not in ['Ticker', 'Symbol', 'Asset_Type', 'Is_Option', 'Sort_Val', 'Ticker_Total_Val']]
        pos_df = pos_df[cols_order]
        # Make P/L Green and Red if positive or negative
        pos_df = pos_df.style.map(style_negative_red_positive_green, subset=['P_L_Percent','P_L', 'Today_s_P_L'])
        st.dataframe(pos_df, hide_index=True,
                     column_config={'date': None,
                                    'Quantity': st.column_config.NumberColumn('Quantity',
                                                                                  format="localized"),
                                    
                                    'Diluted_Cost': st.column_config.NumberColumn('Diluted Cost',
                                                                                  format="localized"),                                      
                                    'Market_Value': st.column_config.NumberColumn('Market Value',
                                                                                  format="localized"),
                                    'Current_Price': st.column_config.NumberColumn('Current Price',
                                                                                  format="localized"),
                                    'P_L_Percent': st.column_config.NumberColumn('P/L %',
                                                                                  format="%.2f %%"),
                                    'P_L': st.column_config.NumberColumn('P/L',
                                                                                  format="localized"),
                                    'Today_s_P_L': st.column_config.NumberColumn('Today\'s P/L',
                                                                                  format="localized"),
                                    'Portfolio_Percent': st.column_config.NumberColumn('Portfolio %',
                                                                                  format="percent")
                                    } 
                    )

    with tab3:
        st.subheader("Net P/L by Market")
        col_us, col_sg = st.columns(2)
        with col_us:
            st.write("**🇺🇸 US Market**")
            us_p_l = dashboard.market_p_l_type('US').sort_values(by='Total_Net_P_L', ascending=False)
            subset_cols = [col for col in ['Stock', 'Option', 'Total_Net_P_L'] if col in us_p_l.columns]
            us_p_l = us_p_l.style.map(style_negative_red_positive_green, subset=subset_cols)
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
            sg_p_l = sg_p_l.style.map(style_negative_red_positive_green, subset=subset_cols)
            st.dataframe(sg_p_l.format("{:+,.2f}", subset=subset_cols),
                        column_config={
                                        'Stock': st.column_config.NumberColumn('Stock'),
                                        'Total_Net_P_L': st.column_config.NumberColumn('Net P/L')
                                        }
                        )

render_live()  
live_update_db()
