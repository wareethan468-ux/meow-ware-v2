"""Auto-grab Roblox **internal function** offsets for the open-source executor.

This is a *separate concern* from ``offset_loader``/``offset_sources``, which
handle **FastFlag** offsets (``FFlags.hpp``). Here we fetch the internal
function-address header published at:

    https://robloxoffsets.com/internal-offsets.hpp

which looks like::

    namespace InternalFunctions {
        namespace Engine {
            inline constexpr std::uintptr_t DecryptYaraRuleset = 0x33E5D20;
            ...
        }
        namespace Game { ... }
    }

These are the RVAs an executor/injector needs to hook Roblox. The prebuilt
``Xeno.dll`` shipped in ``exec/`` bakes its own offsets in at compile time and
cannot ingest these at runtime — so this module's job is to **fetch, validate,
and store** the current header (and keep a repo copy the CI mirror refreshes),
ready for a from-source build or an out-of-process consumer to read.

**Version awareness.** The ``.hpp`` embeds no version, but the site exposes the
Roblox build the offsets target at ``/version`` (e.g. ``version-f5a60436d48947d3``).
Offsets are version-specific, so we fetch that too, store it in a sidecar meta
file, and let callers compare it against the installed Roblox build — offsets
for a different build than the one installed will not line up in memory.

Fetch chain (first valid body wins), mirroring the FFlags policy:
  1. robloxoffsets.com (primary) — requests, then curl
  2. our GitHub mirror (data/internal-offsets.hpp) — requests, then curl
  3. user-data disk copy (%LOCALAPPDATA%/MeowWare/internal-offsets.hpp)
  4. repo data/internal-offsets.hpp (dev / source builds)
  5. bundled baseline shipped with the app (src/data/internal-offsets_baseline.hpp)

**Critical:** robloxoffsets.com returns HTTP 403 to non-browser User-Agents, so
every network fetch here sends a browser-like UA (unlike the FFM UA used by the
FastFlag sources).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Optional

from src.utils.logger import log
from src.utils.paths import resource_path, user_data_dir


# ───────────────────────── sources ─────────────────────────

# Primary: the canonical publisher. 403s any non-browser UA (see module docstring).
INTERNAL_OFFSETS_URL = "https://robloxoffsets.com/internal-offsets.hpp"
# The Roblox build the published offsets target (plain text, e.g. "version-...").
VERSION_URL = "https://robloxoffsets.com/version"

# Our own GitHub mirror — same repo/branch the FFlags GitHub mirror lives in,
# refreshed by .github/workflows/mirror-offsets.yml. Fallback when
# robloxoffsets.com is unreachable or rate-limiting.
GITHUB_MIRROR_URL = (
    "https://raw.githubusercontent.com/4anti/Roblox-Fastflag-Manager/main/data/internal-offsets.hpp"
)
GITHUB_MIRROR_VERSION_URL = (
    "https://raw.githubusercontent.com/4anti/Roblox-Fastflag-Manager/main/data/internal-offsets.version.txt"
)

# Ordered (source_id, url) network chain. Each URL is tried via requests, then
# curl.exe (Windows native SSL) before moving to the next.
NETWORK_SOURCES = [
    ("robloxoffsets", INTERNAL_OFFSETS_URL),
    ("github_mirror", GITHUB_MIRROR_URL),
]
# Version-string sources, same priority order as the offsets themselves.
VERSION_SOURCES = [
    ("robloxoffsets", VERSION_URL),
    ("github_mirror", GITHUB_MIRROR_VERSION_URL),
]

# Browser UA — mandatory for robloxoffsets.com (plain/library UAs get 403).
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


# ───────────────────────── paths ─────────────────────────

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Persistent, always-writable store (matches the FFlags disk-cache location).
USER_CACHE_PATH = os.path.join(user_data_dir(), "internal-offsets.hpp")
# Sidecar recording which Roblox build the stored offsets target + when.
META_PATH = os.path.join(user_data_dir(), "internal-offsets.meta.json")
# Repo copies: CI mirror targets and GitHub-mirror sources; present in dev and
# from-source builds. Read-only from the app's perspective.
REPO_DATA_PATH = os.path.join(_REPO_ROOT, "data", "internal-offsets.hpp")
REPO_VERSION_PATH = os.path.join(_REPO_ROOT, "data", "internal-offsets.version.txt")
# Bundled baseline shipped inside the app (last-resort, offline first-run).
BUNDLED_BASELINE_PATH = resource_path(os.path.join("src", "data", "internal-offsets_baseline.hpp"))


# ───────────────────────── safety constants ─────────────────────────

MAX_BYTES = 5 * 1024 * 1024          # defensive cap (body is regex-scanned)
VERSION_MAX_BYTES = 256              # /version is a short string; reject HTML pages
REQUESTS_TIMEOUT = 10
CURL_TIMEOUT = 15
# Error pages / truncated dumps guard. The real header has ~80 entries; anything
# far below that is almost certainly a bad fetch (captive portal, 404 HTML, a
# dumper caught mid-Roblox-update). Kept well under the real count so a modestly
# smaller-but-legitimate future dump is not rejected.
MIN_VALID_ENTRIES = 20

# Windows: suppress console-window flash when spawning curl.
_SUBPROCESS_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Matches `[inline] [constexpr] [std::]uintptr_t NAME = 0xHEX`. All qualifiers
# optional so this captures the robloxoffsets.com `inline constexpr std::uintptr_t`
# form and any plainer mirror form alike.
_RX_ENTRY = re.compile(
    r'(?:inline\s+)?(?:constexpr\s+)?(?:std::)?uintptr_t\s+'
    r'([A-Za-z_][A-Za-z0-9_]{0,127})\s*=\s*0x([0-9a-fA-F]{1,16})'
)
_RX_NAMESPACE = re.compile(r'namespace\s+([A-Za-z_][A-Za-z0-9_]{0,127})\s*\{')
# Roblox build hash, e.g. version-f5a60436d48947d3 (16 hex chars).
_RX_VERSION = re.compile(r'version-[0-9a-fA-F]{16}')

# The build the *bundled baseline* .hpp targets — captured alongside it at
# package time. Last-resort version for a fully offline packaged first run,
# where neither the user meta nor the repo version file exists.
BASELINE_VERSION = "version-f5a60436d48947d3"


# ───────────────────────── module state ─────────────────────────

_last_source_id: Optional[str] = None
_last_count: int = 0
_last_updated_at: int = 0
_last_version: Optional[str] = None


def last_source_id() -> Optional[str]:
    """Source ID of the most recent successful update/read, or None."""
    return _last_source_id


# ───────────────────────── parse / validate ─────────────────────────

def _decode(body: bytes) -> str:
    return body.decode("utf-8", errors="ignore")


def normalize_version(value) -> Optional[str]:
    """Extract a canonical ``version-<16 hex>`` from arbitrary text, or None.

    Accepts a bare 16-hex hash (prepends ``version-``) or any string containing
    a version token. Rejects anything else (HTML error pages, empty strings).
    """
    s = _decode(value).strip() if isinstance(value, (bytes, bytearray)) else str(value or "").strip()
    if not s:
        return None
    m = _RX_VERSION.search(s)
    if m:
        return m.group(0)
    if re.fullmatch(r'[0-9a-fA-F]{16}', s):
        return f"version-{s}"
    return None


def parse_internal_offsets(text_or_bytes) -> dict[str, int]:
    """Parse the header into a flat ``{FunctionName: rva}`` dict.

    Function names are unique across the file, so a flat map is the useful
    contract for a consumer. Duplicate names keep the first occurrence.
    """
    text = _decode(text_or_bytes) if isinstance(text_or_bytes, (bytes, bytearray)) else str(text_or_bytes)
    out: dict[str, int] = {}
    for name, hx in _RX_ENTRY.findall(text):
        if name in out:
            continue
        try:
            out[name] = int(hx, 16)
        except ValueError:
            continue
    return out


def parse_grouped(text_or_bytes) -> dict[str, dict[str, int]]:
    """Best-effort ``{namespace: {FunctionName: rva}}`` grouping.

    Associates each entry with the nearest preceding ``namespace X {`` header
    (excluding the outer ``InternalFunctions`` wrapper). Entries before any
    inner namespace fall under ``"InternalFunctions"``.
    """
    text = _decode(text_or_bytes) if isinstance(text_or_bytes, (bytes, bytearray)) else str(text_or_bytes)
    markers = [(m.start(), m.group(1)) for m in _RX_NAMESPACE.finditer(text)]
    grouped: dict[str, dict[str, int]] = {}
    for m in _RX_ENTRY.finditer(text):
        pos = m.start()
        ns = "InternalFunctions"
        for mpos, mns in markers:
            if mpos <= pos and mns != "InternalFunctions":
                ns = mns
            elif mpos > pos:
                break
        try:
            rva = int(m.group(2), 16)
        except ValueError:
            continue
        grouped.setdefault(ns, {})[m.group(1)] = rva
    return grouped


def _is_valid(body: Optional[bytes]) -> bool:
    """Reject empty / HTML / truncated responses before they are stored."""
    if not body or len(body) > MAX_BYTES:
        return False
    text = _decode(body)
    if "namespace InternalFunctions" not in text:
        return False
    return len(parse_internal_offsets(text)) >= MIN_VALID_ENTRIES


# ───────────────────────── network fetch (browser UA) ─────────────────────────

def _host(url: str) -> str:
    try:
        return url.split("/")[2]
    except IndexError:
        return url


def fetch_via_requests(url: str, max_bytes: int = MAX_BYTES) -> Optional[bytes]:
    """Fetch via Python requests with a browser UA. Bytes on 200+size-ok, else None."""
    if not url.startswith("https://"):
        return None
    try:
        import requests
    except ImportError:
        return None
    host = _host(url)
    try:
        resp = requests.get(
            url,
            timeout=REQUESTS_TIMEOUT,
            stream=True,
            headers={"User-Agent": _BROWSER_UA, "Accept": "*/*"},
        )
    except Exception as e:
        log(f"[!] {host} via requests: unreachable ({type(e).__name__})", (255, 200, 100))
        return None
    if resp.status_code != 200:
        log(f"[!] {host} via requests: HTTP {resp.status_code}", (255, 200, 100))
        resp.close()
        return None
    body = bytearray()
    try:
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > max_bytes:
                log(f"[!] {host} via requests: exceeded {max_bytes}B cap", (255, 100, 100))
                resp.close()
                return None
    except Exception as e:
        log(f"[!] {host} via requests: read error ({type(e).__name__})", (255, 200, 100))
        resp.close()
        return None
    resp.close()
    return bytes(body)


def fetch_via_curl(url: str, max_bytes: int = MAX_BYTES) -> Optional[bytes]:
    """Fetch via system curl.exe with a browser UA (Windows native SSL path)."""
    curl_path = shutil.which("curl")
    if not curl_path:
        return None
    host = _host(url)
    try:
        result = subprocess.run(
            [curl_path, "-fsSL", "--max-time", str(CURL_TIMEOUT), "-A", _BROWSER_UA, url],
            capture_output=True,
            timeout=CURL_TIMEOUT + 5,
            creationflags=_SUBPROCESS_CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        log(f"[!] {host} via curl: timeout", (255, 200, 100))
        return None
    except Exception as e:
        log(f"[!] {host} via curl: spawn failed ({type(e).__name__})", (255, 200, 100))
        return None
    if result.returncode != 0:
        log(f"[!] {host} via curl: exit {result.returncode}", (255, 200, 100))
        return None
    body = result.stdout or b""
    if not body or len(body) > max_bytes:
        return None
    return body


def _iter_network_sources():
    """Yield (source_id, fetch_callable) for the OFFSETS header: requests then curl, per URL."""
    for sid, url in NETWORK_SOURCES:
        yield sid, (lambda u=url: fetch_via_requests(u))
        yield f"{sid}_curl", (lambda u=url: fetch_via_curl(u))


def fetch_version() -> Optional[str]:
    """Fetch the Roblox build the published offsets target (from /version).

    Tries robloxoffsets.com then the GitHub mirror, requests then curl, with a
    browser UA. Returns a canonical ``version-<16hex>`` or None.
    """
    for _sid, url in VERSION_SOURCES:
        for fetch in (lambda u=url: fetch_via_requests(u, VERSION_MAX_BYTES),
                      lambda u=url: fetch_via_curl(u, VERSION_MAX_BYTES)):
            body = fetch()
            if not body:
                continue
            version = normalize_version(body)
            if version:
                return version
    return None


# ───────────────────────── disk I/O ─────────────────────────

def _read_file(path: str) -> Optional[bytes]:
    try:
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            data = f.read(MAX_BYTES + 1)
        return data if len(data) <= MAX_BYTES else None
    except OSError:
        return None


def _write_cache(body: bytes) -> Optional[str]:
    """Atomically write the header to the user-data store. Returns path or None."""
    tmp = USER_CACHE_PATH + ".tmp"
    try:
        os.makedirs(os.path.dirname(USER_CACHE_PATH), exist_ok=True)
        with open(tmp, "wb") as f:
            f.write(body)
        os.replace(tmp, USER_CACHE_PATH)
        return USER_CACHE_PATH
    except OSError as e:
        log(f"[!] internal-offsets cache write failed: {type(e).__name__}", (255, 200, 100))
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return None


def _write_meta(version: Optional[str], source: str, count: int) -> None:
    """Persist which build the stored offsets target + provenance. Atomic."""
    tmp = META_PATH + ".tmp"
    try:
        os.makedirs(os.path.dirname(META_PATH), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({
                "version": version or "",
                "source": source,
                "count": count,
                "updated_at": int(time.time()),
            }, f, indent=2)
        os.replace(tmp, META_PATH)
    except OSError:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def _read_meta() -> dict:
    try:
        with open(META_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _read_local_version() -> Optional[str]:
    """Version from the sidecar meta, else the repo version file, else the
    build the bundled baseline was captured against."""
    meta = _read_meta()
    v = normalize_version(meta.get("version", ""))
    if v:
        return v
    body = _read_file(REPO_VERSION_PATH)
    v = normalize_version(body) if body else None
    return v or normalize_version(BASELINE_VERSION)


def _read_local_body() -> tuple[Optional[bytes], str]:
    """First valid local body: user cache → repo data → bundled baseline."""
    for path, sid in (
        (USER_CACHE_PATH, "disk_cache"),
        (REPO_DATA_PATH, "repo_data"),
        (BUNDLED_BASELINE_PATH, "bundled_baseline"),
    ):
        body = _read_file(path)
        if _is_valid(body):
            return body, sid
    return None, ""


# ───────────────────────── public API ─────────────────────────

def update_internal_offsets() -> dict:
    """Fetch the latest internal offsets (+ their target Roblox build) and store.

    Tries each network source (browser UA, requests then curl); on the first
    valid body, writes it atomically to the user-data store, fetches the
    matching build hash from ``/version``, records both, and updates module
    state. Falls back to reporting the newest local copy if the network is down.

    Returns ``{'ok': True, 'count', 'source', 'version', 'path'}`` or
    ``{'ok': False, 'error'}``.
    """
    global _last_source_id, _last_count, _last_updated_at, _last_version
    for sid, fetch in _iter_network_sources():
        body = fetch()
        if not body:
            continue
        if not _is_valid(body):
            log(f"[!] internal-offsets {sid}: body failed validation — skipping", (255, 200, 100))
            continue
        count = len(parse_internal_offsets(body))
        path = _write_cache(body)
        version = fetch_version() or _read_local_version()
        _write_meta(version, sid, count)
        _last_source_id, _last_count, _last_updated_at, _last_version = sid, count, int(time.time()), version
        log(f"[+] internal offsets: {count} functions from {sid} for "
            f"{version or 'unknown build'} ({len(body)} bytes)", (100, 255, 100))
        return {"ok": True, "count": count, "source": sid, "version": version,
                "path": path or USER_CACHE_PATH}

    # Network down — surface whatever valid local copy exists.
    body, sid = _read_local_body()
    if body:
        count = len(parse_internal_offsets(body))
        version = _read_local_version()
        _last_source_id, _last_count, _last_version = sid, count, version
        log(f"[~] internal offsets: network unavailable, using {sid} "
            f"({count} functions, {version or 'unknown build'})", (255, 200, 100))
        return {"ok": True, "count": count, "source": sid, "version": version,
                "path": USER_CACHE_PATH if sid == "disk_cache" else ""}

    log("[!] internal offsets: no source available (network + local all failed)", (255, 100, 100))
    return {"ok": False, "error": "Could not fetch internal offsets from any source"}


def get_internal_offsets(as_text: bool = False):
    """Return the current internal offsets without hitting the network.

    Reads the newest valid local copy (user cache → repo → baseline). With
    ``as_text`` returns the raw header string; otherwise the parsed
    ``{name: rva}`` dict. Returns ``""`` / ``{}`` when nothing is available.
    """
    body, _sid = _read_local_body()
    if not body:
        return "" if as_text else {}
    return _decode(body) if as_text else parse_internal_offsets(body)


def get_version() -> Optional[str]:
    """The Roblox build the currently-stored offsets target (no network)."""
    return _last_version or _read_local_version()


def get_status() -> dict:
    """Lightweight status for UI/telemetry — no network. Reflects the last
    update if one ran this session, else the newest local copy on disk."""
    if _last_source_id and _last_count:
        return {
            "ok": True,
            "count": _last_count,
            "source": _last_source_id,
            "version": _last_version or _read_local_version(),
            "updated_at": _last_updated_at or int(_read_meta().get("updated_at", 0) or 0),
            "url": INTERNAL_OFFSETS_URL,
            "path": USER_CACHE_PATH if os.path.isfile(USER_CACHE_PATH) else "",
        }
    body, sid = _read_local_body()
    return {
        "ok": bool(body),
        "count": len(parse_internal_offsets(body)) if body else 0,
        "source": sid or None,
        "version": _read_local_version(),
        "updated_at": int(_read_meta().get("updated_at", 0) or 0),
        "url": INTERNAL_OFFSETS_URL,
        "path": USER_CACHE_PATH if os.path.isfile(USER_CACHE_PATH) else "",
    }
