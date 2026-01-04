import os
import time
import subprocess
from dotenv import load_dotenv
import moomoo as moomoo
from moomoo.trade.open_trade_context import OpenSecTradeContext
from datetime import datetime
from typing import Optional, Dict, List



def start_opend_headless(opend_path):
    try:
        if os.name == 'nt': # Windows
            process = subprocess.Popen([opend_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
        else: # Linux/macOS
            process = subprocess.Popen([opend_path])
        print(f"OpenD started with PID: {process.pid}")
        if process:
             time.sleep(5) # Wait for 5 seconds to ensure OpenD starts properly
             print("Connecting to OpenD via API...")
             return process
    except FileNotFoundError:
        print(f"Error: OpenD executable not found at {opend_path}")
        return None
    
def account_list(trade_obj: OpenSecTradeContext):
    ret, data = trade_obj.get_acc_list()
    if ret == moomoo.RET_OK:
        return data
    else:
        raise Exception('get_acc_list error: ', data)
    
def account_info(trade_obj: OpenSecTradeContext):
    ret, data = trade_obj.accinfo_query(trd_env="REAL",refresh_cache=True,currency="SGD")
    if ret == moomoo.RET_OK:
        return data
    else:
        raise Exception('accinfo_query error: ', data)
    
def get_positions(trade_obj: OpenSecTradeContext):
    ret, data = trade_obj.position_list_query(trd_env="REAL",refresh_cache=True)
    if ret == moomoo.RET_OK:
        return data
    else:
        raise Exception('position_list_query error: ', data)
    
def account_cashflow(trade_obj: OpenSecTradeContext, date:str):
    ret, data = trade_obj.get_acc_cash_flow(clearing_date=date,trd_env="REAL")
    if ret == moomoo.RET_OK:
        return data
    else:
        raise Exception('get_acc_cash_flow error: ', data)
    
def get_historical_orders(trade_obj: OpenSecTradeContext):
    ret, data = trade_obj.history_order_list_query()
    if ret == moomoo.RET_OK:
        return data
    else:
        raise Exception('history_order_list_query error: ', data)
    
    
def main():
    opend_path = r"moomoo_OpenD_9.6.5618_Windows\OpenD.exe"
    opend_process = start_opend_headless(opend_path)
    
    # Get the RSA key path from environment variables
    load_dotenv()
    key_path = os.getenv("KEY_PATH")
    # 1. Configure the RSA private key file globally
    moomoo.SysConfig.set_init_rsa_file(key_path)
    # 2. Create the trade context and enable encryption
    # is_encrypt=True encrypts using RSA key above
    trade_ctx = OpenSecTradeContext(
        host='127.0.0.1',
        port=11111,
        is_encrypt=True,
        security_firm="FUTUSG"
        )
    data = {
        "account_list": account_list(trade_ctx),
        "account_info": account_info(trade_ctx),
        "positions": get_positions(trade_ctx),
        "cashflow": account_cashflow(trade_ctx, date=datetime.now().strftime('%Y-%m-%d')),
        "historical_orders": get_historical_orders(trade_ctx)
        }
    
    trade_ctx.close()
    opend_process.terminate()
    
    return data

if __name__ == "__main__":
    main()