from config import settings
from source import db

from datetime import date, datetime,timedelta
import sqlite3
import pandas as pd
import re
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
import functools
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
    query = f"SELECT * FROM net_p_l"
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

def get_twr(df: pd.DataFrame, start_date: datetime, end_date: datetime):
    start_str: str = start_date.strftime('%Y-%m-%d')
    end_str: str = end_date.strftime('%Y-%m-%d')

    try:
        beginning_nav = df.loc[df['date']==start_str,'nav'].values[0]
        end_nav = df.loc[df['date']==end_str,'nav'].values[0]
    except IndexError:
        return "N/A"

    returns = (end_nav-beginning_nav)/beginning_nav 
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
'''Deal with empty dataframes that can't be plotted'''
def empty_fig():
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
    # If dataframe empty, return empty plotly figure
    if df.empty:
        return empty_fig()

    fig = px.line(df, x='date', y='total_assets',
                template='plotly_dark', height=400)
    '''
    # Points to annotate
    point_indices = {
        "Start": df.index[0],
        "End": df.index[-1],
        "Peak": df['total_assets'].idxmax(),
        "Low": df['total_assets'].idxmin()
    }

    # Group labels by index to handle overlaps (e.g., End is also Peak)
    labels_by_index = {}
    for label, idx in point_indices.items():
        if idx not in labels_by_index:
            labels_by_index[idx] = []
        labels_by_index[idx].append(label)

    # Label unique points
    for idx, labels in labels_by_index.items():
        pt = df.loc[idx]
        
        # Determine the primary label for positioning logic (Peak/Low are most important)
        if 'Peak' in labels:
            primary_label = 'Peak'
        elif 'Low' in labels:
            primary_label = 'Low'
        elif 'End' in labels:
            primary_label = 'End'
        else:
            primary_label = 'Start'

        ax, ay, x_anchor, y_anchor = config_plot_annotation(df, primary_label)
        
        # Combine labels for display text in a consistent order
        display_text = " / ".join(sorted(labels, key=lambda x: ['Start', 'Low', 'Peak', 'End'].index(x)))
        
        fig.add_annotation(
                    x=pt['date'],
                    y=pt['total_assets'],
                    text=f"<b>{display_text}</b><br>{pt['total_assets']:,.2f}",
                    showarrow=False,
                    ax=ax,
                    ay=ay,
                    xanchor=x_anchor,
                    yanchor=y_anchor,
                    font={'size': 14},
                    opacity=0.7,
                    align="center"
                )
    '''
    '''
    # Configure axis ranges to prevent cut off from containers
    config_datetime_axis_range(df,'total_assets',fig)
    '''
    
    fig.update_traces(line=dict(width=4),
                      hovertemplate="<br>".join([
                            "Date: %{x|%b %d, %Y}",
                            "Total Assets: $%{y:,.2f}",
                            "<extra></extra>"  # Removes the trace name box on the side
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
                            font_size=14
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
    '''Rename the table names to indices name'''
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
    # Create the percentage change instead of values.
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

    for col in plt_cols:
        fig.add_trace(go.Scatter(
                x=percent_df['date'], 
                y=percent_df[col],
                name= col,
                mode='lines',
                #line=dict(width=1, shape='spline'),
                visible= True if col in ['SP500','NASDAQ', 'STI'] else 'legendonly',
                opacity=0.6
            ))
    fig.add_trace(go.Scatter(
                x=percent_df['date'], 
                y=percent_df['Portfolio'],
                name= 'My Portfolio',
                mode='lines',
                line=dict(color='#00FFCC', width=4),
                visible= True,
            ))
    fig.update_layout(
        template='plotly_dark',
        height=400,
        hovermode="x unified", # Best for comparing multiple lines
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        xaxis=dict(automargin=True,tickfont=dict(size=16),title="",
            showgrid=False,
            rangeslider=dict(visible=False),
            type="date"
            ),
        yaxis=dict(automargin=True,visible=False)
    )
    return fig

# Modify positions table to add the most information, to be filtered in other functions for displaying graphs and tables
def display_pos(df: pd.DataFrame):
    pos_df = df.copy()
    # Add column is option or not
    option_pattern = r'[A-Z]+\d{6}[CP]\d+'
    pos_df['Is_Option'] = pos_df['Symbol'].str.contains(option_pattern, regex=True)
    # Identify what Ticker, and if is option or stock
    pos_df['Ticker'] = pos_df.apply(lambda x: get_base_ticker(x['Symbol'], x['Is_Option']), axis=1)
    pos_df['Asset_Type'] = pos_df['Is_Option'].map({True: 'Option', False: 'Stock'})

    # Grouping and Sorting: Calculate total portfolio % per ticker to sort groups by size
    # Convert 'Portfolio_Percent' (e.g., "12.5%") to float for calculation
    pos_df['Sort_Val'] = pos_df['Portfolio_Percent'].astype(str).str.rstrip('%').astype(float)
    # Create new dataframe with each Ticker total percentage allocation for each ticker sum it 
    ticker_totals = pos_df.groupby('Ticker')['Sort_Val'].sum().reset_index(name='Ticker_Total_Val')
    # Merge onto Ticker column to match respective ticker, total ticker percentage on resepective ticker regardless option or stock
    pos_df = pos_df.merge(ticker_totals, on='Ticker')
    # Sort by each Ticker Total (desc), then by individual position value within each Ticker (desc)
    pos_df = pos_df.sort_values(by=['Ticker_Total_Val', 'Sort_Val'], ascending=[False, False])
    pos_df['Market_Cap'] = pos_df['Ticker'].apply(lambda x: get_mktcap(x))
    pos_df['Market_Cap_Cat'] = pos_df['Market_Cap'].apply(market_cap_class)
    sector_map = {}
    for ticker in pos_df['Ticker'].unique():
        sector_map[ticker] = get_sector(ticker,datetime.now().strftime("%Y-%m"))

    pos_df['Sector'] = pos_df['Ticker'].map(lambda x: sector_map[x][0])
    pos_df['Industry'] = pos_df['Ticker'].map(lambda x: sector_map[x][1])
    pos_df['Country'] = pos_df['Ticker'].apply(lambda x: get_country(x))
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

# Get sector of ticker symbol passed in via yfinance
@functools.lru_cache(maxsize=30)
def get_sector(ticker_symbol,month_tag: datetime):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # Check if it's an ETF. Then use the industry as the sector
        quote_type = info.get('quoteType', 'UNKNOWN')
        
        if quote_type == 'ETF':
            sector = info.get('category', info.get('fundFamily', 'Index/Fund'))
            # Attempt to get the category or fund family for the industry column
            industry = info.get('category', info.get('fundFamily', 'Index/Fund'))
        else:
            sector = info.get('sector', 'Other')
            industry = info.get('industry', 'Other')
            
        return sector, industry
    except Exception:
        return 'Unknown', 'Unknown'

    
def positions_overview(pos_df: pd.DataFrame):
    pos_copy_df = pos_df.copy()

    # Group by Ticker and percentage alloc. Sum Market Value, Today's P/L and Total P/L
    position_overview = pos_copy_df.groupby(['Ticker','Ticker_Total_Val'])[['Market_Value','Today_s_P_L','P_L']].sum().reset_index()
    
    # Get prices for stocks present in portfolio
    prices_df = pos_copy_df.loc[pos_copy_df['Is_Option'] == False, ['Ticker', 'Current_Price']].drop_duplicates(subset=['Ticker'])
    
    # Identify tickers that only have options (missing from prices_df)
    existing_tickers = set(prices_df['Ticker'])
    all_tickers = set(position_overview['Ticker'])
    missing_tickers = list(all_tickers - existing_tickers)
    # Add missing tickers into prices_df with updated price from yfinance
    if missing_tickers:
        new_prices = []
        for ticker in missing_tickers:
            try:
                # Use fast_info for better performance on single attributes
                price = yf.Ticker(ticker).fast_info['last_price']
                new_prices.append({'Ticker': ticker, 'Current_Price': price})
            except Exception:
                new_prices.append({'Ticker': ticker, 'Current_Price': 0.0})
        
        if new_prices:
            prices_df = pd.concat([prices_df, pd.DataFrame(new_prices)], ignore_index=True)
    # Add current price column to overview
    position_overview = position_overview.merge(prices_df, on='Ticker', how='left')

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

@functools.lru_cache(maxsize=30)
def get_mktcap(ticker: str,month_tag: datetime = datetime.now().strftime("%Y-%m")):
    return yf.Ticker(ticker).info.get('marketCap')
def market_cap_class(market_cap: float):
    if pd.isna(market_cap):
        return 'Unknown'
    if market_cap > 200000000000:
        return 'Mega'
    elif market_cap > 10000000000:
        return 'Large'
    elif market_cap > 2000000000:
        return 'Mid'
    elif market_cap > 300000000:
        return 'Small'
    elif market_cap > 50000000:
        return 'Micro'
    elif market_cap < 50000000:
        return 'Nano'
    else:
        return 'Unknown'

@functools.lru_cache(maxsize=30)
def get_country(ticker: str,month_tag: datetime = datetime.now().strftime("%Y-%m")):
    tk = yf.Ticker(ticker).info
    try: 
        return tk['country']
    except Exception as e:
        return None

def plot_portfolio_characteristics(pos_df: pd.DataFrame):
    # Grouping data for each subplot
    sector_df = pos_df.groupby('Sector')['Ticker_Total_Val'].sum().reset_index().sort_values('Ticker_Total_Val')
    geo_df = pos_df.groupby('Country')['Ticker_Total_Val'].sum().reset_index().sort_values('Ticker_Total_Val')
    mc_df = pos_df.groupby('Market_Cap_Cat')['Ticker_Total_Val'].sum().reset_index().sort_values('Ticker_Total_Val')
    mc_df = mc_df[mc_df['Market_Cap_Cat'] != 'Unknown']

    fig = make_subplots(
        rows=1, cols=3,
        specs=[[{'type': 'xy'}, {'type': 'xy'}, {'type': 'xy'}]],
        subplot_titles=("Sector", "Geography", "Market Cap")
    )
    fig.add_trace(
        go.Bar(x=sector_df['Ticker_Total_Val'], y=sector_df['Sector'], orientation='h', name="Sector"),
        row=1, col=1
    )
    fig.add_trace(
        go.Bar(x=geo_df['Ticker_Total_Val'], y=geo_df['Country'], orientation='h', name="Geography"),
        row=1, col=2
    )
    fig.add_trace(
        go.Bar(x=mc_df['Ticker_Total_Val'], y=mc_df['Market_Cap_Cat'], orientation='h', name="Market Cap"),
        row=1, col=3
    )
    fig.update_layout(
        template='plotly_dark',
        showlegend=False,
        height=400,
        hovermode=False
    )
    return fig


def main():
        
    return 0

if __name__ == "__main__":
    main()