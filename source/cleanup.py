from datetime import datetime
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

    cash_columns = ['fund_assets', 'cash']
    return acc_info[cash_columns].sum(axis=1)[0].round(2)

def get_total_assets(acc_info: pd.DataFrame) -> float:
    return acc_info['total_assets'][0].round(2)

def get_equity(acc_info: pd.DataFrame) -> float:
    return acc_info['securities_assets'][0].round(2) - get_cash(acc_info)

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
                            'diluted_cost':'Diluted_Cost',
                            'market_val':'Market_Value',
                            'nominal_price':'Current_Price',
                            'pl_ratio':'P_L_Percent',
                            'pl_val':'P_L',
                            'today_pl_val':"Today_s_P_L",
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
        pos['Portfolio_Percent'] = 0.0
    else:
        pos['Portfolio_Percent'] = (convert_currency(pos['Market_Value'],"USD","SGD") / total_assets * 100).round(2)
        pos['Portfolio_Percent'] = pos['Portfolio_Percent'].apply(
            lambda x: f"{x:.2f}%"
        )

def cleanup_historical_orders(historical_orders:pd.DataFrame):
    historical_orders = historical_orders.loc[historical_orders['order_status'] == 'FILLED_ALL', 
                                          ['code', 'stock_name','order_market', 'trd_side','order_id','qty', 'price','currency','updated_time']]
    historical_orders.rename(columns={'code': 'Symbol',
                            'stock_name':'Name',
                            'order_market':'Market',
                            'trd_side':'Buy_Sell',
                            'order_id':'Order_ID',
                            'qty':'Quantity',
                            'price':'Current_Price',
                            'currency':'Currency',
                            'updated_time':'date_time'}, inplace=True)
    historical_orders['Symbol'] = historical_orders['Symbol'].apply(extract_ticker)
    return historical_orders

def cleanup_cashflow(cashflow:pd.DataFrame):
    cashflow_filter = ['cashflow_id','clearing_date','currency','cashflow_type','cashflow_direction','cashflow_amount','cashflow_remark']
    cashflow = cashflow.loc[:, cashflow_filter]
    cashflow.rename(columns={'clearing_date':'Date',
                            'currency':'Currency',
                            'cashflow_type':'Type',
                            'cashflow_direction':'in_out',
                            'cashflow_amount':'Amount',
                            'cashflow_remark':'Remark'}, inplace=True)
    cashflow['Amount'] = cashflow['Amount'].round(2)
    return cashflow

def separate_assets(positions:pd.DataFrame):
    # Regex for Option: Root + 6 digits (date) + C/P + 8 digits (strike)
    option_pattern = r'[A-Z]+\d{6}[CP]\d+'
    # Create a boolean mask
    is_option = positions['Symbol'].str.contains(option_pattern, regex=True)
    df_options = positions[is_option].copy()
    df_stocks = positions[~is_option].copy()

    return df_stocks, df_options

def sum_of_mv(df:pd.DataFrame):
    converted_df = df.loc[:, ['Market_Value', 'Currency']].copy()
    converted_df['Market_Value'] = converted_df.apply(
                                lambda row: convert_currency(row['Market_Value'], row['Currency'], 'SGD'), axis=1
                                )
    return converted_df['Market_Value'].sum().round(2)


def portfolio_snapshot_table(date: str, total_assets:float, shares_mv:float, options_mv:float, cash:float):
    data = {
        'date': [date],
        'total_assets': [total_assets],
        'stocks': [shares_mv],
        'options': [options_mv],
        'cash': [cash]
    }
    snapshot_df = pd.DataFrame(data)
    return snapshot_df
def positions_table(positions:pd.DataFrame, date: str):
    positions_df = positions.copy()
    positions_df['date'] = date
    return positions_df


def main():
    return 0

if __name__ == "__main__":
    main()