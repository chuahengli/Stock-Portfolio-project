"""Moomoo OpenD gateway: session lifecycle and account/position/order/cashflow queries."""
import moomoo as moomoo
from moomoo.trade.open_trade_context import OpenSecTradeContext
from config import settings
from config.credentials import generate_opend_xml

import os
import time
import subprocess
from datetime import datetime,date,timedelta
import pandas as pd
from typing import Optional, Dict, List
import psutil
from contextlib import contextmanager
import socket
import atexit
import ctypes

# ---------------------------------------------------------------------------
# OpenD lifecycle ownership.
#
# OpenD is launched with CREATE_NEW_CONSOLE, so it lives in its OWN console
# group: a Ctrl+C delivered to the app's console NEVER reaches it. The live
# poller also uses keep_alive=True, which deliberately skips stop_opend().
# Together those two things orphan the gateway (launcher + its child gateway
# process) on every shutdown, leaving port 11111 occupied and a stale
# "connected" status in the DB.
#
# Two independent cleanup mechanisms, both registered only when THIS process
# actually launched OpenD:
#   * atexit  -> graceful shutdown (Ctrl+C / SIGTERM / normal exit)
#   * Windows Job Object with KILL_ON_JOB_CLOSE -> even a hard kill
#     (taskkill /F, crash) makes the OS terminate OpenD for us.
# ---------------------------------------------------------------------------

_owned_opend_pids: set[int] = set()
_opend_job_handle = None
_cleanup_registered = False


def _kill_pid_tree(pid: int) -> None:
    """Kill pid AND its descendants. OpenD spawns a child gateway process
    (-internal_type_gateway=1); killing only the launcher leaves that child
    holding port 11111."""
    try:
        parent = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return
    # The process can exit between psutil.Process(pid) and .children(); when
    # this runs inside atexit that race would abort the whole cleanup callback.
    try:
        procs = parent.children(recursive=True) + [parent]
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return
    for proc in procs:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    psutil.wait_procs(procs, timeout=3)


def cleanup_owned_opend() -> None:
    """Kill only the OpenD instances this process launched. Idempotent."""
    for pid in list(_owned_opend_pids):
        _kill_pid_tree(pid)
        _owned_opend_pids.discard(pid)


def _ensure_kill_on_close_job():
    """Create a Job Object whose closure kills every assigned process."""
    global _opend_job_handle
    if _opend_job_handle is not None or os.name != "nt":
        return _opend_job_handle
    try:
        k = ctypes.WinDLL("kernel32", use_last_error=True)

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(f"c{i}", ctypes.c_ulonglong) for i in range(6)]

        class BASIC_LIMITS(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32),
            ]

        class EXTENDED_LIMITS(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BASIC_LIMITS),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        k.CreateJobObjectW.restype = ctypes.c_void_p
        k.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        job = k.CreateJobObjectW(None, None)
        if not job:
            return None
        info = EXTENDED_LIMITS()
        info.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        k.SetInformationJobObject.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        if not k.SetInformationJobObject(
            job, 9, ctypes.byref(info), ctypes.sizeof(info)
        ):  # 9 = JobObjectExtendedLimitInformation
            k.CloseHandle.argtypes = [ctypes.c_void_p]
            k.CloseHandle(job)
            return None
        _opend_job_handle = job
    except Exception:
        return None
    return _opend_job_handle


def _register_launched_opend(pid: int) -> None:
    """Take ownership of a freshly launched OpenD: bind it to the kill-on-close
    job and register graceful-shutdown cleanup (once)."""
    global _cleanup_registered
    _owned_opend_pids.add(pid)
    if not _cleanup_registered:
        atexit.register(cleanup_owned_opend)
        _cleanup_registered = True
    job = _ensure_kill_on_close_job()
    if job and os.name == "nt":
        try:
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.OpenProcess.restype = ctypes.c_void_p
            k.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
            # PROCESS_SET_QUOTA | PROCESS_TERMINATE
            h = k.OpenProcess(0x0100 | 0x0001, False, pid)
            if h:
                k.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                k.AssignProcessToJobObject(job, h)
                k.CloseHandle.argtypes = [ctypes.c_void_p]
                k.CloseHandle(h)
        except Exception:
            pass


def is_opend_responsive(host='127.0.0.1', port=11111):
    """Checks if OpenD is actually listening on the port."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except:
        return False
    
def _kill_ghost_opend_processes():
    """Startup ghost cleanup: the port is CLOSED here, so no gateway is serving.
    Any surviving OpenD.exe is a broken/orphaned instance from a crashed run
    that would block a fresh launch. Kill those by name; a *responsive* manual
    gateway never reaches this path (ensure_opend_is_ready returns early)."""
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] == 'OpenD.exe':
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass


def stop_opend():
    """Kill only the OpenD gateways THIS process launched (batch finalize).

    A gateway the user started manually is never touched (README contract) --
    if it were responding, ensure_opend_is_ready() would have returned early.
    Ownership is recorded at launch by _register_launched_opend; the Job Object
    covers hard kills. Called by opend_session(keep_alive=False) after a batch.
    """
    cleanup_owned_opend()

def ensure_opend_is_ready():
    """Starts OpenD if not responding, returns True when ready."""
    if is_opend_responsive():
        return True

    # If port is closed but process exists, it's a ghost from a crashed run.
    # Kill it by name here (ownership is per-process; a prior run's PIDs are
    # meaningless now). A responsive manual gateway returned True above.
    _kill_ghost_opend_processes()
    
    # Generate OpenD.xml from keyring credentials (returns False when none are configured)
    generate_opend_xml()
    
    print("Starting fresh OpenD instance...")
    opend_path = str(settings.OPEND_PATH)
    process = None
    try:
        if os.name == 'nt': # Windows
                process = subprocess.Popen([opend_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
        else: # Linux/macOS
            process = subprocess.Popen([opend_path])
    except:
        print(f"Error: OpenD executable not found at {opend_path}")
    if process is not None:
        _register_launched_opend(process.pid)

    # Wait up to 15 seconds for the port to open
    for _ in range(15):
        if is_opend_responsive():
            print("OpenD is now online.")
            return True
        time.sleep(1)
    return False
    


def configure_moomoo_api():
    """Create the trade context using the keyring-backed RSA key path."""
    from config.credentials import get_secret

    key_path = get_secret("rsa_key_path")
    if not key_path:
        raise RuntimeError(
            "No RSA private key path configured. Run:\n"
            "    python -m config.credentials setup"
        )
    # A .env value may arrive with literal backslash escaping.
    key_path = key_path.replace("\\\\", "\\")

    moomoo.SysConfig.set_init_rsa_file(key_path)
    # moomoo's CallbackExecutor (callback_executor.py:23) and reconnect Timers
    # are non-daemon by default and block on queue.get() / Timer.join(). On
    # Ctrl+C Streamlit's SIGINT/SIGBREAK handler only calls server.stop() and
    # returns, so threading._shutdown() joins those threads BEFORE atexit --
    # hanging forever and leaving OpenD.exe orphaned. Force daemon threads.
    moomoo.SysConfig.set_all_thread_daemon(True)
    # Create the trade context (is_encrypt uses the RSA key set above)
    trade_ctx = OpenSecTradeContext(
        host='127.0.0.1',
        port=11111,
        is_encrypt=True,
        security_firm="FUTUSG"
        )
    return trade_ctx
    
def account_list(trade_obj: OpenSecTradeContext):
    ret, data = trade_obj.get_acc_list()
    if ret != moomoo.RET_OK:
        raise Exception(f"get_acc_list error: {data}")
    return data


def account_info(trade_obj: OpenSecTradeContext):
    ret, data = trade_obj.accinfo_query(trd_env="REAL", refresh_cache=True, currency="SGD")
    if ret != moomoo.RET_OK:
        raise Exception(f"accinfo_query error: {data}")
    return data


def get_positions(trade_obj: OpenSecTradeContext):
    ret, data = trade_obj.position_list_query(trd_env="REAL", refresh_cache=True)
    if ret != moomoo.RET_OK:
        raise Exception(f"position_list_query error: {data}")
    return data

def account_cashflow(trade_obj: OpenSecTradeContext, current_date: datetime, end_date: datetime):
    cash_flow_list = []
    request_count = 0
    consecutive_errors = 0
    max_consecutive_errors = 5  # a dead OpenD/API must abort, not hang the batch forever
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
            consecutive_errors = 0
            if not data.empty:
                cash_flow_list.append(data)
            request_count += 1
            current_date -= timedelta(days=1)

        elif ret == moomoo.RET_ERROR:
            consecutive_errors += 1
            print(f"Error on {date_str} (consecutive {consecutive_errors}/{max_consecutive_errors}): {data}")
            if consecutive_errors >= max_consecutive_errors:
                print("Too many consecutive cashflow errors - aborting this fetch (partial data kept).")
                break
            time.sleep(30)
            start_time = time.time()
            request_count = 0
            
    if cash_flow_list:
        cash_flow_data = pd.concat(cash_flow_list, ignore_index=True)
    else:
        cash_flow_data = pd.DataFrame()

    if cash_flow_data.empty:
        # Handle the case where no cashflow data was retrieved
        print("Warning: No cashflow data found for the given period.")

    return cash_flow_data
    
def get_historical_orders(trade_obj: OpenSecTradeContext):
    start = datetime.combine(settings.START_DATE, datetime.min.time()).strftime('%Y-%m-%d %H:%M:%S')
    end = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ret, data = trade_obj.history_order_list_query(start=start, end=end)
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