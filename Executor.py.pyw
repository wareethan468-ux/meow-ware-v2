"""Executor launcher (windowed .pyw).

PyInstaller produces crashing exes on this Python 3.14 install (even a bare
hello-world segfaults), so we run the executor directly through the local
interpreter instead. Double-clicking this file runs it via pythonw.exe (no
console window) and self-elevates to admin so the injector (emulation.exe) can
attach to Roblox.

All startup progress + any error is written to executor_boot.log next to this
file. A line "WINDOW_SHOWN" there means the UI rendered successfully.

Set EXECUTOR_NO_ELEVATE=1 to run without requesting admin (for testing).
"""
import os
import sys
import ctypes
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "executor_boot.log"


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(str(msg) + "\n")
    except Exception:
        pass


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def pythonw_path():
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        w = exe.with_name("pythonw.exe")
        if w.exists():
            return str(w)
    w = Path(sys.prefix) / "pythonw.exe"
    return str(w) if w.exists() else sys.executable


def elevate():
    params = '"{}"'.format(os.path.abspath(__file__))
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", pythonw_path(), params, str(ROOT), 1)
    log("elevate: ShellExecuteW rc={} via {}".format(rc, pythonw_path()))


def run_ui():
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    import webview
    from src.gui.api import Api
    from run_executor import _resolve_exec_html

    html = _resolve_exec_html()
    log("webview={} exec_html={} exists={}".format(
        getattr(webview, "__version__", "?"), html, Path(str(html)).exists()))

    api = Api()
    window = webview.create_window(
        title="Executor",
        url=str(html),
        js_api=api,
        width=850,
        height=620,
        min_size=(600, 450),
        resizable=True,
        frameless=True,
        easy_drag=False,
        background_color="#09090b",
    )
    api._window = window

    def _shown():
        log("WINDOW_SHOWN")
    try:
        window.events.shown += _shown
    except Exception as e:
        log("shown-hook failed: {}".format(e))

    log("starting webview loop …")
    webview.start(debug=False)
    log("webview loop exited (window closed)")


def main():
    try:
        LOG.write_text("", encoding="utf-8")
    except Exception:
        pass
    log("=== boot === admin={} exe={} py={}".format(
        is_admin(), sys.executable, sys.version.split()[0]))

    if not is_admin() and os.environ.get("EXECUTOR_NO_ELEVATE") != "1":
        log("not admin -> requesting elevation")
        elevate()
        return

    try:
        run_ui()
    except Exception:
        log("FATAL:\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
