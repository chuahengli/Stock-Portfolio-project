"""Plotly figures and DataFrame formatting for the Streamlit dashboard.

Read-only. Static classification (sector / industry / country / market cap)
comes from the `symbol_meta` table, populated by the batch. No network calls
happen here: the 10s render loop must stay cheap and independent of yfinance.
"""
from source import db

from datetime import date, datetime, timedelta
import pandas as pd
import re
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

# Style Pandas dataframe
def style_negative_red_positive_green(val):
            color = '#A52A2A' if val < 0 else '#4CAF50'
            return f'color: {color}'

def asset_allocation_data(current_date:datetime):
    date_str = current_date.strftime('%Y-%m-%d')
    query = f"SELECT stocks,options,cash FROM portfolio_snapshots WHERE date = '{date_str}'"
    df = db.read_db(query)
    return df

def plot_asset_allocation(df: pd.DataFrame):
    df=df.copy().T
    df.columns = ['Value']    
    if df.empty:
        return empty_fig()
    
    total_assets = df['Value'].sum()
    df['Legend_Label'] = [
        f"{idx}: {val/total_assets:.1%}" 
        for idx, val in zip(df.index, df['Value'])
    ]
    text_label = [f"${val:,.2f}" for val in df['Value']]
    fig = px.bar(df,
                x='Value',
                y=df.index,
                orientation='h',
                template='plotly_dark',
                color='Legend_Label',
                text=text_label,
                height=400
                )
    fig.update_layout(
                    xaxis=dict(automargin=True,visible=False),
                    yaxis=dict(tickfont=dict(size=14),automargin=True,title_text=""),
                    xaxis_range=[0, max(df['Value']) * 1.2],
                    title_text="",
                    font=dict(
                            size=14
                            ),
                    legend_title_text="Asset Breakdown",
                    legend={
                                'yanchor':"top",
                                'y':0.99,
                                'xanchor': "left",
                                'x': 0.9,
                                'font': {
                                        'size': 14
                                        },
                                'title': {
                                            'font': {
                                                    'size': 14
                                                    }    
                                        }
                            },
                    hovermode=False
                    )
    fig.update_traces(textfont_size=14, textposition='outside',cliponaxis=False)
    return fig

def market_p_l_type(market: str):
    # Latest snapshot only; earlier dates remain queryable in net_p_l.
    query = "SELECT * FROM net_p_l WHERE date = (SELECT MAX(date) FROM net_p_l)"
    net_P_L = db.read_db(query)
    
    # Split by market 'US','SG','HK' etc.
    net_P_L = net_P_L[net_P_L['Market']==market].round(2)
    # If option
    option_pattern = r'[A-Z]+\d{6}[CP]\d+'
    # Column with Is_Option. 
    net_P_L['Is_Option'] = net_P_L['Symbol'].str.contains(option_pattern, regex=True)
    # New Column 'Ticker' according to if Option or not
    net_P_L['Ticker'] = net_P_L.apply(lambda x: get_base_ticker(x['Symbol'], x['Is_Option']), axis=1)
    # New column 'Asset Type' if is option, option gain, else stock gain
    net_P_L['Asset_Type'] = net_P_L['Is_Option'].map({True: 'Option', False: 'Stock'})


    # Create new dataframe with Ticker, Type, and Net_P_L
    pivot_df = net_P_L.pivot_table(index='Ticker', columns='Asset_Type', values='Net_P_L', aggfunc='sum').fillna(0)
    pivot_df['Total_Net_P_L'] = pivot_df.sum(axis=1)

    # Define which columns to round, checking if they exist first
    cols_to_round = [col for col in ['Stock', 'Option', 'Total_Net_P_L'] if col in pivot_df.columns]

    # Round the specified columns to 2 decimal places
    pivot_df[cols_to_round] = pivot_df[cols_to_round].round(2)

    return pivot_df

def get_base_ticker(symbol: str, is_opt):
    if is_opt:
        # For options, extract just the leading letters (e.g., 'AMZN' from 'AMZN260918C...')
        return re.match(r'^[A-Z]+', symbol).group()
    return symbol 

def get_twr(df: pd.DataFrame, start_date: datetime = None, end_date: datetime = None):
    """Time-Weighted Return between two snapshot dates.

    With start_date=None the window begins at the earliest snapshot in `df` --
    the tracking inception. Anchoring to recorded data keeps the measure honest
    rather than relying on a configured reference date.
    """
    if df is None or df.empty:
        return "N/A"

    # Resolve start date
    if start_date is None:
        start_str = str(pd.to_datetime(df['date']).min().date())
    elif isinstance(start_date, (date, datetime)):
        start_str = start_date.strftime('%Y-%m-%d')
    else:
        start_str = str(start_date)[:10]

    # Resolve end date
    if end_date is None:
        end_str = str(pd.to_datetime(df['date']).max().date())
    elif isinstance(end_date, (date, datetime)):
        end_str = end_date.strftime('%Y-%m-%d')
    else:
        end_str = str(end_date)[:10]

    try:
        beginning_nav = df.loc[df['date'] == start_str, 'nav'].values[0]
        end_nav = df.loc[df['date'] == end_str, 'nav'].values[0]
    except IndexError:
        return "N/A"

    if beginning_nav == 0:
        return "N/A"

    returns = (end_nav - beginning_nav) / beginning_nav
    twr = f"{returns:.2%}"
    return twr

def config_plot_annotation(df: pd.DataFrame, label: str):
    x_anchor = "center"
    y_anchor = "middle"
    ax, ay = 0, 0
    if label == "Start":
        x_anchor = "right"  
        ax = -40            
    elif label == "End":
        x_anchor = "left"   
        ax = 40             
    elif label == "Peak":
        y_anchor = "bottom" 
        ay = -40            
    elif label == "Low":
        y_anchor = "top"    
        ay = 40
    return ax,ay,x_anchor,y_anchor


def config_datetime_axis_range(df: pd.DataFrame,y_metric: str, fig):
    # Extend x axis range for margin for annotation
    min_date = df['date'].min() - pd.Timedelta(days=round(len(df['date'])*0.2))
    max_date = df['date'].max() + pd.Timedelta(days=round(len(df['date'])*0.2))

    y_min = df[y_metric].min()
    y_max = df[y_metric].max()
    y_range = y_max - y_min
    buffer = y_range * 0.3 if y_range != 0 else 0.1
    fig.update_layout(
        yaxis_range=[y_min - buffer, y_max + buffer],
        xaxis_range=[min_date,max_date]
    )


def empty_fig():
    """Placeholder figure when a DataFrame is empty."""
    fig = go.Figure()
    fig.add_annotation(
        text="No Data Available for selected range",
        xref="paper", 
        yref="paper",
        x=0.5, 
        y=0.5, 
        showarrow=False,
        font=dict(size=20, color="gray")
    )
    fig.update_layout(
        template='plotly_dark',
        xaxis=dict(visible=False),
        yaxis=dict(visible=False)
    )
    return fig


def plot_asset_trend(df: pd.DataFrame):
    df['date'] = pd.to_datetime(df['date']).dt.date
    if df.empty:
        return empty_fig()

    fig = px.line(df, x='date', y='total_assets',
                template='plotly_dark', height=400)
    fig.update_traces(line=dict(width=4),
                      hovertemplate="<br>".join([
                            "Total Assets: $%{y:,.2f}",
                            "<extra></extra>"
                        ])
        )
    fig.update_layout(
                        xaxis=dict(automargin=True,tickfont=dict(size=16),title="",
                                   showgrid=False,
                                   type="date"
                                    ),
                        yaxis=
                            dict(automargin=True,title="",showgrid=False, visible=False),
                        hovermode="x unified",
                        hoverlabel=dict(
                            font_size=14,
                            bgcolor="rgba(30, 30, 30, 0.8)"
                            )
                        )
    return fig

def comparison_df(portfolio_snapshots_df: pd.DataFrame, benchmark_df: pd.DataFrame):
    twr = portfolio_snapshots_df.copy()
    benchmark = benchmark_df.copy()
    # Convert to datetime object and standardise the format to date only
    twr['date'] = pd.to_datetime(twr['date']).dt.date
    benchmark['Date'] = pd.to_datetime(benchmark['Date']).dt.date

    # Pivot the benchmark table so each Symbol is its own column
    # This turns [Date, Symbol, Close] into [Date, ^HSI, ^N225, ^STI]
    bench_pivoted = benchmark.pivot(index='Date', columns='Symbol', values='Close')
    # Rename columns from Yahoo ticker symbols to display index names
    indices_dict = db.indices_dict()
    for key,value in  indices_dict.items():
        if value in bench_pivoted.columns:
            bench_pivoted.rename(columns={value: key}, inplace=True)

    # Merge the 2 tables and using the dates in portfolio_snapshots only
    master_df = pd.merge(twr[['date', 'nav']], bench_pivoted, left_on='date', right_index=True, how='left')
    master_df = master_df.sort_values('date')

    # Fill NaN values with last known value forward
    master_df = master_df.ffill()
    # Fill NaN values with known values after. Backward fill
    master_df = master_df.bfill()
    
    return master_df

def comparison_percent(df: pd.DataFrame):
    percent_df = df.copy()
    # Rebase each column to its first value as a percentage change.
    cols_to_normalize = percent_df.columns.drop('date')
    # Define first row as intitial, then apply percentage change from initial to all following rows of columns for nav and indices
    for col in cols_to_normalize:
            if col in percent_df.columns:
                first_val = percent_df[col].iloc[0]
                # Check if first value is NaN, or if is 0
                if pd.notna(first_val) and first_val != 0:
                    percent_df[col] = round((percent_df[col] / first_val - 1) * 100 , 2)
                    
                else:
                    # Fallback: if data is entirely missing for a column, set pct to 0
                    percent_df[col] = 0.0
    percent_df.rename(columns={'nav': 'Portfolio'},inplace=True)
    return percent_df

def plt_performance_comparison(percent_df: pd.DataFrame):
    fig = go.Figure()
    plt_cols = [col for col in percent_df.columns if col not in ['date','Portfolio']]

    def get_legend_name(name, df_col):
        if not df_col.empty:
            last_val = df_col.iloc[-1]
            # Formats as "SP500: +5.23%" or "SP500: -1.20%"
            return f"{name}: {last_val:+.2f}%"
        return name
    
    for col in plt_cols:
        fig.add_trace(go.Scatter(
                x=percent_df['date'], 
                y=percent_df[col],
                name= get_legend_name(col, percent_df[col]),
                # Store in customdata the index name, same number of rows as the original dataframe
                customdata=[[col]] * len(percent_df),
                mode='lines',
                line=dict(width=1),
                visible= True if col in ['SP500','NASDAQ', 'STI'] else 'legendonly',
                opacity=0.8,
                # Dynamic hover template: "Index Name: Value%"
                hovertemplate="%{customdata[0]}: %{y:.2f}%<extra></extra>"
            ))
    fig.add_trace(go.Scatter(
                x=percent_df['date'], 
                y=percent_df['Portfolio'],
                name= get_legend_name('My Portfolio', percent_df['Portfolio']),
                customdata=[['My Portfolio']] * len(percent_df),
                mode='lines',
                line=dict(color='#00FFCC', width=4),
                visible= True,
                # Bold the portfolio to make it stand out in the hover list
                hovertemplate="%{customdata[0]}: %{y:.2f}%<extra></extra>"
            ))
    fig.update_layout(
        template='plotly_dark',
        height=400,
        hovermode="x unified", # Best for comparing multiple lines
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            entrywidth=0,
            entrywidthmode='pixels',
            font = dict(size=14)
        ),
        hoverlabel=dict(
            bgcolor="rgba(30, 30, 30, 0.8)", # Semi-transparent dark background
            font_size=14
        ),
        xaxis=dict(automargin=True,tickfont=dict(size=14),title="",
            showgrid=False,
            rangeslider=dict(visible=False),
            type="date"
            ),
        yaxis=dict(automargin=True,
                   showticklabels=True,
                   tickfont=dict(size=14),
                   ticksuffix="%",
                   gridcolor='rgba(255,255,255,0.1)')
    )
    return fig

# Modify positions table to add the most information, to be filtered in other functions for displaying graphs and tables
def display_pos(df: pd.DataFrame):
    pos_df = df.copy()
    pos_df = pos_df[pos_df['Market_Value'].notna() & (pos_df['Market_Value'] != 0)]
    # Add column is option or not
    option_pattern = r'[A-Z]+\d{6}[CP]\d+'
    pos_df['Is_Option'] = pos_df['Symbol'].astype(str).str.contains(option_pattern, regex=True)
    # Identify what Ticker, and if is option or stock
    pos_df['Ticker'] = pos_df.apply(lambda x: get_base_ticker(x['Symbol'], x['Is_Option']), axis=1)
    pos_df['Asset_Type'] = pos_df['Is_Option'].map({True: 'Option', False: 'Stock'})

    # Grouping and Sorting: Calculate total portfolio % per ticker to sort groups by size
    # Convert 'Portfolio_Percent' (e.g., "12.5%") to float for calculation
    pos_df['Sort_Val'] = (pos_df['Portfolio_Percent'].astype(str).str.rstrip('%')
                          .replace('', '0').astype(float))
    # Create new dataframe with each Ticker total percentage allocation for each ticker sum it 
    ticker_totals = pos_df.groupby('Ticker')['Sort_Val'].sum().reset_index(name='Ticker_Total_Val')
    # Merge onto Ticker column to match respective ticker, total ticker percentage on resepective ticker regardless option or stock
    pos_df = pos_df.merge(ticker_totals, on='Ticker')
    # Sort by each Ticker Total (desc), then by individual position value within each Ticker (desc)
    pos_df = pos_df.sort_values(by=['Ticker_Total_Val', 'Sort_Val'], ascending=[False, False])
    # Static classification comes from `symbol_meta` (written by the batch).
    # No yfinance on a 10s render tick: a 401/429 must not blank the charts.
    try:
        meta = db.read_symbol_meta()
    except Exception:
        meta = pd.DataFrame()
    meta = (meta.drop_duplicates(subset=['Symbol']).set_index('Symbol')
            if not meta.empty and 'Symbol' in meta else None)

    def lookup(ticker, col, default=None):
        if meta is not None and ticker in meta.index:
            val = meta.at[ticker, col]
            if pd.notna(val) and str(val).strip() and str(val).strip().lower() != 'nan':
                return val
        return default

    pos_df['Sector'] = pos_df['Ticker'].apply(lambda t: lookup(t, 'Sector', 'Unknown'))
    pos_df['Industry'] = pos_df['Ticker'].apply(lambda t: lookup(t, 'Industry', 'Unknown'))
    pos_df['Country'] = pos_df['Ticker'].apply(lambda t: lookup(t, 'Country', 'Unknown'))
    pos_df['Market_Cap'] = pd.to_numeric(
        pos_df['Ticker'].apply(lambda t: lookup(t, 'Market_Cap', None)), errors='coerce'
    )
    pos_df['Market_Cap_Cat'] = pos_df['Market_Cap'].apply(market_cap_class)
    return pos_df

def style_pos(pos_df: pd.DataFrame):
    # Reorder columns to show Ticker and Asset Type first
    cols_order = ['Ticker', 'Asset_Type'] + [c for c in pos_df.columns if c in 
                                             ['Name', 'Market', 'Quantity', 'Current_Price', 'Diluted_Cost', 'Market_Value', 'P_L_Percent', 'P_L', 'Today_s_P_L', 'Portfolio_Percent']]
    pos_df_styled = pos_df[cols_order]
    # Rename
    pos_df_styled = pos_df_styled.rename(
        columns={
                'Asset_Type': 'Asset Type',
                'Market_Value': 'Market Value',
                'Diluted_Cost': 'Diluted Cost',
                'Current_Price': 'Price',
                'P_L_Percent': 'P/L %',
                'P_L': 'P/L',
                'Today_s_P_L': 'Today\'s P/L',
                'Portfolio_Percent': 'Portfolio %'
        }
    )
    # Chain styling: apply color based on numeric value first, then format for display.
    return pos_df_styled.style.map(
        style_negative_red_positive_green, subset=['P/L %', 'P/L', "Today's P/L"]
    ).format({
        'Quantity': '{:,.2f}', 'Price': '{:,.3f}', 'Market Value': '{:,.2f}',
        'Diluted Cost': '{:,.3f}', 'P/L %': '{:+,.2f}%', 'P/L': '{:+,.2f}',
        "Today's P/L": '{:+,.2f}'
    }).hide(axis="index")

def positions_overview(pos_df: pd.DataFrame):
    pos_copy_df = pos_df.copy()

    # Group by Ticker and percentage alloc. Sum Market Value, Today's P/L and Total P/L
    position_overview = pos_copy_df.groupby(['Ticker','Ticker_Total_Val'])[['Market_Value','Today_s_P_L','P_L']].sum().reset_index()
    
    # Current price comes from the stored position / live-quote row. Option-only
    # tickers have no stock quote: show 0 instead of a network lookup on a 10s
    # render tick (the old live lookup produced the 401/429 storms).
    prices_df = (pos_copy_df.loc[pos_copy_df['Is_Option'] == False,
                                ['Ticker', 'Current_Price']]
                 .drop_duplicates(subset=['Ticker']))
    position_overview = position_overview.merge(prices_df, on='Ticker', how='left')
    position_overview['Current_Price'] = pd.to_numeric(
        position_overview['Current_Price'], errors='coerce'
    ).fillna(0.0)

    # Condition for if option
    condition = pos_copy_df['Is_Option'] == False
    # Multiply cost and quantity, if shares, if not shares multiply by another 100, create to column Total Cost for more accurate P/L % calc
    pos_copy_df['Total_Cost'] = np.where(
        condition,
        pos_copy_df['Diluted_Cost'] * pos_copy_df['Quantity'], # If True (Not an option)
        pos_copy_df['Diluted_Cost'] * pos_copy_df['Quantity'] * 100 # If False (Is an option)
    )
    # Group by Ticker and sum for each Ticker, total cost of stock and options of same ticker
    total_cost_df = pos_copy_df.groupby('Ticker')['Total_Cost'].sum().reset_index()
    position_overview = position_overview.merge(total_cost_df, on='Ticker')
    # Create P/L % column using Total_Cost
    position_overview['P_L_Percent'] = (position_overview['P_L'] / position_overview['Total_Cost'])
    # Set column order and remove Total_Cost column
    cols_order = ['Ticker','Market_Value','Current_Price','P_L_Percent','P_L','Today_s_P_L','Ticker_Total_Val']
    # Reorder columns
    position_overview = position_overview[cols_order]
    position_overview.sort_values(by='Ticker_Total_Val', inplace=True, ascending=False)
    # Style using colour, green for positive red for negative for subset of columns
    position_overview = position_overview.style.map(style_negative_red_positive_green, subset=['P_L', 'Today_s_P_L','P_L_Percent'])
    return position_overview

def market_cap_class(market_cap):
    """Bucket a market cap. Non-numeric / missing -> 'Unknown' (never crash)."""
    try:
        v = float(market_cap)
    except (TypeError, ValueError):
        return 'Unknown'
    if pd.isna(v) or v <= 0:
        return 'Unknown'
    if v > 200_000_000_000:
        return 'Mega'
    if v > 10_000_000_000:
        return 'Large'
    if v > 2_000_000_000:
        return 'Mid'
    if v > 300_000_000:
        return 'Small'
    if v > 50_000_000:
        return 'Micro'
    if v < 50_000_000:
        return 'Nano'
    return 'Unknown'


def plot_portfolio_characteristics(pos_df: pd.DataFrame):
    """Three horizontal bars: Sector / Geography / Market Cap.

    An empty group must not produce a NaN x-axis range -- that is exactly what
    rendered the Geography and Market Cap panes blank. Missing metadata is shown
    as its own 'Unknown' bucket instead of being silently dropped by groupby.
    """
    def _group(col):
        g = pos_df.groupby(col, dropna=False)['Sort_Val'].sum().reset_index()
        # Cast to string first: filling a float column with 'Unknown' raises a
        # pandas 4 dtype warning and will break in a future version.
        g[col] = (g[col].astype(object).where(g[col].notna(), 'Unknown')
                  .astype(str).str.strip().replace({'': 'Unknown', 'nan': 'Unknown',
                                                   'None': 'Unknown'}))
        return g.sort_values('Sort_Val')

    sector_df = _group('Sector')
    geo_df = _group('Country')
    mc_df = _group('Market_Cap_Cat')
    # Keep 'Unknown' as a visible bucket. Dropping it is what used to
    # leave the Market Cap pane completely blank when yfinance failed.

    fig = make_subplots(
        rows=2, cols=2,
        specs=[[{'type': 'bar'}, {'type': 'bar'}],
               [{'type': 'bar'}, None]],
        subplot_titles=("Sector", "Geography", "Market Cap"),
    )
    groups = [
        (1, 1, sector_df, 'Sector', 'Sector'),
        (1, 2, geo_df, 'Country', 'Geography'),
        (2, 1, mc_df, 'Market_Cap_Cat', 'Market Cap'),
    ]
    for r, c, g, col, name in groups:
        fig.add_trace(
            go.Bar(
                x=g['Sort_Val'], y=g[col], orientation='h',
                text=[f"{v:.2f}%" for v in g['Sort_Val']],
                textposition='outside', cliponaxis=False, name=name,
                marker=dict(color='#D4AF37'),
            ), row=r, col=c,
        )
    fig.update_layout(
        template='plotly_dark', showlegend=False, font=dict(size=14),
        height=800, bargap=0.2, margin=dict(l=150), hovermode=False,
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
    )
    for r, c, g, _, name in groups:
        top = float(g['Sort_Val'].max()) if len(g) and pd.notna(g['Sort_Val'].max()) else 0.0
        fig.update_xaxes(range=[0, top * 1.2 if top > 0 else 1], row=r, col=c)
        if g.empty:
            axis_num = {(1, 1): 1, (1, 2): 2, (2, 1): 3}[(r, c)]
            try:
                fig.add_annotation(
                    text=f"No data ({name})", x=0.5, y=0.5,
                    xref=f"x{axis_num} domain", yref=f"y{axis_num} domain",
                    showarrow=False, font=dict(size=14, color='#9A9A9A'),
                )
            except Exception:
                pass
    fig.update_xaxes(visible=False)
    fig.update_yaxes(tickfont=dict(size=14))
    return fig


def trade_ledger():
    """Chronological buy/sell audit ledger from the `transactions` table."""
    query = (
        "SELECT date_time, Symbol, Name, Market, Buy_Sell, Quantity, "
        "Fill_Price, Multiplier, Gross_Amount, Currency "
        "FROM transactions ORDER BY date_time DESC"
    )
    df = db.read_db(query)
    return df


def ledger_summary(market: str = None):
    """Per-symbol net realised cash flow (SELL proceeds - BUY cost), an audit proxy
    for realised P/L. Optionally restricted to a single market."""
    query = (
        "SELECT Symbol, Market, Currency, SUM(Gross_Amount) AS Net_Cash_Flow "
        "FROM transactions"
    )
    if market:
        query += f" WHERE Market = '{market}'"
    query += " GROUP BY Symbol, Market, Currency ORDER BY Net_Cash_Flow"
    df = db.read_db(query)
    if not df.empty:
        df["Net_Cash_Flow"] = df["Net_Cash_Flow"].round(2)
    return df


def plot_income_trend(income_df: pd.DataFrame):
    """Area chart of cumulative dividend/coupon income over time (in SGD)."""
    if income_df is None or income_df.empty:
        return empty_fig()
    income_df = income_df.copy()
    income_df['Date'] = pd.to_datetime(income_df['Date'])
    fig = px.area(
        income_df, x='Date', y='Cumulative',
        template='plotly_dark', height=300,
    )
    fig.update_traces(
        line=dict(width=3, color='#4CAF50'),
        fillcolor='rgba(76,175,80,0.2)',
        hovertemplate="Cumulative Income (SGD): $%{y:,.2f}<extra></extra>",
    )
    fig.update_layout(
        showlegend=False,
        hovermode='x unified',
        yaxis=dict(title="", automargin=True, showgrid=False),
        xaxis=dict(title="", automargin=True, showgrid=False),
    )
    return fig


def main():
        
    return 0

if __name__ == "__main__":
    main()