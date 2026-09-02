"""Path helpers for bundled resources (PyInstaller) and user data."""

from __future__ import annotations

import os
import sys


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def resource_path(relative: str) -> str:
    """Resolve a bundled-resource path. In PyInstaller frozen builds, files
    bundled via --add-data live under sys._MEIPASS. In dev, fall back to the
    repo root.
    """
    base = getattr(sys, "_MEIPASS", None) if getattr(sys, "frozen", False) else None
    if base:
        return os.path.join(base, relative)
    return os.path.join(_REPO_ROOT, relative)


def user_data_dir() -> str:
    """Return the native per-user application data directory."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        path = os.path.join(local_app_data, "MeowWare")
    elif sys.platform == "darwin":
        path = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "MeowWare")
    else:
        path = os.path.join(os.path.expanduser("~"), ".FFlagManager")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path
