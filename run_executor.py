"""
Launcher to open the Executor in a standalone desktop window.
"""
import os
import sys
from pathlib import Path
import webview
from src.gui.api import Api


def _resolve_exec_html() -> Path:
    """Locate the executor UI (exec/dist/index.html) in both dev and frozen builds.

    Frozen: prefer the copy bundled into the PyInstaller temp dir (_MEIPASS),
    then an ``exec`` folder sitting next to the .exe. Dev: the ``exec`` folder
    lives at the repo root, one level above this file.
    """
    candidates = []
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            candidates.append(Path(meipass) / 'exec' / 'dist' / 'index.html')
        exe_dir = Path(sys.executable).resolve().parent
        candidates += [
            exe_dir / 'exec' / 'dist' / 'index.html',
            exe_dir.parent / 'exec' / 'dist' / 'index.html',
        ]
    else:
        here = Path(__file__).resolve().parent
        candidates += [
            here.parent / 'exec' / 'dist' / 'index.html',   # top-level exec/dist (built UI)
            here / 'exec' / 'dist' / 'index.html',
            here.parent / 'exec' / 'index.html',             # dev source fallback
        ]

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def main():
    api = Api()

    exec_html = _resolve_exec_html()

    window = webview.create_window(
        title='Executor',
        url=str(exec_html),
        js_api=api,
        width=850,
        height=620,
        min_size=(600, 450),
        resizable=True,
        frameless=True,
        easy_drag=False,
        background_color='#09090b',
    )
    
    api._window = window
    webview.start(debug=False)

if __name__ == '__main__':
    main()
