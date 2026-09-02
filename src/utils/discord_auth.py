"""Discord Authentication, License Key & Terms Acceptance Manager for Vellium Tweaker."""
from __future__ import annotations

import json
import os
import struct
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import urllib.request
import urllib.parse

from src.utils.config import Config
from src.utils.logger import log

AUTH_FILE = Config.APP_DIR / "auth_state.json"
DEFAULT_CLIENT_ID = "1543317341448704050"
SUPABASE_URL = "https://rdrtqrvozedfvcskwtna.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_PUBLIC_KEY", "sb_publishable_9ibbPO1-YKfliFE2e5bdtQ_V5SeNSpy")
_AUTH_LOCK = threading.Lock()


def get_auth_state() -> Dict[str, Any]:
    """Retrieve persisted authentication, license key, and Terms of Service acceptance state."""
    with _AUTH_LOCK:
        try:
            if AUTH_FILE.exists():
                with open(AUTH_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        terms_accepted = bool(data.get("terms_accepted", False))
                        discord_user = data.get("discord_user")
                        license_key = data.get("license_key")
                        key_type = data.get("key_type", "daily")
                        expires_at = data.get("expires_at")

                        # Check key expiration
                        key_valid = False
                        if license_key:
                            if not expires_at:
                                # Lifetime key
                                key_valid = True
                            else:
                                try:
                                    exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                                    now = datetime.now(timezone.utc)
                                    key_valid = now < exp_dt
                                except Exception:
                                    key_valid = True

                        authenticated = bool(terms_accepted and discord_user and key_valid)
                        return {
                            "authenticated": authenticated,
                            "terms_accepted": terms_accepted,
                            "discord_user": discord_user,
                            "license_key": license_key,
                            "key_type": key_type,
                            "expires_at": expires_at,
                            "key_valid": key_valid,
                        }
        except Exception as e:
            log(f"[*] Error reading auth state: {e}")
    return {
        "authenticated": False,
        "terms_accepted": False,
        "discord_user": None,
        "license_key": None,
        "key_type": None,
        "expires_at": None,
        "key_valid": False,
    }


def save_auth_state(state: Dict[str, Any]) -> bool:
    """Save authentication and terms state permanently to auth_state.json."""
    with _AUTH_LOCK:
        try:
            Config.APP_DIR.mkdir(parents=True, exist_ok=True)
            existing = {}
            if AUTH_FILE.exists():
                try:
                    with open(AUTH_FILE, "r", encoding="utf-8") as f:
                        existing = json.load(f) or {}
                except Exception:
                    pass
            existing.update(state)
            with open(AUTH_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
            log("[+] Persisted auth and license state")
            return True
        except Exception as e:
            log(f"[!] Error saving auth state: {e}")
            return False


def validate_license_key(key_code: str, discord_user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Verify an access key with the Supabase database."""
    clean_code = (key_code or "").strip().upper()
    if not clean_code:
        return {"ok": False, "error": "Please enter a valid key code"}
    if not SUPABASE_KEY:
        return {"ok": False, "error": "License service is not configured"}

    try:
        query_url = f"{SUPABASE_URL}/rest/v1/access_keys?key_code=eq.{urllib.parse.quote(clean_code)}&select=*"
        req = urllib.request.Request(
            query_url,
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not data or not isinstance(data, list):
                return {"ok": False, "error": "Invalid key. Generate a 12h key via the Discord bot /getkey"}

            key_record = data[0]
            if not key_record.get("is_active", True):
                return {"ok": False, "error": "This key has been revoked or deactivated"}

            expires_str = key_record.get("expires_at")
            if expires_str:
                exp_dt = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                if now > exp_dt:
                    return {"ok": False, "error": "This key has expired. Please run /getkey in Discord for a new daily key."}

            # Save valid session locally
            save_auth_state({
                "license_key": clean_code,
                "key_type": key_record.get("key_type", "daily"),
                "expires_at": expires_str,
                "key_validated_at": time.time(),
            })

            log(f"[+] License key '{clean_code}' verified successfully ({key_record.get('key_type', 'daily')})", (100, 255, 100))
            return {
                "ok": True,
                "key_code": clean_code,
                "key_type": key_record.get("key_type", "daily"),
                "expires_at": expires_str,
                "message": "Key verified successfully",
            }
    except Exception as e:
        log(f"[!] Error verifying license key: {e}", (255, 100, 100))
        return {"ok": False, "error": f"Verification error: {e}"}


def detect_local_discord_user() -> Optional[Dict[str, Any]]:
    """Query Discord desktop application IPC pipe to detect the active Discord user."""
    for i in range(10):
        pipe_path = f"\\\\.\\pipe\\discord-ipc-{i}"
        try:
            pipe = open(pipe_path, "r+b", buffering=0)
            payload = json.dumps({"v": 1, "client_id": DEFAULT_CLIENT_ID}).encode("utf-8")
            pipe.write(struct.pack("<II", 0, len(payload)) + payload)
            hdr = pipe.read(8)
            if len(hdr) == 8:
                _, rlen = struct.unpack("<II", hdr)
                res = json.loads(pipe.read(rlen).decode("utf-8"))
                user_raw = res.get("data", {}).get("user")
                if user_raw and isinstance(user_raw, dict):
                    user_id = str(user_raw.get("id", ""))
                    avatar_hash = str(user_raw.get("avatar") or "")
                    username = str(user_raw.get("username", "Discord User"))
                    global_name = str(user_raw.get("global_name") or username)

                    avatar_url = ""
                    if avatar_hash and user_id:
                        avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png?size=128"
                    elif user_id:
                        disc = int(user_raw.get("discriminator", 0) or 0)
                        default_index = (int(user_id) >> 22) % 6 if disc == 0 else disc % 5
                        avatar_url = f"https://cdn.discordapp.com/embed/avatars/{default_index}.png"

                    pipe.close()
                    return {
                        "id": user_id,
                        "username": username,
                        "global_name": global_name,
                        "avatar_url": avatar_url,
                        "method": "discord_ipc",
                    }
            pipe.close()
        except Exception:
            continue
    return None
