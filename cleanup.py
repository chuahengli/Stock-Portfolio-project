import moomoo_api
from typing import Optional, Dict, List
import pandas as pd

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

def main():
    data = moomoo_api.main()
    # data = {"account_list": ..., "account_info": ..., "positions": ..., "cashflow": ..., "historical_orders": ...}
    acc_info = cleanup_acc_info(data["account_info"])
    print(acc_info)
    print ("Total Assets: ",get_total_assets(acc_info))
    print ("Securities: ",get_securities(acc_info))
    print ("Cash: ",get_cash(acc_info))
    print ("Bonds: ",get_bonds(acc_info))
    return 0

if __name__ == "__main__":
    main()