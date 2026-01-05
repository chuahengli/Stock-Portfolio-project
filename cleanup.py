from datetime import datetime
import moomoo_api
from typing import Optional, Dict, List
import pandas as pd
import re
import yfinance as yf

def cleanup_acc_info(acc_info:pd.DataFrame):
    filter_list = ['total_assets','securities_assets', 'fund_assets','bond_assets','cash','pending_asset','frozen_cash','avl_withdrawal_cash','risk_status',
               'us_cash', 'us_avl_withdrawal_cash','usd_net_cash_power','usd_assets',
               'sg_cash', 'sg_avl_withdrawal_cash','sgd_net_cash_power', 'sgd_assets']
    acc_info = acc_info.loc[:, filter_list]
    columns_to_round = [
    'total_assets', 'securities_assets', 'fund_assets', 'bond_assets',
    'cash', 'pending_asset', 'frozen_cash', 'avl_withdrawal_cash',
    'us_cash', 'us_avl_withdrawal_cash', 'usd_net_cash_power',
    'usd_assets', 'sg_cash', 'sg_avl_withdrawal_cash',
    'sgd_net_cash_power', 'sgd_assets'
    ]
    acc_info.loc[:, columns_to_round] = acc_info[columns_to_round].round(2)
    return acc_info

def get_cash(acc_info: pd.DataFrame) -> float:

    cash_columns = ['fund_assets', 'cash', 'pending_asset', 'frozen_cash', 'avl_withdrawal_cash',]
    return acc_info[cash_columns].sum(axis=1)[0].round(2)

def get_total_assets(acc_info: pd.DataFrame) -> float:
    return acc_info['total_assets'][0].round(2)

def get_securities(acc_info: pd.DataFrame) -> float:
    return acc_info['securities_assets'][0].round(2)

def get_bonds(acc_info: pd.DataFrame) -> float:
    return acc_info['bond_assets'][0].round(2)

def extract_ticker(code: str) -> str:
    pattern = r"^[A-Z]+\.(?P<ticker>[A-Z0-9]+).*"
    match = re.match(pattern, code)
    if match:
        return match.group("ticker")
    else:
        return None
    
def cleanup_positions(positions:pd.DataFrame):
    pos_filter_col = ['code', 'stock_name', 'position_market', 'qty','diluted_cost','market_val','nominal_price', 'pl_ratio','pl_val','today_pl_val','currency']
    positions = positions.loc[:, pos_filter_col]
    rounding_dict = {
                    'qty': 2,
                    'diluted_cost': 2,
                    'market_val': 2,
                    'nominal_price': 2,
                    'pl_ratio': 2,
                    'pl_val': 2,
                    'today_pl_val': 2
                    }
    positions = positions.round(rounding_dict)
    positions = positions.sort_values(by='market_val', ascending=False).reset_index(drop=True)
    positions.rename(columns={'code': 'Symbol',
                            'stock_name':'Name',
                            'position_market':'Market',
                            'qty':'Quantity',
                            'diluted_cost':'Diluted Cost',
                            'market_val':'Market Value',
                            'nominal_price':'Current Price',
                            'pl_ratio':'P/L %',
                            'pl_val':'P/L',
                            'today_pl_val':"Today's P/L",
                            'currency':'Currency'}, inplace=True)
    positions['Symbol'] = positions['Symbol'].apply(extract_ticker)
    return positions



def get_exchange_rate(from_currency:str,to_currency:str):
    if from_currency == to_currency:
        return 1.0
    elif to_currency == 'USD':
        ticker = f"{from_currency}=X"
    else:
        ticker = f"{from_currency}{to_currency}=X"
    price_data = yf.download(tickers=ticker, period='2d',
                             auto_adjust=True,
                             interval='1m',
                             progress=False,
                             prepost=True)
    if price_data.empty:
        print("Warning: Could not download share price data.")
        return 

    # Extract the most recent price for each ticker
    # Forward-fill to propagate the last valid price, then select the last row.
    # This handles cases where some tickers may not have traded in the last minute.
    latest_price = price_data['Close'].ffill().iloc[-1].round(decimals=3).item()
    return latest_price

def convert_currency(value, from_currency:str, to_currency:str) -> Optional[float]:
    """Converts a given amount from one currency to another."""
    rate = get_exchange_rate(from_currency, to_currency)
    if rate:
        converted_amount = value * rate
        return round(converted_amount, 2)
    else:
        return None

def update_portfolio_percentage(pos: pd.DataFrame, total_assets: float) -> None:
    if total_assets == 0:
        pos['% of Portfolio'] = 0.0
    else:
        pos['% of Portfolio'] = (convert_currency(pos['Market Value'],"USD","SGD") / total_assets * 100).round(2)
        pos['% of Portfolio'] = pos['% of Portfolio'].apply(
            lambda x: f"{x:.2f}%"
        )

def cleanup_historical_orders(historical_orders:pd.DataFrame):
    historical_orders = historical_orders.loc[historical_orders['order_status'] == 'FILLED_ALL', 
                                          ['code', 'stock_name','order_market', 'trd_side','qty', 'price','currency','updated_time']]
    historical_orders.rename(columns={'code': 'Symbol',
                            'stock_name':'Name',
                            'order_market':'Market',
                            'trd_side':'Buy/Sell',
                            'qty':'Quantity',
                            'price':'Current Price',
                            'currency':'Currency',
                            'updated_time':'Date & Time'}, inplace=True)
    historical_orders['Symbol'] = historical_orders['Symbol'].apply(extract_ticker)
    return historical_orders

def main():
    trade_obj, process = moomoo_api.start_opend_headless()
    acc_list = moomoo_api.account_list(trade_obj)
    acc_info = moomoo_api.account_info(trade_obj)
    positions = moomoo_api.get_positions(trade_obj)
    cashflow = moomoo_api.account_cashflow(trade_obj, date=datetime.now().strftime('%Y-%m-%d'))
    historical_orders = moomoo_api.get_historical_orders(trade_obj)
    trade_obj.close()
    process.terminate()

    acc_info = cleanup_acc_info(acc_info)
    print(acc_info)
    print ("Total Assets: ",get_total_assets(acc_info))
    print ("Securities: ",get_securities(acc_info))
    print ("Cash: ",get_cash(acc_info))
    print ("Bonds: ",get_bonds(acc_info))
    positions = cleanup_positions(positions)
    update_portfolio_percentage(positions, get_total_assets(acc_info))
    print(positions)
    historical_orders = cleanup_historical_orders(historical_orders)
    print(historical_orders)
    return 0

if __name__ == "__main__":
    main()