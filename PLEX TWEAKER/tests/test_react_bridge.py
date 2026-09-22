import json
from types import SimpleNamespace

from src.core import offset_loader
from src.gui import api as api_module
from src.gui.api import Api
from src.utils.config import Config


def test_disguise_mode_persists_and_updates_native_title(monkeypatch):
    api = Api.__new__(Api)
    api.settings = {}
    api._window = SimpleNamespace(title="Meow Ware")
    monkeypatch.setattr(Config, "save_settings", lambda *_args: True)

    result = api.set_disguise_mode(True)

    assert result == {"ok": True, "enabled": True}
    assert api.settings["disguise_mode"] is True
    assert api._window.title == "Spotify"

    api.set_disguise_mode(False)
    assert api._window.title == "Meow Ware"


def test_clear_logs_bridge_returns_cursor(monkeypatch):
    cleared = []
    monkeypatch.setattr(api_module, "clear_console_logs", lambda: cleared.append(True))
    monkeypatch.setattr(api_module, "get_logs_since", lambda *_args: ([], 37, 4))

    result = Api.__new__(Api).clear_logs()

    assert cleared == [True]
    assert result == {"ok": True, "total": 37, "tail_epoch": 4}


def test_uploaded_hpp_is_validated_and_installed(tmp_path, monkeypatch):
    header = tmp_path / "FFlags.hpp"
    entries = "\n".join(
        f"inline constexpr uintptr_t FFlagBridgeTest{i} = 0x{0x200000 + i * 8:X};"
        for i in range(offset_loader.MIN_VALID_FLAGS)
    )
    header.write_text(
        "namespace FFlagList { inline constexpr uintptr_t Pointer = 0x100000; }\n" + entries,
        encoding="ascii",
    )
    cache = tmp_path / "offsets_cache.json"
    monkeypatch.setattr(offset_loader, "CACHE_PATH", str(cache))
    monkeypatch.setattr(offset_loader, "_rotate_history_if_needed", lambda *_args: None)

    result = offset_loader.import_offset_dump(str(header), "version-test")

    assert result["ok"] is True
    assert result["count"] == offset_loader.MIN_VALID_FLAGS
    saved = json.loads(cache.read_text(encoding="utf-8"))
    assert len(saved["flags"]) == offset_loader.MIN_VALID_FLAGS
    assert saved["struct_offsets"]["Pointer"] == "0x100000"
    offset_loader.reset_cache()
