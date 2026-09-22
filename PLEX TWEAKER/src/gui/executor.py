r"""
executor.py — QuorumAPI.dll (.NET) integration for the Vellium Executor window.

The real QuorumAPI is a managed **.NET 8** assembly exposing a ``QuorumModule``
class. We host it in-process through pythonnet's *coreclr* runtime and drive it
straight from Python, so the existing pywebview / React UI works without any
WinForms or separate C# host app.

Public methods (called from exec/App.jsx):
  executor_attach()     -> QuorumModule.AttachAPI(noCmd); result read from QuorumStatus
  executor_status()     -> QuorumModule.IsAttached()
  executor_run(script)  -> QuorumModule.ExecuteScript(script)

Implementation notes:
  * The DLL is obfuscated with Cyrillic-homoglyph decoy methods (e.g. ``AttachAРI``
    with a Cyrillic 'Р'). Only the pure-ASCII members used below are the real API.
  * ``from QuorumAPI import ...`` does not resolve under the coreclr host, so we
    load the assembly with Assembly.LoadFrom and construct via Activator; instance
    methods/fields then bind naturally through pythonnet.
  * Injecting into Roblox requires the host process to be **elevated (admin)**.
"""

import sys
import threading
import ctypes
from pathlib import Path

from src.utils.logger import log
from src.utils.platform_support import IS_WINDOWS, windows_only_error

# ── QuorumStates enum members (from the assembly) ────────────────────────────
#   Attaching, Attached, NotAttached, NoProcessFound, TamperDetected, Error, Executed
_ATTACH_OK_STATES = ('Attached', 'Attaching', 'Executed')
_EXEC_OK_STATES = ('Executed', 'Attached')

# ── Tunable QuorumModule behaviour flags (static fields on the .NET type) ─────
QUORUM_USE_AUTOUPDATE     = True    # let it fetch its runtime deps when attaching
QUORUM_USE_AUTOUPDATE_API = False   # do NOT let it overwrite the DLL we've loaded
QUORUM_AUTOUPDATE_LOGS    = False   # no injector console log spam
QUORUM_DUMB_MODE          = False   # no blocking MessageBox popups — we surface errors in the UI
QUORUM_ATTACH_NOCMD       = True    # hide the injector console window

_lock = threading.RLock()
_quorum = None        # cached QuorumModule instance
_qm_type = None       # cached .NET Type (for static calls / field access)
_init_error = None    # remember a hard init failure so we don't retry endlessly


def _get_exec_dir() -> Path | None:
    """Resolve the exec/ folder that actually contains QuorumAPI.dll.

    More than one folder named ``exec`` can exist in the tree; prefer the one
    holding the DLL, falling back to a bare ``exec`` only if none contain it.
    """
    markers = ('QuorumAPI.dll',)
    try:
        if getattr(sys, 'frozen', False):
            base = Path(sys.executable).parent
        else:
            base = Path(__file__).resolve().parent.parent.parent
        fallback = None
        for candidate in (base / 'exec', base.parent / 'exec'):
            if not candidate.exists():
                continue
            if any((candidate / m).exists() for m in markers):
                return candidate
            if fallback is None:
                fallback = candidate
        return fallback
    except Exception:
        return None


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _state_name(value) -> str:
    """Render a QuorumStates enum value as its member name."""
    try:
        return value.ToString()
    except Exception:
        return str(value)


def _ensure_quorum():
    """Load coreclr + QuorumAPI.dll and construct QuorumModule exactly once.

    Returns (instance, type). Raises RuntimeError with a user-friendly message
    on failure (and caches it so repeated clicks don't re-trigger a slow load).
    """
    global _quorum, _qm_type, _init_error
    with _lock:
        if _quorum is not None:
            return _quorum, _qm_type
        if _init_error is not None:
            raise RuntimeError(_init_error)
        try:
            exec_dir = _get_exec_dir()
            if exec_dir is None:
                raise RuntimeError('exec/ folder not found next to the app')
            dll = exec_dir / 'QuorumAPI.dll'
            if not dll.exists():
                raise RuntimeError(f'QuorumAPI.dll not found ({dll})')

            # Host modern .NET (coreclr). Must happen before `import clr`.
            try:
                from pythonnet import load as _pnload
                _pnload('coreclr')
            except Exception as e:
                # Already-loaded is fine; a genuine failure surfaces on import below.
                log(f'[*] Executor: coreclr load note: {e}', (150, 150, 150))

            import clr  # noqa: F401  (registers the CLR import hooks)
            from System.Reflection import Assembly
            from System import Activator

            asm = Assembly.LoadFrom(str(dll))
            t = asm.GetType('QuorumAPI.QuorumModule', True)

            for name, val in (
                ('UseAutoUpdate', QUORUM_USE_AUTOUPDATE),
                ('UseAutoUpdateAPI', QUORUM_USE_AUTOUPDATE_API),
                ('_AutoUpdateLogs', QUORUM_AUTOUPDATE_LOGS),
                ('DumbMode', QUORUM_DUMB_MODE),
            ):
                try:
                    t.GetField(name).SetValue(None, val)
                except Exception as e:
                    log(f'[~] Executor: could not set {name}: {e}', (200, 200, 120))

            inst = Activator.CreateInstance(t)
            _quorum, _qm_type = inst, t
            log('[+] Executor: QuorumAPI.dll loaded (.NET 8 via coreclr).', (120, 220, 120))
            return _quorum, _qm_type
        except Exception as e:
            _init_error = f'Failed to load QuorumAPI.dll: {e}'
            log(f'[!] Executor init error: {e}', (255, 100, 100))
            raise RuntimeError(_init_error)


def _is_roblox_open(t) -> bool:
    """Static QuorumModule.IsRobloxOpen(). Defaults to True on probe failure so a
    quirk in the check never blocks a legitimate attach."""
    try:
        return bool(t.GetMethod('IsRobloxOpen').Invoke(None, None))
    except Exception:
        return True


class ExecutorMixin:
    """Mixes executor_attach / executor_status / executor_run into the Api class."""

    def executor_attach(self):
        """Inject QuorumAPI into all running Roblox clients."""
        if not IS_WINDOWS:
            return windows_only_error('Vellium Executor')
        try:
            q, t = _ensure_quorum()
        except Exception as e:
            return {'ok': False, 'error': str(e)}

        if not _is_roblox_open(t):
            return {'ok': False, 'error': 'Roblox is not running — open Roblox first, then click Inject'}

        try:
            log('[*] Executor: attaching via QuorumAPI …', (180, 180, 255))
            task = q.AttachAPI(QUORUM_ATTACH_NOCMD)   # async → block on the Task
            task.GetAwaiter().GetResult()

            state = _state_name(q.QuorumStatus)
            if bool(q.IsAttached()) or state in _ATTACH_OK_STATES:
                log(f'[+] Executor: attached (state={state}).', (100, 255, 100))
                result = {'ok': True, 'state': state}
                if not _is_admin():
                    result['warn'] = 'Running without admin — if execution fails, relaunch as administrator'
                return result

            if state == 'NoProcessFound':
                return {'ok': False, 'error': 'No Roblox process found — open Roblox first'}
            if state == 'TamperDetected':
                return {'ok': False, 'error': 'QuorumAPI reported TamperDetected (integrity check failed)'}

            hint = '' if _is_admin() else ' — try relaunching the executor as administrator'
            return {'ok': False, 'error': f'Attach failed (state={state}){hint}'}
        except Exception as e:
            return {'ok': False, 'error': f'Attach error: {e}'}

    def executor_status(self):
        """Return {'attached': bool}. Does not force-load .NET — the 3 s frontend
        poll stays cheap until the user actually injects."""
        if not IS_WINDOWS:
            return {'attached': False, 'available': False, 'error': 'Vellium Executor is only available on Windows'}
        with _lock:
            q = _quorum
        if q is None:
            return {'attached': False}
        try:
            return {'attached': bool(q.IsAttached())}
        except Exception:
            return {'attached': False}

    def executor_run(self, script: str):
        """Execute a Lua script in all attached Roblox clients."""
        if not IS_WINDOWS:
            return windows_only_error('Vellium Executor')
        if not script or not str(script).strip():
            return {'ok': False, 'error': 'Script is empty'}
        try:
            q, t = _ensure_quorum()
        except Exception as e:
            return {'ok': False, 'error': str(e)}

        try:
            if not bool(q.IsAttached()):
                return {'ok': False, 'error': 'Not attached — click Inject first'}

            state = _state_name(q.ExecuteScript(str(script)))
            if state in _EXEC_OK_STATES:
                log(f'[+] Executor: script executed (state={state}).', (100, 255, 100))
                return {'ok': True, 'output': f'✔ Executed ({state})'}
            return {'ok': False, 'error': f'Execute failed (state={state})'}
        except Exception as e:
            return {'ok': False, 'error': f'Execute error: {e}'}
