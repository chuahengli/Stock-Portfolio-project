import os
import time
import subprocess
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
import yfinance as yf
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
    
    
def main():
    opend_path = r"moomoo_OpenD_9.6.5618_Windows\OpenD.exe"
    opend_process = start_opend_headless(opend_path)
    time.sleep(5)
    opend_process.terminate()
    return

if __name__ == "__main__":
    main()