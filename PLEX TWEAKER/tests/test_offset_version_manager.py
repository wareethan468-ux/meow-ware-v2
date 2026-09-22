from types import SimpleNamespace

from src.core import offset_loader, offset_sources
from src.core.roblox_manager import RobloxManager
from src.core.version_changer import deployment
from src.gui.api import Api


def test_version_hash_normalization_rejects_urls_and_bad_hashes():
    assert offset_loader.normalize_version_hash("f5a60436d48947d3") == "version-f5a60436d48947d3"
    assert offset_loader.normalize_version_hash("version-f5a60436d48947d3") == "version-f5a60436d48947d3"
    assert offset_loader.normalize_version_hash("https://example.com/file") is None
    assert offset_loader.normalize_version_hash("version-short") is None


def test_version_dump_uses_only_the_hardcoded_imtheo_host(monkeypatch):
    requested = []
    monkeypatch.setattr(offset_sources, "fetch_via_requests", lambda url: requested.append(url) or b"body")
    monkeypatch.setattr(offset_loader, "_activate_offset_body", lambda body, build, source: {"ok": True, "count": 900, "build": build})

    result = offset_loader.sync_version_dump("version-f5a60436d48947d3")

    assert result["ok"] is True
    assert requested == ["https://offsets.imtheo.lol/version-f5a60436d48947d3/fflags.hpp"]


def test_custom_offset_selection_reloads_flag_catalog(monkeypatch):
    api = Api.__new__(Api)
    api.flag_manager = SimpleNamespace(
        official_types={"old": "bool"},
        official_prefixes={"old": "FFlag"},
        load_offsets=lambda: None,
    )
    api._last_offsets_loaded_state = True
    api._needs_ui_refresh = False
    monkeypatch.setattr(offset_loader, "sync_version_dump", lambda version: {"ok": True, "count": 700, "build": version})

    result = api.sync_offsets_selection("custom", "f5a60436d48947d3")

    assert result["ok"] is True
    assert result["build"] == "version-f5a60436d48947d3"
    assert api.flag_manager.official_types == {}
    assert api._needs_ui_refresh is True


def test_nonlatest_build_requires_explicit_downgrade_consent(monkeypatch):
    api = Api.__new__(Api)
    api._fix_state = "idle"
    api.roblox_manager = None
    monkeypatch.setattr(RobloxManager, "get_roblox_version_string", staticmethod(lambda: "version-1111111111111111"))
    monkeypatch.setattr(deployment, "get_latest_production_guid", lambda: "version-2222222222222222")

    result = api.start_roblox_version_download("custom", "version-f5a60436d48947d3", False)

    assert result["state"] == "confirm_required"
