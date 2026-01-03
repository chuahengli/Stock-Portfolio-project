import os
from dotenv import load_dotenv
import moomoo as moomoo
from moomoo.trade.open_trade_context import OpenSecTradeContext
import pandas as pd
import yfinance as yf
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import re

# Get list of accounts
def account_list(trade_obj: OpenSecTradeContext):
    ret, data = trade_obj.get_acc_list()
    if ret == moomoo.RET_OK:
        return data
    else:
        raise Exception('get_acc_list error: ', data)

# Get account information    
def account_info(trade_obj: OpenSecTradeContext):
    ret, data = trade_obj.accinfo_query(trd_env="REAL",refresh_cache=True,currency="SGD")
    if ret == moomoo.RET_OK:
        return data
    else:
        raise Exception('accinfo_query error: ', data)

# Get positions
def get_positions(trade_obj: OpenSecTradeContext):
    ret, data = trade_obj.position_list_query(trd_env="REAL",refresh_cache=True)
    if ret == moomoo.RET_OK:
        return data
    else:
        raise Exception('position_list_query error: ', data)
    
# Get account cashflow for a specific date
def account_cashflow(trade_obj: OpenSecTradeContext, date:str):
    ret, data = trade_obj.get_acc_cash_flow(clearing_date=date,trd_env="REAL")
    if ret == moomoo.RET_OK:
        return data
    else:
        raise Exception('get_acc_cash_flow error: ', data)

# Get historical orders
def get_historical_orders(trade_obj: OpenSecTradeContext):
    ret, data = trade_obj.history_order_list_query(trd_env="REAL")
    if ret == moomoo.RET_OK:
        return data
    else:
        raise Exception('history_order_list_query error: ', data)
    
def plot_portfolio_composition(portfolio_df: pd.DataFrame) -> None:
    
    positive_mv = portfolio_df[portfolio_df['market_val'] > 0]
    
    if positive_mv.empty:
        print("Warning: No positions with positive market value to plot.")
        return

    # Sort by Market Value to make the chart easier to read
    sorted_df = positive_mv.sort_values(by='market_val', ascending=False)

    plt.figure(figsize=(10, 6))
    sns.barplot(x='market_val', y='stock_name', data=sorted_df, hue='stock_name', palette='Dark2', legend=False)
    plt.title('Portfolio Composition by Market Value', fontsize=16)
    plt.xlabel('Market Value ($)')
    plt.ylabel('Stock Name')
    plt.gca().get_xaxis().set_major_formatter(
        plt.FuncFormatter(lambda x, p: f'${x:,.0f}')
    )
    plt.grid(axis='x', linestyle='--', alpha=0.7)
    plt.show()

def plot_pl_by_position(portfolio_df: pd.DataFrame) -> None:
    """
    Plots a bar chart showing the P/L for each position, colored by profit or loss.
    """
    # Sort by P/L for a more organized chart
    sorted_df = portfolio_df.sort_values(by='pl_val', ascending=False)
    
    # Create a color palette for the bars
    colors = ["#00d63d" if x > 0 else "#dd2a13" for x in sorted_df['pl_val']]
    
    plt.figure(figsize=(12, 8))
    sns.barplot(
        x='pl_val',
        y='stock_name',
        data=sorted_df,
        hue='stock_name',
        palette=colors,
        legend=False
    )
    plt.title('Profit/Loss by Position', fontsize=16)
    plt.xlabel('Profit/Loss ($)')
    plt.ylabel('Stock Name')
    plt.grid(axis='x', linestyle='--', alpha=0.7)
    plt.show()


def main():
    # Load environment variables from .env file
    load_dotenv()

    # Pipenv automatically loads KEY_PATH from your .env file
    key_path = os.getenv("KEY_PATH")

    if not key_path:
        raise ValueError("KEY_PATH not found. Have you created your .env file?")

    # 1. Configure the RSA private key file globally
    # This sets the key path for all subsequent contexts.
    moomoo.SysConfig.set_init_rsa_file(key_path)

    # 2. Create the trade context and enable encryption
    # is_encrypt=True tells this specific context to use the key configured above.
    trade_ctx = OpenSecTradeContext(
                                    host='127.0.0.1',
                                    port=11111,
                                    is_encrypt=True,
                                    security_firm="FUTUSG"
                                    )
    acc_list = account_list(trade_ctx)
    #print("Account List:", acc_list)
    acc_info = account_info(trade_ctx)
    positions = get_positions(trade_ctx)
    cashflow = account_cashflow(trade_ctx, date='2025-08-26')
    #print("Cashflow on 2025-08-26:", cashflow)  
    historical_orders = get_historical_orders(trade_ctx)
    


    trade_ctx.close()

    acc_info = acc_info[['total_assets','securities_assets', 'fund_assets','market_val','pending_asset','risk_status',
               'us_cash', 'us_avl_withdrawal_cash','usd_net_cash_power','usd_assets',
               'sg_cash', 'sg_avl_withdrawal_cash','sgd_net_cash_power', 'sgd_assets']]
    print("Account Info:", acc_info)

    positions = positions[['code', 'stock_name', 'position_market', 'qty','diluted_cost','market_val','nominal_price', 'pl_ratio','pl_val','today_pl_val','currency']]
    positions = positions.round({
                                'diluted_cost': 3,
                                'market_val': 3,
                                'nominal_price': 3,
                                'pl_ratio': 3,
                                'pl_val': 3,
                                'today_pl_val': 3
                                })
    positions = positions.sort_values(by='market_val', ascending=False).reset_index(drop=True)
    print("Positions:", positions)

    historical_orders = historical_orders.loc[historical_orders['order_status'] == 'FILLED_ALL', 
                                          ['code', 'stock_name','order_market', 'trd_side','order_status','qty', 'price','currency']]
    print("Historical Orders:", historical_orders)

    plot_portfolio_composition(positions)
    plot_pl_by_position(positions)

if __name__ == "__main__":
    main()