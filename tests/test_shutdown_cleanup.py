"""Regression tests for OpenD shutdown / Ctrl+C cleanup.

Pure logic + real OS processes, but NO broker gateway and NO network. These
encode the reported bug: OpenD was launched with CREATE_NEW_CONSOLE (own console
group), the poller used keep_alive=True, and moomoo's non-daemon
CallbackExecutor thread blocked threading._shutdown() on Ctrl+C -- so the
Python process hung, atexit never ran, and both OpenD.exe processes survived.

The behavioural tests here go RED if the fix is removed; do not replace them
with source-string assertions alone (a green string check proves nothing).
"""
import ast
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

from source import moomoo_api, live

REPO_ROOT = Path(__file__).resolve().parents[1]
MOOMOO_API_SRC = Path(moomoo_api.__file__).read_text(encoding="utf-8")
LIVE_SRC = Path(live.__file__).read_text(encoding="utf-8")
STREAMLIT_SRC = (REPO_ROOT / "streamlit_app.py").read_text(encoding="utf-8")


def test_launcher_takes_ownership_of_opend_pid():
    """ensure_opend_is_ready must register the launched PID (atexit + job)."""
    assert "_register_launched_opend(process.pid)" in MOOMOO_API_SRC
    assert "CREATE_NEW_CONSOLE" in MOOMOO_API_SRC


def test_atexit_hook_is_registered_on_first_launch():
    assert "atexit.register(cleanup_owned_opend)" in MOOMOO_API_SRC


def test_job_object_uses_kill_on_job_close():
    """0x2000 = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: the OS kills OpenD even
    when the parent is taskkill /F'd and atexit cannot run."""
    assert "0x2000" in MOOMOO_API_SRC and "KILL_ON_JOB_CLOSE" in MOOMOO_API_SRC
    assert "AssignProcessToJobObject" in MOOMOO_API_SRC


def test_kill_pid_tree_includes_descendants():
    """OpenD spawns a child gateway; killing only the launcher leaves port
    11111 occupied. The cleanup MUST walk children recursively."""
    assert "children(recursive=True)" in MOOMOO_API_SRC


def test_children_race_is_guarded():
    """psutil.Process(pid) -> .children() can raise NoSuchProcess if OpenD
    exits between the two calls. Inside atexit that would abort cleanup."""
    body = MOOMOO_API_SRC[
        MOOMOO_API_SRC.index("def _kill_pid_tree"):
        MOOMOO_API_SRC.index("def cleanup_owned_opend")]
    assert "children(recursive=True)" in body
    assert "except (psutil.NoSuchProcess, psutil.AccessDenied):" in body


def test_cleanup_only_kills_owned_pids():
    """Must not kill a gateway the app did NOT launch (e.g. user's manual
    OpenD instance). Ownership is tracked in a set."""
    assert "_owned_opend_pids" in MOOMOO_API_SRC
    assert "def cleanup_owned_opend" in MOOMOO_API_SRC
    stop_body = MOOMOO_API_SRC[
        MOOMOO_API_SRC.index("def stop_opend"):
        MOOMOO_API_SRC.index("def ensure_opend_is_ready")]
    assert "process_iter" not in stop_body, \
        "stop_opend must not kill every OpenD.exe by name"
    assert "cleanup_owned_opend()" in stop_body
    # Startup ghost cleanup (port CLOSED) is a separate, by-name path.
    assert "def _kill_ghost_opend_processes" in MOOMOO_API_SRC


def test_kill_tree_on_a_real_process():
    """Functional check: kill a stand-in tree and confirm it is gone."""
    p = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )
    time.sleep(0.5)
    pid = p.pid
    assert psutil.pid_exists(pid)
    moomoo_api._owned_opend_pids.add(pid)
    try:
        moomoo_api.cleanup_owned_opend()
        time.sleep(0.5)
        assert not psutil.pid_exists(pid), "kill tree left the process alive"
        assert pid not in moomoo_api._owned_opend_pids
    finally:
        moomoo_api._owned_opend_pids.discard(pid)
        if psutil.pid_exists(pid):
            psutil.Process(pid).kill()


def test_poller_stop_cleans_up_gateway_and_status():
    """Toggling Live Mode off must close OpenD, not just set an Event."""
    assert "cleanup_owned_opend()" in LIVE_SRC
    assert "join(timeout=" in LIVE_SRC
    assert 'set_live_status("idle"' in LIVE_SRC


def test_dashboard_clears_stale_live_state_at_startup():
    """A crashed previous session must not leave 'connected' + stale quotes."""
    assert "clear_live_layer" in STREAMLIT_SRC
    assert "live_session_initialised" in STREAMLIT_SRC


# ---------------------------------------------------------------------------
# The reported Ctrl+C hang: moomoo.SysConfig.ALL_THREAD_DAEMON defaults to
# False, so CallbackExecutor is non-daemon and blocks threading._shutdown()
# BEFORE atexit. These are the tests that were missing when all 42 passed.
# ---------------------------------------------------------------------------

def test_daemon_flag_is_set_before_trade_context():
    assert "moomoo.SysConfig.set_all_thread_daemon(True)" in MOOMOO_API_SRC
    assert MOOMOO_API_SRC.index("set_all_thread_daemon(True)") \
        < MOOMOO_API_SRC.index("OpenSecTradeContext(")


def test_daemon_flag_actually_makes_callback_executor_daemon():
    """Behavioural: the flag must change the SDK thread's .daemon attribute.
    A source-string check alone would pass with the call in a dead branch."""
    import moomoo
    from moomoo.common.callback_executor import CallbackExecutor

    moomoo.SysConfig.set_all_thread_daemon(False)
    c_off = CallbackExecutor()
    moomoo.SysConfig.set_all_thread_daemon(True)
    c_on = CallbackExecutor()
    try:
        assert c_off._thread.daemon is False, "SDK default should be non-daemon"
        assert c_on._thread.daemon is True, "flag did not flip the SDK thread"
    finally:
        # Both threads block on queue.get(); release them so pytest can exit.
        c_off._queue.put(None)
        c_on._queue.put(None)
        moomoo.SysConfig.set_all_thread_daemon(False)


def test_shutdown_exits_cleanly_with_flag(tmp_path):
    """End-to-end (no broker): emulate Streamlit's stop-and-return handler.
    Without the flag the child HANGS in threading._shutdown() and atexit never
    fires -- exactly the reported 'terminal got issue'."""
    script = tmp_path / "_shutdown_child.py"
    script.write_text(
        "import atexit, sys, threading\n"
        "import moomoo\n"
        "from moomoo.common.callback_executor import CallbackExecutor\n"
        "moomoo.SysConfig.set_all_thread_daemon(sys.argv[1] == 'fixed')\n"
        "c = CallbackExecutor()\n"
        "print('daemon=%s' % c._thread.daemon, flush=True)\n"
        "atexit.register(lambda: print('ATEXIT_FIRED', flush=True))\n"
        "stop = threading.Event()\n"
        "threading.Timer(0.4, lambda: stop.set()).start()\n"
        "stop.wait()\n",
        encoding="utf-8",
    )
    for mode, expect_clean in (("current", False), ("fixed", True)):
        p = subprocess.Popen(
            [sys.executable, str(script), mode],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        hung = False
        try:
            out, _ = p.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            hung = True
            p.kill()
            out, _ = p.communicate()
        if expect_clean:
            assert not hung, "daemon flag did not unblock interpreter shutdown"
            assert "ATEXIT_FIRED" in out, "atexit (cleanup_owned_opend) never ran"
        else:
            assert hung, "non-daemon CallbackExecutor should hang shutdown"
            assert "ATEXIT_FIRED" not in out


def test_console_shutdown_hook_is_chained_and_registered():
    """Windows Ctrl+C arrives as a console control event; Streamlit's script
    thread cannot call signal.signal(), so a SetConsoleCtrlHandler hook is
    required. It must chain (return False) to Streamlit's own handler, use
    the correct BOOL return ABI, and be armed before the poller thread starts.
    """
    assert "SetConsoleCtrlHandler" in LIVE_SRC
    assert "WINFUNCTYPE(ctypes.c_int, ctypes.c_uint32)" in LIVE_SRC
    assert "return False" in LIVE_SRC
    assert "_install_console_shutdown_hook()" in LIVE_SRC
    assert LIVE_SRC.index("_install_console_shutdown_hook()") \
        < LIVE_SRC.index("self._thread = threading.Thread")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console hook only")
def test_console_hook_registers_and_uninstalls():
    """Real ctypes registration (no console control event sent)."""
    live._install_console_shutdown_hook()
    assert live._console_hook_registered
    assert live._console_hook_cb is not None
    live._install_console_shutdown_hook()  # idempotent
    assert live._console_hook_registered
    live._uninstall_console_shutdown_hook()
    assert not live._console_hook_registered
    assert live._console_hook_cb is None


def test_poller_stop_does_not_close_ctx_from_caller_thread():
    """Closing the trade context from stop() would race an in-flight
    accinfo/position query. _run owns the context via opend_session's
    finally; stop() must only signal the Event. AST-walk real calls, not
    docstring prose mentioning ctx.close()."""
    tree = ast.parse(LIVE_SRC)
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "LivePoller")
    stop = next(n for n in cls.body
                if isinstance(n, ast.FunctionDef) and n.name == "stop")
    calls = [n.func.attr for n in ast.walk(stop)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert "close" not in calls
