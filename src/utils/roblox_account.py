"""Roblox User Account and Profile Detection for Vellium Tweaker using Python Roblox API."""
from __future__ import annotations

import asyncio
import glob
import json
import os
import re
import threading
import time
import urllib.request
from typing import Any, Dict, Optional

from src.utils.config import Config
from src.utils.logger import log

_CACHE_LOCK = threading.Lock()
_USER_CACHE: Dict[str, Dict[str, Any]] = {}
_LAST_DETECTED_UID: Optional[str] = None
_SESSION_START_TIMES: Dict[int, float] = {}

CACHED_USER_FILE = Config.APP_DIR / "cached_user.json"

try:
    import roblox
    from roblox.thumbnails import AvatarThumbnailType
    _HAS_ROBLOX_LIB = True
except Exception:
    _HAS_ROBLOX_LIB = False


def _load_persisted_profile() -> Optional[Dict[str, Any]]:
    try:
        if CACHED_USER_FILE.exists():
            with open(CACHED_USER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data and isinstance(data, dict) and data.get("user_id"):
                    return data
    except Exception:
        pass
    return None


def _save_persisted_profile(profile: Dict[str, Any]):
    try:
        Config.APP_DIR.mkdir(parents=True, exist_ok=True)
        with open(CACHED_USER_FILE, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)
    except Exception:
        pass


def _fetch_profile_via_roblox_lib(uid_int: int) -> Optional[Dict[str, Any]]:
    """Fetch user profile and headshot avatar using the Python roblox API library."""
    if not _HAS_ROBLOX_LIB:
        return None
    try:
        async def _async_fetch():
            client = roblox.Client()
            user = await client.get_user(uid_int)
            avatar_url = ""
            try:
                avatars = await client.thumbnails.get_user_avatar_thumbnails(
                    users=[user],
                    type=AvatarThumbnailType.headshot,
                    size=(150, 150),
                    is_circular=True,
                )
                if avatars and len(avatars) > 0:
                    avatar_url = avatars[0].image_url or ""
            except Exception:
                pass
            return {
                "user_id": str(uid_int),
                "username": user.name or f"User_{uid_int}",
                "display_name": user.display_name or user.name or f"User_{uid_int}",
                "avatar_url": avatar_url,
            }

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_async_fetch())
        finally:
            loop.close()
    except Exception:
        return None


def _fetch_json(url: str) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _get_log_directories() -> list[str]:
    """Return all known candidate directories where Roblox client logs may reside."""
    dirs = [
        os.path.expandvars(r"%LOCALAPPDATA%\Roblox\logs"),
        os.path.expandvars(r"%LOCALAPPDATA%\Bloxstrap\Logs"),
        os.path.expandvars(r"%LOCALAPPDATA%\Bloxstrap\Roblox\Logs"),
        os.path.expandvars(r"%TEMP%\Roblox\logs"),
        os.path.expandvars(r"%APPDATA%\Roblox\logs"),
        os.path.expandvars(r"%LOCALAPPDATA%\Packages\ROBLOXCORPORATION.ROBLOX_55nm5eh3cm0pr\LocalState\logs"),
    ]
    return [d for d in dirs if os.path.isdir(d)]


def _extract_user_id_from_text(text: str) -> Optional[str]:
    """Scan log chunk for Roblox User ID using multiple high-accuracy signatures."""
    patterns = [
        r"(?i)userid[:\s=]+(\d{4,12})",
        r"(?i)user\s*id[:\s=]+(\d{4,12})",
        r"(?i)user_id[:\s=]+(\d{4,12})",
        r'(?i)"userId":\s*(\d{4,12})',
        r"(?i)friends\.roblox\.com/v1/user/(\d{4,12})",
        r"(?i)users\.roblox\.com/v1/users/(\d{4,12})",
        r"(?i)roblox\.com/users/(\d{4,12})",
        r"(?i)thumbnails\.roblox\.com/v1/users/avatar[a-z0-9\-]*\?userIds=(\d{4,12})",
        r"(?i)economy\.roblox\.com/v1/users/(\d{4,12})",
        r"(?i)presence\.roblox\.com/v1/presence/users.*?(\d{4,12})",
        r"(?i)data-user-id=[\"'](\d{4,12})[\"']",
        r"(?i)\[UserProvider\]\s*User:\s*(\d{4,12})",
        r"(?i)playerid[:\s=]+(\d{4,12})",
        r"(?i)player\s*id[:\s=]+(\d{4,12})",
        r"(?i)authenticated\s+user\s+(\d{4,12})",
        r"(?i)LocalPlayer::userId[:\s=]+(\d{4,12})",
        r"(?i)Connection accepted from .*?userId[:\s=]+(\d{4,12})",
        r"(?i)targetid[:\s=]+(\d{4,12})",
        r"(?i)rbx-user-id[:\s=]+(\d{4,12})",
    ]
    for pat in patterns:
        matches = re.findall(pat, text)
        if matches:
            for m in reversed(matches):
                if len(m) >= 4 and m != "00000000":
                    return m
    return None


def detect_roblox_user_id() -> Optional[str]:
    """Scan the most recent Roblox log files across all install types for the active user ID."""
    global _LAST_DETECTED_UID

    candidate_files = []
    for d in _get_log_directories():
        try:
            for ext in ("*.log", "*.txt"):
                for log_path in glob.glob(os.path.join(d, ext)):
                    try:
                        candidate_files.append((os.path.getmtime(log_path), log_path))
                    except Exception:
                        pass
        except Exception:
            pass

    # Sort newest logs first
    candidate_files.sort(key=lambda x: x[0], reverse=True)

    for _, fpath in candidate_files[:40]:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                if size <= 600000:
                    f.seek(0)
                    chunk = f.read()
                else:
                    f.seek(0)
                    head = f.read(200000)
                    f.seek(max(0, size - 400000))
                    tail = f.read()
                    chunk = head + "\n" + tail

                uid = _extract_user_id_from_text(chunk)
                if uid:
                    _LAST_DETECTED_UID = uid
                    return uid
        except Exception:
            continue

    if _LAST_DETECTED_UID:
        return _LAST_DETECTED_UID

    # Fallback to persisted profile if available
    persisted = _load_persisted_profile()
    if persisted and persisted.get("user_id"):
        return str(persisted["user_id"])

    return None


def get_roblox_profile(user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetch user profile details (username, displayName, avatar headshot) via roblox library."""
    uid = user_id or detect_roblox_user_id()
    if not uid:
        return _load_persisted_profile()

    now = time.time()
    with _CACHE_LOCK:
        cached = _USER_CACHE.get(str(uid))
        if cached and (now - cached.get("_cached_at", 0) < 600):
            return cached

    # 1. Try python roblox library
    try:
        lib_data = _fetch_profile_via_roblox_lib(int(uid))
        if lib_data and lib_data.get("username"):
            profile = {
                "user_id": str(uid),
                "username": lib_data["username"],
                "display_name": lib_data.get("display_name") or lib_data["username"],
                "avatar_url": lib_data.get("avatar_url") or "",
                "_cached_at": now,
            }
            _save_persisted_profile(profile)
            with _CACHE_LOCK:
                _USER_CACHE[str(uid)] = profile
            return profile
    except Exception:
        pass

    # 2. Fallback to direct HTTP API requests
    persisted = _load_persisted_profile()
    username = (persisted.get("username") if persisted and str(persisted.get("user_id")) == str(uid) else None) or f"User_{uid}"
    display_name = (persisted.get("display_name") if persisted and str(persisted.get("user_id")) == str(uid) else None) or username
    avatar_url = (persisted.get("avatar_url") if persisted and str(persisted.get("user_id")) == str(uid) else "") or ""

    user_data = _fetch_json(f"https://users.roblox.com/v1/users/{uid}")
    if user_data and "name" in user_data:
        username = user_data["name"]
        display_name = user_data.get("displayName") or username

    thumb_data = _fetch_json(
        f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={uid}&size=150x150&format=Png&isCircular=true"
    )
    if thumb_data and "data" in thumb_data and len(thumb_data["data"]) > 0:
        new_avatar = thumb_data["data"][0].get("imageUrl") or ""
        if new_avatar:
            avatar_url = new_avatar

    profile = {
        "user_id": str(uid),
        "username": username,
        "display_name": display_name,
        "avatar_url": avatar_url,
        "_cached_at": now,
    }

    _save_persisted_profile(profile)

    with _CACHE_LOCK:
        _USER_CACHE[str(uid)] = profile

    return profile


def record_session_start(pid: int):
    if pid and pid not in _SESSION_START_TIMES:
        _SESSION_START_TIMES[pid] = time.time()


def cleanup_sessions(active_pids: list[int]):
    stale = [p for p in _SESSION_START_TIMES if p not in active_pids]
    for p in stale:
        _SESSION_START_TIMES.pop(p, None)


def get_session_duration(pid: int) -> float:
    start = _SESSION_START_TIMES.get(pid)
    return max(0.0, time.time() - start) if start else 0.0

