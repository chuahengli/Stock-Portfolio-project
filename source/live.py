"""Live moomoo quote poller.

The dashboard wants a 10 s cadence from the broker (moomoo / futu OpenD), but
the nightly batch (main.py) takes ~76 s and owns the FK-ordered snapshot write.
This module is a SEPARATE, lightweight writer:

  * one long-lived OpenD session (accinfo_query + position_list_query = 2 calls),
  * polls every `interval` seconds in a background daemon thread,
  * writes ONLY to the dedicated `live_account` / `live_quotes` tables,
  * recomputes SGD totals with the STORED FX rate (no yfinance on the tick),
  * records its state in app_meta so the dashboard can show a real status.

It never touches cashflow / orders / price history / NAV units, so it cannot
race or corrupt the batch. The batch remains the single writer of record.

Threading note: all DB access goes through db_contextmanager, which opens its
own connection per call (check_same_thread=False is NOT relied on -- each call
gets a fresh connection). SQLite WAL handles the concurrent reader/writer.
"""
from __future__ import annotations

import os
import threading
import time
import traceback
from datetime import date, datetime

import pandas as pd

from source import db, cleanup, moomoo_api

# ---------------------------------------------------------------------------
# Windows shutdown hook.
#
# streamlit_app.py executes in Streamlit's SCRIPT THREAD, where signal.signal()
# raises "signal only works in main thread". A Ctrl+C / console-close arrives
# as a console control event, so use SetConsoleCtrlHandler instead: it can be
# installed from any thread and fires on CTRL_C_EVENT / CTRL_BREAK_EVENT /
# CTRL_CLOSE_EVENT (on window close atexit is NOT reliable, so this hook is the
# only path that cleans up). We chain to the previous handler -- Streamlit's
# own -- so the web server still stops normally, then proactively stop the
# poller so ctx.close(), cleanup_owned_opend() and the status reset happen
# IMMEDIATELY rather than at interpreter teardown. atexit + the Job Object
# remain the safety net for a hard kill. Non-Windows relies on Streamlit's
# SIGTERM/SIGINT handler returning normally (atexit runs there) plus daemon
# threads; signal.signal() cannot be installed from the script thread anyway.
# ---------------------------------------------------------------------------

_CTRL_HANDLER = None
_console_hook_registered = False
_console_hook_cb = None  # keep a reference alive (ctypes does not)
if os.name == "nt":
    import ctypes
    import atexit as _atexit

    # HandlerRoutine: BOOL WINAPI (DWORD). BOOL is a 32-bit int, not c_bool.
    _CTRL_HANDLER = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint32)


def _install_console_shutdown_hook() -> None:
    """Register once per process, on Windows only. No-op elsewhere/batch."""
    global _console_hook_registered, _console_hook_cb
    if _console_hook_registered or os.name != "nt":
        return
    k = ctypes.WinDLL("kernel32", use_last_error=True)

    @_CTRL_HANDLER
    def _on_console_event(ctrl_type):
        if ctrl_type in (0, 1, 2):  # CTRL_C / CTRL_BREAK / CTRL_CLOSE
            try:
                LivePoller.get().stop()
            except Exception:
                pass
        # Chain so Streamlit's own SIGINT/SIGBREAK handler still stops the
        # server. Returning False lets the next handler in the chain run.
        return False

    try:
        k.SetConsoleCtrlHandler.argtypes = [_CTRL_HANDLER, ctypes.c_bool]
        k.SetConsoleCtrlHandler.restype = ctypes.c_bool
        if k.SetConsoleCtrlHandler(_on_console_event, True):
            _console_hook_cb = _on_console_event  # prevent GC of callback
            _console_hook_registered = True
            _atexit.register(_uninstall_console_shutdown_hook)
    except Exception:
        pass


def _uninstall_console_shutdown_hook() -> None:
    global _console_hook_registered, _console_hook_cb
    if not _console_hook_registered or _console_hook_cb is None or os.name != "nt":
        return
    try:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.SetConsoleCtrlHandler.argtypes = [_CTRL_HANDLER, ctypes.c_bool]
        k.SetConsoleCtrlHandler.restype = ctypes.c_bool
        k.SetConsoleCtrlHandler(_console_hook_cb, False)
    except Exception:
        pass
    _console_hook_registered = False
    _console_hook_cb = None


class LivePoller:
    """Process-level singleton. Start once; the Streamlit fragment only reads."""

    _instance: "LivePoller | None" = None
    _cls_lock = threading.Lock()

    def __init__(self, interval: float = 10.0):
        self.interval = interval
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    @classmethod
    def get(cls, interval: float = 10.0) -> "LivePoller":
        with cls._cls_lock:
            if cls._instance is None:
                cls._instance = cls(interval)
            return cls._instance

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            # Ctrl+C / console-close cleanup must be armed BEFORE the first
            # OpenD session is opened (install once per process).
            _install_console_shutdown_hook()
            self._thread = threading.Thread(
                target=self._run, name="moomoo-live-poller", daemon=True
            )
            self._thread.start()
            db.set_live_status("starting", "Opening OpenD session...")

    def stop(self, join_timeout: float = 5.0) -> None:
        """Signal the poll loop to exit, close the OpenD session and kill any
        OpenD the app itself launched. Also clears the stale 'connected' status.

        The atexit / Job Object hooks in moomoo_api are the safety net for a
        hard kill (Ctrl+C / taskkill /F); this is the graceful path used when
        the user toggles Live Mode off."""
        self._stop.set()
        # Cooperative shutdown: _run owns the trade context, and
        # opend_session(keep_alive=True)'s finally ALWAYS calls ctx.close().
        # Closing it here would race an in-flight accinfo/position query.
        # The stop Event makes the poll loop exit and its finally close the
        # CallbackExecutor queue immediately (no interpreter-teardown join).
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=join_timeout)
        try:
            moomoo_api.cleanup_owned_opend()
        except Exception:
            pass
        try:
            db.set_live_status("idle", "Live Mode off.")
        except Exception:
            pass

    def _run(self) -> None:
        # The live_* tables must exist before the first write (the nightly
        # batch may not have run yet on a fresh clone).
        try:
            db.init_db()
        except Exception:
            pass
        # Keep OpenD alive for the whole session so we don't spawn/kill the
        # gateway every 10 s. If it dies, the loop retries the connection.
        while not self._stop.is_set():
            try:
                with moomoo_api.opend_session(keep_alive=True) as ctx:
                    db.set_live_status("connected", "")
                    while not self._stop.wait(self.interval):
                        try:
                            self._poll_once(ctx)
                        except Exception as e:
                            db.set_live_status("error", f"{type(e).__name__}: {e}")
                            traceback.print_exc()
            except Exception as e:
                db.set_live_status("disconnected", f"{type(e).__name__}: {e}")
                if self._stop.wait(min(self.interval, 5)):
                    break
        db.set_live_status("idle", "Stopped.")

    def _poll_once(self, ctx) -> None:
        acc_raw = moomoo_api.account_info(ctx)
        pos_raw = moomoo_api.get_positions(ctx)
        account, quotes = build_live_snapshot(acc_raw, pos_raw)
        db.write_live_snapshot(account, quotes)
        db.set_live_status("connected", account["as_of"])


def build_live_snapshot(acc_raw: pd.DataFrame,
                        pos_raw: pd.DataFrame) -> tuple[dict, list[dict]]:
    """Pure transform: raw moomoo frames -> (account dict, quote rows).

    Reuses the SAME cleaning as the batch (cleanup_positions / acc_info) so the
    live numbers are directly comparable. SGD conversion uses the stored FX
    rate from app_meta (written by the batch) -- never a live yfinance call.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = date.today().strftime("%Y-%m-%d")

    acc = cleanup.cleanup_acc_info(acc_raw)
    pos = cleanup.cleanup_positions(pos_raw)

    # sum_of_mv uses live yfinance FX; use the stored-rate path instead.
    def _sum_sgd(frame):
        # pandas calls apply(axis=1) once with a dummy all-NaN row on an EMPTY
        # frame for dtype inference; that row would hit the FX path with a
        # nonsensical currency. Guard it explicitly.
        if frame.empty:
            return 0.0
        return round(float(frame.apply(
            lambda r: db.convert_currency_cached(r["Market_Value"], r["Currency"], "SGD"),
            axis=1,
        ).sum()), 2)

    shares, options = cleanup.separate_assets(pos)
    stocks_mv = _sum_sgd(shares)
    options_mv = _sum_sgd(options)
    cash = cleanup.get_cash(acc)
    account = {
        "total_assets": round(stocks_mv + options_mv + cash, 2),
        "stocks": stocks_mv,
        "options": options_mv,
        "cash": cash,
        "as_of": now,
    }

    # Recompute Portfolio_Percent from the live values, using the SAME
    # internally-consistent total as the metric row above.
    total = account["total_assets"]
    if pos.empty:
        pos["Portfolio_Percent"] = pd.Series(dtype="object")
    else:
        mv_sgd = pos.apply(
            lambda r: db.convert_currency_cached(r["Market_Value"], r["Currency"], "SGD"),
            axis=1,
        )
        pos["Portfolio_Percent"] = (
            (mv_sgd / total * 100).round(2).apply(lambda x: f"{x:.2f}%")
            if total else "0.00%"
        )

    quotes = []
    for r in pos.itertuples(index=False):
        quotes.append({
            "Symbol": r.Symbol,
            "Name": r.Name,
            "Market": r.Market,
            "Quantity": r.Quantity,
            "Diluted_Cost": r.Diluted_Cost,
            "Current_Price": r.Current_Price,
            "Market_Value": r.Market_Value,
            "P_L_Percent": r.P_L_Percent,
            "P_L": r.P_L,
            "Today_s_P_L": r.Today_s_P_L,
            "Currency": r.Currency,
            "Portfolio_Percent": r.Portfolio_Percent,
            "date": today,
            "as_of": now,
        })
    return account, quotes


# Module-level convenience used by the dashboard.
def ensure_started(interval: float = 10.0) -> LivePoller:
    poller = LivePoller.get(interval)
    poller.start()
    return poller
