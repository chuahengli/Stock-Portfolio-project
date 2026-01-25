import moomoo as moomoo
from moomoo.trade.open_trade_context import OpenSecTradeContext
from config import settings

import os
import time
import subprocess
from dotenv import load_dotenv
from datetime import datetime,date,timedelta
import pandas as pd
from typing import Optional, Dict, List
import psutil
from contextlib import contextmanager
import socket

def is_opend_responsive(host='127.0.0.1', port=11111):
    """Checks if OpenD is actually listening on the port."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except:
        return False
    
def stop_opend():
    """Forcefully kills any OpenD process (Clean reset)."""
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] == 'OpenD.exe':
            try:
                proc.kill() 
            except:
                pass

def ensure_opend_is_ready():
    """Starts OpenD if not responding, returns True when ready."""
    if is_opend_responsive():
        return True

    # If port is closed but process exists, it's a ghost. Kill it.
    stop_opend()
    
    print("Starting fresh OpenD instance...")
    opend_path = str(settings.OPEND_PATH)
    try:
        if os.name == 'nt': # Windows
                process = subprocess.Popen([opend_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
        else: # Linux/macOS
            process = subprocess.Popen([opend_path])
    except:
        print(f"Error: OpenD executable not found at {opend_path}")
    
    '''Wait up to 15 seconds for the port to open'''
    for _ in range(15):
        if is_opend_responsive():
            print("OpenD is now online.")
            return True
        time.sleep(1)
    return False
    


def configure_moomoo_api():
    # Get the RSA key path from environment variables
    load_dotenv(settings.BASE_DIR / ".env")
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
    return trade_ctx
    
def account_list(trade_obj: OpenSecTradeContext):
    ret, data = trade_obj.get_acc_list()
    if ret == moomoo.RET_OK:
        return data
    else:
        raise Exception('get_acc_list error: ', data)
        return None
    
def account_info(trade_obj: OpenSecTradeContext):
    ret, data = trade_obj.accinfo_query(trd_env="REAL",refresh_cache=True,currency="SGD")
    if ret == moomoo.RET_OK:
        return data
    else:
        raise Exception('accinfo_query error: ', data)
        return None
    
def get_positions(trade_obj: OpenSecTradeContext):
    ret, data = trade_obj.position_list_query(trd_env="REAL",refresh_cache=True)
    if ret == moomoo.RET_OK:
        return data
    else:
        raise Exception('position_list_query error: ', data)
        return None

def account_cashflow(trade_obj: OpenSecTradeContext, current_date: datetime, end_date: datetime):
    cash_flow_data = pd.DataFrame()
    request_count = 0
    start_time = time.time()
    
    while end_date <= current_date:
        # Rate Limit Check: 20 requests per 30 seconds
        if request_count >= 20:
            elapsed = time.time() - start_time
            if elapsed < 30:
                wait_time = 30 - elapsed + 1 # Add 1s buffer
                print(f"Quota used. Waiting {wait_time:.2f}s...")
                time.sleep(wait_time)
            # Reset window
            request_count = 0
            start_time = time.time()

        date_str = current_date.strftime('%Y-%m-%d')
        ret, data = trade_obj.get_acc_cash_flow(clearing_date=date_str, trd_env="REAL")

        if ret == moomoo.RET_OK:
            if not data.empty:
                cash_flow_data = pd.concat([cash_flow_data, data], ignore_index=True)
            request_count += 1
            current_date -= timedelta(days=1)

        elif ret == moomoo.RET_ERROR:
            print(f"Error on {date_str}: {data}")
            time.sleep(30)
            start_time = time.time()
            request_count = 0
    if cash_flow_data.empty:
        # Handle the case where no cashflow data was retrieved
        print("Warning: No cashflow data found for the given period.")

    return cash_flow_data
    
def get_historical_orders(trade_obj: OpenSecTradeContext):
    ret, data = trade_obj.history_order_list_query(start="2023-08-07 00:00:00",end=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    if ret == moomoo.RET_OK:
        return data 
    else:
        raise Exception('history_order_list_query error: ', data)

# Manage context, and whether keep openD alive or kill it
@contextmanager
def opend_session(keep_alive: bool = False):
    """Context manager to handle OpenD lifecycle."""
    ensure_opend_is_ready()
    trade_ctx = None
    try:
        trade_ctx = configure_moomoo_api()
        yield trade_ctx
    finally:
        if trade_ctx:
            trade_ctx.close()
        if not keep_alive:
            stop_opend()

def main():
    return 0

if __name__ == "__main__":
    main()