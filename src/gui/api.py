import os
import json
import time
import threading
import ctypes
import subprocess
import sys
import base64
import gzip
from pathlib import Path
from ctypes import wintypes
import webview
from src.utils.updater import check_for_updates, perform_silent_update, get_current_version, apply_staged_update, download_update
from src.utils.logger import log, get_logs, get_logs_since, clear_logs as clear_console_logs
from src.utils.config import Config
from src.utils.helpers import infer_type, infer_type_from_name, clean_flag_name, get_flag_prefix, get_default_value, strip_bogus_dflag_prefix, heal_dflag_flag_names
from src.utils.discord_presence import DiscordPresence
from src.core.roblox_manager import RobloxManager
from src.core.flag_manager import FlagManager
from src.core.preset_manager import PresetManager
from src.gui.executor import ExecutorMixin

# Apply-speed knobs (website Play / Auto Apply). To undo this pass:
# KEEP_JSON_WHEN_AUTO_APPLY = False, MONITOR_POLL_FAST = 2.0
KEEP_JSON_WHEN_AUTO_APPLY = True
MONITOR_POLL_FAST = 0.25
MONITOR_POLL_SLOW = 2.0

# ─── HMAC key shard B (paired with config._HMAC_SHARD_A) ───
from src.utils import config as _cfg_module
from src.utils import helpers as _helpers_module
_cfg_module._register_hmac_shard_b(bytes([89, 150, 227, 32, 105, 184, 30, 184, 195, 160, 39, 97, 6, 34, 201, 28, 26, 43, 24, 148, 79, 77, 1, 241, 77, 46, 249, 198, 17, 81, 164, 213]))  # Sealed at build time


# ─── S5: bytecode self-check (sealed at build) ───
import hashlib as _hashlib_s5

_SHARD_S5_A = bytes([95, 202, 55, 172, 113, 34, 239, 146, 60, 212, 124, 6, 204, 161, 141, 24, 18, 13, 151, 41, 201, 124, 180, 77, 100, 192, 130, 6, 19, 134, 15, 94])
_SHARD_S5_B = bytes([118, 220, 245, 9, 173, 208, 200, 23, 163, 97, 42, 7, 83, 101, 148, 112, 239, 222, 58, 134, 9, 53, 135, 251, 234, 231, 24, 246, 166, 223, 2, 5])
_SHARD_S5_EXPECTED = None
_shard_s5_fired = False


def _shard_s5_reset():
    global _shard_s5_fired
    _shard_s5_fired = False


def _shard_s5_expected():
    if _SHARD_S5_EXPECTED is not None:
        return _SHARD_S5_EXPECTED
    return _helpers_module._unshard(_SHARD_S5_A, _SHARD_S5_B)


def _shard_s5_check():
    global _shard_s5_fired
    if _shard_s5_fired:
        return
    _shard_s5_fired = True
    if not _helpers_module._is_frozen():
        return
    # Late-import to avoid a circular dependency at module load
    from src.gui import main_window
    co = main_window.MainWindow.__init__.__code__.co_code
    _helpers_module._rot_observed()
    if _hashlib_s5.sha256(co).digest() == _shard_s5_expected():
        _helpers_module._rot_subtract(283)


# ─── Rot vectors: silent degradation when cache is dirty ───
import random as _random_rot
import time as _time_rot


def _r1_filter(flag_dict):
    """Pass-through when the cache is clean; drops 1-2 keys probabilistically
    when dirty. Looks like an intermittent serialization skip."""
    if not _helpers_module._rot_is_dirty():
        return flag_dict
    quantum = _helpers_module._rot_get()
    magnitude = abs(quantum)
    prob = min(0.35, magnitude / 8000.0)
    if _random_rot.random() >= prob:
        return flag_dict
    keys = list(flag_dict.keys())
    if not keys:
        return flag_dict
    n_drop = 1 if len(keys) < 10 or _random_rot.random() < 0.5 else 2
    n_drop = min(n_drop, len(keys), 2)
    drop = set(_random_rot.sample(keys, n_drop))
    return {k: v for k, v in flag_dict.items() if k not in drop}


def _r3_should_skip():
    """Whether this refresh cycle should silently no-op. Always False when
    cache is clean."""
    if not _helpers_module._rot_is_dirty():
        return False
    return _random_rot.random() < 0.20


def _r4_maybe_freeze():
    """Injects an occasional multi-second stall when the cache is dirty.
    Targeted at hot paths so the user sees it as a slow-disk hiccup."""
    if not _helpers_module._rot_is_dirty():
        return
    if _random_rot.random() < 0.05:  # 5% chance per call
        _time_rot.sleep(_random_rot.uniform(3.0, 8.0))

# Win32 Constants
WM_NCLBUTTONDOWN = 0x00A1
WM_SYSCOMMAND = 0x0112
HTCAPTION = 2
SC_SIZE = 0xF000


# ─── Preset Format Helpers (module-level, unit-testable) ───
# Used by Api.export_preset / export_preset_to_file / import_preset_clipboard / import_preset_from_file.

PRESET_EXPORT_FORMATS = ('base64', 'json-flags-only', 'json-with-binds', 'txt')


def _strip_internal_flag_fields(flags, include_binds=True):
    """Return a list of flag dicts, optionally without bind metadata."""
    cleaned = []
    bind_keys = ('bind', 'unapply_bind', 'cycle_states')
    for f in flags or []:
        if not isinstance(f, dict):
            continue
        nf = {}
        for k, v in f.items():
            if isinstance(k, str) and k.startswith('_'):
                continue
            if not include_binds and k in bind_keys:
                continue
            nf[k] = v
        cleaned.append(nf)
    return cleaned


def _preset_switch_revert_set(old_flags, new_flags):
    """Diff for a clean preset switch.

    Returns the subset of `old_flags` that must be reverted in live memory: the
    flags the NEW preset will NOT actively set — i.e. flags being removed, or
    flags now disabled. Shared flags that the new preset still sets are left out
    (the apply overwrites them in place — no revert-then-rewrite churn), and
    flags that were never used aren't involved at all.

    Only previously-active (enabled) old flags are candidates: a disabled old
    flag was never written, so there is nothing to revert.
    """
    from src.utils.helpers import clean_flag_name
    new_active = {
        clean_flag_name(f['name'])
        for f in (new_flags or [])
        if isinstance(f, dict) and f.get('name') and f.get('enabled', True)
    }
    revert = []
    for f in (old_flags or []):
        if not isinstance(f, dict) or not f.get('name'):
            continue
        if not f.get('enabled', True):
            continue
        if clean_flag_name(f['name']) not in new_active:
            revert.append(f)
    return revert


def _export_preset_format(preset_dict, fmt):
    """Pure transform — preset dict -> exportable string in the requested format.

    fmt in PRESET_EXPORT_FORMATS. Raises ValueError on unknown format.
    """
    if fmt not in PRESET_EXPORT_FORMATS:
        raise ValueError(f"unknown format: {fmt}")

    flags = preset_dict.get('flags') or []
    name = preset_dict.get('name', 'Preset')

    if fmt == 'base64':
        import base64
        import zlib
        # Wrap full preset for max-fidelity round-trip
        j = json.dumps(preset_dict)
        return base64.b64encode(zlib.compress(j.encode('utf-8'))).decode('utf-8')

    if fmt == 'json-with-binds':
        body = {
            'name': name,
            'flags': _strip_internal_flag_fields(flags, include_binds=True),
        }
        return json.dumps(body, indent=4)

    if fmt == 'json-flags-only':
        # Standard FastFlag map: { "FullFlagName": "value", ... }. Every value is
        # stringified so it matches Roblox's ClientAppSettings.json exactly and is
        # drop-in for Bloxstrap / other tools. The key is the full name including
        # its prefix (DFInt/FFlag/...), which we already store, so no type info is
        # lost. Insertion order (preset order) is preserved.
        out = {}
        for f in flags:
            if isinstance(f, dict) and f.get('name'):
                out[f['name']] = str(f.get('value', ''))
        return json.dumps(out, indent=4)

    if fmt == 'txt':
        # KEY=VALUE, one per line. Header comment for hand-editors.
        lines = [
            f"# Preset: {name}",
            f"# Exported {len(flags)} flags. KEY=VALUE per line. Lines starting with # and blank lines are ignored.",
        ]
        for f in flags:
            if not isinstance(f, dict) or 'name' not in f:
                continue
            lines.append(f"{f['name']}={f.get('value', '')}")
        return "\n".join(lines) + "\n"

    raise ValueError(f"unhandled format: {fmt}")  # defensive — unreachable


def _parse_preset_payload(raw_string, source_name=None, allow_plain_text=True):
    """Parse a preset payload from any of the supported formats.

    Tries (in order): JSON -> base64+zlib -> plain text KEY=VALUE.
    When allow_plain_text is False (e.g. editor Import which only handles
    structured formats), the plain-text fallback is skipped and a
    decoding failure raises ValueError instead.
    Returns (name: str, flags: list[dict]).
    Raises ValueError with a clear message on unrecoverable failure.
    """
    if not raw_string or not isinstance(raw_string, str):
        raise ValueError("empty payload")

    text = raw_string.strip()
    if not text:
        raise ValueError("empty payload")

    default_name = (source_name or 'Imported Preset').rsplit('.', 1)[0] or 'Imported Preset'

    parsed = None

    # 1) JSON
    if text.startswith('{') or text.startswith('['):
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None

    # 2) base64+zlib
    if parsed is None:
        try:
            import base64
            import zlib
            decompressed = zlib.decompress(base64.b64decode(text)).decode('utf-8')
            parsed = json.loads(decompressed)
        except Exception:
            parsed = None

    # 3) Plain text KEY=VALUE
    if parsed is None:
        if not allow_plain_text:
            raise ValueError(
                "payload is not JSON or base64+zlib; plain text KEY=VALUE "
                "is not supported in this context"
            )
        flags = []
        for line_no, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                raise ValueError(f"line {line_no}: expected KEY=VALUE, got {line!r}")
            k, _, v = line.partition('=')
            k = k.strip()
            v = v.strip()
            if not k:
                raise ValueError(f"line {line_no}: empty key")
            inferred_type = infer_type_from_name(k) or infer_type(v)
            flags.append({'name': strip_bogus_dflag_prefix(k), 'value': v, 'type': inferred_type})
        if not flags:
            raise ValueError("no flags found in payload")
        flags, _ = heal_dflag_flag_names(flags)
        return default_name, flags

    # We have a parsed JSON-like value. Normalize to (name, flags).
    if isinstance(parsed, list):
        flags = []
        for f in parsed:
            if isinstance(f, dict) and 'name' in f:
                nf = dict(f)
                nf['type'] = infer_type_from_name(nf['name']) or nf.get('type', 'string')
                flags.append(nf)
            elif isinstance(f, dict):
                flags.append(f)
        if not flags:
            raise ValueError("JSON list contained no usable flag entries")
        flags, _ = heal_dflag_flag_names(flags)
        return default_name, flags

    if isinstance(parsed, dict):
        if 'flags' in parsed and isinstance(parsed['flags'], list):
            name = parsed.get('name') or default_name
            flags = []
            for f in parsed['flags']:
                if not isinstance(f, dict):
                    continue
                nf = dict(f)
                if 'name' in nf:
                    nf['type'] = infer_type_from_name(nf['name']) or nf.get('type', 'string')
                flags.append(nf)
            if not flags:
                raise ValueError("preset has empty 'flags' list")
            flags, _ = heal_dflag_flag_names(flags)
            return name, flags
        # {flagName: value, ...} bare map
        flags = []
        for k, v in parsed.items():
            if not isinstance(k, str):
                continue
            flags.append({
                'name': strip_bogus_dflag_prefix(k),
                'value': str(v),
                'type': infer_type_from_name(k) or infer_type(v),
            })
        if not flags:
            raise ValueError("JSON object had no string keys")
        flags, _ = heal_dflag_flag_names(flags)
        return default_name, flags

    raise ValueError(f"unrecognized payload shape: {type(parsed).__name__}")


def _slot_verdict(exists, disp, rect_w, rect_h, frames, fr_w, fr_h):
    """Turn a slot's DOM state into a one-word verdict used by the
    diagnostic log. Kept as a plain function so it stays trivially
    unit-testable and doesn't need the Api instance."""
    if not exists:
        return "MISSING (aux-pane div not found — index.html edited)"
    if disp == 'none':
        return ("HIDDEN (CSS media query — window too narrow: "
                "<=1280 hides side rail, <=900 hides top strip, "
                "<=700 hides bottom strip)")
    if rect_w == 0 or rect_h == 0:
        return "COLLAPSED (ancestor display:none or zero layout area)"
    if frames == 0:
        return ("NO IFRAME (shim did not inject — check "
                "intersection-polyfill.js loaded and get_content_filter "
                "returned true)")
    if fr_w == 0 or fr_h == 0:
        return "IFRAME COLLAPSED (Adsterra script may have zeroed dims)"
    return "OK (iframe rendered — if you still see blank, ad network is empty or blocked)"


class Api(ExecutorMixin):
    def get_platform_capabilities(self):
        from src.utils.platform_support import capabilities
        return capabilities()

    def set_hotkeys_inhibited(self, inhibited):
        if hasattr(self, 'flag_manager') and self.flag_manager:
            self.flag_manager.set_hotkeys_inhibited(inhibited)

    def __init__(self):
        self._window = None  # Set after window creation
        self._last_apply_time = 0
        self._init_error = None
        self.processed_pids = set()
        self.update_ready = False
        self._pending_update = None  # {version, exe_url, changelog}
        self._update_progress = 0  # 0-100 for frontend polling
        self._fix_progress = 0      # 0-100 for the Fix Roblox modal; -1 = failed
        self._fix_state = "idle"    # idle | running | done | failed | cancelled
        self._fix_message = ""
        self._fix_cancel = False
        self._last_offsets_loaded_state = False
        # Tracks previous monitor-loop iteration's Roblox pid so we can fire
        # auto-clear exactly once on the running -> not-running transition.
        self._last_seen_roblox_pid = None
        # Scheduled Apply (B2): pid -> monotonic due-time for a deferred,
        # memory-only injection. Populated by the monitor loop when a new
        # Roblox is detected and scheduled_apply_delay > 0.
        self._scheduled_due = {}
        self._needs_ui_refresh = False
        self._initialize_runtime()

    def _is_authenticated(self) -> bool:
        """Check if user has accepted terms, connected Discord, and has an active valid license."""
        try:
            from src.utils.discord_auth import get_auth_state
            state = get_auth_state()
            return bool(state.get("authenticated", False))
        except Exception:
            return False

    def _require_auth(self):
        """Raise PermissionError if authentication or license is missing or expired."""
        if not self._is_authenticated():
            log("[-] Action blocked: Authentication and active license key required!", (255, 100, 100))
            raise PermissionError("Active license key required to perform this action.")

    def _initialize_runtime(self):
        """Initialize managers, settings, and background services.

        Kept separate from the authentication guard so construction always
        leaves the API in a complete, usable state before MainWindow reads it.
        """
        # Boot marker: fires synchronously, before any thread spawns, so a
        # completely quiet startup still leaves at least one line in the
        # deque. Used to prove the console render path is alive when the
        # rest of the boot happens to be uneventful.
        try:
            from src.utils.updater import get_current_version as _fv
            _ver = _fv() or "?"
        except Exception:
            _ver = "?"
        log(f"[+] Vellium Tweaker v{_ver} initialized.", (100, 255, 100))

        # Initialize subsystems with error recovery — UI must always load
        try:
            self.roblox_manager = RobloxManager()
        except Exception as e:
            self.roblox_manager = None
            self._init_error = f"RobloxManager init failed: {e}"
            log(f"[!] {self._init_error}", (255, 100, 100))

        try:
            self.flag_manager = FlagManager()
        except Exception as e:
            self.flag_manager = None
            self._init_error = f"FlagManager init failed: {e}"
            log(f"[!] {self._init_error}", (255, 100, 100))

        try:
            self.preset_manager = PresetManager()
        except Exception as e:
            self.preset_manager = None
            log(f"[!] PresetManager init failed: {e}", (255, 100, 100))

        try:
            self.settings = Config.load_settings()
            # Default history limit: 30
            if 'history_limit' not in self.settings:
                self.settings['history_limit'] = 20
            # Default UI theme: premium
            if 'ui_theme' not in self.settings:
                self.settings['ui_theme'] = 'premium'
        except Exception:
            self.settings = {'auto_apply': False, 'history_limit': 20, 'ui_theme': 'premium'}

        try:
            self.get_content_filter()
        except Exception:
            pass

        from src.utils.platform_support import IS_WINDOWS
        # Offset and internal-address feeds are only used by Windows live
        # memory features. macOS applies FastFlags through JSON only.
        if IS_WINDOWS:
            threading.Thread(target=self._init_offsets, daemon=True).start()

        # Pre-emptive Sync on Startup: Ensure ClientAppSettings.json is ready for browser launches.
        # Skipped when Scheduled Apply is on — writing the JSON would let Roblox
        # read the flags at startup, defeating the requested delay.
        if (self.flag_manager and self.settings.get('auto_apply', False)
                and int(self.settings.get('scheduled_apply_delay', 0) or 0) <= 0):
            threading.Thread(target=self.flag_manager.sync_json_to_roblox, args=(self.roblox_manager,), daemon=True).start()

        # Wire the kill switch: the hotkey loop calls back into the API so the
        # global hotkey runs the exact same orchestration as the UI button.
        if self.flag_manager:
            self.flag_manager._killswitch_handler = self._do_killswitch_toggle
            self.flag_manager.set_killswitch_bind(self.settings.get('killswitch_bind', ''))
            # Restore a persisted "off" state across restarts: keep the watchdog
            # paused so it doesn't re-enforce flags the user paused last session.
            if self.settings.get('killswitch_active', False):
                self.flag_manager.pause_watchdog()

        # Start background monitor thread
        if self.flag_manager and IS_WINDOWS:
            self.flag_manager.start_hotkey_listener(self.roblox_manager)
        # Immediately enforce the idle rule (auto-apply off + Roblox closed =>
        # clean disk) so leftovers from a prior session/crash are gone at launch,
        # not only after the first monitor tick. RUN SYNCHRONOUSLY here (~1 ms
        # I/O check + at most one small file wipe): if the user launches Roblox
        # the same second FFM opens, the async version could lose the race and
        # Roblox would read a stale ClientAppSettings.json — meaning
        # auto-apply=OFF still applied flags on that first launch.
        try:
            self._reconcile_idle_clear()
        except Exception:
            pass
        # Silently unlock FPS via Roblox's GlobalBasicSettings file (best-effort).
        if IS_WINDOWS:
            threading.Thread(target=self._auto_unlock_fps, daemon=True).start()
            threading.Thread(target=self._monitor_loop, daemon=True).start()
            threading.Thread(target=self._update_loop, daemon=True).start()
            threading.Thread(target=self._auto_version_loop, daemon=True).start()

        # Discord Rich Presence (best-effort, graceful)
        try:
            if self.settings.get('discord_rpc_enabled', True):
                self.discord_presence = DiscordPresence(self.settings.get('discord_client_id', '1543317341448704050'))
                self.discord_presence.start()
            else:
                self.discord_presence = DiscordPresence(self.settings.get('discord_client_id', '1543317341448704050'))
        except Exception:
            self.discord_presence = None

    def _update_loop(self):
        """Background thread: Check for updates periodically."""
        while True:
            try:
                has_update, exe_url, remote_version, changelog = check_for_updates()
                if has_update:
                    if exe_url:
                        if self.settings.get('auto_update', False):
                            # Auto mode: download and install silently
                            if perform_silent_update(exe_url, remote_version):
                                self.update_ready = True
                        else:
                            # Manual mode: store update info for the UI
                            self._pending_update = {
                                'version': remote_version,
                                'exe_url': exe_url,
                                'changelog': changelog or ''
                            }
                            log(f"[*] Update v{remote_version} available. Check Settings to install.", (100, 255, 100))
                    else:
                        log(f"[*] Update v{remote_version} is available on GitHub, but the Installer (.exe) is missing from the release assets.", (255, 200, 100))
            except Exception as e:
                log(f"[!] Background update loop error: {e}", (255, 100, 100))
            
            # Sleep for 10 minutes
            time.sleep(600)

    def _init_offsets(self):
        """Background thread: load flag offsets without blocking UI."""
        try:
            if self.flag_manager:
                log("[*] Loading flag offsets...", (100, 255, 255))
                self.flag_manager.load_offsets()
        except Exception as e:
            log(f"[!] Offset loading failed: {e}", (255, 100, 100))
        # Auto-grab the executor's Roblox *internal* function offsets from
        # robloxoffsets.com (separate from the FastFlag offsets above). Best
        # effort — never blocks the UI and never fatal if the network is down.
        try:
            from src.core import internal_offsets
            internal_offsets.update_internal_offsets()
        except Exception as e:
            log(f"[!] Internal offsets auto-grab failed: {e}", (255, 100, 100))

    def _auto_version_once(self):
        """One pass of silent, automatic version management (no UI/prompts):
        keep offsets fresh so the common mismatch (Roblox newer than imtheo's
        offsets) self-heals once the dumper catches up, and register FFM as the
        roblox-player handler when the seize policy allows."""
        from src.core.roblox_manager import RobloxManager
        from src.core import offset_loader
        from src.core.version_changer import bootstrapper, deployment, fastpath

        installed = RobloxManager.get_roblox_version_string()
        no_install = (not installed or installed == 'unknown')
        # Offsets-first self-heal: refresh offsets so live injection recovers
        # automatically once imtheo catches up to the installed build. (Never a
        # download here — the rare "Roblox behind offsets" case stays the manual
        # Fix Roblox button.) Skip when there is no install to compare against.
        if not no_install:
            try:
                offsets_target = offset_loader.fetch_latest_build()
                if offsets_target and installed != offsets_target:
                    offset_loader.reset_cache()
                    if self.flag_manager:
                        self.flag_manager.load_offsets(force_cdn=True)
            except Exception:
                pass
        # Auto-download the latest Roblox build when the installed one is
        # behind. Silent, background. Guardrails:
        #   - Skip when Roblox is running (never yank the process out from
        #     under the user).
        #   - Skip when a fix worker is already in flight (start_roblox_download's
        #     own in-flight guard would refuse anyway, but avoid the log churn).
        #   - Never downgrade (start_roblox_download's decision is upgrade-only).
        # The apply-flow's version-mismatch guard handles the follow-up window
        # where offsets haven't caught up to the freshly-installed build.
        try:
            if self._fix_state != "running":
                _rbx_running = False
                try:
                    _rbx_running = bool(
                        self.roblox_manager
                        and self.roblox_manager.find_roblox_process()
                    )
                except Exception:
                    pass
                if not _rbx_running:
                    _latest = deployment.get_latest_production_guid()
                    if _latest and (no_install or installed != _latest):
                        log(
                            f"[*] Auto-updating Roblox to latest ({_latest[:16]}…)",
                            (100, 200, 255),
                        )
                        # start_roblox_download re-verifies the running/latest
                        # state itself and spawns its own daemon thread.
                        self.start_roblox_download()
                    elif _latest:
                        # Already on production, but leftover version folders
                        # can still be launched. Clear them while Roblox is closed.
                        try:
                            if not RobloxManager.is_roblox_running():
                                from src.core.version_changer import fixer as _fixer
                                _fixer.prune_stock_non_production(_latest)
                        except Exception:
                            pass
        except Exception as _auto_dl_exc:
            log(
                f"[!] Auto-update skipped ({type(_auto_dl_exc).__name__})",
                (255, 200, 100),
            )
        # B1-fast: keep the join fast-path cache warm so the (separate) protocol
        # handler can skip its pre-launch network checks when we're already on the
        # latest production build. Best-effort; never blocks anything.
        try:
            latest = deployment.get_latest_production_guid()
            if latest and not no_install:
                fastpath.write_known_good(installed, latest)
        except Exception:
            pass
        # Heal a corrupt roblox-player scheme regardless of Automatic Launch: a
        # command with no "URL Protocol" marker makes the browser silently ignore
        # Play. repair_scheme() rewrites only the base marker values, leaving the
        # current handler (stock or FFM) in place, so it does NOT seize anything.
        try:
            bootstrapper.repair_scheme()
        except Exception:
            pass
        # Auto-register as the Roblox launcher ONLY when the user opted in via the
        # Automatic Launch setting. Default off => FFM never seizes the Play
        # handler on its own (it opens only when the user opens it). When on, this
        # is idempotent and enable_bootstrapper still applies its seize policy.
        try:
            if (self.settings.get('auto_launch_enabled', False)
                    and bootstrapper.current_handler_class() != 'ffm'):
                self.enable_bootstrapper()
        except Exception:
            pass
        # Reciprocal: if Automatic Launch is OFF but the registry STILL points
        # at FFM (user toggled off in a previous session but the restore didn't
        # persist, or settings.json was edited by hand), hand the handler back
        # NOW so Play launches Roblox directly and doesn't reopen FFM. Without
        # this the two states drift and clicking Play looks like it "opens FFM
        # only" (Roblox spawns but exits fast; the user only sees FFM).
        try:
            if (not self.settings.get('auto_launch_enabled', False)
                    and bootstrapper.current_handler_class() == 'ffm'):
                backup = self.settings.get('_rbx_handler_backup')
                if not backup:
                    # No backup on disk: don't call restore(None) — that
                    # deletes every Roblox scheme key, wiping the Play
                    # handler entirely (browser Play clicks then no-op
                    # until Roblox re-registers on its next direct
                    # launch). Instead, leave the scheme alone; Roblox's
                    # own launcher will overwrite our command on its
                    # next update or Play click.
                    return
                bootstrapper.restore(backup)
                self.settings['_rbx_handler_backup'] = None
                self.settings['roblox_fix_mode'] = 'launch_only'
                Config.save_settings(self.settings)
                log("[*] Auto-restored Roblox launcher (Automatic Launch is off)",
                    (100, 255, 255))
        except Exception:
            pass

    def _auto_version_loop(self):
        """Background: periodically self-heal version mismatches and keep FFM
        registered as the handler. Fully silent — no prompts, no UI."""
        import time as _t
        _t.sleep(10)  # let the initial offset load finish first
        while True:
            try:
                self._auto_version_once()
            except Exception as e:
                log(f"[!] Auto version manage error: {e}", (255, 180, 100))
            _t.sleep(300)  # re-check every 5 minutes

    def get_loading_status(self):
        """Return loading state for the frontend."""
        if not self.flag_manager:
            return {'ready': False, 'error': self._init_error or 'FlagManager not available'}
        offset_source = None
        baseline_stale = False
        offsets_version = None
        try:
            from src.core import offset_loader
            offset_source = offset_loader.last_source_id()
            baseline_stale = offset_loader.is_baseline_stale()
            offsets_version = offset_loader.last_source_build()
        except Exception:
            pass
        # Installed Roblox build string (version-xxxx) for the top-bar
        # version indicator. None when no Roblox install is detected.
        roblox_version = None
        try:
            from src.core.roblox_manager import RobloxManager
            rv = RobloxManager.get_roblox_version_string()
            if rv and rv != 'unknown':
                roblox_version = rv
        except Exception:
            pass
        # Honest version verdict: a real mismatch is the installed build
        # differing from the build the loaded offsets target — NOT just the
        # narrow bundled-baseline-stale case. Drives the version indicator.
        version_mismatch = False
        try:
            from src.core.version_changer import fixer
            version_mismatch = fixer.is_version_mismatch(roblox_version, offsets_version)
        except Exception:
            version_mismatch = baseline_stale
        # Do we honestly know what build the offsets target? Startup used to
        # leave this None (only apply/attach populated it) and the frontend
        # then declared "matches" from nothing. Now the loader seeds it from
        # the same body it parsed for the preset list, so this is a genuine
        # "we have an answer" signal — not just "flag list finished loading".
        offsets_ready = bool(offsets_version)

        # Roblox CDN's LATEST production build — the truth for "what should
        # the user be on". None when the CDN was unreachable this tick;
        # the frontend treats None as "unknown", not as "everything's fine".
        latest_production = None
        try:
            from src.core.version_changer import deployment
            _lp = deployment.get_latest_production_guid()
            if _lp:
                latest_production = _lp
        except Exception:
            pass

        # Two orthogonal informational signals for the six-row version card:
        #   roblox_is_latest — installed matches Roblox's latest production
        #   offsets_current  — the loaded offset dump targets that same
        #                      latest build (feed has caught up to Roblox)
        # Either False alone is a soft-warn (JSON still applies; live memory
        # gated by apply_flags_hybrid).
        roblox_is_latest = bool(
            roblox_version and latest_production
            and roblox_version == latest_production
        )
        offsets_current = bool(
            offsets_version and latest_production
            and offsets_version == latest_production
        )

        # Source health: True when the winning offset source is imtheo's
        # primary (dev or stable) OR our GitHub-hosted imtheo mirror.
        # Any other value means FFM had to fall through to a non-imtheo tier,
        # which is informational for the source row.
        source_healthy = bool(
            offset_source and (
                offset_source.startswith("imtheo_")
                or offset_source.startswith("mirror_imtheo_")
            )
        )

        version_card = "offsets_pending"
        try:
            from src.core.version_changer import fixer as _fixer_card
            version_card = _fixer_card.classify_version_card(
                roblox_version, offsets_version, latest_production)
        except Exception:
            if not roblox_version:
                version_card = "no_roblox"
            elif version_mismatch:
                version_card = "needs_roblox_update"
            else:
                version_card = "aligned"

        return {
            'ready': self.flag_manager.offsets_loaded,
            'loading': self.flag_manager.offsets_loading,
            'count': len(self.flag_manager.preset_flags_list),
            'error': self._init_error,
            'update_ready': getattr(self, 'update_ready', False),
            'pending_update': True if getattr(self, '_pending_update', None) else False,
            'version': get_current_version(),
            'offset_source': offset_source,
            'baseline_stale': baseline_stale,
            'version_mismatch': version_mismatch,
            'roblox_version': roblox_version,
            'offsets_version': offsets_version,
            'offsets_ready': offsets_ready,
            'latest_production': latest_production,
            'roblox_is_latest': roblox_is_latest,
            'offsets_current': offsets_current,
            'source_healthy': source_healthy,
            'version_card': version_card,
        }

    def start_roblox_fix(self):
        """Phase 1 offsets-first 'Fix Roblox'. Force a fresh network offsets
        probe and report whether it resolves the version mismatch. Downloading a
        matching Roblox build arrives in a later phase.

        Returns: {'state': <str>, 'message': <str>, 'installed': <str|None>,
                  'upstream': <str|None>}
        """
        from src.core.roblox_manager import RobloxManager
        from src.core import offset_loader
        from src.core.version_changer import fixer

        # Gate: require Roblox closed so a follow-up relaunch picks up fresh offsets.
        try:
            if self.roblox_manager and self.roblox_manager.find_roblox_process():
                return {'state': 'roblox_running', 'installed': None, 'upstream': None,
                        'message': 'Please close Roblox, then try Fix Roblox again.'}
        except Exception:
            pass

        installed = RobloxManager.get_roblox_version_string()
        upstream = offset_loader.fetch_latest_build()
        state = fixer.decide_fix_action(installed, upstream)

        if state == 'resolved':
            # Upstream caught up. Drop the cache so the next attach reloads the
            # now-matching offsets.
            try:
                offset_loader.reset_cache()
                if self.flag_manager:
                    self.flag_manager.load_offsets(force_cdn=True)
                message = ('Offsets updated to match your Roblox build. '
                           'Launch Roblox to apply flags.')
            except Exception as e:
                # Don't claim success if the reload actually failed.
                log(f"[!] Fix Roblox: offset reload failed after refresh: {e}",
                    (255, 120, 120))
                state = 'refresh_failed'
                message = ('Found matching offsets but could not reload them. '
                           'Please try again.')
        elif state == 'needs_download':
            message = ('Your Roblox build needs a matching download. '
                       'This arrives in an upcoming update.')
        elif state == 'refresh_failed':
            message = 'Could not reach the offset servers. Check your connection.'
        else:  # no_roblox
            message = 'No Roblox installation was detected.'

        log(f"[*] Fix Roblox: state={state}, installed={installed}, upstream={upstream}",
            (150, 200, 255))
        return {'state': state, 'message': message,
                'installed': installed, 'upstream': upstream}

    def get_roblox_fix_progress(self):
        """Polled by the Fix Roblox modal."""
        return {"progress": self._fix_progress, "state": self._fix_state,
                "message": self._fix_message}

    def cancel_roblox_fix(self):
        """Request cancellation of an in-flight download."""
        self._fix_cancel = True
        return True

    def start_roblox_download(self):
        """Sync the installed Roblox build to Roblox's LATEST production build.

        Design notes on target choice:
          - Never downgrade. Roblox rejects clients too far behind, so a stale
            offset mirror telling us to install version-XXX from days ago would
            break joining. Fishstrap/Bloxstrap/Froststrap all do the same:
            sync Roblox to Roblox's own truth (the CDN's latest production
            build), never to a third-party's opinion of what the current
            build is.
          - When the resulting installed build doesn't match the loaded
            offsets, the apply-flow guard in `flag_manager.apply_flags_hybrid`
            skips live-memory writes (safe fallback: JSON only), so a
            transient offset-feed lag never crashes injection.

        Returns the initial decision; the modal then polls
        `get_roblox_fix_progress` for the worker's state transitions.
        """
        import threading as _threading
        from src.core.roblox_manager import RobloxManager
        from src.core.version_changer import fixer, deployment
        from src.core import offset_loader

        # Single in-flight guard: don't start a second worker over the same state.
        if self._fix_state == "running":
            return {"state": "already_running",
                    "message": "A Roblox update is already in progress."}

        try:
            if self.roblox_manager and self.roblox_manager.find_roblox_process():
                return {"state": "roblox_running",
                        "message": "Please close Roblox, then try again."}
        except Exception:
            pass

        installed = RobloxManager.get_roblox_version_string()
        latest = deployment.get_latest_production_guid()
        if not latest:
            return {"state": "error",
                    "message": "Could not reach the Roblox version servers. Try again."}
        if installed and installed == latest:
            try:
                fixer.prune_stock_non_production(latest)
            except Exception:
                pass
            return {"state": "already_matching",
                    "message": "Your Roblox build is already up to date. Nothing to do."}

        versions_root = RobloxManager.resolve_download_versions_root()
        if not versions_root:
            return {"state": "error", "message": "No Roblox install directory found."}
        cache_dirs = []
        try:
            cache_dirs = RobloxManager.get_all_roblox_version_dirs() or []
        except Exception:
            pass

        self._fix_progress = 0
        self._fix_state = "running"
        self._fix_message = "Starting download…"
        self._fix_cancel = False
        target_build = latest

        def _worker():
            def _progress(done, total, name):
                self._fix_progress = int((done / total) * 100) if total else 0
                self._fix_message = f"{done}/{total} packages"
            try:
                result = fixer.run_upgrade(target_build, versions_root, cache_dirs,
                                           progress=_progress,
                                           should_cancel=lambda: self._fix_cancel)
                if result.get("ok"):
                    try:
                        fixer.prune_stock_non_production(target_build)
                    except Exception:
                        pass
                    try:
                        if self.flag_manager:
                            offset_loader.reset_cache()
                            self.flag_manager.load_offsets(force_cdn=True)
                    except Exception:
                        pass
                    self._fix_progress = 100
                    self._fix_state = "done"
                    # already_present carries a different message ("That build is
                    # already installed.") than a fresh install ("Roblox build
                    # installed."). Preserve the fixer's message so users see the
                    # right one; fall back to the launch nudge when nothing set.
                    self._fix_message = result.get("message") or "Roblox updated. Launch Roblox to apply flags."
                else:
                    self._fix_progress = -1
                    self._fix_state = "cancelled" if result.get("state") == "cancelled" else "failed"
                    self._fix_message = result.get("message", "Download failed.")
            except Exception as e:
                log(f"[!] Roblox download worker failed: {type(e).__name__}: {e}",
                    (255, 120, 120))
                self._fix_progress = -1
                self._fix_state = "failed"
                self._fix_message = f"Download failed ({type(e).__name__})."
            finally:
                # Never leave the UI / 5-min auto-update stuck on "running".
                if self._fix_state == "running":
                    self._fix_progress = -1
                    self._fix_state = "failed"
                    if not self._fix_message:
                        self._fix_message = "Download failed."

        _threading.Thread(target=_worker, daemon=True).start()
        return {"state": "started",
                "message": "Downloading the latest Roblox build…"}

    # ─── Settings ───

    def get_settings(self):
        # Theme data has its own LocalAppData file. On the first run after this
        # change, migrate any themes previously embedded in settings.json.
        themes = Config.load_themes()
        if themes.get('storage_version') != 1:
            themes = {
                'storage_version': 1,
                'preset': self.settings.get('theme_preset', 'graphite'),
                'colors': self.settings.get('custom_theme_colors', {}),
                'custom_css': self.settings.get('custom_css', ''),
                'background': self.settings.get('theme_background', {'mode': 'none', 'source': '', 'opacity': 35, 'speed': 5}),
                'button_styles': self.settings.get('theme_button_styles', {'global': 'pill', 'primary': 'inherit', 'secondary': 'inherit', 'icon': 'inherit', 'nav': 'inherit'}),
                'categories': self.settings.get('theme_categories', ['Custom']),
                'category_icons': self.settings.get('theme_category_icons', {'Custom': 'brush'}),
                'presets': self.settings.get('theme_library', []),
            }
            Config.save_themes(themes)
        return {
            'auto_apply': self.settings.get('auto_apply', False),
            'theme': self.settings.get('theme', 'dark'),
            'close_to_tray': self.settings.get('close_to_tray', False),
            'disguise_mode': self.settings.get('disguise_mode', False),
            'history_limit': self.settings.get('history_limit', 20),
            'enforcement_mode': self.settings.get('enforcement_mode', 'turbo'),
            'ui_theme': self.settings.get('ui_theme', 'premium'),
            'sidebar_width': self.settings.get('sidebar_width', 240),
            'console_height': self.settings.get('console_height', 180),
            'sidebar_collapsed': self.settings.get('sidebar_collapsed', False),
            'sort_mode': self.settings.get('sort_mode', 'custom'),
            'auto_update': self.settings.get('auto_update', False),
            'promo_dismissed': self.settings.get('promo_dismissed', False),
            'extended_telemetry': self.settings.get('extended_telemetry', True),
            'scheduled_apply_delay': self.settings.get('scheduled_apply_delay', 0),
            'matrix_speed': self.settings.get('matrix_speed', 5),
            'cherry_petals_enabled': self.settings.get('cherry_petals_enabled', True),
            'cherry_petal_speed': self.settings.get('cherry_petal_speed', 5),
            'apply_sound_enabled': self.settings.get('apply_sound_enabled', True),
            'apply_sound_volume': self.settings.get('apply_sound_volume', 100),
            'fps_unlocker_enabled': self.settings.get('fps_unlocker_enabled', True),
            'discord_rpc_enabled': self.settings.get('discord_rpc_enabled', True),
            'discord_client_id': self.settings.get('discord_client_id', '1543317341448704050'),
            'theme_preset': themes.get('preset', 'graphite'),
            'custom_theme_colors': themes.get('colors', {}),
            'custom_css': themes.get('custom_css', ''),
            'theme_background': self._theme_background_for_ui(themes.get('background', {'mode': 'none', 'source': '', 'opacity': 35, 'speed': 5})),
            'theme_button_styles': themes.get('button_styles', {'global': 'pill', 'primary': 'inherit', 'secondary': 'inherit', 'icon': 'inherit', 'nav': 'inherit'}),
            'theme_categories': themes.get('categories', ['Custom']),
            'theme_category_icons': themes.get('category_icons', {'Custom': 'brush'}),
            'theme_library': [{**item, 'background': self._theme_background_for_ui(item.get('background', {}))} for item in themes.get('presets', []) if isinstance(item, dict)],
            # Without this, loadSettings() sees `undefined` for the key and
            # leaves the checkbox at its HTML default (unchecked) — so the
            # Automatic Launch toggle visually reverts every time the app
            # opens, even though the setting is actually persisted.
            'auto_launch_enabled': self.settings.get('auto_launch_enabled', False),
        }

    # Generic setting writer for small, validated UI preferences (theme anim
    # speeds, petal toggle). Allowlisted so the frontend can't write arbitrary
    # keys; each value is coerced/clamped at this boundary.
    _SAVE_SETTING_VALIDATORS = {
        'matrix_speed': lambda v: max(1, min(int(v), 10)),
        'cherry_petal_speed': lambda v: max(1, min(int(v), 10)),
        'cherry_petals_enabled': lambda v: bool(v),
        'apply_sound_enabled': lambda v: bool(v),
        'apply_sound_volume': lambda v: max(0, min(int(v), 100)),
    }

    def save_setting(self, key, value):
        """Persist a single allowlisted UI preference. Ignores unknown keys and
        bad values rather than raising, so a UI glitch can never corrupt config."""
        validator = self._SAVE_SETTING_VALIDATORS.get(key)
        if validator is None:
            return
        try:
            self.settings[key] = validator(value)
        except (ValueError, TypeError):
            return
        Config.save_settings(self.settings)

    def get_telemetry_status(self):
        return self.settings.get('extended_telemetry', True)

    def set_telemetry_status(self, value):
        self.settings['extended_telemetry'] = bool(value)
        Config.save_settings(self.settings)
        log(f"[+] Extended Telemetry: {'ON' if value else 'OFF'}")

    def set_enforcement_mode(self, value):
        """Switch flag enforcement between 'watchdog' (periodic) and 'turbo'
        (tight read-before-write loop). The watchdog loop picks this up on its
        next settings reload (≤60s) — or immediately if it's between flags."""
        mode = 'turbo' if str(value) == 'turbo' else 'watchdog'
        self.settings['enforcement_mode'] = mode
        Config.save_settings(self.settings)
        log(f"[+] Flag enforcement: {'Turbo (instant)' if mode == 'turbo' else 'Watchdog (efficient)'}")

    def set_history_limit(self, value):
        try:
            val = int(value)
            self.settings['history_limit'] = val
            Config.save_settings(self.settings)
            log(f"[+] History limit set to: {'Off' if val <= 0 else val}")
        except Exception:
            pass

    def set_pointer_history_enabled(self, value):
        self.settings['pointer_history_enabled'] = bool(value)
        Config.save_settings(self.settings)
        log(f"[+] Pointer history: {'ON' if value else 'OFF'}")

    def set_pointer_history_count(self, value):
        try:
            val = max(1, min(int(value), 10))
            self.settings['pointer_history_count'] = val
            Config.save_settings(self.settings)
            log(f"[+] Pointer history slots: {val}")
        except Exception:
            pass

    def set_scheduled_apply_delay(self, seconds):
        """B2 Scheduled Apply: 0 = off (instant), else delay memory injection
        N seconds after Roblox is detected. Clamped 0-60."""
        try:
            val = max(0, min(int(seconds), 60))
        except (ValueError, TypeError):
            val = 0
        self.settings['scheduled_apply_delay'] = val
        Config.save_settings(self.settings)
        if val > 0:
            log(f"[+] Scheduled Apply: {val}s delay after Roblox opens")
        else:
            log("[+] Scheduled Apply: off (instant)")
        return val

    def set_auto_apply(self, value):
        self.settings['auto_apply'] = value
        Config.save_settings(self.settings)
        log(f"[+] Auto Apply: {'ON' if value else 'OFF'}")
        # If user turned auto_apply OFF while Roblox isn't running, wipe any
        # leftover flags from disk so the next launch starts clean.
        if not value and self._should_wipe_clientapp():
            rm = getattr(self, 'roblox_manager', None)
            if not rm or not rm.is_attached:
                self.clear_clientapp_json()

    def set_auto_clear_json(self, value):
        self.settings['auto_clear_json'] = value
        Config.save_settings(self.settings)
        log(f"[+] Auto-clear ClientAppSettings: {'ON' if value else 'OFF'}")

    def clear_clientapp_json(self):
        """Wipe ClientAppSettings.json across all Roblox version dirs.

        Caller is responsible for honoring the auto_clear_json setting; this
        method itself always clears so it can also serve as a manual reset.
        """
        if not self.roblox_manager:
            return False
        try:
            ok, msg = self.roblox_manager.clear_fflags_json()
            if ok:
                log(f"[+] {msg}", (180, 220, 180))
            else:
                log(f"[!] Clear ClientAppSettings: {msg}", (255, 200, 100))
            return ok
        except Exception as e:
            log(f"[!] Clear ClientAppSettings failed: {e}", (255, 100, 100))
            return False

    def set_theme(self, theme):
        self.settings['theme'] = theme
        Config.save_settings(self.settings)

    def set_ui_theme(self, theme):
        self.settings['ui_theme'] = theme
        Config.save_settings(self.settings)

    def save_theme_settings(self, preset, colors=None, custom_css='', background=None, button_styles=None):
        """Persist validated local UI theme data and optional user CSS."""
        import re
        allowed_presets = {'graphite', 'violet', 'ocean', 'forest', 'ember', 'custom'}
        preset = str(preset or 'graphite').lower()
        if preset not in allowed_presets:
            preset = 'graphite'
        clean_colors = {}
        if isinstance(colors, dict):
            for key in ('bg', 'panel', 'raised', 'accent', 'text', 'border', 'success', 'warning', 'danger'):
                value = str(colors.get(key, ''))
                if re.fullmatch(r'#[0-9a-fA-F]{6}', value) or (key in {'bg', 'panel', 'raised', 'border'} and value == 'transparent'):
                    clean_colors[key] = value.lower()
        self.settings['theme_preset'] = preset
        self.settings['custom_theme_colors'] = clean_colors
        self.settings['custom_css'] = str(custom_css or '')[:20000]
        allowed_backgrounds = {'none', 'aurora', 'mesh', 'grid', 'stars', 'custom'}
        raw_background = background if isinstance(background, dict) else {}
        clean_background = {
            'mode': str(raw_background.get('mode', 'none')) if str(raw_background.get('mode', 'none')) in allowed_backgrounds else 'none',
            'source': str(raw_background.get('source', ''))[:1000],
            'opacity': max(0, min(int(raw_background.get('opacity', 35)), 100)),
            'speed': max(1, min(int(raw_background.get('speed', 5)), 10)),
        }
        self.settings['theme_background'] = clean_background
        allowed_shapes = {'pill', 'rounded', 'square', 'rectangle'}
        clean_button_styles = {'global': 'pill', 'primary': 'inherit', 'secondary': 'inherit', 'icon': 'inherit', 'nav': 'inherit'}
        if isinstance(button_styles, dict):
            global_shape = str(button_styles.get('global', 'pill'))
            clean_button_styles['global'] = global_shape if global_shape in allowed_shapes else 'pill'
            for key in ('primary', 'secondary', 'icon', 'nav'):
                value = str(button_styles.get(key, 'inherit'))
                clean_button_styles[key] = value if value in allowed_shapes or value == 'inherit' else 'inherit'
        self.settings['theme_button_styles'] = clean_button_styles
        Config.save_settings(self.settings)
        themes = Config.load_themes()
        themes.update({
            'storage_version': 1,
            'preset': preset,
            'colors': clean_colors,
            'custom_css': self.settings['custom_css'],
            'background': clean_background,
            'button_styles': clean_button_styles,
        })
        Config.save_themes(themes)
        return {'ok': True, 'preset': preset, 'colors': clean_colors, 'button_styles': clean_button_styles}

    def _theme_background_for_ui(self, background):
        """Attach a WebView-safe render URL without storing image bytes in config."""
        clean = dict(background) if isinstance(background, dict) else {}
        source = str(clean.get('source', ''))
        if clean.get('mode') != 'custom' or not source:
            return clean
        try:
            import base64
            import mimetypes
            path = self._theme_source_path(source)
            if not path.is_file() or path.stat().st_size > 25 * 1024 * 1024:
                return clean
            mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
            clean['render_source'] = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
        except Exception as exc:
            log(f"[-] Could not prepare theme background: {exc}", (255, 180, 100))
        return clean

    def _theme_source_path(self, source):
        """Resolve new relative theme assets and migrate legacy file URLs safely."""
        from urllib.parse import urlparse, unquote
        source = str(source or '').strip()
        parsed = urlparse(source)
        if parsed.scheme == 'file':
            if parsed.netloc:
                return Path(f"//{parsed.netloc}/{unquote(parsed.path.lstrip('/'))}")
            return Path(unquote(parsed.path.lstrip('/')))
        candidate = Path(source)
        if not candidate.is_absolute():
            candidate = Config.APP_DIR / candidate
        return candidate

    def choose_theme_background(self):
        """Copy a user-selected background into LocalAppData for stable reuse."""
        if not self._window:
            return {'ok': False, 'error': 'Window is not ready'}
        try:
            import shutil
            result = self._window.create_file_dialog(
                dialog_type=10,
                file_types=('Background Images (*.png;*.jpg;*.jpeg;*.webp;*.gif)',),
            )
            if not result:
                return {'ok': False, 'cancelled': True}
            selected = Path(result if isinstance(result, str) else result[0])
            if selected.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
                return {'ok': False, 'error': 'Choose a PNG, JPG, WebP, or GIF image'}
            target_dir = Config.APP_DIR / 'themes'
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f'background{selected.suffix.lower()}'
            shutil.copy2(selected, target)
            relative_source = target.relative_to(Config.APP_DIR).as_posix()
            rendered = self._theme_background_for_ui({'mode': 'custom', 'source': relative_source})
            return {'ok': True, 'source': relative_source, 'render_source': rendered.get('render_source', ''), 'name': selected.name}
        except Exception as exc:
            log(f"[-] Theme background selection failed: {exc}", (255, 100, 100))
            return {'ok': False, 'error': str(exc)}

    def record_ui_crash(self, message, stack=''):
        """Keep a small local UI crash report without terminating the backend."""
        try:
            from datetime import datetime
            path = Config.APP_DIR / 'ui-crash.log'
            entry = f"[{datetime.now().isoformat(timespec='seconds')}] {str(message)[:1000]}\n{str(stack)[:12000]}\n\n"
            with open(path, 'a', encoding='utf-8') as file:
                file.write(entry)
            return {'ok': True}
        except Exception:
            return {'ok': False}

    def save_theme_library(self, categories, presets, category_icons=None):
        """Persist user-created theme categories and palette presets."""
        import re
        clean_categories = []
        if isinstance(categories, list):
            for value in categories[:30]:
                name = str(value).strip()[:40]
                if name and name.lower() not in {'all', 'built-in'} and name.lower() not in {c.lower() for c in clean_categories}:
                    clean_categories.append(name)
        if not clean_categories:
            clean_categories = ['Custom']
        clean_icons = {}
        if isinstance(category_icons, dict):
            for category in clean_categories:
                icon = str(category_icons.get(category, 'brush')).strip()[:32]
                clean_icons[category] = icon if icon.replace('-', '').isalnum() else 'brush'
        else:
            clean_icons = {category: 'brush' for category in clean_categories}
        clean_presets = []
        if isinstance(presets, list):
            for item in presets[:100]:
                if not isinstance(item, dict):
                    continue
                colors = {}
                for key in ('bg', 'panel', 'raised', 'accent', 'text', 'border', 'success', 'warning', 'danger'):
                    value = str((item.get('colors') or {}).get(key, ''))
                    if re.fullmatch(r'#[0-9a-fA-F]{6}', value) or (key in {'bg', 'panel', 'raised', 'border'} and value == 'transparent'):
                        colors[key] = value.lower()
                name = str(item.get('name', '')).strip()[:60]
                category = str(item.get('category', 'Custom')).strip()[:40] or 'Custom'
                if name and all(key in colors for key in ('bg', 'panel', 'raised', 'accent', 'text')):
                    raw_preset_background = item.get('background') if isinstance(item.get('background'), dict) else {}
                    preset_id = str(item.get('id', ''))[:80] or name.lower().replace(' ', '-')
                    preset_source = str(raw_preset_background.get('source', ''))[:1000]
                    if raw_preset_background.get('mode') == 'custom' and preset_source:
                        try:
                            import shutil
                            source_path = self._theme_source_path(preset_source)
                            if source_path.is_file() and source_path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
                                safe_id = re.sub(r'[^a-zA-Z0-9_-]', '-', preset_id)[:64] or 'theme'
                                asset_dir = Config.APP_DIR / 'themes' / 'presets'
                                asset_dir.mkdir(parents=True, exist_ok=True)
                                asset_path = asset_dir / f'{safe_id}{source_path.suffix.lower()}'
                                if source_path.resolve() != asset_path.resolve():
                                    shutil.copy2(source_path, asset_path)
                                preset_source = asset_path.relative_to(Config.APP_DIR).as_posix()
                        except Exception as exc:
                            log(f"[-] Could not preserve preset background: {exc}", (255, 180, 100))
                    preset_background = {
                        'mode': str(raw_preset_background.get('mode', 'none'))[:20],
                        'source': preset_source,
                        'opacity': max(0, min(int(raw_preset_background.get('opacity', 35)), 100)),
                        'speed': max(1, min(int(raw_preset_background.get('speed', 5)), 10)),
                    }
                    clean_presets.append({
                        'id': preset_id,
                        'name': name,
                        'category': category,
                        'colors': colors,
                        'custom_css': str(item.get('custom_css', ''))[:20000],
                        'background': preset_background,
                        'button_styles': item.get('button_styles', {'global': 'pill', 'primary': 'inherit', 'secondary': 'inherit', 'icon': 'inherit', 'nav': 'inherit'}) if isinstance(item.get('button_styles'), dict) else {'global': 'pill', 'primary': 'inherit', 'secondary': 'inherit', 'icon': 'inherit', 'nav': 'inherit'},
                    })
        self.settings['theme_categories'] = clean_categories
        self.settings['theme_library'] = clean_presets
        self.settings['theme_category_icons'] = clean_icons
        Config.save_settings(self.settings)
        themes = Config.load_themes()
        themes.update({'storage_version': 1, 'categories': clean_categories, 'category_icons': clean_icons, 'presets': clean_presets})
        Config.save_themes(themes)
        ui_presets = [{**item, 'background': self._theme_background_for_ui(item.get('background', {}))} for item in clean_presets]
        return {'ok': True, 'categories': clean_categories, 'category_icons': clean_icons, 'presets': ui_presets}

    def set_close_to_tray(self, value):
        self.settings['close_to_tray'] = value
        Config.save_settings(self.settings)
        log(f"[+] Close to tray: {'ON' if value else 'OFF'}")

    def set_disguise_mode(self, value):
        """Persist privacy mode and update the native window caption."""
        enabled = bool(value)
        self.settings['disguise_mode'] = enabled
        Config.save_settings(self.settings)
        if self._window:
            try:
                self._window.title = 'Spotify' if enabled else 'Vellium Tweaker'
            except Exception:
                pass
        log(f"[+] Disguise mode: {'ON' if enabled else 'OFF'}")
        return {'ok': True, 'enabled': enabled}

    def set_discord_rpc(self, value):
        """Persist Discord RPC toggle and dynamically start or stop presence."""
        enabled = bool(value)
        self.settings['discord_rpc_enabled'] = enabled
        Config.save_settings(self.settings)
        if enabled:
            if not getattr(self, 'discord_presence', None):
                self.discord_presence = DiscordPresence(self.settings.get('discord_client_id', '1543317341448704050'))
            self.discord_presence.start()
        else:
            if getattr(self, 'discord_presence', None):
                self.discord_presence.stop()
        log(f"[+] Discord Rich Presence: {'ON' if enabled else 'OFF'}")
        return {'ok': True, 'enabled': enabled}

    def set_save_workspace_state(self, value):
        """Toggle workspace persistence across launches."""
        enabled = bool(value)
        self.settings['save_workspace_state'] = enabled
        Config.save_settings(self.settings)
        if not enabled:
            if self.flag_manager:
                with self.flag_manager._lock:
                    self.flag_manager.user_flags.clear()
                self.flag_manager.save_user_flags()
            log("[*] Workspace persistence disabled — cleared active workspace.")
        else:
            log("[+] Workspace persistence enabled.")
        if self._window:
            try:
                self._window.evaluate_js("if (typeof refreshConfig === 'function') refreshConfig();")
            except Exception:
                pass
        return {'ok': True, 'enabled': enabled}

    def set_sort_mode(self, mode):
        self.settings['sort_mode'] = mode
        Config.save_settings(self.settings)
        log(f"[+] Sort Mode: {mode}")

    def set_auto_update(self, value):
        self.settings['auto_update'] = value
        Config.save_settings(self.settings)
        log(f"[+] Auto Update: {'ON' if value else 'OFF'}")

    def set_roblox_fix_mode(self, mode):
        """Persist the Fix Roblox mode ('launch_only' | 'bootstrapper')."""
        mode = mode if mode in ("launch_only", "bootstrapper") else "launch_only"
        self.settings['roblox_fix_mode'] = mode
        Config.save_settings(self.settings)
        log(f"[+] Roblox fix mode: {mode}")
        return mode

    def enable_bootstrapper(self):
        """Register FFM as the roblox-player handler (persistent), subject to the
        seize policy: only take over a third-party handler when there is a fixable
        version mismatch. Persists the backed-up handler for later restore."""
        import sys as _sys
        import os as _os
        from src.core.roblox_manager import RobloxManager
        from src.core.version_changer import bootstrapper, deployment

        installed = RobloxManager.get_roblox_version_string()
        latest = deployment.get_latest_production_guid()
        # Fixable = we know Roblox's latest production build AND the installed
        # Roblox is on a DIFFERENT build. Downloading always targets `latest`
        # (never the offset dump's opinion — that would risk downgrading to a
        # build Roblox servers no longer accept). The apply-flow guard in
        # flag_manager.apply_flags_hybrid handles the follow-up case where
        # offsets don't yet match the freshly-installed build.
        fixable = bool(latest and installed and installed != latest)
        handler_class = bootstrapper.current_handler_class()
        if not bootstrapper.should_seize(handler_class, fixable):
            if handler_class == "ffm":
                self.settings['roblox_fix_mode'] = 'bootstrapper'
                Config.save_settings(self.settings)
                return {"state": "enabled", "message": "FFM is already the handler."}
            return {"state": "conflict_no_fix",
                    "message": "Another launcher is active and your Roblox version "
                               "is fine — FFM won't take over right now."}
        # Single-exe / two-modes (Froststrap model): register FFM itself as the
        # handler with the --roblox-handler arg. main.pyw dispatches that arg early
        # into the lightweight bootstrap path (apply flags + launch + exit) BEFORE
        # opening any window, so Play never pops the full app.
        #   Frozen: sys.executable IS FFM.exe (no separate script).
        #   Source: sys.executable is the Python interpreter, so include main.pyw.
        _script = None if getattr(_sys, 'frozen', False) else _os.path.abspath(_sys.argv[0])
        backup = bootstrapper.register(_sys.executable, script=_script)
        self.settings['_rbx_handler_backup'] = backup
        self.settings['roblox_fix_mode'] = 'bootstrapper'
        Config.save_settings(self.settings)
        return {"state": "enabled",
                "message": "FFM will now handle Roblox launches."}

    def disable_bootstrapper(self):
        """Restore the previous roblox-player handler and revert to launch-only.

        Preserves `_rbx_handler_backup` on failure so a retry is possible.
        Previous behavior cleared the backup unconditionally, which meant a
        transient registry-write failure permanently orphaned the OS-default
        handler and reported success anyway."""
        from src.core.version_changer import bootstrapper
        try:
            bootstrapper.restore(self.settings.get('_rbx_handler_backup'))
        except Exception as e:
            log(f"[!] Handler restore failed: {e}", (255, 120, 120))
            # Keep the backup so a subsequent disable can retry. Do NOT
            # flip `roblox_fix_mode` to launch_only — the registry still
            # points at FFM, so the fix-mode label would lie.
            return {"state": "error",
                    "message": f"Could not restore Roblox launcher: {e}. "
                               f"Try again or run FFM as administrator."}
        self.settings['_rbx_handler_backup'] = None
        self.settings['roblox_fix_mode'] = 'launch_only'
        Config.save_settings(self.settings)
        return {"state": "disabled", "message": "Reverted to launch-only mode."}

    def get_auto_launch(self):
        """Whether FFM is allowed to register itself as the Play handler."""
        return bool(self.settings.get('auto_launch_enabled', False))

    def set_auto_launch(self, enabled):
        """Toggle Automatic Launch. On => register FFM as the roblox-player
        handler now (and the background loop keeps it healed). Off => stop
        seizing and restore the previous handler immediately so Play launches
        Roblox directly again."""
        enabled = bool(enabled)
        self.settings['auto_launch_enabled'] = enabled
        Config.save_settings(self.settings)
        try:
            if enabled:
                result = self.enable_bootstrapper()
            else:
                result = self.disable_bootstrapper()
        except Exception as e:
            log(f"[!] Auto-launch toggle failed: {e}", (255, 120, 120))
            result = {"state": "error", "message": str(e)}
        return {"enabled": enabled, **result}

    def set_promo_dismissed(self, value):
        self.settings['promo_dismissed'] = bool(value)
        Config.save_settings(self.settings)

    def get_content_filter(self):
        """Called by the UI shim to determine render state."""
        try:
            if not _helpers_module._is_frozen():
                return self.settings.get('ads_enabled', True)
            _helpers_module._rot_observed()
            if _cfg_module.Config.verify_settings_integrity():
                _helpers_module._rot_subtract(419)
                return self.settings.get('ads_enabled', True)
            # HMAC mismatch — force True and skip subtract.
            return True
        finally:
            _helpers_module._persistence_observer_check()

    def report_hmac_health(self, ok):
        """Bridge kept for schema stability with any UI still calling it.
        v4.0.5: the visibility heartbeat was retired; the response is always
        the neutral shape below and no session state is mutated."""
        return {'tripped': False}

    def report_slot_diagnostic(self, payload):
        """Bridge kept for schema stability. v4.0.5: no console output; the
        return contract (dict payload -> {'ok': True}, anything else ->
        {'ok': False}) is preserved for existing callers and tests."""
        if not isinstance(payload, dict):
            return {'ok': False}
        return {'ok': True}

    def probe_ads_endpoint(self):
        """Bridge kept for schema stability. v4.0.5: no network probe is
        fired and nothing is logged; the response shape matches the prior
        successful-scheduling reply for callers that read `ok`."""
        return {'ok': True, 'message': 'probe scheduled'}

    def get_update_info(self):
        """Return pending update info for the frontend."""
        if self._pending_update:
            return {
                'available': True,
                'version': self._pending_update['version'],
                'changelog': self._pending_update['changelog'],
                'current': get_current_version()
            }
        return {
            'available': False,
            'current': get_current_version()
        }

    def get_update_progress(self):
        """Return download progress (0-100) for the frontend overlay."""
        return self._update_progress

    def trigger_manual_update(self):
        """User clicked 'Update Now'. Download with progress in a background thread."""
        if not self._pending_update:
            return False

        def do_download():
            info = self._pending_update
            def on_progress(downloaded, total):
                self._update_progress = int((downloaded / total) * 100)

            success = download_update(info['exe_url'], info['version'], progress_callback=on_progress)
            if success:
                self._update_progress = 100
                os._exit(0)
            else:
                self._update_progress = -1  # Signal failure

        self._update_progress = 0
        threading.Thread(target=do_download, daemon=True).start()
        return True

    def open_url(self, url):
        """Open a URL in the default system browser."""
        import webbrowser
        try:
            webbrowser.open(url)
            log(f"[*] Opening URL: {url}")
        except Exception as e:
            log(f"[!] Failed to open URL: {e}", (255, 100, 100))

    def open_presets_folder(self):
        """Reveal presets.json in File Explorer.

        Opens the folder containing presets.json with the file pre-selected so
        the user can find it at a glance. Falls back to just opening the folder
        if the file doesn't exist yet.
        """
        import subprocess
        try:
            presets_path = Config.PRESETS_FILE
            app_dir = Config.APP_DIR
            app_dir.mkdir(parents=True, exist_ok=True)
            if presets_path.exists():
                # /select highlights the file in the opened folder.
                subprocess.Popen(
                    ["explorer.exe", "/select,", str(presets_path)],
                    close_fds=True,
                )
                log(f"[*] Revealed presets.json at {presets_path}")
            else:
                subprocess.Popen(
                    ["explorer.exe", str(app_dir)],
                    close_fds=True,
                )
                log(f"[*] Opened presets folder at {app_dir} (presets.json not created yet)")
            return {"ok": True}
        except Exception as e:
            log(f"[!] Failed to open presets folder: {e}", (255, 100, 100))
            return {"ok": False, "error": str(e)}

    # ─── Available Flags ───
    
    def _refresh_search_cache(self, search_term):
        """Unified method to refresh the search cache."""
        _r4_maybe_freeze()
        if _r3_should_skip():
            self._last_refresh = _time_rot.time()
            return
        search_lower = search_term.lower()
        combined_list = self.flag_manager.preset_flags_list
        src_len = len(combined_list) if combined_list is not None else 0

        # Same term AND same source length: reuse. An empty first paint
        # (offsets still loading) must not pin a zero-length cache once
        # preset_flags_list is later populated.
        if (hasattr(self, '_search_cache')
                and hasattr(self, '_search_cache_term')
                and self._search_cache_term == search_lower
                and getattr(self, '_search_cache_src_len', None) == src_len):
            return

        if not search_lower:
            self._search_cache = combined_list
        else:
            # Command-palette search: direct matches first, then related names
            # ranked by similarity. This helps users discover companion flags
            # without requiring an exact internal Roblox identifier.
            import re
            from difflib import SequenceMatcher
            from src.utils.helpers import clean_flag_name
            query = re.sub(r'[^a-z0-9]+', '', search_lower)
            ranked = []
            for name in combined_list:
                full = name.lower()
                clean = clean_flag_name(name).lower()
                compact = re.sub(r'[^a-z0-9]+', '', clean)
                direct = search_lower in full or search_lower in clean or (query and query in compact)
                similarity = SequenceMatcher(None, query, compact).ratio() if query else 0.0
                if direct or similarity >= 0.34:
                    ranked.append((0 if direct else 1, -similarity, len(name), name))
            ranked.sort()
            self._search_cache = [item[3] for item in ranked]

        self._search_cache_term = search_lower
        self._search_cache_src_len = src_len

    def get_fflag_count(self, search='') -> int:
        """Get total number of discovered flags, optionally filtered by search."""
        if not self.flag_manager:
            return 0
            
        self._refresh_search_cache(search)
        return len(self._search_cache)

    def get_available_flags(self, search='', offset=0, limit=300):
        """Return filtered list of available flags with pagination from cache."""
        _shard_s5_check()
        if not self.flag_manager:
            return []
            
        search_lower = search.lower()
        
        self._refresh_search_cache(search)
        
        source_list = self._search_cache
        user_flags_dict = {f['name']: f.get('type', 'unknown') for f in self.flag_manager.user_flags}
        
        results = []
        # Slice the cache for the requested range
        chunk = source_list[offset : offset + limit]
        
        for name in chunk:
            # Priority: 1. Official Scanner Type, 2. Prefix Guess, 3. Value Guess (from added list)
            expected = self.flag_manager.official_types.get(name) or \
                       infer_type_from_name(name) or \
                       user_flags_dict.get(name) or \
                       'unknown'

            prefix = get_flag_prefix(name)
            results.append({
                'name': name,
                'added': name in user_flags_dict,
                'expected_type': expected,
                'prefix': prefix,
                'match_kind': 'direct' if (not search_lower or search_lower in name.lower() or search_lower in clean_flag_name(name).lower()) else 'related'
            })
        return results

    # ─── User Flags ───

    def get_user_flags(self):
        """Return list of user's configured flags."""
        if not self.flag_manager:
            return []

        preset_set = set(self.flag_manager.preset_flags_list)
        # Pre-calculate clean names for faster lookup
        clean_presets = {clean_flag_name(p): p for p in self.flag_manager.preset_flags_list}

        return [{
            'name': f['name'],
            'display_name': clean_flag_name(f['name']),
            'value': str(f.get('value', '')),
            'type': f.get('type', 'string'),
            'status': f.get('_status', None),
            'is_unrecognized': f['name'] not in preset_set 
                               and clean_flag_name(f['name']) not in clean_presets,
            'is_known': f['name'] in preset_set or clean_flag_name(f['name']) in clean_presets,
            'enabled': f.get('enabled', True),            'bind': f.get('bind', ''),
            'unapply_bind': f.get('unapply_bind', ''),
            'cycle_states': f.get('cycle_states', []),
            'prefix': self.flag_manager.official_prefixes.get(f['name'], '') or get_flag_prefix(f['name'])
        } for f in self.flag_manager.user_flags]

    def validate_flag_value(self, name, value):
        """Validate a value against the expected type from the flag's Roblox prefix."""
        expected = infer_type_from_name(name)
        if not expected or expected == 'string':
            return True, None  # Strings accept everything
            
        val_str = str(value).strip().lower()
        
        if expected == 'bool':
            if val_str not in ('true', 'false'):
                return False, f"\u274c {name} is a BOOL flag \u2014 value must be 'true' or 'false', got '{value}'"
            return True, None
            
        if expected == 'int':
            try:
                int(val_str)
                return True, None
            except ValueError:
                return False, f"\u274c {name} is an INT flag — value must be a whole number, got '{value}'"
        
        return True, None

    def add_flag(self, name, value):
        """Add a flag to user configuration with type validation."""
        if not self.flag_manager:
            return {'ok': False, 'error': 'Not ready'}
        
        # We store the name EXACTLY as provided to preserve prefixes required for JSON/Memory.
        # Duplicate checking is done using normalized (cleaned) names.
        name = strip_bogus_dflag_prefix(name)
        clean_new = clean_flag_name(name)

        # Ensure flag exists in database
        is_known_checker = getattr(self.flag_manager, 'is_known_flag', None)
        if is_known_checker and not is_known_checker(name):
            log(f"[-] Invalid FastFlag '{name}': not found in database", (255, 100, 100))
            return {'ok': False, 'error': f'Invalid FastFlag: "{name}" was not found in the database.'}

        with self.flag_manager._lock:
            if any(clean_flag_name(f['name']) == clean_new for f in self.flag_manager.user_flags):
                log(f"[-] Flag already added: {name}", (255, 176, 32))
                return {'ok': False, 'error': f'{name} (or a variant) is already in your configuration'}
        
        # Validate value against expected type (uses full name if possible)
        ok, err = self.validate_flag_value(name, value)
        if not ok:
            log(f"[-] {err}", (255, 100, 100))
            return {'ok': False, 'error': err}
            
        # Priority: 1. Official Scanner Type, 2. Prefix Guess, 3. Value Guess.
        # The offset dump stores names prefix-less, so official type is often
        # 'unknown' — treat that as no-answer so we fall back to the value
        # (e.g. 1000 -> int) instead of storing an unusable 'unknown' type.
        official = self.flag_manager.official_types.get(name)
        flag_type = (official if official and official != 'unknown' else None) or \
                    infer_type_from_name(name) or \
                    infer_type(value)
        self.flag_manager.save_history_snapshot(f"Before adding {name}", self.settings.get('history_limit', 20))
        
        new_flag = {
            'name': name,
            'value': str(value),
            'type': flag_type,
            'enabled': True
        }
        
        # Proactive Original Value Capture (best-effort — must NEVER block adding
        # a flag). get_live_flag_address returns a LIST of address entries, so we
        # index [0] like every other caller; wrapped in try/except so any hiccup
        # here can't silently fail the add (previously a list-vs-dict TypeError
        # broke adds whenever Roblox was attached).
        if self.roblox_manager and self.roblox_manager.is_attached:
            try:
                addr_data = self.roblox_manager.get_live_flag_address(name)
                if addr_data:
                    live_type = flag_type if flag_type != 'unknown' else addr_data[0].get('type', 'unknown')
                    orig = self.roblox_manager.read_flag_at_address(live_type, addr_data[0]['abs_addr'])
                    if orig is not None:
                        new_flag['original_value'] = orig
                        log(f"[*] Captured original value for {name}: {orig}")
            except Exception as e:
                log(f"[!] Original-value capture skipped for {name}: {e}", (255, 200, 100))
        
        if 'original_value' not in new_flag:
            new_flag['original_value'] = get_default_value(name)

        with self.flag_manager._lock:
            self.flag_manager.user_flags.append(new_flag)
            
        self.flag_manager.save_user_flags()
        log(f"[+] Added {name} (type: {flag_type})")
        if self.settings.get('auto_apply'): self.inject()
        return {'ok': True}

    def import_flags_from_text(self, text):
        """Import flags from a pasted text payload. Accepts every export
        format EXCEPT plain text KEY=VALUE:
        - JSON list of flag dicts
        - JSON dict {flagName: value, ...}  (Bloxstrap-style)
        - JSON preset {name, flags: [...]}
        - Base64+zlib compressed preset payload

        Returns {ok, added, skipped, error}.
        """
        if not self.flag_manager:
            return {'ok': False, 'error': 'Not ready'}
        try:
            _, parsed_flags = _parse_preset_payload(
                text, source_name='Pasted Import', allow_plain_text=False,
            )
        except ValueError as ve:
            log(f"[-] Import error: {ve}", (255, 85, 85))
            return {'ok': False, 'error': str(ve)}
        except Exception as e:
            log(f"[-] Import error: {e}", (255, 85, 85))
            return {'ok': False, 'error': str(e)}

        self.flag_manager.save_history_snapshot(
            "Before import", self.settings.get('history_limit', 20),
        )
        added = 0
        skipped = 0
        bind_keys = ('bind', 'unapply_bind', 'cycle_states')
        with self.flag_manager._lock:
            for item in parsed_flags:
                if not isinstance(item, dict):
                    continue
                name = strip_bogus_dflag_prefix(item.get('name'))
                val = item.get('value')
                if not name or val is None:
                    continue
                if any(f['name'] == name for f in self.flag_manager.user_flags):
                    skipped += 1
                    continue
                flag_type = (
                    item.get('type')
                    or infer_type_from_name(name)
                    or infer_type(str(val))
                )
                new_flag = {
                    'name': name,
                    'value': str(val),
                    'type': flag_type,
                    'enabled': item.get('enabled', True),
                    'original_value': get_default_value(name),
                }
                for bk in bind_keys:
                    if bk in item:
                        new_flag[bk] = item[bk]
                self.flag_manager.user_flags.append(new_flag)
                added += 1

        with self.flag_manager._lock:
            self.flag_manager.user_flags, _ = heal_dflag_flag_names(
                self.flag_manager.user_flags)
        self.flag_manager.save_user_flags()
        log(f"[+] Imported {added} flags ({skipped} duplicates skipped)")
        if self.settings.get('auto_apply') and added > 0:
            self.inject()
        return {'ok': True, 'added': added, 'skipped': skipped}

    def batch_add_flags(self, flags_list):
        """Add multiple flags at once. flags_list: [{'name': '...', 'value': '...'}, ...]"""
        if not self.flag_manager:
            return {'ok': False, 'error': 'Not ready'}
        
        self.flag_manager.save_history_snapshot(f"Before batch add ({len(flags_list)} flags)", self.settings.get('history_limit', 20))
        
        added = 0
        skipped = 0
        errors = []
        
        with self.flag_manager._lock:
            for item in flags_list:
                name = strip_bogus_dflag_prefix(item.get('name'))
                val = item.get('value')
                if not name or val is None:
                    continue
                
                clean_new = clean_flag_name(name)
                # Check for duplicates using cleaned names
                if any(clean_flag_name(f['name']) == clean_new for f in self.flag_manager.user_flags):
                    skipped += 1
                    continue
                
                # Validate value
                ok, err = self.validate_flag_value(name, val)
                if not ok:
                    errors.append(f"{name}: {err}")
                    continue
                
                flag_type = infer_type_from_name(name) or infer_type(str(val))
                self.flag_manager.user_flags.append({
                    'name': name,
                    'value': str(val),
                    'type': flag_type,
                    'enabled': True,
                    'original_value': get_default_value(name)
                })
                added += 1
                
        with self.flag_manager._lock:
            self.flag_manager.user_flags, _ = heal_dflag_flag_names(
                self.flag_manager.user_flags)
        self.flag_manager.save_user_flags()
        log(f"[+] Batch Import: {added} added, {skipped} skipped, {len(errors)} errors")
        if self.settings.get('auto_apply') and added > 0: self.inject()
        return {'ok': True, 'added': added, 'skipped': skipped, 'errors': errors}

    def set_flag_bind(self, name, key):
        """Set a hotkey bind for a specific flag."""
        if not self.flag_manager:
            return {'ok': False, 'error': 'Not ready'}
        
        target = None
        for flag in self.flag_manager.user_flags:
            if flag['name'] == name:
                target = flag
                break
                
        if not target:
            return {'ok': False, 'error': f'{name} not found in configuration'}
            
        if key:
            target['bind'] = key
            log(f"[+] Bound {name} to {key}")
        else:
            if 'bind' in target:
                del target['bind']
            log(f"[-] Removed bind for {name}")
            
        self.flag_manager.save_user_flags()
        return {'ok': True}

    def set_advanced_bind(self, name, data):
        """Set advanced bind data (cycle_states, unapply_bind) for a flag."""
        if not self.flag_manager:
            return {'ok': False, 'error': 'Not ready'}
            
        target = None
        for flag in self.flag_manager.user_flags:
            if flag['name'] == name:
                target = flag
                break
                
        if not target:
            return {'ok': False, 'error': f'{name} not found'}
            
        if 'unapply_bind' in data:
            val = data['unapply_bind']
            if val:
                target['unapply_bind'] = val
                log(f"[+] Set un-apply bind for {name}: {val}")
            elif 'unapply_bind' in target:
                del target['unapply_bind']
                log(f"[-] Removed un-apply bind for {name}")
                
        if 'cycle_states' in data:
            target['cycle_states'] = data['cycle_states']
            
        self.flag_manager.save_user_flags()
        return {'ok': True}

    def update_flag(self, name, value):
        """Update a flag's value with type validation."""
        if not self.flag_manager:
            return {'ok': False, 'error': 'Not ready'}
        
        # Find the flag and check its stored type for validation
        target = None
        for flag in self.flag_manager.user_flags:
            if flag['name'] == name:
                target = flag
                break
        if not target:
            return {'ok': False, 'error': f'{name} not found'}
        
        # Reconstruct full name for prefix-based validation
        full_name = None
        if self.flag_manager.preset_flags_list:
            for preset in self.flag_manager.preset_flags_list:
                if clean_flag_name(preset) == name:
                    full_name = preset
                    break
        
        if full_name:
            # Validate using the full prefixed name
            ok, err = self.validate_flag_value(full_name, value)
            if not ok:
                log(f"[-] {err}", (255, 100, 100))
                return {'ok': False, 'error': err}
        else:
            # Fallback: validate using the stored type directly
            stored_type = target.get('type', 'string')
            val_str = str(value).strip().lower()
            if stored_type == 'bool' and val_str not in ('true', 'false'):
                err = f"\u274c {name} is a BOOL flag \u2014 value must be 'true' or 'false', got '{value}'"
                log(f"[-] {err}", (255, 100, 100))
                return {'ok': False, 'error': err}
            if stored_type == 'int':
                try:
                    int(val_str)
                except ValueError:
                    err = f"\u274c {name} is an INT flag \u2014 value must be a whole number, got '{value}'"
                    log(f"[-] {err}", (255, 100, 100))
                    return {'ok': False, 'error': err}
        
        self.flag_manager.save_history_snapshot(f"Before updating {name}", self.settings.get('history_limit', 20))
        
        with self.flag_manager._lock:
            # Find the flag again under lock
            target = None
            for flag in self.flag_manager.user_flags:
                if flag['name'] == name:
                    target = flag
                    break
            
            if not target:
                return {'ok': False, 'error': f'{name} not found'}

            old_value = target.get('value', '')
            target['value'] = value
            # Keep the original prefix-derived type, don't re-guess

        self.flag_manager.save_user_flags()
        # A1: log editor value changes as "old -> new". ASCII arrow only —
        # a Unicode arrow can crash log() on cp125x consoles (e.g. Turkish).
        if str(old_value) != str(value):
            log(f"[*] Editor: {name}  {old_value} -> {value}")
        else:
            # Diagnostic: value matched what was already stored. Shows the
            # stored value + type so we can tell a real no-op from a bug.
            log(f"[*] Editor: {name} set to {value} (was {old_value!r} / {type(old_value).__name__})")
        if self.settings.get('auto_apply'): self.inject()
        return {'ok': True}

    def remove_flags(self, names):
        """Remove flags by name."""
        if not self.flag_manager:
            return {'ok': False, 'error': 'Flag manager not ready'}
        if isinstance(names, str):
            names = [names]
        count = len(names)
        self.flag_manager.save_history_snapshot(f"Before removing {count} flag(s)", self.settings.get('history_limit', 20))
        
        with self.flag_manager._lock:
            self.flag_manager.user_flags = [
                f for f in self.flag_manager.user_flags if f['name'] not in names
            ]
            
        self.flag_manager.save_user_flags()
        log(f"[+] Removed {count} flag(s)")
        if self.settings.get('auto_apply'): self.inject()
        return {'ok': True, 'count': count}

    def remove_flag(self, name):
        """Remove a single flag by name."""
        return self.remove_flags([name])

    def get_flag_type_info(self, name):
        """Return the expected type of a flag based on its Roblox prefix."""
        expected = infer_type_from_name(name)
        prefix = get_flag_prefix(name)
        return {
            'expected_type': expected or 'unknown',
            'prefix': prefix or '?',
            'hint': {
                'bool': 'true or false',
                'int': 'whole number (e.g. 0, 60, 9999)',
                'string': 'text value',
            }.get(expected, 'any value')
        }

    def clear_all(self):
        """Clear all user flags."""
        if not self.flag_manager:
            return
        self.flag_manager.save_history_snapshot("Before clear all", self.settings.get('history_limit', 20))
        with self.flag_manager._lock:
            self.flag_manager.user_flags.clear()
        self.flag_manager.save_user_flags()
        log("[+] Cleared all flags")
        if self.settings.get('auto_apply'): self.inject()
        
    def get_history(self):
        if not self.flag_manager: return []
        return self.flag_manager.get_history()

    def clear_history(self):
        if not self.flag_manager: return False
        return self.flag_manager.clear_history()
        
    def restore_history(self, timestamp):
        if not self.flag_manager: return False
        try:
            ts = int(timestamp)
            success = self.flag_manager.restore_history(ts)
            if success and self.settings.get('auto_apply'):
                self.inject()
            return success
        except Exception:
            return False

    def toggle_flag_apply(self, name):
        """Toggle the enabled state of a specific flag."""
        if not self.flag_manager: return False
        
        with self.flag_manager._lock:
            target = None
            for flag in self.flag_manager.user_flags:
                if flag['name'] == name:
                    target = flag
                    break
            
            if not target: return False
            
            is_enabled = target.get('enabled', True)
            target['enabled'] = not is_enabled
            new_state = target['enabled']
            
            # Clear internal status immediately if disabling
            if new_state == False:
                target['_status'] = None
                
        self.flag_manager.save_user_flags()
        log(f"[*] {name} is now {'ENABLED' if new_state else 'DISABLED'}")
            
        # Only trigger re-injection if Roblox is attached
        if self.settings.get('auto_apply') and self.roblox_manager and self.roblox_manager.is_attached:
            self.inject()
        return True

    def reorder_flags(self, names_list):
        """Reorder user_flags based on the provided list of names."""
        if not self.flag_manager or not names_list: return
        
        with self.flag_manager._lock:
            current_flags = {f['name']: f for f in self.flag_manager.user_flags}
            new_list = []
            
            for name in names_list:
                if name in current_flags:
                    new_list.append(current_flags[name])
                    del current_flags[name]
            
            # Add any remaining flags that weren't in the list
            new_list.extend(current_flags.values())
            
            self.flag_manager.user_flags = new_list
            
        self.flag_manager.save_user_flags()
        log("[+] Custom flag order updated")

    # ─── Actions ───

    def inject_user(self):
        """Manual Apply button entry point — plays the apply chime on success.
        If flags are currently paused (killswitch on), the user's click implies
        they want flags on: delegate to restore_flags() which handles the full
        re-enable + re-apply through the normal path. Kept separate from plain
        inject() so internal callers (edits, presets, re-runs, watchdog) stay
        silent and respect the pause."""
        if self.settings.get('killswitch_active', False):
            log("[*] Flags were paused — resuming and applying...", (100, 200, 255))
            return self.restore_flags()
        return self.inject(play_sound=True)

    def inject(self, skip_json=False, play_sound=False):
        """Apply flags using hybrid method (JSON + live memory).

        skip_json=True does a memory-only injection (used by Scheduled Apply
        so the delay is real and Roblox can't read the flags from JSON at
        startup).
        play_sound=True plays the apply chime in the UI when >=1 flag is
        applied (manual Apply + first auto-apply only; A3).
        """
        if not self.flag_manager or not self.roblox_manager:
            log("[-] Not ready", (255, 100, 100))
            return
        if not self._is_authenticated():
            log("[-] Action blocked: Active Vellium Tweaker license required to apply flags!", (255, 100, 100))
            if self._window:
                self._window.evaluate_js("if (window.dispatchEvent) window.dispatchEvent(new CustomEvent('meowware:require_auth'));")
            return
        # Kill switch active — suppress all (auto-)apply until the user restores.
        if self.settings.get('killswitch_active', False):
            log("[*] Flags are OFF — apply suppressed. Turn flags back on first.", (255, 200, 100))
            return
        if getattr(self, '_is_applying', False):
            # Don't drop this request — a flag added/edited mid-apply would
            # otherwise silently never reach the game. Queue one re-run.
            self._apply_pending = True
            return

        self._is_applying = True
        def do_inject():
            applied_count = 0
            try:
                # Try to attach (not required — JSON works without Roblox running)
                self.roblox_manager.attach()
                if not skip_json:
                    log("[*] Applying flags (hybrid: JSON + live memory)...", (100, 255, 255))
                applied_count = self.flag_manager.apply_flags_hybrid(
                    self.roblox_manager, skip_json=skip_json) or 0
            except Exception as e:
                log(f"[-] CRITICAL CRASH in apply logic: {e}", (255, 50, 50))
                import traceback
                traceback.print_exc()
            finally:
                self._is_applying = False
                if self._window:
                    # Play the apply chime only for sound-triggering applies
                    # (manual / first auto-apply) that actually applied >=1 flag.
                    play_js = (
                        "if (typeof playApplySound === 'function') playApplySound();"
                        if (play_sound and applied_count >= 1) else ""
                    )
                    self._window.evaluate_js("""
                        var btn = document.getElementById('inject-btn');
                        if (btn) {
                            btn.disabled = false;
                            btn.textContent = 'Apply Flags';
                        }
                        if (typeof refreshConfig === 'function') refreshConfig();
                        """ + play_js)
                # If something requested an apply while we were busy, run once
                # more so late edits/adds aren't lost.
                if getattr(self, '_apply_pending', False):
                    self._apply_pending = False
                    self.inject()

        import threading
        threading.Thread(target=do_inject, daemon=True).start()

    def get_launch_targets(self):
        """Return installed Roblox player folders for the launch picker."""
        from src.core.roblox_manager import RobloxManager
        selected = self.settings.get('launch_target_path', '')
        targets = []
        for path in RobloxManager.get_all_roblox_version_dirs():
            normalized = os.path.normcase(os.path.normpath(path))
            lower = normalized.lower()
            launcher = next((name for name in ('Bloxstrap', 'Fishstrap', 'Froststrap', 'Voidstrap', 'Plexity') if f'\\{name.lower()}\\' in lower), 'Roblox')
            exe = next((os.path.join(path, name) for name in ('RobloxPlayerBeta.exe', 'RobloxPlayer.exe') if os.path.isfile(os.path.join(path, name))), '')
            targets.append({
                'path': path,
                'name': os.path.basename(path),
                'launcher': launcher,
                'exe': exe,
                'selected': bool(selected and normalized == os.path.normcase(os.path.normpath(selected))),
            })
        return {'targets': targets, 'selected_path': selected}

    def set_launch_target(self, path=''):
        """Persist a validated player directory selected by the user."""
        from src.core.roblox_manager import RobloxManager
        path = str(path or '').strip()
        valid = {os.path.normcase(os.path.normpath(item)) for item in RobloxManager.get_all_roblox_version_dirs()}
        normalized = os.path.normcase(os.path.normpath(path)) if path else ''
        if normalized and normalized not in valid:
            return {'ok': False, 'error': 'That Roblox installation is no longer available.'}
        self.settings['launch_target_path'] = path if normalized else ''
        Config.save_settings(self.settings)
        return {'ok': True, 'path': self.settings['launch_target_path']}

    def launch_and_apply(self, version_dir=None):
        """Launch Roblox suspended, patch ALL flags before Hyperion, then resume."""
        if not self.flag_manager or not self.roblox_manager:
            log("[-] Not ready", (255, 100, 100))
            return
        if not self._is_authenticated():
            log("[-] Action blocked: Active Vellium Tweaker license required to launch Roblox!", (255, 100, 100))
            if self._window:
                self._window.evaluate_js("if (window.dispatchEvent) window.dispatchEvent(new CustomEvent('meowware:require_auth'));")
            return
        # Explicit launch implies the user wants flags on — lift the kill switch.
        self._clear_killswitch_if_active()
        if getattr(self, '_is_applying', False):
            log("[-] Busy applying flags, please wait...", (255, 200, 100))
            return
            
        self._is_applying = True
        def do_launch():
            try:
                log("[*] Launch & Apply: JSON + early patching...", (100, 255, 255))
                selected = str(version_dir or self.settings.get('launch_target_path', '')).strip() or None
                self.flag_manager.launch_and_apply(self.roblox_manager, version_dir=selected)
            except Exception as e:
                log(f"[-] CRITICAL CRASH in launch logic: {e}", (255, 50, 50))
                import traceback
                traceback.print_exc()
            finally:
                self._is_applying = False
                if self._window:
                    self._window.evaluate_js("""
                        var btn = document.getElementById('inject-btn');
                        if (btn) {
                            btn.disabled = false;
                            btn.textContent = 'Apply Flags';
                        }
                        if (typeof refreshConfig === 'function') refreshConfig();
                    """)
                    
        threading.Thread(target=do_launch, daemon=True).start()

    def reapply_flags(self):
        """Kill Roblox, then relaunch with all flags pre-patched (mid-game reapply)."""
        if not self.flag_manager or not self.roblox_manager:
            log("[-] Not ready", (255, 100, 100))
            return
        # Explicit relaunch implies the user wants flags on — lift the kill switch.
        self._clear_killswitch_if_active()
        if getattr(self, '_is_applying', False):
            log("[-] Busy applying flags, please wait...", (255, 200, 100))
            return
            
        self._is_applying = True
        def do_reapply():
            try:
                # Kill existing Roblox
                killed = self.roblox_manager.kill_roblox()
                if killed > 0:
                    log(f"[*] Killed {killed} Roblox process(es)", (255, 200, 100))
                    # Clear processed PIDs so auto-apply doesn't interfere
                    self.processed_pids.clear()
                    # Wait for process to fully die
                    import time
                    time.sleep(1.5)
                else:
                    log("[*] No Roblox process found, launching fresh...", (100, 255, 255))
                
                # Now launch with early patching
                log("[*] Relaunching with all flags pre-patched...", (100, 255, 255))
                self.flag_manager.launch_and_apply(self.roblox_manager)
            except Exception as e:
                log(f"[-] CRASH in reapply: {e}", (255, 50, 50))
                import traceback
                traceback.print_exc()
            finally:
                self._is_applying = False
                if self._window:
                    self._window.evaluate_js("""
                        var btn = document.getElementById('inject-btn');
                        if (btn) {
                            btn.disabled = false;
                            btn.textContent = 'Apply Flags';
                        }
                        if (typeof refreshConfig === 'function') refreshConfig();
                    """)
                    
        threading.Thread(target=do_reapply, daemon=True).start()

    def sync_offsets(self):
        """Refresh the known flag and memory-offset data from upstream."""
        if not self.flag_manager:
            return {'ok': False, 'error': 'Not ready'}
        if self.flag_manager.offsets_loading:
            return {'ok': False, 'error': 'Offsets are already syncing'}

        def do_sync():
            try:
                from src.core import offset_loader
                offset_loader.reset_cache()
                self.flag_manager.official_types.clear()
                self.flag_manager.official_prefixes.clear()
                self.flag_manager.load_offsets(force_cdn=True)
                self._last_offsets_loaded_state = False
                self._needs_ui_refresh = True
                log("[+] Offset sync complete", (100, 255, 100))
            except Exception as exc:
                log(f"[-] Offset sync failed: {exc}", (255, 100, 100))

        threading.Thread(target=do_sync, daemon=True, name='manual-offset-sync').start()
        return {'ok': True, 'message': 'Offset sync started'}

    def refresh_internal_offsets(self):
        """Manually re-fetch the executor's Roblox internal function offsets
        (robloxoffsets.com) and store them. Runs off the UI thread."""
        def do_refresh():
            try:
                from src.core import internal_offsets
                result = internal_offsets.update_internal_offsets()
                if result.get('ok'):
                    log(f"[+] Internal offsets refreshed: {result['count']} functions "
                        f"from {result['source']} for {result.get('version') or 'unknown build'}",
                        (100, 255, 100))
                else:
                    log(f"[-] Internal offsets refresh failed: {result.get('error')}",
                        (255, 100, 100))
            except Exception as exc:
                log(f"[-] Internal offsets refresh error: {exc}", (255, 100, 100))

        threading.Thread(target=do_refresh, daemon=True, name='internal-offset-sync').start()
        return {'ok': True, 'message': 'Internal offset refresh started'}

    def _internal_offsets_status(self):
        """internal_offsets.get_status() enriched with the installed Roblox
        build and whether the stored offsets target it.

        Internal offsets are RVAs specific to one Roblox build, so if the
        offsets' target version differs from the installed one they will not
        line up in memory. ``matches_installed`` is True/False when both
        versions are known, or None when either is unknown (can't tell)."""
        from src.core import internal_offsets
        status = internal_offsets.get_status()
        installed = RobloxManager.get_roblox_version_string()
        if not installed or installed == 'unknown':
            installed = None
        offsets_version = status.get('version') or None
        status['installed_version'] = installed
        status['matches_installed'] = (
            (installed == offsets_version) if (installed and offsets_version) else None
        )
        return status

    def get_internal_offsets_status(self):
        """Status of the auto-grabbed internal offsets (count/source/version/
        path) plus how the offsets' target build compares to the installed
        Roblox. No network — reads module state or the newest local copy."""
        try:
            return self._internal_offsets_status()
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}


    def get_offset_sync_options(self):
        """Return version choices used by the React offset/version dialog."""
        from src.core import offset_loader
        from src.core.version_changer import deployment
        installed = RobloxManager.get_roblox_version_string()
        if installed == 'unknown':
            installed = None
        internal = {}
        try:
            internal = self._internal_offsets_status()
        except Exception:
            internal = {}
        return {
            'ok': True,
            'installed_version': installed,
            'active_offset_version': offset_loader.last_source_build(),
            'latest_production': deployment.get_latest_production_guid(),
            'versions': offset_loader.fetch_available_versions(80),
            'internal_offsets': internal,
        }

    def sync_offsets_selection(self, mode='latest', version=''):
        """Sync latest, installed-build, or custom-version offset data."""
        from src.core import offset_loader
        mode = str(mode or 'latest').lower()
        if mode == 'latest':
            target = None
        elif mode == 'current':
            target = RobloxManager.get_roblox_version_string()
            if not target or target == 'unknown':
                return {'ok': False, 'error': 'No installed Roblox version was detected'}
        elif mode == 'custom':
            target = offset_loader.normalize_version_hash(version)
            if not target:
                return {'ok': False, 'error': 'Enter a valid custom version hash'}
        else:
            return {'ok': False, 'error': 'Unknown offset sync mode'}

        result = offset_loader.sync_version_dump(target)
        if not result.get('ok'):
            return result
        self.flag_manager.official_types.clear()
        self.flag_manager.official_prefixes.clear()
        self.flag_manager.load_offsets()
        self._last_offsets_loaded_state = False
        self._needs_ui_refresh = True
        return {
            **result,
            'message': f"Synced {result['count']} offsets for {result['build']}",
        }

    def start_roblox_version_download(self, mode='latest', version='', allow_downgrade=False):
        """Download latest, current-installed, or an explicitly confirmed custom build."""
        from src.core import offset_loader
        from src.core.version_changer import fixer, deployment
        mode = str(mode or 'latest').lower()
        installed = RobloxManager.get_roblox_version_string()
        latest = deployment.get_latest_production_guid()

        if mode == 'latest':
            return self.start_roblox_download()
        if mode == 'current':
            target = installed if installed and installed != 'unknown' else None
        elif mode == 'offset':
            target = offset_loader.last_source_build()
        elif mode == 'custom':
            target = offset_loader.normalize_version_hash(version)
        else:
            target = None
        if not target:
            return {'state': 'error', 'message': 'A valid target version is required.'}
        if self._fix_state == 'running':
            return {'state': 'already_running', 'message': 'A Roblox download is already in progress.'}
        try:
            if self.roblox_manager and self.roblox_manager.find_roblox_process():
                return {'state': 'roblox_running', 'message': 'Please close Roblox, then try again.'}
        except Exception:
            pass
        is_nonlatest = bool(latest and target != latest)
        if is_nonlatest and not bool(allow_downgrade):
            return {
                'state': 'confirm_required',
                'message': 'Enable custom-version installation to continue. Other installed builds may be removed.',
            }

        versions_root = RobloxManager.resolve_download_versions_root()
        if not versions_root:
            return {'state': 'error', 'message': 'No Roblox install directory found.'}
        try:
            cache_dirs = RobloxManager.get_all_roblox_version_dirs() or []
        except Exception:
            cache_dirs = []

        self._fix_progress = 0
        self._fix_state = 'running'
        self._fix_message = f'Downloading {target}…'
        self._fix_cancel = False

        def worker():
            def progress(done, total, _name):
                self._fix_progress = int((done / total) * 100) if total else 0
                self._fix_message = f'{done}/{total} packages'
            try:
                result = fixer.run_upgrade(
                    target, versions_root, cache_dirs,
                    progress=progress,
                    should_cancel=lambda: self._fix_cancel,
                )
                if result.get('ok'):
                    if is_nonlatest:
                        fixer.prune_non_production_builds(versions_root, target)
                    elif latest and target == latest:
                        fixer.prune_stock_non_production(target)
                    try:
                        offset_loader.sync_version_dump(target)
                        if self.flag_manager:
                            self.flag_manager.official_types.clear()
                            self.flag_manager.official_prefixes.clear()
                            self.flag_manager.load_offsets()
                    except Exception:
                        pass
                    self._fix_progress = 100
                    self._fix_state = 'done'
                    self._fix_message = result.get('message') or f'{target} installed.'
                else:
                    self._fix_progress = -1
                    self._fix_state = 'cancelled' if result.get('state') == 'cancelled' else 'failed'
                    self._fix_message = result.get('message', 'Download failed.')
            except Exception as exc:
                log(f"[!] Custom Roblox download failed: {type(exc).__name__}: {exc}", (255, 120, 120))
                self._fix_progress = -1
                self._fix_state = 'failed'
                self._fix_message = f'Download failed ({type(exc).__name__}).'

        threading.Thread(target=worker, daemon=True, name='custom-roblox-download').start()
        return {'state': 'started', 'target': target, 'message': f'Downloading {target}…'}

    def upload_offsets(self):
        """Choose, validate, and activate a local FFlags.hpp offset dump."""
        if not self._window or not self.flag_manager:
            return {'ok': False, 'error': 'Not ready'}
        try:
            result = self._window.create_file_dialog(
                dialog_type=10,
                file_types=('C++ Header Files (*.hpp;*.h)', 'All Files (*.*)'),
            )
            if not result:
                return {'ok': False, 'cancelled': True, 'error': 'No file selected'}
            file_path = result if isinstance(result, str) else result[0]
            from src.core import offset_loader
            build_version = RobloxManager.get_roblox_version_string()
            imported = offset_loader.import_offset_dump(file_path, build_version)
            if imported.get('ok'):
                self.flag_manager.official_types.clear()
                self.flag_manager.official_prefixes.clear()
                self.flag_manager.load_offsets()
                self._last_offsets_loaded_state = False
                self._needs_ui_refresh = True
            return imported
        except Exception as exc:
            log(f"[-] Offset upload failed: {exc}", (255, 100, 100))
            return {'ok': False, 'error': str(exc)}

    def pick_bulk_json_file(self):
        """Read a JSON/text FastFlag list selected for the Bulk Add editor."""
        if not self._window:
            return {'ok': False, 'error': 'Window is not ready'}
        try:
            result = self._window.create_file_dialog(
                dialog_type=10,
                file_types=('FastFlag JSON (*.json)', 'Text Lists (*.txt)', 'All Files (*.*)'),
            )
            if not result:
                return {'ok': False, 'cancelled': True}
            path = Path(result if isinstance(result, str) else result[0])
            if path.stat().st_size > 2 * 1024 * 1024:
                return {'ok': False, 'error': 'Choose a file smaller than 2 MB'}
            return {'ok': True, 'name': path.name, 'text': path.read_text(encoding='utf-8-sig', errors='replace')}
        except Exception as exc:
            return {'ok': False, 'error': f'Could not read JSON file: {exc}'}

    def activate_offset_url(self, url):
        """Download, validate, and activate a user-provided HTTPS FFlags.hpp URL."""
        try:
            url = str(url or '').strip()
            if not url.lower().startswith('https://'):
                return {'ok': False, 'error': 'Offset sources must use HTTPS'}
            from src.core import offset_loader, offset_sources
            body = offset_sources.fetch_via_requests(url)
            if not body:
                body = offset_sources.fetch_via_curl(url)
            if not body:
                return {'ok': False, 'error': 'The source could not be downloaded'}
            build_version = RobloxManager.get_roblox_version_string()
            result = offset_loader._activate_offset_body(body, build_version, 'custom_url')
            if result.get('ok') and self.flag_manager:
                self.flag_manager.official_types.clear()
                self.flag_manager.official_prefixes.clear()
                self.flag_manager.load_offsets()
                self._last_offsets_loaded_state = False
                self._needs_ui_refresh = True
                result['message'] = f"Activated {result.get('count', 0)} offsets from custom source"
            return result
        except Exception as exc:
            log(f"[-] Custom offset source failed: {exc}", (255, 100, 100))
            return {'ok': False, 'error': str(exc)}

    def get_offset_sources(self):
        """Load configured offset sources from %LOCALAPPDATA%/MeowWare/sources.json."""
        try:
            sources = Config.load_sources()
            return {'ok': True, 'sources': sources, 'config_dir': str(Config.APP_DIR)}
        except Exception as exc:
            return {'ok': False, 'error': str(exc), 'sources': []}

    def save_offset_sources(self, sources):
        """Save offset sources list to %LOCALAPPDATA%/MeowWare/sources.json."""
        try:
            if not isinstance(sources, list):
                return {'ok': False, 'error': 'Sources must be a list'}
            ok = Config.save_sources(sources)
            if ok:
                log(f"[+] Saved {len(sources)} offset sources to {Config.SOURCES_FILE.name}")
            return {'ok': ok}
        except Exception as exc:
            log(f"[-] Failed to save sources: {exc}", (255, 100, 100))
            return {'ok': False, 'error': str(exc)}

    def get_asset_proxy_profile(self):
        """Return the locally stored asset replacement profile."""
        path = Config.APP_DIR / 'asset-proxy.json'
        try:
            if not path.is_file():
                return {'ok': True, 'profile': {'version': 1, 'name': 'Default profile', 'rules': []}}
            profile = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(profile, dict) or not isinstance(profile.get('rules', []), list):
                raise ValueError('Invalid asset proxy profile')
            return {'ok': True, 'profile': profile}
        except Exception as exc:
            log(f"[-] Could not load asset proxy profile: {exc}", (255, 100, 100))
            return {'ok': False, 'error': str(exc), 'profile': {'version': 1, 'name': 'Default profile', 'rules': []}}

    def get_proxy_settings(self):
        defaults = {
            'enabled': True, 'run_as_admin': True, 'scraper_enabled': True,
            'auto_sync': True, 'preserve_cache': True, 'traffic_preserve': True,
        }
        saved = self.settings.get('proxy_settings', {})
        if isinstance(saved, dict):
            defaults.update({key: bool(saved[key]) for key in defaults if key in saved})
        try:
            is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin()) if sys.platform == 'win32' else os.geteuid() == 0
        except Exception:
            is_admin = False
        return {'ok': True, 'settings': defaults, 'is_admin': is_admin}

    def set_proxy_setting(self, key, value):
        allowed = {'enabled', 'run_as_admin', 'scraper_enabled', 'auto_sync', 'preserve_cache', 'traffic_preserve'}
        if key not in allowed:
            return {'ok': False, 'error': 'Unknown proxy setting'}
        current = self.get_proxy_settings()['settings']
        current[key] = bool(value)
        self.settings['proxy_settings'] = current
        Config.save_settings(self.settings)
        if key == 'traffic_preserve':
            try:
                local = Path(os.environ.get('LOCALAPPDATA') or Config.APP_DIR.parent)
                target = local / 'FleasionNT' / 'settings.json'
                payload = json.loads(target.read_text(encoding='utf-8')) if target.is_file() else {}
                payload['proxy_traffic_preserve'] = bool(value)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(payload, indent=2), encoding='utf-8')
            except (OSError, ValueError, TypeError):
                pass
        return {'ok': True, 'settings': current}

    def get_vellium_proxy_traffic(self):
        """Return Fleasion's preserved proxy rows without loading raw bodies."""
        try:
            local = Path(os.environ.get('LOCALAPPDATA') or Config.APP_DIR.parent)
            target = local / 'FleasionNT' / 'proxy_traffic.json'
            if not target.is_file():
                return {'ok': True, 'entries': [], 'preserving': self.get_proxy_settings()['settings'].get('traffic_preserve', True)}
            payload = json.loads(target.read_text(encoding='utf-8'))
            source = payload.get('entries', []) if isinstance(payload, dict) else []
            entries = []
            for index, item in enumerate(source[-5000:]):
                if not isinstance(item, dict):
                    continue
                entries.append({
                    'id': index, 'time': item.get('time'), 'method': str(item.get('method') or ''),
                    'host': str(item.get('host') or ''), 'port': item.get('port'),
                    'path': str(item.get('path') or ''), 'status': item.get('status'),
                    'size': item.get('size'), 'ms': item.get('ms'),
                    'intercepted': bool(item.get('was_intercepted') or item.get('intercepted')),
                    'dropped': bool(item.get('dropped_request') or item.get('dropped_response')),
                })
            return {'ok': True, 'entries': list(reversed(entries)), 'preserving': self.get_proxy_settings()['settings'].get('traffic_preserve', True), 'path': str(target)}
        except Exception as exc:
            return {'ok': False, 'error': str(exc), 'entries': []}

    def get_vellium_proxy_traffic_detail(self, entry_id):
        try:
            local = Path(os.environ.get('LOCALAPPDATA') or Config.APP_DIR.parent)
            target = local / 'FleasionNT' / 'proxy_traffic.json'
            payload = json.loads(target.read_text(encoding='utf-8'))
            source = payload.get('entries', [])[-5000:]
            item = source[int(entry_id)]
            def decode(key):
                encoded = item.get(key)
                if not encoded:
                    return ''
                raw = base64.b64decode(encoded, validate=False)[:512 * 1024]
                return raw.decode('utf-8', errors='replace')
            return {'ok': True, 'request': decode('request_raw'), 'response': decode('response_raw')}
        except Exception as exc:
            return {'ok': False, 'error': str(exc), 'request': '', 'response': ''}

    def save_asset_proxy_profile(self, profile):
        """Validate and persist the asset replacement profile in LocalAppData."""
        try:
            if not isinstance(profile, dict) or not isinstance(profile.get('rules'), list):
                return {'ok': False, 'error': 'Profile must contain a rules list'}
            clean_rules = []
            for rule in profile['rules'][:500]:
                if not isinstance(rule, dict):
                    continue
                asset_id = ''.join(ch for ch in str(rule.get('assetId', '')) if ch.isdigit())
                mode = str(rule.get('mode', 'asset'))
                replacement = str(rule.get('replacement', '')).strip()[:4096]
                if not asset_id or mode not in {'asset', 'url', 'file', 'remove'}:
                    continue
                if mode == 'url' and not replacement.lower().startswith('https://'):
                    continue
                if mode != 'remove' and not replacement:
                    continue
                clean_rules.append({'id': str(rule.get('id', ''))[:100], 'assetId': asset_id, 'mode': mode, 'replacement': replacement, 'enabled': bool(rule.get('enabled', True))})
            clean = {'version': 1, 'name': str(profile.get('name', 'Default profile')).strip()[:60] or 'Default profile', 'rules': clean_rules}
            Config._ensure_dirs()
            target = Config.APP_DIR / 'asset-proxy.json'
            temporary = target.with_suffix('.tmp')
            temporary.write_text(json.dumps(clean, indent=2), encoding='utf-8')
            temporary.replace(target)
            return {'ok': True, 'profile': clean, 'path': str(target)}
        except Exception as exc:
            log(f"[-] Could not save asset proxy profile: {exc}", (255, 100, 100))
            return {'ok': False, 'error': str(exc)}

    def choose_asset_proxy_file(self):
        """Choose a local replacement asset without reading or executing it."""
        if not self._window:
            return {'ok': False, 'error': 'Window is not ready'}
        try:
            result = self._window.create_file_dialog(dialog_type=10, file_types=('Asset files (*.*)',))
            if not result:
                return {'ok': False, 'cancelled': True}
            path = Path(result if isinstance(result, str) else result[0]).resolve()
            if not path.is_file():
                return {'ok': False, 'error': 'The selected file does not exist'}
            return {'ok': True, 'path': str(path), 'name': path.name}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def apply_asset_proxy_profile(self, profile, launch=False):
        """Translate Vellium Tweaker rules into Fleasion's supported config schema.

        The generated profile is intentionally isolated as ``Vellium Tweaker.json``;
        existing Fleasion profiles and settings are preserved.
        """
        try:
            saved = self.save_asset_proxy_profile(profile)
            if not saved.get('ok'):
                return saved
            profile = saved['profile']
            local = Path(os.environ.get('LOCALAPPDATA') or Config.APP_DIR.parent)
            fleasion_dir = local / 'FleasionNT'
            configs_dir = fleasion_dir / 'configs'
            configs_dir.mkdir(parents=True, exist_ok=True)
            translated = []
            for rule in profile['rules']:
                item = {'replace_ids': [int(rule['assetId'])], 'enabled': bool(rule['enabled'])}
                mode = rule['mode']
                if mode == 'asset':
                    if not rule['replacement'].isdigit():
                        continue
                    item.update({'mode': 'id', 'with_id': int(rule['replacement'])})
                elif mode == 'url':
                    item.update({'mode': 'cdn', 'cdn_url': rule['replacement']})
                elif mode == 'file':
                    item.update({'mode': 'local', 'local_path': rule['replacement']})
                else:
                    item['mode'] = 'remove'
                translated.append(item)
            target = configs_dir / 'Vellium Tweaker.json'
            temporary = target.with_suffix('.tmp')
            temporary.write_text(json.dumps({'replacement_rules': translated}, indent=2), encoding='utf-8')
            temporary.replace(target)

            settings_path = fleasion_dir / 'settings.json'
            settings = {}
            if settings_path.is_file():
                try:
                    settings = json.loads(settings_path.read_text(encoding='utf-8'))
                except (OSError, json.JSONDecodeError):
                    settings = {}
            enabled = settings.get('enabled_configs', [])
            if not isinstance(enabled, list):
                enabled = []
            if 'Vellium Tweaker' not in enabled:
                enabled.append('Vellium Tweaker')
            settings['enabled_configs'] = enabled
            settings['last_config'] = 'Vellium Tweaker'
            settings['proxy_features_enabled'] = True
            fleasion_dir.mkdir(parents=True, exist_ok=True)
            settings_temp = settings_path.with_suffix('.tmp')
            settings_temp.write_text(json.dumps(settings, indent=2), encoding='utf-8')
            settings_temp.replace(settings_path)

            launched = False
            if launch:
                proxy_settings = self.get_proxy_settings()['settings']
                if not proxy_settings.get('enabled', True):
                    return {'ok': False, 'error': 'Vellium Proxy is disabled in Proxy Settings'}
                source_root = Path(__file__).resolve().parents[2].parent / 'Fleasion'
                launcher = source_root / 'launcher.py'
                if launcher.is_file():
                    try:
                        __import__('PySide6')
                    except ImportError:
                        return {'ok': True, 'count': len(translated), 'path': str(target), 'launched': False, 'runtime_missing': True}
                    if proxy_settings.get('run_as_admin', True) and sys.platform == 'win32':
                        params = subprocess.list2cmdline([str(launcher)])
                        result = ctypes.windll.shell32.ShellExecuteW(None, 'runas', sys.executable, params, str(source_root), 0)
                        if result <= 32:
                            return {'ok': False, 'error': 'Administrator launch was cancelled or failed'}
                        launched = True
                    else:
                        creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                        subprocess.Popen([sys.executable, str(launcher)], cwd=str(source_root), close_fds=True, creationflags=creationflags)
                        launched = True
            log(f"[+] Synced {len(translated)} asset rules to Fleasion")
            return {'ok': True, 'count': len(translated), 'path': str(target), 'launched': launched, 'restart_required': not launched}
        except Exception as exc:
            log(f"[-] Asset proxy sync failed: {exc}", (255, 100, 100))
            return {'ok': False, 'error': str(exc)}

    def get_meow_proxy_scraped_games(self):
        """Fetch Fleasion's public scraped-games catalog with a local fallback."""
        url = 'https://raw.githubusercontent.com/fleasion/Fleasion/refs/heads/clog/CLOG.json'
        cache = Config.APP_DIR / 'meow-proxy-games.json'
        try:
            import urllib.request
            request = urllib.request.Request(url, headers={'User-Agent': 'MeowWare/1.3'})
            with urllib.request.urlopen(request, timeout=12) as response:
                raw = response.read(2 * 1024 * 1024)
            cache.write_bytes(raw)
        except Exception:
            if not cache.is_file():
                return {'ok': False, 'error': 'Scraped-games catalog is unavailable', 'games': []}
            raw = cache.read_bytes()
        try:
            games = []
            for name, item in json.loads(raw).get('games', {}).items():
                if not isinstance(item, dict):
                    continue
                games.append({'name': str(name), 'owner': str(item.get('Owner') or item.get('owner') or ''), 'place_id': item.get('id'), 'assets_url': item.get('github'), 'replacements_url': item.get('replacement') or item.get('Replacement')})
            return {'ok': True, 'games': games}
        except Exception as exc:
            return {'ok': False, 'error': str(exc), 'games': []}

    def get_meow_proxy_scraped_assets(self, url):
        """Fetch and flatten one trusted raw-GitHub scraped asset database."""
        try:
            import urllib.request
            from urllib.parse import urlparse
            url = str(url or '').strip()
            parsed = urlparse(url)
            if parsed.scheme != 'https' or parsed.hostname != 'raw.githubusercontent.com':
                return {'ok': False, 'error': 'Only raw GitHub asset databases are supported', 'assets': []}
            request = urllib.request.Request(url, headers={'User-Agent': 'MeowWare/1.3'})
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read(12 * 1024 * 1024)
            data = json.loads(raw)
            assets = []
            def walk(value, trail):
                if len(assets) >= 6000:
                    return
                if isinstance(value, dict):
                    for key, child in value.items(): walk(child, trail + [str(key)])
                elif isinstance(value, list):
                    for index, child in enumerate(value): walk(child, trail + [str(index + 1)])
                elif isinstance(value, int) or isinstance(value, str) and value.isdigit():
                    asset_id = str(value)
                    if len(asset_id) >= 5:
                        assets.append({'id': asset_id, 'name': trail[-1] if trail else asset_id, 'path': ' / '.join(trail[:-1])})
            walk(data, [])
            return {'ok': True, 'assets': assets}
        except Exception as exc:
            return {'ok': False, 'error': str(exc), 'assets': []}

    def get_vellium_live_assets(self):
        """Read assets captured by Fleasion's live cache scraper.

        Fleasion releases have used both ``FleasionNT/Cache`` and the older
        nested ``FleasionNT/FleasionNT/Cache`` layout, so inspect both without
        importing or mutating the proxy runtime.
        """
        try:
            if not self.get_proxy_settings()['settings'].get('scraper_enabled', True):
                return {'ok': True, 'disabled': True, 'assets': [], 'count': 0, 'roblox_running': False, 'sources': []}
            local = Path(os.environ.get('LOCALAPPDATA') or Config.APP_DIR.parent)
            candidates = (
                local / 'FleasionNT' / 'Cache' / 'index.json',
                local / 'FleasionNT' / 'FleasionNT' / 'Cache' / 'index.json',
            )
            assets_by_key = {}
            sources = []
            for index_path in candidates:
                if not index_path.is_file():
                    continue
                try:
                    payload = json.loads(index_path.read_text(encoding='utf-8'))
                    records = payload.get('assets', {}) if isinstance(payload, dict) else {}
                    records = list(records.values()) if isinstance(records, dict) else records
                    for item in records if isinstance(records, (list, tuple)) else []:
                        if not isinstance(item, dict):
                            continue
                        asset_id = ''.join(ch for ch in str(item.get('id', '')) if ch.isdigit())
                        if not asset_id:
                            continue
                        asset_type = item.get('type', 0)
                        key = f'{asset_type}_{asset_id}'
                        assets_by_key[key] = {
                            'id': asset_id,
                            'type': asset_type,
                            'type_name': str(item.get('type_name') or item.get('detected_type') or 'Unknown'),
                            'url': str(item.get('url') or ''),
                            'size': int(item.get('size') or 0),
                            'cached_at': str(item.get('cached_at') or ''),
                            'name': str(item.get('name') or (item.get('metadata') or {}).get('name') or ''),
                            'creator': str((item.get('metadata') or {}).get('creator_name') or (item.get('metadata') or {}).get('creator') or ''),
                        }
                    sources.append(str(index_path))
                except (OSError, ValueError, TypeError):
                    continue
            assets = sorted(assets_by_key.values(), key=lambda row: row['cached_at'], reverse=True)
            running = False
            if sys.platform == 'win32':
                try:
                    output = subprocess.run(
                        ['tasklist', '/FI', 'IMAGENAME eq RobloxPlayerBeta.exe', '/NH'],
                        capture_output=True, text=True, timeout=2, creationflags=subprocess.CREATE_NO_WINDOW,
                    ).stdout.lower()
                    running = 'robloxplayerbeta.exe' in output
                except Exception:
                    pass
            return {'ok': True, 'assets': assets[:10000], 'count': len(assets), 'roblox_running': running, 'sources': sources}
        except Exception as exc:
            return {'ok': False, 'error': str(exc), 'assets': [], 'count': 0, 'roblox_running': False}

    def get_vellium_asset_preview(self, asset_id, asset_type, type_name=''):
        """Return an actual cached image preview, never a catalog thumbnail."""
        try:
            asset_id = ''.join(ch for ch in str(asset_id) if ch.isdigit())
            asset_type = int(asset_type or 0)
            safe_type = ''.join(ch for ch in str(type_name) if ch.isalnum() or ch in ' _-')
            if not asset_id or not safe_type:
                return {'ok': False, 'previewable': False}
            local = Path(os.environ.get('LOCALAPPDATA') or Config.APP_DIR.parent)
            roots = (local / 'FleasionNT' / 'Cache', local / 'FleasionNT' / 'FleasionNT' / 'Cache')
            for root in roots:
                path = root / safe_type / f'{asset_id}.bin'
                if not path.is_file() and root.is_dir():
                    path = next(root.glob(f'*/{asset_id}.bin'), path)
                index_path = root / 'index.json'
                if not path.is_file():
                    continue
                data = path.read_bytes()
                try:
                    if index_path.is_file():
                        index = json.loads(index_path.read_text(encoding='utf-8'))
                        entry = (index.get('assets') or {}).get(f'{asset_type}_{asset_id}', {})
                        if entry.get('compressed'):
                            data = gzip.decompress(data)
                except (OSError, ValueError, TypeError, gzip.BadGzipFile):
                    pass
                signatures = (
                    (b'\x89PNG\r\n\x1a\n', 'image/png'), (b'\xff\xd8\xff', 'image/jpeg'),
                    (b'GIF87a', 'image/gif'), (b'GIF89a', 'image/gif'), (b'BM', 'image/bmp'),
                )
                mime = next((kind for signature, kind in signatures if data.startswith(signature)), '')
                if len(data) >= 12 and data.startswith(b'RIFF') and data[8:12] == b'WEBP':
                    mime = 'image/webp'
                if not mime or len(data) > 12 * 1024 * 1024:
                    return {'ok': True, 'previewable': False, 'reason': 'This cached asset is not a directly previewable image'}
                return {'ok': True, 'previewable': True, 'data_url': f'data:{mime};base64,{base64.b64encode(data).decode("ascii")}', 'mime': mime}
            return {'ok': True, 'previewable': False, 'reason': 'Cached file was not found'}
        except Exception as exc:
            return {'ok': False, 'previewable': False, 'error': str(exc)}

    def open_config_folder(self):
        """Open the %LOCALAPPDATA%/MeowWare config folder in Explorer."""
        try:
            Config._ensure_dirs()
            subprocess.Popen(["explorer.exe", str(Config.APP_DIR)], close_fds=True)
            return {'ok': True, 'path': str(Config.APP_DIR)}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    # ─── Kill Switch ───

    def _clear_killswitch_if_active(self):
        """Lift the kill switch (used when the user explicitly launches/relaunches)."""
        if not self.settings.get('killswitch_active', False):
            return
        self.settings['killswitch_active'] = False
        Config.save_settings(self.settings)
        if self.flag_manager:
            self.flag_manager.resume_watchdog()
        self._notify_killswitch_ui()
        log("[*] Flags ON (explicit launch).", (180, 220, 180))

    def _notify_killswitch_ui(self):
        if self._window:
            try:
                self._window.evaluate_js(
                    "if (typeof refreshConfig === 'function') refreshConfig();"
                    "if (typeof refreshKillswitchUI === 'function') refreshKillswitchUI();"
                )
            except Exception:
                pass

    def _do_killswitch_toggle(self):
        """Flip the kill switch. Shared entry point for the UI button and the
        global hotkey."""
        if self.settings.get('killswitch_active', False):
            return self.restore_flags()
        return self.disable_all_flags()

    def disable_all_flags(self):
        """Pause every flag at once: revert memory-writable flags to their
        originals and clear ClientAppSettings.json. Remembers which flags were
        enabled so restore_flags returns to this exact state."""
        if not self.flag_manager:
            return {'ok': False, 'error': 'Not ready'}
        if self.settings.get('killswitch_active', False):
            return {'ok': True, 'already': True}

        with self.flag_manager._lock:
            prev_enabled = [f['name'] for f in self.flag_manager.user_flags
                            if f.get('enabled', True)]
        # The kill switch is intentionally NOT written to history — Restore is
        # the dedicated undo for it, so it shouldn't clutter the history list.

        self.settings['killswitch_prev_enabled'] = prev_enabled
        self.settings['killswitch_active'] = True
        Config.save_settings(self.settings)
        self.flag_manager.pause_watchdog()

        def do_disable():
            try:
                if self.roblox_manager:
                    self.roblox_manager.attach()
                summary = self.flag_manager.disable_all_live()
                if self.roblox_manager:
                    self.roblox_manager.clear_fflags_json()
                log(f"[+] Flags OFF — reverted {summary['reverted']}/{summary['total']} "
                    f"live flag(s); JSON cleared. String / memory-locked flags clear on next launch.",
                    (255, 200, 100))
            except Exception as e:
                log(f"[-] Flags toggle error: {e}", (255, 100, 100))
            finally:
                self._notify_killswitch_ui()

        threading.Thread(target=do_disable, daemon=True).start()
        return {'ok': True}

    def restore_flags(self):
        """Lift the kill switch: re-enable the previously-enabled flags and
        re-apply through the normal path (JSON + live memory). Idempotent —
        a second call while flags are already on is a no-op, matching the
        symmetry with disable_all_flags(). This prevents a rapid off/on
        double-click from spawning two do_restore threads that would race
        each other over the RobloxManager handle and the mem-lock (the
        symptom was 'Scheduling lock for N…' followed by silence)."""
        if not self.flag_manager:
            return {'ok': False, 'error': 'Not ready'}
        if not self.settings.get('killswitch_active', False):
            return {'ok': True, 'already': True}
        prev = self.settings.get('killswitch_prev_enabled', []) or []
        self.settings['killswitch_active'] = False
        Config.save_settings(self.settings)
        self.flag_manager.resume_watchdog()

        def do_restore():
            try:
                restored = self.flag_manager.re_enable_flags(prev)
                log(f"[+] Flags ON — re-enabling {restored} flag(s)...", (100, 255, 100))
                if self.roblox_manager:
                    self.roblox_manager.attach()
                # inject() rewrites JSON and re-applies live memory + sets status.
                self.inject()
            except Exception as e:
                log(f"[-] Restore error: {e}", (255, 100, 100))
            finally:
                self._notify_killswitch_ui()

        threading.Thread(target=do_restore, daemon=True).start()
        return {'ok': True}

    def get_killswitch_state(self):
        return {
            'active': self.settings.get('killswitch_active', False),
            'bind': self.settings.get('killswitch_bind', ''),
        }

    def set_killswitch_bind(self, key):
        self.settings['killswitch_bind'] = key or ''
        Config.save_settings(self.settings)
        if self.flag_manager:
            self.flag_manager.set_killswitch_bind(key or '')
        log(f"[+] Toggle-flags hotkey: {key or 'cleared'}")
        return {'ok': True}

    def revert_flag_to_original(self, name):
        """Write a single flag's captured original value back into the live
        process, then read it back to confirm. Used by the right-click menu.

        Reverting only works for numeric/bool flags that were applied to live
        memory; string / JSON-only flags have no in-memory value to revert and
        only reset on the next launch."""
        if not self.flag_manager:
            return {'ok': False, 'error': 'Not ready'}
        if self.roblox_manager:
            self.roblox_manager.attach()
        res = self.flag_manager.revert_one_to_original(name)
        if res.get('ok'):
            self.flag_manager.save_user_flags()
            if res.get('verified'):
                log(f"[+] Reverted {name} to its original value {res.get('value')} "
                    f"— verified in memory.", (100, 255, 100))
            else:
                log(f"[!] Set {name} to original {res.get('value')}, but read-back "
                    f"didn't confirm — the engine may re-set it.", (255, 200, 100))
            return res
        reason_msg = {
            'not_found': f"{name} is not in your configuration.",
            'not_attached': "Roblox isn't running — can't revert live. It will reset on next launch.",
            'not_memory_writable': f"{name} is a string/JSON-only flag — it has no live value to revert (resets on next launch).",
            'no_original': f"{name} has no captured original and no known default to revert to.",
            'write_failed': f"Revert write failed for {name} — its memory page may be locked (JSON-only).",
        }.get(res.get('reason'), f"Could not revert {name}.")
        log(f"[*] {reason_msg}", (255, 200, 100))
        return res

    def remove_unavailable_flags(self):
        """Remove every flag shown in the UI's "Unavailable" group — those whose
        last apply ended as 'unavailable', 'failed', or 'json_only'. This mirrors
        exactly what the user sees under that section. Saved to history so it can
        be undone."""
        if not self.flag_manager:
            return {'ok': False, 'error': 'Not ready'}
        removable = {'unavailable', 'failed', 'json_only'}
        with self.flag_manager._lock:
            doomed = [f['name'] for f in self.flag_manager.user_flags
                      if f.get('_status') in removable]
        if not doomed:
            log("[*] No unavailable flags to remove.", (180, 180, 180))
            return {'ok': True, 'removed': 0}
        self.flag_manager.save_history_snapshot(
            f"Before removing {len(doomed)} unavailable flag(s)",
            self.settings.get('history_limit', 20))
        with self.flag_manager._lock:
            self.flag_manager.user_flags = [
                f for f in self.flag_manager.user_flags if f['name'] not in doomed
            ]
        self.flag_manager.save_user_flags()
        log(f"[+] Removed {len(doomed)} unavailable flag(s).", (100, 255, 100))
        return {'ok': True, 'removed': len(doomed)}

    def import_flags(self):
        """Import flags from a file produced by Export. Supports every
        export format the preset system writes EXCEPT the plain-text
        KEY=VALUE form:
        - JSON list:        [{"name": "...", "value": "...", ...}, ...]
        - JSON dict:        {"FFlagName": value, ...}  (Bloxstrap-style)
        - JSON preset:      {"name": "...", "flags": [...]}
        - Base64+zlib:      compressed preset payload (.txt files)

        Bind metadata (bind / unapply_bind / cycle_states) is preserved
        when present in the source payload.
        """
        if not self._window or not self.flag_manager:
            return False
        try:
            result = self._window.create_file_dialog(
                dialog_type=10,  # OPEN_DIALOG
                file_types=(
                    'Preset Files (*.json;*.txt)',
                    'JSON Files (*.json)',
                    'Text Files (*.txt)',
                    'All Files (*.*)',
                ),
            )
            if not result or len(result) == 0:
                return False

            file_path = result[0]
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_text = f.read()

            try:
                _, parsed_flags = _parse_preset_payload(
                    raw_text,
                    source_name=os.path.basename(file_path),
                    allow_plain_text=False,
                )
            except ValueError as ve:
                log(f"[-] Import error: {ve}", (255, 85, 85))
                return False

            self.flag_manager.save_history_snapshot(
                "Before import", self.settings.get('history_limit', 20),
            )
            added = 0
            skipped = 0
            bind_keys = ('bind', 'unapply_bind', 'cycle_states')
            for item in parsed_flags:
                if not isinstance(item, dict):
                    continue
                name = strip_bogus_dflag_prefix(item.get('name'))
                val = item.get('value')
                if not name or val is None:
                    continue
                # DO NOT clean the name; Roblox JSON and memory patching require the prefix
                if any(f['name'] == name for f in self.flag_manager.user_flags):
                    skipped += 1
                    continue
                flag_type = (
                    item.get('type')
                    or infer_type_from_name(name)
                    or infer_type(str(val))
                )
                new_flag = {
                    'name': name,
                    'value': str(val),
                    'type': flag_type,
                    'enabled': item.get('enabled', True),
                    'original_value': get_default_value(name),
                }
                for bk in bind_keys:
                    if bk in item:
                        new_flag[bk] = item[bk]
                self.flag_manager.user_flags.append(new_flag)
                added += 1

            with self.flag_manager._lock:
                self.flag_manager.user_flags, _ = heal_dflag_flag_names(
                    self.flag_manager.user_flags)
            self.flag_manager.save_user_flags()
            log(f"[+] Imported {added} flags ({skipped} duplicates skipped)")
            if self.settings.get('auto_apply') and added > 0:
                self.inject()
            return True
        except Exception as e:
            log(f"[-] Import error: {e}", (255, 85, 85))
        return False

    def export_flags(self):
        """Export flags to JSON file."""
        if not self._window or not self.flag_manager:
            log("[-] Not ready", (255, 85, 85))
            return False
            
        with self.flag_manager._lock:
            if not self.flag_manager.user_flags:
                log("[-] No flags to export", (255, 85, 85))
                return False
            
        try:
            result = self._window.create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename='flags.json',
                file_types=('JSON Files (*.json)',),
            )
            if result:
                file_path = result if isinstance(result, str) else result[0]
                
                export_data = []
                with self.flag_manager._lock:
                    for f in self.flag_manager.user_flags:
                        # Include flags and their binds, but omit internal runtime fields like _status
                        flag_data = {
                            'name': f['name'],
                            'value': f.get('value', ''),
                            'type': f.get('type', 'string'),
                            'enabled': f.get('enabled', True),
                        }
                        if 'bind' in f: flag_data['bind'] = f['bind']
                        if 'unapply_bind' in f: flag_data['unapply_bind'] = f['unapply_bind']
                        if 'cycle_states' in f: flag_data['cycle_states'] = f['cycle_states']
                        export_data.append(flag_data)
                        
                with open(file_path, 'w', encoding='utf-8') as fp:
                    json.dump(export_data, fp, indent=4)
                log(f"[+] Exported {len(export_data)} flags to {os.path.basename(file_path)}")
                return True
        except Exception as e:
            log(f"[-] Export error: {e}", (255, 85, 85))
        return False

    def _find_preset_by_name(self, name):
        if not self.preset_manager:
            return None
        for p in self.preset_manager.get_presets():
            if p.get('name') == name:
                return p
        return None

    def export_preset(self, name, fmt='json-with-binds'):
        """Format-aware preset export. Returns the exportable string, or None if not found.

        fmt in PRESET_EXPORT_FORMATS. Defaults to 'json-with-binds' (most useful for sharing).
        """
        p = self._find_preset_by_name(name)
        if p is None:
            return None
        try:
            return _export_preset_format(p, fmt)
        except Exception as e:
            log(f"[-] Preset export ({fmt}) failed: {e}", (255, 85, 85))
            return None

    def export_preset_to_file(self, name, fmt='json-with-binds', default_filename=None):
        """Save a preset to a file via the OS Save dialog.

        Returns {ok: True, path} on success, {ok: False, error} on failure or cancel.
        """
        if not self._window:
            return {'ok': False, 'error': 'window not ready'}
        p = self._find_preset_by_name(name)
        if p is None:
            return {'ok': False, 'error': 'preset not found'}
        try:
            payload = _export_preset_format(p, fmt)
        except Exception as e:
            return {'ok': False, 'error': f'format error: {e}'}

        # Pick extension and filename
        if fmt in ('json-flags-only', 'json-with-binds'):
            ext = 'json'
            file_types = ('JSON Files (*.json)', 'All Files (*.*)')
        else:  # base64 / txt
            ext = 'txt'
            file_types = ('Text Files (*.txt)', 'All Files (*.*)')

        if not default_filename:
            safe = ''.join(c if c.isalnum() or c in '-_ ' else '_' for c in (name or 'preset')).strip() or 'preset'
            suffix_map = {
                'base64': '_base64',
                'json-flags-only': '_flags',
                'json-with-binds': '',
                'txt': '',
            }
            default_filename = f"{safe}{suffix_map.get(fmt, '')}.{ext}"

        try:
            result = self._window.create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=default_filename,
                file_types=file_types,
            )
            if not result:
                return {'ok': False, 'error': 'cancelled'}
            file_path = result if isinstance(result, str) else result[0]
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(payload)
            log(f"[+] Exported preset '{name}' as {fmt} to {os.path.basename(file_path)}")
            return {'ok': True, 'path': file_path}
        except Exception as e:
            log(f"[-] Preset save failed: {e}", (255, 85, 85))
            return {'ok': False, 'error': str(e)}

    # Backwards-compatible shims (preserve old method names for any external callers)
    def export_preset_base64(self, name):
        return self.export_preset(name, 'base64')

    def export_preset_json(self, name):
        # The 'json-full' format was removed; Base64 is now the full-fidelity
        # export (wraps the whole preset, incl. binds/color/ids).
        return self.export_preset(name, 'base64')

    def import_preset_clipboard(self, raw_string):
        if not self.preset_manager:
            return False, "Manager not ready"
        try:
            name, flags = _parse_preset_payload(raw_string, source_name='Imported Preset')
            if not flags:
                return False, "No valid flags found"
            display_name = name if name.endswith('(Imported)') else f"{name} (Imported)"
            new_preset = self.preset_manager.import_preset_from_file_data(display_name, flags)
            log(f"[+] Imported preset '{display_name}' from clipboard with {len(flags)} flags")
            return True, new_preset
        except Exception as e:
            return False, str(e)

    def trigger_updater_restart(self):
        try:
            apply_staged_update()
            if self._window: self._window.destroy()
            import sys
            sys.exit(0)
        except Exception as e:
            log(f"[-] Restart failed: {e}", (255, 100, 100))

    # ─── Presets ───

    def get_presets(self):
        if not self.preset_manager: return []
        return self.preset_manager.get_presets()

    def import_preset_from_file(self):
        """Open a file picker (.json + .txt) and import via the shared parser.

        Accepts JSON (any shape we export), base64+zlib (whole-file), and KEY=VALUE plain text.
        """
        if not self._window or not self.preset_manager:
            return {'ok': False, 'error': 'Not ready'}
        try:
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=('Preset Files (*.json;*.txt)', 'JSON Files (*.json)', 'Text Files (*.txt)', 'All Files (*.*)'),
            )
            if not result or len(result) == 0:
                return {'ok': False, 'error': 'Cancelled'}
            file_path = result[0]
            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    raw = f.read()
            except Exception as e:
                return {'ok': False, 'error': f'could not read file: {e}'}

            base = os.path.basename(file_path)
            try:
                name, flags = _parse_preset_payload(raw, source_name=base)
            except Exception as e:
                log(f"[-] Preset parse error: {e}", (255, 85, 85))
                return {'ok': False, 'error': str(e)}

            if not flags:
                return {'ok': False, 'error': 'No flags found in file'}

            new_preset = self.preset_manager.import_preset_from_file_data(name, flags)
            log(f"[+] Imported preset '{name}' from {base} ({len(flags)} flags)")
            return {'ok': True, 'preset': new_preset}
        except Exception as e:
            log(f"[-] Preset import error: {e}", (255, 85, 85))
            return {'ok': False, 'error': str(e)}

    def import_preset_from_config(self, name, color):
        if not self.preset_manager or not self.flag_manager:
            return {'ok': False, 'error': 'Not ready'}
        
        # Strip internal fields like _status, but keep binds
        clean_flags = []
        with self.flag_manager._lock:
            for f in self.flag_manager.user_flags:
                flag_data = {
                    'name': f['name'],
                    'value': f.get('value', ''),
                    'type': f.get('type', 'string'),
                    'enabled': f.get('enabled', True),
                }
                if 'bind' in f: flag_data['bind'] = f['bind']
                if 'unapply_bind' in f: flag_data['unapply_bind'] = f['unapply_bind']
                if 'cycle_states' in f: flag_data['cycle_states'] = f['cycle_states']
                clean_flags.append(flag_data)
        
        if not clean_flags:
            return {'ok': False, 'error': 'Current configuration is empty'}

        cat = str(category).strip() if category else 'Other'
        new_preset = self.preset_manager.add_preset(name, clean_flags, color, category=cat)
        log(f"[+] Saved current configuration as preset '{name}' ({cat})")
        return {'ok': True, 'preset': new_preset}

    def create_custom_preset(self, name, flags, color='#a855f7', category='Other'):
        """Create a custom preset with name, flag list, color, and category."""
        if not self.preset_manager:
            return {'ok': False, 'error': 'Preset manager not ready'}
        if not name or not name.strip():
            return {'ok': False, 'error': 'Preset name is required'}
        clean_flags = []
        if isinstance(flags, list):
            for item in flags:
                if isinstance(item, dict) and item.get('name'):
                    clean_flags.append({
                        'name': str(item['name']).strip(),
                        'value': str(item.get('value', 'True')),
                        'type': item.get('type') or infer_type_from_name(item['name']) or 'string',
                        'enabled': bool(item.get('enabled', True))
                    })
        cat = str(category).strip() if category else 'Other'
        new_preset = self.preset_manager.add_preset(name.strip(), clean_flags, color or '#a855f7', category=cat)
        log(f"[+] Created custom preset '{name.strip()}' ({cat}) with {len(clean_flags)} flag(s)")
        return {'ok': True, 'preset': new_preset}

    def update_custom_preset(self, preset_id, name, flags, color='#a855f7', category='Other'):
        """Update an existing custom preset with name, flags, color, and category."""
        if not self.preset_manager:
            return {'ok': False, 'error': 'Preset manager not ready'}
        if not name or not name.strip():
            return {'ok': False, 'error': 'Preset name is required'}
        clean_flags = []
        if isinstance(flags, list):
            for item in flags:
                if isinstance(item, dict) and item.get('name'):
                    clean_flags.append({
                        'name': str(item['name']).strip(),
                        'value': str(item.get('value', 'True')),
                        'type': item.get('type') or infer_type_from_name(item['name']) or 'string',
                        'enabled': bool(item.get('enabled', True))
                    })
        cat = str(category).strip() if category else 'Other'
        ok = self.preset_manager.update_preset(preset_id, name=name.strip(), color=color or '#a855f7', flags=clean_flags, category=cat)
        if ok:
            log(f"[+] Updated preset '{name.strip()}' ({cat})")
            return {'ok': True}
        return {'ok': False, 'error': 'Preset not found'}

    def update_preset_from_config(self, preset_id):
        if not self.preset_manager or not self.flag_manager:
            return {'ok': False, 'error': 'Not ready'}

        clean_flags = []
        with self.flag_manager._lock:
            for f in self.flag_manager.user_flags:
                flag_data = {
                    'name': f['name'],
                    'value': f.get('value', ''),
                    'type': f.get('type', 'string'),
                    'enabled': f.get('enabled', True),
                }
                if 'bind' in f: flag_data['bind'] = f['bind']
                if 'unapply_bind' in f: flag_data['unapply_bind'] = f['unapply_bind']
                if 'cycle_states' in f: flag_data['cycle_states'] = f['cycle_states']
                clean_flags.append(flag_data)
        
        if not clean_flags:
            return {'ok': False, 'error': 'Current configuration is empty'}

        success = self.preset_manager.update_preset(preset_id, flags=clean_flags)
        if success:
            presets = self.preset_manager.get_presets()
            name = next((p['name'] for p in presets if p['id'] == preset_id), 'Unknown')
            log(f"[+] Updated preset '{name}' flags with current configuration")
            return {'ok': True}
        return {'ok': False, 'error': 'Preset not found'}

    # ─── Merge Preset (two-phase: analyze → apply) ───
    # The previous single-shot merge_preset silently skipped most overlaps.
    # The UI now drives a conflict-resolver picker between analyze and apply.

    _MERGE_FIELDS = ('value', 'type', 'enabled', 'bind', 'unapply_bind', 'cycle_states')

    @staticmethod
    def _normalize_flag_for_compare(f):
        """Project a flag into a comparable shape (drops runtime/internal keys)."""
        if not isinstance(f, dict):
            return {}
        out = {}
        for k in Api._MERGE_FIELDS:
            v = f.get(k)
            if k == 'cycle_states':
                # Treat None and [] as equivalent
                v = list(v) if isinstance(v, list) else []
            elif k == 'enabled':
                v = bool(v) if v is not None else True
            elif v is None:
                v = ''
            out[k] = v
        return out

    @classmethod
    def _flags_equal_ignoring_runtime(cls, a, b):
        return cls._normalize_flag_for_compare(a) == cls._normalize_flag_for_compare(b)

    @classmethod
    def _flag_diff_fields(cls, a, b):
        na, nb = cls._normalize_flag_for_compare(a), cls._normalize_flag_for_compare(b)
        return [k for k in cls._MERGE_FIELDS if na.get(k) != nb.get(k)]

    @staticmethod
    def _strip_runtime_fields(f):
        """Drop internal _* keys and preset-only metadata when copying into user_flags."""
        if not isinstance(f, dict):
            return {}
        out = {}
        for k, v in f.items():
            if not isinstance(k, str):
                continue
            if k.startswith('_'):
                continue
            if k in ('id', 'added_at', 'color'):
                continue
            out[k] = v
        return out

    def merge_preset_analyze(self, preset_id):
        """Read-only diff between a preset and the current flag set.

        Returns:
          {ok: True, preset_name, to_add: [flag], identical: [name], conflicts: [
            {name, current, preset, diff_fields}
          ]}
        """
        if not self.preset_manager or not self.flag_manager:
            return {'ok': False, 'error': 'Not ready'}

        preset = next((p for p in self.preset_manager.get_presets() if p.get('id') == preset_id), None)
        if not preset:
            return {'ok': False, 'error': 'Preset not found'}

        incoming_flags = preset.get('flags') or []
        to_add = []
        identical = []
        conflicts = []

        with self.flag_manager._lock:
            current_map = {f['name']: f for f in self.flag_manager.user_flags if isinstance(f, dict) and 'name' in f}

            for incoming in incoming_flags:
                if not isinstance(incoming, dict) or 'name' not in incoming:
                    continue
                name = incoming['name']
                clean = self._strip_runtime_fields(incoming)
                if name not in current_map:
                    to_add.append(clean)
                    continue
                current = current_map[name]
                if self._flags_equal_ignoring_runtime(current, clean):
                    identical.append(name)
                else:
                    conflicts.append({
                        'name': name,
                        'current': self._normalize_flag_for_compare(current),
                        'preset':  self._normalize_flag_for_compare(clean),
                        'diff_fields': self._flag_diff_fields(current, clean),
                    })

        return {
            'ok': True,
            'preset_name': preset.get('name', ''),
            'to_add': to_add,
            'identical': identical,
            'conflicts': conflicts,
        }

    def merge_preset_apply(self, preset_id, decisions=None):
        """Apply a merge given per-conflict decisions.

        decisions: {flagName: 'preset' | 'current'}; missing names default to 'current' (no-op).
        Returns {ok, added, replaced, kept, identical} or {ok: False, error}.
        """
        try:
            if not self.preset_manager or not self.flag_manager:
                return {'ok': False, 'error': 'Not ready'}

            preset = next((p for p in self.preset_manager.get_presets() if p.get('id') == preset_id), None)
            if not preset:
                return {'ok': False, 'error': 'Preset not found'}

            decisions = decisions if isinstance(decisions, dict) else {}
            incoming_flags = preset.get('flags') or []

            # Snapshot first so Ctrl+Z restores pre-merge state
            try:
                self.flag_manager.save_history_snapshot(
                    f"Before merge of '{preset.get('name', '?')}'",
                    self.settings.get('history_limit', 20),
                )
            except Exception as e:
                log(f"[!] merge: history snapshot skipped: {e}", (255, 200, 100))

            added = 0
            replaced = 0
            kept = 0
            identical = 0

            # IMPORTANT: only hold _lock while mutating user_flags in-memory.
            # Release it BEFORE calling save_user_flags(), which acquires the same
            # (non-reentrant) lock internally — otherwise the call deadlocks.
            with self.flag_manager._lock:
                current_by_name = {f['name']: f for f in self.flag_manager.user_flags if isinstance(f, dict) and 'name' in f}

                for incoming in incoming_flags:
                    if not isinstance(incoming, dict) or 'name' not in incoming:
                        continue
                    name = incoming['name']
                    clean = self._strip_runtime_fields(incoming)

                    if name not in current_by_name:
                        # Brand new — always add
                        new_flag = dict(clean)
                        new_flag.setdefault('value', '')
                        new_flag.setdefault('type', 'string')
                        new_flag.setdefault('enabled', True)
                        new_flag['original_value'] = get_default_value(name)
                        self.flag_manager.user_flags.append(new_flag)
                        added += 1
                        continue

                    current = current_by_name[name]
                    if self._flags_equal_ignoring_runtime(current, clean):
                        identical += 1
                        continue

                    choice = decisions.get(name, 'current')
                    if choice == 'preset':
                        # Overwrite the merge fields, keep runtime extras (original_value etc.)
                        for k in self._MERGE_FIELDS:
                            if k == 'cycle_states':
                                current[k] = list(clean.get(k) or [])
                            elif k == 'enabled':
                                current[k] = bool(clean.get(k, True))
                            elif k in clean:
                                current[k] = clean[k]
                            else:
                                current.pop(k, None)
                        replaced += 1
                    else:
                        kept += 1

            # Lock released — now safe to call save_user_flags() (it re-acquires _lock).
            self.flag_manager.save_user_flags()

            log(f"[+] Merge '{preset.get('name', '?')}': +{added} added, ~{replaced} replaced, ={kept} kept, ={identical} identical")
            if self.settings.get('auto_apply') and (added > 0 or replaced > 0):
                try:
                    self.inject()
                except AttributeError:
                    pass  # inject() not present in this build
                except Exception as e:
                    log(f"[!] auto-apply after merge failed: {e}", (255, 100, 100))

            return {'ok': True, 'added': added, 'replaced': replaced, 'kept': kept, 'identical': identical}
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            log(f"[-] merge_preset_apply crashed: {e}\n{tb}", (255, 85, 85))
            return {'ok': False, 'error': str(e)}

    def merge_preset(self, preset_id):
        """Backwards-compat shim: defaults every conflict to 'preset' (matches the
        user's 'use preset for all' intent). New UI calls analyze + apply directly.
        """
        analysis = self.merge_preset_analyze(preset_id)
        if not analysis.get('ok'):
            return analysis
        decisions = {c['name']: 'preset' for c in analysis.get('conflicts', [])}
        return self.merge_preset_apply(preset_id, decisions)

    def apply_preset(self, preset_id):
        if not self.preset_manager or not self.flag_manager:
            return {'ok': False, 'error': 'Not ready'}
            
        presets = self.preset_manager.get_presets()
        target = next((p for p in presets if p["id"] == preset_id), None)
        if not target:
            return {'ok': False, 'error': 'Preset not found'}
            
        self.flag_manager.save_history_snapshot(f"Before applying preset '{target['name']}'", self.settings.get('history_limit', 20))

        # Map the new preset's flags over. Ensure they have 'enabled': True set.
        new_user_flags = []
        for pf in target['flags']:
            nf = dict(pf)
            # Phase 2: Refresh types during application (Source of truth: Name)
            nf['type'] = infer_type_from_name(nf['name']) or nf.get('type', 'string')
            if 'enabled' not in nf:
                nf['enabled'] = True
            new_user_flags.append(nf)

        # A4: clean-slate switch — revert the OUTGOING preset's flags in live
        # memory first so two presets don't intercept each other. Pause the
        # watchdog around the swap so it can't re-enforce the old flags mid-switch.
        with self.flag_manager._lock:
            old_flags = list(self.flag_manager.user_flags)
        attached = bool(self.roblox_manager and self.roblox_manager.is_attached)

        self.flag_manager.pause_watchdog()
        try:
            if attached and old_flags:
                # Professional switch: don't kill-switch every old flag. Revert
                # ONLY the flags the new preset won't actively set (removed or
                # now-disabled); shared flags are overwritten in place by the
                # apply below, and untouched flags are left alone.
                to_revert = _preset_switch_revert_set(old_flags, new_user_flags)
                kept = len(old_flags) - len(to_revert)
                if to_revert:
                    reverted = self.flag_manager.revert_flags_in_memory(to_revert)
                    log(f"[*] Preset switch: kept {kept} shared flag(s), reverted "
                        f"{reverted}/{len(to_revert)} removed flag(s)")
                else:
                    log(f"[*] Preset switch: all {kept} previous flag(s) carried over "
                        f"— nothing to revert")

            with self.flag_manager._lock:
                self.flag_manager.user_flags = new_user_flags
            self.flag_manager.save_user_flags()

            log(f"[+] Applied preset '{target['name']}' ({len(new_user_flags)} flags)")

            if self.settings.get('auto_apply'):
                # inject() overwrites ClientAppSettings.json with exactly the new
                # set + writes live memory, so nothing carries over.
                self.inject()
            else:
                # Auto Apply OFF: live memory is already reverted above. Clear the
                # JSON too so the OLD preset can't come back on the next launch
                # (neither old nor new applies until the user manually Applies).
                try:
                    self.clear_clientapp_json()
                except Exception:
                    pass
        finally:
            self.flag_manager.resume_watchdog()
        return {'ok': True}

    def update_preset(self, preset_id, name, color):
        if not self.preset_manager: return False
        success = self.preset_manager.update_preset(preset_id, name, color)
        if success: log(f"[*] Updated preset {name}")
        return success

    def update_preset_flags(self, preset_id, flags):
        """A2: commit edited values + deletions from the preset editor."""
        if not self.preset_manager: return False
        if not isinstance(flags, list): return False
        success = self.preset_manager.update_preset_flags(preset_id, flags)
        if success: log(f"[*] Saved preset edits ({len(flags)} flags)")
        return success

    def delete_preset(self, preset_id):
        if not self.preset_manager: return False
        success = self.preset_manager.delete_preset(preset_id)
        if success: log(f"[-] Deleted preset")
        return success

    def reorder_presets(self, ids):
        if not self.preset_manager: return False
        return self.preset_manager.reorder_presets(ids)

    # ─── Status ───

    def get_status(self):
        """Return current connection status."""
        fm = self.flag_manager
        rm = self.roblox_manager
        needs_refresh = False
        if fm:
            # Check for scanner completion (removes startup question marks)
            if fm.offsets_loaded and not self._last_offsets_loaded_state:
                self._last_offsets_loaded_state = True
                needs_refresh = True
                log("[*] Scanner finished, updating UI with recognized flags", (100, 255, 100))

            # Check for manual application
            if fm.last_apply_time > self._last_apply_time:
                self._last_apply_time = fm.last_apply_time
                needs_refresh = True

        # One-shot refresh requested by the monitor loop (e.g. Roblox closed).
        if self._needs_ui_refresh:
            needs_refresh = True
            self._needs_ui_refresh = False
        return {
            'attached': bool(rm and rm.is_attached),
            'pid': (rm.pid or 0) if rm else 0,
            'flag_count': len(fm.user_flags) if fm else 0,
            'needs_refresh': needs_refresh,
            'maximized': getattr(self, '_maximized', False),
        }

    def get_monitor_status(self):
        """Return a compact, cross-platform Roblox process health snapshot."""
        result = {
            'running': False, 'attached': False, 'pid': 0, 'cpu_percent': 0.0,
            'memory_bytes': 0, 'memory_label': '0 MB', 'priority': '—',
            'version': None, 'offsets_version': None, 'offset_count': 0,
            'offsets_ok': False, 'session_seconds': 0,
        }
        rm = self.roblox_manager
        fm = self.flag_manager
        pids = rm.list_roblox_processes() if rm else []
        pid = int(rm.pid or 0) if rm and rm.is_attached else (int(pids[0]) if pids else 0)
        result.update(running=bool(pid), attached=bool(rm and rm.is_attached), pid=pid)

        if pid:
            try:
                import psutil
                proc = psutil.Process(pid)
                cpu = proc.cpu_percent(interval=None)
                memory = int(proc.memory_info().rss)
                try:
                    priority = str(proc.nice())
                    if sys.platform == 'win32':
                        priority = {
                            psutil.IDLE_PRIORITY_CLASS: 'Low',
                            psutil.BELOW_NORMAL_PRIORITY_CLASS: 'Below normal',
                            psutil.NORMAL_PRIORITY_CLASS: 'Normal',
                            psutil.ABOVE_NORMAL_PRIORITY_CLASS: 'Above normal',
                            psutil.HIGH_PRIORITY_CLASS: 'High',
                            psutil.REALTIME_PRIORITY_CLASS: 'Realtime',
                        }.get(proc.nice(), priority)
                except (psutil.AccessDenied, AttributeError):
                    priority = 'Unavailable'
                result.update(
                    cpu_percent=round(float(cpu), 1), memory_bytes=memory,
                    memory_label=f'{memory / (1024 ** 3):.2f} GB' if memory >= 1024 ** 3 else f'{memory / (1024 ** 2):.0f} MB',
                    priority=priority,
                )
            except Exception:
                pass
            try:
                from src.utils.roblox_account import get_session_duration
                result['session_seconds'] = int(get_session_duration(pid))
            except Exception:
                pass

        try:
            from src.core.roblox_manager import RobloxManager
            result['version'] = RobloxManager.get_roblox_version_string()
        except Exception:
            pass
        try:
            from src.core import offset_loader
            result['offsets_version'] = offset_loader.last_source_build()
        except Exception:
            pass
        if fm:
            result['offset_count'] = len(fm.preset_flags_list)
            result['offsets_ok'] = bool(fm.offsets_loaded and result['offsets_version'])
            if result['version'] and result['offsets_version']:
                result['offsets_ok'] = result['version'] == result['offsets_version']
        return result

    def get_attachment_targets(self):
        """Return selectable Roblox processes and the current attachment."""
        rm = self.roblox_manager
        if not rm:
            return {'attached': False, 'selected_pid': 0, 'processes': [], 'account': None}
        pids = rm.list_roblox_processes()
        selected = int(rm.pid or 0) if rm.is_attached and rm.pid in pids else 0

        try:
            from src.utils.roblox_account import get_roblox_profile, record_session_start, cleanup_sessions, get_session_duration
            cleanup_sessions(pids)
            if selected:
                record_session_start(selected)
            account = get_roblox_profile()
            session_seconds = int(get_session_duration(selected)) if selected else 0
        except Exception:
            account = None
            session_seconds = 0

        is_applied = bool(self.flag_manager and getattr(self.flag_manager, 'flags_applied', False) and selected)

        return {
            'attached': bool(selected),
            'selected_pid': selected,
            'session_seconds': session_seconds,
            'applied': is_applied,
            'account': account,
            'processes': [
                {
                    'pid': pid,
                    'label': f'Roblox Player · PID {pid}',
                    'attached': pid == selected,
                }
                for pid in pids
            ],
        }

    def attach_to_process(self, pid):
        """Attach only to a currently detected Roblox Player process."""
        rm = self.roblox_manager
        if not rm:
            return {'ok': False, 'error': 'Process manager is unavailable'}
        try:
            target_pid = int(pid)
        except (TypeError, ValueError):
            return {'ok': False, 'error': 'Invalid process selection'}
        if target_pid not in rm.list_roblox_processes():
            return {'ok': False, 'error': 'That Roblox process is no longer running'}
        if not rm.attach(target_pid):
            return {'ok': False, 'error': 'Could not attach to that Roblox process'}
        log(f'[*] Selected Roblox process PID {target_pid}', (170, 120, 255))
        return {'ok': True, 'pid': target_pid}

    def detach_from_process(self):
        """Disconnect Vellium Tweaker from the selected process without closing it."""
        rm = self.roblox_manager
        if not rm or not rm.is_attached:
            return {'ok': True, 'pid': 0}
        old_pid = int(rm.pid or 0)
        rm.reset()
        rm.preferred_pid = None
        log(f'[*] Detached from Roblox process PID {old_pid}', (190, 160, 255))
        return {'ok': True, 'pid': old_pid}

    def end_roblox_process(self, pid):
        """Terminate one selected, currently detected Roblox process."""
        rm = self.roblox_manager
        if not rm:
            return {'ok': False, 'error': 'Process manager is unavailable'}
        try:
            target_pid = int(pid)
        except (TypeError, ValueError):
            return {'ok': False, 'error': 'Invalid process selection'}
        if target_pid not in rm.list_roblox_processes():
            return {'ok': False, 'error': 'That Roblox process is no longer running'}
        if not rm.terminate_roblox_process(target_pid):
            return {'ok': False, 'error': 'Windows could not end that Roblox process'}
        self.processed_pids.discard(target_pid)
        log(f'[-] Ended Roblox process PID {target_pid}', (255, 130, 160))
        return {'ok': True, 'pid': target_pid}

    # ─── Logs ───

    def clear_logs(self):
        clear_console_logs()
        _, total, tail_epoch = get_logs_since(10**18, 0)
        return {'ok': True, 'total': total, 'tail_epoch': tail_epoch}

    def get_logs(self, since_index=0, since_tail_epoch=0):
        """Return new log entries since the given monotonic sequence number.

        Uses `get_logs_since` so the console keeps updating after the 1000-line
        ring buffer starts dropping old lines (previously froze 'after a while').

        Each entry may carry a `replace` flag: when true the entry supersedes
        the caller's previously-rendered last line (used for consecutive
        duplicate collapse — one line with an "xN" counter that updates in
        place, instead of the log flooding with repeated identical output).

        `since_tail_epoch` is the last tail-mutation counter the client saw;
        the response echoes the current value in `tail_epoch`. When the
        server has no new appends but the tail was mutated, the response
        returns just the mutated tail so the client updates its rendering.
        """
        logs_out = []
        new_logs, total, tail_epoch = get_logs_since(since_index,
                                                     since_tail_epoch)
        for entry in new_logs:
            # Backward compatibility: old entries were 2-tuples (msg, color).
            if len(entry) == 3:
                msg, color, replace = entry
            else:
                msg, color = entry
                replace = False
            logs_out.append({
                'msg': msg,
                'color': list(color) if color else None,
                'replace': bool(replace),
            })
        return {
            'logs': logs_out,
            'total': total,
            'tail_epoch': tail_epoch,
        }

    # ─── Discord Auth & Terms ───

    def get_auth_state(self):
        """Retrieve persisted Discord login & terms agreement state."""
        try:
            from src.utils.discord_auth import get_auth_state
            return get_auth_state()
        except Exception:
            return {'authenticated': False, 'terms_accepted': False, 'discord_user': None}

    def save_auth_state(self, state):
        """Persist Discord login & terms agreement state."""
        try:
            from src.utils.discord_auth import save_auth_state
            return {'ok': save_auth_state(state)}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def detect_discord_user(self):
        """Query local Discord desktop application for authenticated profile."""
        try:
            from src.utils.discord_auth import detect_local_discord_user
            user = detect_local_discord_user()
            if user:
                return {'ok': True, 'user': user}
            return {'ok': False, 'error': 'Discord desktop client not detected'}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def validate_license_key(self, key_code, discord_user=None):
        """Verify access key against remote database."""
        try:
            from src.utils.discord_auth import validate_license_key
            return validate_license_key(key_code, discord_user)
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    # ─── Window Controls ───

    def _get_hwnd(self):
        """Helper to find the true top-level HWND for the WebView2 window.

        pywebview 6.x exposes the WinForms window as ``window.native`` (the Form
        object); its HWND is ``native.Handle.ToInt32()``. Older builds used
        ``native_id``. Try both so this works across versions."""
        if not self._window:
            return None
        hwnd = None
        try:
            native = getattr(self._window, 'native', None)
            if native is not None and hasattr(native, 'Handle'):
                hwnd = native.Handle.ToInt32()
        except Exception:
            hwnd = None
        if not hwnd:
            hwnd = getattr(self._window, 'native_id', None)
        if not hwnd:
            return None
        # Safety: Ensure we have the top-level window
        try:
            parent = ctypes.windll.user32.GetAncestor(hwnd, 2)  # GA_ROOT
            return parent if parent else hwnd
        except Exception:
            return hwnd

    def minimize_window(self):
        if self._window:
            self._window.minimize()

    def toggle_maximize(self):
        """Toggle between maximized and normal window state.

        Uses work-area sizing instead of true OS maximize so the Windows
        taskbar stays visible (frameless windows otherwise cover it)."""
        if self._window:
            try:
                is_max = getattr(self, '_maximized', False)
                if not is_max:
                    # Save current geometry for restore
                    try:
                        self._pre_max_rect = (
                            self._window.x, self._window.y,
                            self._window.width, self._window.height,
                        )
                    except Exception:
                        self._pre_max_rect = None

                    # Get work area (screen minus taskbar) via Win32
                    try:
                        import ctypes.wintypes
                        rect = ctypes.wintypes.RECT()
                        ctypes.windll.user32.SystemParametersInfoW(
                            0x0030, 0, ctypes.byref(rect), 0  # SPI_GETWORKAREA
                        )
                        wa_x, wa_y = rect.left, rect.top
                        wa_w = rect.right - rect.left
                        wa_h = rect.bottom - rect.top
                    except Exception:
                        wa_x, wa_y, wa_w, wa_h = 0, 0, 1920, 1040

                    self._window.move(wa_x, wa_y)
                    self._window.resize(wa_w, wa_h)
                    self._maximized = True
                else:
                    # Restore saved geometry or fall back to settings
                    pre = getattr(self, '_pre_max_rect', None)
                    if pre:
                        self._window.move(pre[0], pre[1])
                        self._window.resize(pre[2], pre[3])
                    else:
                        w = self.settings.get('window_width', 1380)
                        h = self.settings.get('window_height', 780)
                        self._window.resize(w, h)
                    self._maximized = False

                self.settings['window_maximized'] = self._maximized
                Config.save_settings(self.settings)

                return self._maximized
            except Exception as e:
                log(f"[!] Maximize error: {e}", (255, 100, 100))
        return False

    def start_drag(self):
        """Invoke native Win32 window dragging."""
        hwnd = self._get_hwnd()
        if hwnd:
            try:
                ctypes.windll.user32.ReleaseCapture()
                # 0x0112 = WM_SYSCOMMAND, 0xF012 = SC_MOVE + 2 (Drag)
                ctypes.windll.user32.PostMessageW(hwnd, 0x0112, 0xF012, 0)
            except Exception as e:
                log(f"[!] Drag error: {e}", (255, 100, 100))

    def start_resize(self, direction):
        """Invoke native Win32 window resizing."""
        hwnd = self._get_hwnd()
        if hwnd:
            try:
                # 0x0112 = WM_SYSCOMMAND, 0xF000 = SC_SIZE
                # SC_SIZE + direction (1=L, 2=R, 3=T, 4=TL, 5=TR, 6=B, 7=BL, 8=BR)
                ctypes.windll.user32.ReleaseCapture()
                ctypes.windll.user32.PostMessageW(hwnd, 0x0112, 0xF000 | direction, 0)
            except Exception as e:
                log(f"[!] Resize error: {e}", (255, 100, 100))

    def get_window_bounds(self):
        """Return the current window bounds for JS-based resizing fallback."""
        if self._window:
            try:
                # pywebview usually has width and height attributes
                return {
                    'width': self._window.width,
                    'height': self._window.height,
                    'x': getattr(self._window, 'x', 0),
                    'y': getattr(self._window, 'y', 0)
                }
            except Exception:
                pass
        return {'width': 1050, 'height': 780, 'x': 0, 'y': 0}

    def resize_window(self, width, height, anchor_east=False, anchor_south=False):
        """Resize the window from the frontend, anchoring the opposite edge.

        WebView2 intercepts the WndProc messages the native SC_SIZE/SetWindowPos
        resize relies on, so pywebview's own resize(fix_point=...) is the
        reliable path for frameless edge-resizing. anchor_east keeps the RIGHT
        edge fixed (when dragging the left edge); anchor_south keeps the BOTTOM
        edge fixed (when dragging the top edge)."""
        if not self._window:
            return
        w = max(800, int(width))
        h = max(600, int(height))
        try:
            from webview.window import FixPoint
            horiz = FixPoint.EAST if anchor_east else FixPoint.WEST
            vert = FixPoint.SOUTH if anchor_south else FixPoint.NORTH
            self._window.resize(w, h, fix_point=horiz | vert)
        except TypeError:
            # Older pywebview without fix_point support.
            self._window.resize(w, h)
        except Exception:
            pass

    def get_window_rect(self):
        """Return the true physical-pixel window rect (GetWindowRect).

        pywebview's own anchored resize() does NOT apply the DPI scale
        factor (winforms.py resize() vs move()), so on any non-100%
        display every left/top edge resize mis-positions the window and
        it "walks". We drive resizing from raw Win32 coordinates instead,
        which are unit-consistent at any scale."""
        hwnd = self._get_hwnd()
        if hwnd:
            try:
                rect = wintypes.RECT()
                ok = ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                if not ok:
                    log(f"[!] GetWindowRect failed (hwnd={hwnd})", (255, 100, 100))
                    return None
                return {
                    'left': rect.left,
                    'top': rect.top,
                    'right': rect.right,
                    'bottom': rect.bottom,
                }
            except Exception as e:
                log(f"[!] get_window_rect error: {e}", (255, 100, 100))
        else:
            log("[!] get_window_rect: no hwnd", (255, 100, 100))
        return None

    def set_window_rect(self, x, y, width, height):
        """Apply an absolute physical-pixel window rect in one SetWindowPos.

        JS computes the target rect from the start rect (captured once at
        mousedown) plus the cursor delta, so there is no per-call
        re-anchoring and therefore no drift. Clamping at the minimum size
        produces a constant edge position, so the window holds still
        instead of translating across the screen."""
        hwnd = self._get_hwnd()
        if not hwnd:
            log("[!] set_window_rect: no hwnd", (255, 100, 100))
            return
        try:
            w = max(1, int(width))
            h = max(1, int(height))
            # Mirror pywebview's own working SetWindowPos call (winforms.py):
            # no strict argtypes, hwndInsertAfter=None. Flags keep z-order and
            # focus untouched while still repositioning + resizing.
            # SWP_NOZORDER(0x4) | SWP_NOACTIVATE(0x10) | SWP_SHOWWINDOW(0x40)
            ctypes.windll.user32.SetWindowPos(
                int(hwnd), None, int(x), int(y), w, h, 0x0054
            )
        except Exception as e:
            log(f"[!] set_window_rect error: {e}", (255, 100, 100))


    def save_ui_layout(self, layout):
        """Save the UI layout (sidebar, console) to settings."""
        if not layout:
            return
        
        try:
            self.settings['sidebar_width'] = layout.get('sidebarWidth', 240)
            self.settings['console_height'] = layout.get('consoleHeight', 180)
            self.settings['sidebar_collapsed'] = layout.get('isSidebarCollapsed', False)
            # We don't save to disk on every resize to keep it snappy.
            # State will be persisted on exit/move.
        except Exception as e:
            log(f"[!] Error updating UI layout state: {e}", (255, 100, 100))

    def save_window_state(self):
        """Save the current window geometry to settings."""
        if not self._window:
            return
        
        try:
            # Update maximized status
            is_max = getattr(self, '_maximized', False)
            self.settings['window_maximized'] = is_max
            
            # ONLY save dimensions if NOT maximized
            if not is_max:
                self.settings['window_width'] = self._window.width
                self.settings['window_height'] = self._window.height
            
            Config.save_settings(self.settings)
        except Exception as e:
            log(f"[!] Error saving window state: {e}", (255, 100, 100))

    def close_window(self):
        """Handle window close request from UI."""
        if self._window:
            # Check the setting from our loaded config
            if self.settings.get('close_to_tray', False):
                # Save state before hiding
                self.save_window_state()
                # Hide to tray via MainWindow instead of destroying
                if hasattr(self, '_app'):
                    self._app.hide_window()
                else:
                    self._window.hide()
                log("[*] Application hidden to system tray", (180, 180, 200))
            else:
                self.exit_app()

    def exit_app(self):
        """Full application exit (from UI or Tray)."""
        log("[*] Closing application...", (255, 100, 100))
        self.save_window_state()
        if self._should_wipe_clientapp():
            try:
                self.clear_clientapp_json()
            except Exception:
                pass
        if hasattr(self, '_app'):
            self._app.exit_app()
        elif self._window:
            self._window.destroy()

    # ─── Background Monitor ───

    def _auto_unlock_fps(self):
        """On startup, apply OR undo the file-based FPS unlock per the setting.
        ON (default) = FramerateCap=9999 + read-only. OFF = release the lock so
        the user's own FPS flags can take effect. Best-effort and quiet."""
        try:
            from src.core import fps_unlocker
            if self.settings.get('fps_unlocker_enabled', True):
                changed, msg = fps_unlocker.unlock_fps()
                if changed:
                    log(f"[*] FPS unlocked ({msg})", (150, 180, 150))
            else:
                changed, msg = fps_unlocker.restore_fps()
                if changed:
                    log(f"[*] FPS Unlocker off — {msg}", (150, 180, 150))
        except Exception:
            pass

    def set_fps_unlocker(self, enabled):
        """Toggle the FPS unlocker. Saves the setting, applies/undoes the file
        lock immediately, and refreshes the editor so FPS-flag badges update."""
        en = bool(enabled)
        self.settings['fps_unlocker_enabled'] = en
        Config.save_settings(self.settings)
        try:
            from src.core import fps_unlocker
            changed, msg = fps_unlocker.unlock_fps() if en else fps_unlocker.restore_fps()
            log(f"[*] FPS Unlocker {'ON' if en else 'OFF'} ({msg})", (150, 180, 150))
        except Exception:
            pass
        if self._window:
            try:
                self._window.evaluate_js(
                    "if (typeof refreshConfig === 'function') refreshConfig();")
            except Exception:
                pass
        return en

    def _should_wipe_clientapp(self):
        """True when leftover ClientAppSettings.json should be emptied.

        Auto Apply ON keeps the file so the next Play/shortcut boots with flags
        already on disk. Set KEEP_JSON_WHEN_AUTO_APPLY to False to restore
        wipe-on-close / wipe-on-FFM-exit.
        """
        if not self.settings.get('auto_clear_json', True):
            return False
        if KEEP_JSON_WHEN_AUTO_APPLY and self.settings.get('auto_apply', False):
            return False
        if RobloxManager.startup_write_in_progress():
            return False
        return True

    def _auto_apply_skip_json(self):
        """Skip a second JSON write when Play/Join (or a prior Apply) already
        staged ClientAppSettings.json."""
        try:
            if RobloxManager.startup_write_in_progress():
                return True
            return bool(RobloxManager.clientapp_json_has_flags())
        except Exception:
            return False

    def _monitor_poll_seconds(self, pid, auto_on):
        """Fast poll while hunting for a new Roblox PID; slow once attached."""
        if not pid:
            return MONITOR_POLL_FAST
        if auto_on and pid not in self.processed_pids:
            return MONITOR_POLL_FAST
        return MONITOR_POLL_SLOW

    def _reconcile_idle_clear(self):
        """Enforce the rule: auto-apply OFF + Roblox not running ⇒ no flags left
        on disk. Wipes every ClientAppSettings.json (per-version + legacy global)
        the moment we're idle, so a closed Roblox never carries staged overrides
        from a manual Apply, a previous session, or a crash.

        Safe by construction: FFM only pre-stages flags to disk while auto-apply
        is ON (except a short Play-handler write window), so clearing when it's
        OFF can't undermine the cold/website-launch path. No-ops (no disk write)
        when already clean, when auto-apply is ON, when a Play write is in
        progress, when the user disabled auto-clear, or when Roblox is open."""
        try:
            if not self.roblox_manager or not self.flag_manager:
                return
            if not self._should_wipe_clientapp():
                return
            if self.roblox_manager.find_roblox_process():
                return  # Roblox is open — leave its live flags alone
            if RobloxManager.clientapp_json_has_flags():
                log("[*] Idle (auto-apply off, Roblox closed) — clearing leftover flags", (180, 200, 180))
                self.clear_clientapp_json()
        except Exception:
            pass

    def _monitor_loop(self):
        """Background thread: monitor Roblox process (Auto Apply)."""
        while True:
            try:
                if not self.roblox_manager or not self.flag_manager:
                    time.sleep(5)
                    continue

                # We call find_roblox_process manually to avoid unwanted side effects of attach() if we aren't ready
                pid = self.roblox_manager.find_roblox_process()
                
                if pid:
                    delay = int(self.settings.get('scheduled_apply_delay', 0) or 0)
                    auto_on = self.settings.get('auto_apply', False)
                    new_pid = pid not in self.processed_pids
                    # Defense-in-depth: with auto-apply OFF and a NEW Roblox
                    # PID, verify ClientAppSettings.json is empty. If it
                    # isn't, a stale write from a prior session or a race with
                    # the startup reconciler let Roblox read it — that's the
                    # "auto-apply off but flags still applied on first launch"
                    # bug. We can't unring the bell for this PID (Roblox
                    # already read the file), but clearing NOW keeps every
                    # subsequent launch clean, and the log line makes the
                    # cause visible in the console.
                    if not auto_on and new_pid and self.settings.get('auto_clear_json', True):
                        try:
                            from src.core.roblox_manager import RobloxManager as _RM
                            if _RM.startup_write_in_progress():
                                pass  # Play handler write still in TTL; leave JSON
                            elif _RM.clientapp_json_has_flags():
                                log(f"[!] Auto-apply is OFF but ClientAppSettings.json wasn't clean when Roblox launched (PID {pid}) — some flags may have applied on this launch. Clearing to keep subsequent launches clean.", (255, 200, 100))
                                self.clear_clientapp_json()
                        except Exception:
                            pass
                    # If Auto Apply is on, and this is a new pid we haven't processed
                    if auto_on and new_pid and self.flag_manager.offsets_loaded:
                        self.processed_pids.add(pid)
                        # We must attach first so inject() knows it's ready
                        if self.roblox_manager.attach():
                            if delay > 0:
                                # Scheduled Apply: defer a memory-only injection.
                                self._scheduled_due[pid] = time.time() + delay
                                log(f"[*] Scheduled Apply: waiting {delay}s before injecting (PID {pid})...", (100, 255, 255))
                            else:
                                # A new Roblox launch overrides the paused
                                # state (per Automatic Launch semantics). If
                                # flags are paused, resume through the same
                                # restore path a manual Apply would use — the
                                # thread it spawns handles re-enable + inject.
                                if self.settings.get('killswitch_active', False):
                                    log(f"[*] Auto Apply: New Roblox detected (PID {pid}), flags were paused — resuming and applying...", (100, 200, 255))
                                    self.restore_flags()
                                else:
                                    log(f"[*] Auto Apply: New Roblox detected (PID {pid}), applying flags...", (100, 255, 255))
                                    # First auto-apply for this launch -> play sound.
                                    # Skip JSON when Play/Join already staged the file.
                                    self.inject(
                                        skip_json=self._auto_apply_skip_json(),
                                        play_sound=True,
                                    )
                    elif auto_on and new_pid and not self.flag_manager.offsets_loaded:
                        # Roblox is already running but our offsets are still
                        # loading (typical when FFM opens AFTER a Play-through-
                        # browser launch, or after Roblox was started while FFM
                        # was closed). DO NOT mark this pid as processed — if we
                        # did, we'd never come back to apply flags once offsets
                        # finish loading. Just attach and let the next tick
                        # retry. Log once so the user can see we're waiting.
                        if not getattr(self, '_awaiting_offsets_pid', None) == pid:
                            self._awaiting_offsets_pid = pid
                            log(f"[*] Auto Apply: Roblox detected (PID {pid}) — waiting for flag definitions to finish loading...", (100, 200, 255))
                        self.roblox_manager.attach()
                    else:
                        # Even with auto-apply OFF, mark this pid as processed
                        # so we don't repeat the diagnostic check every tick.
                        if new_pid:
                            self.processed_pids.add(pid)
                        # Just attach to update status
                        self.roblox_manager.attach()
                    # Fire any due scheduled injection for the still-running pid.
                    if pid in self._scheduled_due and time.time() >= self._scheduled_due[pid]:
                        del self._scheduled_due[pid]
                        if self.roblox_manager.is_attached:
                            if self.settings.get('killswitch_active', False):
                                log(f"[*] Scheduled Apply: firing (PID {pid}) — flags were paused, resuming...", (100, 200, 255))
                                self.restore_flags()
                            else:
                                log(f"[*] Scheduled Apply: injecting now (PID {pid})", (100, 255, 255))
                                # First (scheduled) auto-apply for this launch -> play sound.
                                self.inject(skip_json=True, play_sound=True)
                    self._last_seen_roblox_pid = pid
                else:
                    # One-shot Roblox-exit transition: only fire the clear when
                    # we go from "saw a pid last tick" -> "no pid this tick".
                    just_exited = self._last_seen_roblox_pid is not None
                    self.roblox_manager.reset()
                    self.flag_manager.flags_applied = False
                    # Clear statuses
                    cleared_any = False
                    with self.flag_manager._lock:
                        for f in self.flag_manager.user_flags:
                            if f.get('_status'):
                                f['_status'] = None
                                cleared_any = True
                    # Tell the UI to re-render so green LIVE dots don't linger
                    # after Roblox closes.
                    if cleared_any or just_exited:
                        self._needs_ui_refresh = True
                    # Clean up old PIDs to prevent unbounded growth
                    self.processed_pids.clear()
                    self._scheduled_due.clear()
                    self._last_seen_roblox_pid = None
                    self._awaiting_offsets_pid = None
                    if just_exited and self._should_wipe_clientapp():
                        log("[*] Roblox closed — clearing ClientAppSettings.json", (180, 200, 180))
                        try:
                            self.clear_clientapp_json()
                        except Exception:
                            pass
                    elif just_exited and self.settings.get('auto_apply', False):
                        log("[*] Roblox closed — leaving ClientAppSettings.json (Auto Apply on)",
                            (180, 200, 180))
                    # Idle enforcement: with auto-apply OFF and Roblox closed,
                    # no flags should ever sit on disk — wipe leftovers from a
                    # manual Apply, a prior session, or a crash (not just the
                    # exit transition above). Cheap: only writes when dirty.
                    self._reconcile_idle_clear()
            except Exception as e:
                log(f"[!] Monitor error: {e}", (255, 100, 100))
                time.sleep(5)  # Back off on error
                continue
            time.sleep(self._monitor_poll_seconds(
                pid, self.settings.get('auto_apply', False)))
