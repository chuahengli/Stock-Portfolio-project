import os
import time
import subprocess
from dotenv import load_dotenv
import moomoo as moomoo
from moomoo.trade.open_trade_context import OpenSecTradeContext
from datetime import datetime,date,timedelta
import pandas as pd
from typing import Optional, Dict, List
import psutil

def manage_opend():
    opend_path = r"moomoo_OpenD_9.6.5618_Windows\OpenD.exe"

    # Check if OpenD is already running
    existing_proc = None
    for proc in psutil.process_iter(['name', 'pid']):
        if proc.info['name'] == 'OpenD.exe':
            existing_proc = proc
            break
    if existing_proc:
        print(f"OpenD already running (PID: {existing_proc.info['pid']}). Using existing instance.")
        # Return the existing process and True (it was already running)
        return existing_proc, True
    # If not running, start it
    print("Starting new OpenD instance...")
    new_proc = start_opend_headless(opend_path)
    return new_proc, False

def start_opend_headless(opend_path: str):
    try:
        if os.name == 'nt': # Windows
            process = subprocess.Popen([opend_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
        else: # Linux/macOS
            process = subprocess.Popen([opend_path])
        print(f"OpenD started with PID: {process.pid}")
        print("Connecting to OpenD via API...")
        time.sleep(5)  # Wait for OpenD to initialize
        return process
    except FileNotFoundError:
        print(f"Error: OpenD executable not found at {opend_path}")
        return None


def configure_moomoo_api():
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
    

    
    
def run(current_date: datetime, end_date: datetime): 
    proc_handle, was_already_running = manage_opend()
    trade_ctx = None
    # Initialize variables to None to prevent UnboundLocalError if an exception occurs early
    acc_info, positions, cashflow, historical_orders = None, None, None, None
    try:
        trade_ctx = configure_moomoo_api()
        acc_list = account_list(trade_ctx)
        acc_info = account_info(trade_ctx)
        positions = get_positions(trade_ctx)
        cashflow = account_cashflow(trade_ctx, current_date, end_date)
        historical_orders = get_historical_orders(trade_ctx)

    except Exception as e:
        print(f"API Error: {e}")
    finally:
        if trade_ctx:
            trade_ctx.close()
        #KILL THE PROCESS
        # If we started it, OR if you want it dead regardless:
        if proc_handle:
            print("Shutting down OpenD...")
            proc_handle.terminate() # Gentle request to close
            
            # Wait 2 seconds, if still alive, kill it forcefully
            try:
                proc_handle.wait(timeout=2)
            except subprocess.TimeoutExpired:
                print("OpenD didn't close, forcing kill...")
                proc_handle.kill()

    

    print(acc_info)
    print(positions)
    print(cashflow)
    print(historical_orders)

    return acc_info, positions, cashflow, historical_orders

def main():
    return 0

if __name__ == "__main__":
    main()