"""Optional Discord Rich Presence for Vellium Tweaker.

No image assets are sent: Discord renders the activity as a clean text card.
The service is intentionally best-effort and never blocks application startup.
"""
from __future__ import annotations

import json
import os
import struct
import threading
import time
import uuid

from src.utils.logger import log


DEFAULT_CLIENT_ID = "1543317341448704050"


class DiscordPresence:
    def __init__(self, client_id: str | None = None):
        if client_id is None:
            self.client_id = str(os.environ.get("MEOW_WARE_DISCORD_CLIENT_ID", "") or DEFAULT_CLIENT_ID).strip()
        else:
            self.client_id = str(client_id).strip()
        self._pipe = None
        self._rpc = None
        self._stop = threading.Event()
        self._thread = None
        self._start_time = int(time.time())

    def start(self):
        if not self.client_id or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="meow-ware-discord-rpc")
        self._thread.start()

    def _connect_pipe(self):
        for i in range(10):
            pipe_path = f"\\\\.\\pipe\\discord-ipc-{i}"
            try:
                pipe = open(pipe_path, "r+b", buffering=0)
                payload = json.dumps({"v": 1, "client_id": self.client_id}).encode("utf-8")
                pipe.write(struct.pack("<II", 0, len(payload)) + payload)
                resp_hdr = pipe.read(8)
                if len(resp_hdr) == 8:
                    _, resp_len = struct.unpack("<II", resp_hdr)
                    pipe.read(resp_len)
                return pipe
            except Exception:
                continue
        return None

    def _send_activity(self, pipe):
        payload = json.dumps({
            "cmd": "SET_ACTIVITY",
            "args": {
                "pid": os.getpid(),
                "activity": {
                    "details": "Using Vellium Tweaker",
                    "state": "Tuning Roblox FastFlags",
                    "timestamps": {
                        "start": self._start_time
                    }
                }
            },
            "nonce": str(uuid.uuid4())
        }).encode("utf-8")
        pipe.write(struct.pack("<II", 1, len(payload)) + payload)
        resp_hdr = pipe.read(8)
        if len(resp_hdr) == 8:
            _, resp_len = struct.unpack("<II", resp_hdr)
            pipe.read(resp_len)

    def _run(self):
        try:
            # 1. Direct Windows pipe connection (zero external dependency)
            self._pipe = self._connect_pipe()
            if self._pipe:
                self._send_activity(self._pipe)
                log("[+] Discord Rich Presence connected")
                while not self._stop.is_set():
                    self._stop.wait(timeout=15)
                return

            # 2. Fallback to pypresence if available
            try:
                from pypresence import Presence
                self._rpc = Presence(self.client_id)
                self._rpc.connect()
                self._rpc.update(
                    details="Using Vellium Tweaker",
                    state="Tuning Roblox FastFlags",
                    start=self._start_time,
                )
                log("[+] Discord Rich Presence connected")
                self._stop.wait()
            except Exception as exc:
                log(f"[*] Discord Rich Presence unavailable: {exc}")
        except Exception as exc:
            log(f"[*] Discord Rich Presence unavailable: {exc}")
        finally:
            if self._pipe:
                try:
                    self._pipe.close()
                except Exception:
                    pass
                self._pipe = None
            if self._rpc:
                try:
                    self._rpc.clear()
                    self._rpc.close()
                except Exception:
                    pass
                self._rpc = None

    def stop(self):
        self._stop.set()

    def restart(self, client_id: str):
        self.stop()
        self.client_id = str(client_id or "").strip()
        self._thread = None
        self.start()

