"""Small, dependency-free platform capability helpers."""

from __future__ import annotations

import sys

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"


def capabilities() -> dict:
    platform_name = "macos" if IS_MACOS else "windows" if IS_WINDOWS else sys.platform
    return {
        "platform": platform_name,
        "is_windows": IS_WINDOWS,
        "is_macos": IS_MACOS,
        "fflag_injector": IS_WINDOWS or IS_MACOS,
        "live_memory": IS_WINDOWS,
        "proxy": IS_WINDOWS,
        "executor": IS_WINDOWS,
        "offsets": IS_WINDOWS,
    }


def windows_only_error(feature: str) -> dict:
    return {"ok": False, "error": f"{feature} is only available on Windows"}
