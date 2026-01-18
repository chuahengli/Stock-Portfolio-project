
from config import settings
from source import db
from datetime import date, datetime,timedelta
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
import mplcyberpunk
import matplotlib.dates as mdates
import re

def setup():
    # Setup and configure default style and fontstyles
    mpl.style.use('cyberpunk')
    plt.rcParams['font.family'] = 'Calibri'
    plt.rcParams['font.size'] = 12

def asset_allocation_data(current_date:datetime):
    date_str = current_date.strftime('%Y-%m-%d')
    query = f"SELECT stocks,options,cash FROM portfolio_snapshots WHERE date = '{date_str}'"
    df = db.read_db(query)
    return df

def plot_asset_allocation(df: pd.DataFrame):
    if df.empty:
        # Return an empty figure or a message
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "No Data Available", ha='center')
        return fig
    df = df.rename(columns={'stocks': 'Stocks', 'options': 'Options', 'cash': 'Cash'})
    categories = df.columns.to_list()
    total_assets = df.iloc[0].sum()
    values = df.iloc[0].values
    percentages = (values / total_assets) * 100
    
    colour_list = ['skyblue', 'coral', 'gray']

    fig, ax = plt.subplots(layout='constrained',figsize=(9, 3))
    bars = ax.barh(y=categories,
        width=values,
        color=colour_list,
        height=0.6)
    ax.grid(visible=True, linestyle='--', alpha=0.5)
    bar_labels = [f"{p:.1f}%" for p in percentages]
    ax.bar_label(bars, labels=bar_labels, padding=8, fontsize=14)

    ax.spines[['top', 'right', 'bottom','left']].set_visible(False) # Remove box borders
    ax.xaxis.set_visible(False) # Hide x-axis numbers since we have labels on the bars
    ax.tick_params(axis='y', labelsize=14, length=0)
    plt.title(f"Asset Allocation\n${total_assets:,.2f} (SGD)",
                fontsize=20,
                pad=20)
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

def asset_trend_data():
    query = f"SELECT date, total_assets FROM portfolio_snapshots"
    df = db.read_db(query)
    return df


def plot_asset_trend(data: pd.DataFrame):
    if data.empty:
        # Return an empty figure or a message
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "No Data Available", ha='center')
        return fig
    data['date'] = pd.to_datetime(data['date'])
    data.sort_values('date', inplace=True)

    fig, ax = plt.subplots(layout='constrained',figsize=(8, 5))
    # Auto format date
    fig.autofmt_xdate()
    ax.plot(data['date'],
            data['total_assets'],
            dash_capstyle= 'round',
            dash_joinstyle='round',
            linewidth=3)
    
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d, %Y'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.set_xticks(ticks=data['date'])
    ax.grid(visible=True, linestyle='--', alpha=0.5)
    
    plt.title("Asset Trend",
            fontsize=24,
            pad=20)
    return fig


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

def plot_twr(data: pd.DataFrame):
    if data.empty:
        # Return an empty figure or a message
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "No Data Available", ha='center')
        return fig
    data['date'] = pd.to_datetime(data['date'])
    data.sort_values('date', inplace=True)

    fig, ax = plt.subplots(layout='constrained',figsize=(8, 5))
    # Auto format date
    fig.autofmt_xdate()
    ax.plot(data['date'],
            data['nav'],
            dash_capstyle= 'round',
            dash_joinstyle='round',
            linewidth=3)
    
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d, %Y'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.set_xticks(ticks=data['date'])
    ax.grid(visible=True, linestyle='--', alpha=0.5)
    
    plt.title("Time Weighted Returns",
            fontsize=24,
            pad=20)
    return fig

def main():
        
    return 0

if __name__ == "__main__":
    main()