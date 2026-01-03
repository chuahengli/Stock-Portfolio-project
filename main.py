import pandas as pd
import yfinance as yf
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import re
from typing import Optional, Dict, List
import tkinter as tk
from tkinter import filedialog
import os

def upload_csv_file(what_to_upload:str):
    root = tk.Tk()
    root.withdraw() # Hide the root window as we only want the file dialog.

     # Use filedialog.askopenfilename to open the file explorer.
    # The 'filetypes' parameter is used to filter for only CSV files.
    # The 'title' sets the text for the dialog window.
    # The 'initialdir' is a good practice to set a starting directory,
    # here we use the user's home directory.
    filepath = filedialog.askopenfilename(
        title=what_to_upload,
        initialdir=os.path.expanduser("~"),
        filetypes=(("CSV Files", "*.csv"), ("All Files", "*.*"))
    )
    if filepath:
        print(f"File selected: {filepath}")
        return str(filepath)
    else:
        print("No file selected.")
        return None

def load_and_process_positions(filepath: str) -> pd.DataFrame:
    """
    Loads position data from a CSV and performs initial processing.
    """
    df = pd.read_csv(filepath, encoding='utf-8')
    # Keep only the first 10 columns as a starting point
    df = df[df.columns[0:10]]

    # Explicitly remove the "Today's P/L" column if it exists
    if "Today's P/L" in df.columns:
        df = df.drop(columns=["Today's P/L"])

    return df

def update_current_share_price(shares: pd.DataFrame) -> pd.DataFrame:
    tickers = shares['Symbol'].dropna().unique().tolist()
    if not tickers:
        return shares

    """
    price_data = yf.download(tickers=tickers,
                             period='1d',
                             interval='1h',
                             progress=False)
    """
    price_data = yf.download(tickers=tickers, period='2d',
                             interval='1m',
                             progress=False,
                             prepost=True)

    if price_data.empty:
        print("Warning: Could not download share price data.")
        return shares

    # Extract the most recent price for each ticker
    # Forward-fill to propagate the last valid price, then select the last row.
    # This handles cases where some tickers may not have traded in the last minute.
    latest_prices = price_data['Close'].ffill().iloc[-1].round(decimals=3)
    price_map = latest_prices.to_dict() if isinstance(latest_prices, pd.Series) else {tickers[0]: latest_prices}
    shares['Current price'] = shares['Symbol'].map(price_map)
    return shares

def get_price_from_custom_format(custom_option_string: str) -> Optional[float]:
    """
    Parses a custom option string, finds the contract in the yfinance
    option chain, and returns its last traded price.

    Args:
        custom_option_string: A string in the format "TICKER YYMMDD STRIKE_PRICE(C/P)"
                              e.g., "AMZN 260918 195.00C"

    Returns:
        The last price as a float, or None if not found or an error occurs.
    """
    try:
        # 1. Parse the string using a robust regular expression
        pattern = r'^(?P<ticker>[A-Z]+)\s+(?P<date>\d{6})\s+(?P<strike>[\d.]+)(?P<type>[CP])$'
        match = re.match(pattern, custom_option_string.strip())

        if not match:
            print(f"Warning: Could not parse symbol '{custom_option_string}'")
            return None

        parts = match.groupdict()
        underlying_ticker = parts['ticker']
        exp_date_str = datetime.strptime(parts['date'], '%y%m%d').strftime('%Y-%m-%d')
        strike_price = float(parts['strike'])
        option_type = parts['type']

        # 2. Fetch the option chain for the specific expiration date
        ticker_obj = yf.Ticker(underlying_ticker)
        if option_type == 'C':
            chain = ticker_obj.option_chain(exp_date_str).calls
        else:
            chain = ticker_obj.option_chain(exp_date_str).puts

        # 3. Find the specific contract by its strike price
        contract = chain[chain['strike'] == strike_price]

        # 4. Extract the price if the contract was found
        if not contract.empty:
            return contract['lastPrice'].iloc[0].round(decimals=3)
        else:
            print(f"Warning: Contract for '{custom_option_string}' not found in the option chain.")
            return None

    except Exception as e:
        print(f"Warning: An error occurred for '{custom_option_string}'. Reason: {e}")
        return None

def get_option_prices_from_list(option_list: List[str]) -> Dict[str, Optional[float]]:
    """
    Takes a list of custom option strings and returns a dictionary
    mapping each option to its current price.
    """
    price_results = {}
    for option_string in option_list:
        price_results[option_string] = get_price_from_custom_format(option_string)
    return price_results

def update_option_prices(options: pd.DataFrame) -> pd.DataFrame:
    """
    Fetches current prices for a DataFrame of options.
    """
    contracts = options['Name'].to_list()
    price_dictionary = get_option_prices_from_list(contracts)
    options['Current price'] = options['Name'].map(price_dictionary)
    return options

def update_market_val(portfolio_df: pd.DataFrame) -> None:
    # 1. Create a boolean mask: a Series of True/False for each row.
    is_option = portfolio_df['Symbol'].str.len() > 4

    # 2. Use np.where to create a new Series with the correct quantity for each row.
    effective_quantity = np.where(
        is_option,                      # Condition: For each row, is it an option?
        portfolio_df['Quantity'] * 100, # Value if True: Use Quantity * 100
        portfolio_df['Quantity']        # Value if False: Use just the Quantity
    )

    # 3. Use the new 'effective_quantity' for the final calculation.
    portfolio_df['Market Value'] = (portfolio_df['Current price'].fillna(0) * effective_quantity).round(2)

def update_pl(portfolio_df: pd.DataFrame) -> None:
    is_option = portfolio_df['Symbol'].str.len() > 4
    effective_quantity = np.where(is_option, 
                                  portfolio_df['Quantity'] * 100, 
                                  portfolio_df['Quantity'])
    portfolio_df['P/L'] = ((portfolio_df['Current price'].fillna(0) - portfolio_df['Diluted Cost'].fillna(0)) * effective_quantity).round(2)

def update_pl_ratio(portfolio_df: pd.DataFrame) -> None:
     # Use np.divide to safely handle potential division by zero
    pl_ratio_numeric = np.divide(portfolio_df['Current price'] - portfolio_df['Diluted Cost'], portfolio_df['Diluted Cost']) * 100
    portfolio_df['P/L Ratio'] = pl_ratio_numeric.round(2)
    portfolio_df['P/L Ratio'] = portfolio_df['P/L Ratio'].apply(
        lambda x: f"+{x:.2f}%" if x > 0 else f"{x:.2f}%"
    )
# update % of Portfolio not done yet
def update_portfolio_percentage(portfolio_df: pd.DataFrame) -> None:
    total_market_value = portfolio_df['Market Value'].sum()
    if total_market_value == 0:
        portfolio_df['% of Portfolio'] = 0.0
    else:
        portfolio_df['% of Portfolio'] = (portfolio_df['Market Value'] / total_market_value * 100).round(2)
        portfolio_df['% of Portfolio'] = portfolio_df['% of Portfolio'].apply(
            lambda x: f"{x:.2f}%"
        )

def plot_portfolio_composition(portfolio_df: pd.DataFrame) -> None:
    
    positive_mv = portfolio_df[portfolio_df['Market Value'] > 0]
    
    if positive_mv.empty:
        print("Warning: No positions with positive market value to plot.")
        return

    # Sort by Market Value to make the chart easier to read
    sorted_df = positive_mv.sort_values(by='Market Value', ascending=False)

    plt.figure(figsize=(10, 6))
    sns.barplot(x='Market Value', y='Symbol', data=sorted_df, palette='rocket')
    plt.title('Portfolio Composition by Market Value', fontsize=16)
    plt.xlabel('Market Value ($)')
    plt.ylabel('Symbol')
    plt.gca().get_xaxis().set_major_formatter(
        plt.FuncFormatter(lambda x, p: f'${x:,.0f}')
    )
    plt.show()

def plot_pl_by_position(portfolio_df: pd.DataFrame) -> None:
    """
    Plots a bar chart showing the P/L for each position, colored by profit or loss.
    """
    # Sort by P/L for a more organized chart
    sorted_df = portfolio_df.sort_values(by='P/L', ascending=False)
    
    # Create a color palette for the bars
    colors = ["#00d63d" if x > 0 else "#dd2a13" for x in sorted_df['P/L']]
    
    plt.figure(figsize=(12, 8))
    sns.barplot(
        x='P/L',
        y='Symbol',
        data=sorted_df,
        palette=colors
    )
    plt.title('Profit/Loss by Position', fontsize=16)
    plt.xlabel('Profit/Loss ($)')
    plt.ylabel('Symbol')
    plt.grid(axis='x', linestyle='--', alpha=0.7)
    plt.show()

def plot_asset_class_allocation(portfolio_df: pd.DataFrame) -> None:
    """
    Plots a bar chart showing the total market value in Shares vs. Options.
    """
    # Create a temporary 'Asset Type' column for grouping
    df = portfolio_df.copy()
    df['Asset Type'] = np.where(df['Symbol'].str.len() > 4, 'Options', 'Shares')
    
    # Group by asset type and sum the market value for assets with positive value
    allocation = df[df['Market Value'] > 0].groupby('Asset Type')['Market Value'].sum()
    
    if allocation.empty:
        print("Warning: No assets with positive market value to plot for allocation.")
        return

    plt.figure(figsize=(8, 8))
    colours = ['#4c72b0', '#c44e52', '#55a868', '#8172b3', '#ccb974', '#64b5cd']
    plt.pie(
        allocation,
        labels=allocation.index,
        autopct='%1.1f%%',
        startangle=90,
        explode=[0.05] * len(allocation), # Explode all slices slightly for better visibility
        colors=colours
    )
    plt.title('Asset Class Allocation by Market Value', fontsize=16)
    plt.ylabel('') # Hide the y-label as it's not needed for a pie chart
    plt.show()
    


def main():
    filepath = upload_csv_file("Securities Positions CSV File")
    df = load_and_process_positions(filepath)
    shares = df[df['Symbol'].str.len() <= 4]
    options = df[df['Symbol'].str.len() > 4]


    shares = update_current_share_price(shares)
    options = update_option_prices(options)

    portfolio_df = pd.concat([shares, options], ignore_index=True)

    update_market_val(portfolio_df)
    update_pl(portfolio_df)
    update_pl_ratio(portfolio_df)
    update_portfolio_percentage(portfolio_df)
    
    # Sort the final DataFrame by 'Market Value' in descending order for a clear overview
    portfolio_df = portfolio_df.sort_values(by='Market Value', ascending=False, ignore_index=True)

    print("\n--- Detailed Positions ---")
    print(portfolio_df)

    # --- Visualization ---
    print("\nGenerating visualizations...")
    plot_portfolio_composition(portfolio_df)
    plot_pl_by_position(portfolio_df)
    plot_asset_class_allocation(portfolio_df)

    cash_filepath = upload_csv_file("Cash position CSV File")
    cash = pd.read_csv(cash_filepath, encoding='utf-8')
    print(cash)

if __name__ == "__main__":
    main()
