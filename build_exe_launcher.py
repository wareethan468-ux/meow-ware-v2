"""Build Executor.exe as a self-contained windowed launcher, using the same
mechanism pip uses for GUI console-scripts: distlib's prebuilt w64.exe launcher
+ a shebang pointing at pythonw.exe + an appended zip whose __main__.py runs the
executor UI through the local interpreter.

No PyInstaller (broken on this 3.14), no admin manifest (runs as invoker → no UAC).
Output: Executor.exe in the repo root.
"""
import io
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PYW = os.path.join(sys.prefix, "pythonw.exe")            # C:\Python314\pythonw.exe
LAUNCHER = os.path.join(os.path.dirname(__import__("pip._vendor.distlib", fromlist=["x"]).__file__), "w64.exe")
OUT = os.path.join(HERE, "Executor.exe")

# This is the __main__.py that ends up inside the exe's appended zip. It runs
# under pythonw.exe with sys.argv[0] == the exe path, so the repo root is the
# exe's own directory.
MAIN_PY = r'''
import os, sys, ctypes, traceback
from pathlib import Path

def find_root():
    cands = []
    if sys.argv and sys.argv[0]:
        cands.append(Path(sys.argv[0]).resolve().parent)
    try:
        cands.append(Path(__file__).resolve().parent.parent)
    except Exception:
        pass
    cands.append(Path.cwd())
    for c in cands:
        if (c / "src" / "gui" / "api.py").exists() or (c / "run_executor.py").exists():
            return c
    return cands[0]

ROOT = find_root()
LOG = ROOT / "executor_boot.log"

def log(m):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(str(m) + "\n")
    except Exception:
        pass

def resolve_html():
    cands = [
        ROOT.parent / "exec" / "dist" / "index.html",
        ROOT / "exec" / "dist" / "index.html",
        ROOT.parent / "exec" / "index.html",
    ]
    for c in cands:
        if c.exists():
            return c
    return cands[0]

def main():
    try:
        LOG.write_text("", encoding="utf-8")
    except Exception:
        pass
    os.chdir(str(ROOT))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    log("=== boot(exe) === py=%s argv0=%s root=%s" % (sys.version.split()[0], (sys.argv[0] if sys.argv else ""), ROOT))
    try:
        import webview
        from src.gui.api import Api
        html = resolve_html()
        log("webview=%s html=%s exists=%s" % (getattr(webview, "__version__", "?"), html, Path(str(html)).exists()))
        api = Api()
        window = webview.create_window(
            title="Executor", url=str(html), js_api=api,
            width=850, height=620, min_size=(600, 450),
            resizable=True, frameless=True, easy_drag=False,
            background_color="#09090b",
        )
        api._window = window
        try:
            window.events.shown += (lambda: log("WINDOW_SHOWN"))
        except Exception as e:
            log("shown hook failed: %s" % e)
        log("starting webview loop")
        webview.start(debug=False)
        log("webview loop exited")
    except Exception:
        tb = traceback.format_exc()
        log("FATAL:\n" + tb)
        try:
            ctypes.windll.user32.MessageBoxW(0, "Executor failed to start.\n\nSee executor_boot.log\n\n" + tb[-600:], "Executor", 0x10)
        except Exception:
            pass
        raise

main()
'''


def main():
    if not os.path.exists(PYW):
        raise SystemExit("pythonw.exe not found at %s" % PYW)
    if not os.path.exists(LAUNCHER):
        raise SystemExit("distlib w64.exe not found at %s" % LAUNCHER)

    with open(LAUNCHER, "rb") as f:
        launcher = f.read()

    shebang = b"#!" + PYW.encode("utf-8") + b"\n"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("__main__.py", MAIN_PY)
    zip_data = buf.getvalue()

    blob = launcher + shebang + zip_data
    with open(OUT, "wb") as f:
        f.write(blob)

    print("launcher : %s (%d bytes)" % (LAUNCHER, len(launcher)))
    print("shebang  : %r" % shebang)
    print("zip      : %d bytes" % len(zip_data))
    print("wrote    : %s (%d bytes)" % (OUT, len(blob)))


if __name__ == "__main__":
    main()
