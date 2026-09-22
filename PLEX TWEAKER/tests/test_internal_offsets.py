from src.core import internal_offsets


SAMPLE = b"""namespace InternalFunctions {
    namespace Luau {
    }
    namespace Engine {
        inline constexpr std::uintptr_t DecryptYaraRuleset = 0x33E5D20;
        inline constexpr std::uintptr_t TaskSchedulerConstructor = 0xD3E820;
    }
    namespace Game {
        inline constexpr std::uintptr_t RemoteFunctionInvokeClient = 0x506ACA0;
    }
}
"""


def _big_body(n: int = 40) -> bytes:
    lines = [b"namespace InternalFunctions {\n    namespace Engine {\n"]
    for i in range(n):
        lines.append(f"        inline constexpr std::uintptr_t Fn{i} = 0x{0x100000 + i:X};\n".encode())
    lines.append(b"    }\n}\n")
    return b"".join(lines)


def test_parse_flat_returns_name_to_rva():
    parsed = internal_offsets.parse_internal_offsets(SAMPLE)
    assert parsed["DecryptYaraRuleset"] == 0x33E5D20
    assert parsed["TaskSchedulerConstructor"] == 0xD3E820
    assert parsed["RemoteFunctionInvokeClient"] == 0x506ACA0
    assert len(parsed) == 3


def test_parse_grouped_buckets_by_inner_namespace():
    grouped = internal_offsets.parse_grouped(SAMPLE)
    assert grouped["Engine"]["DecryptYaraRuleset"] == 0x33E5D20
    assert grouped["Game"]["RemoteFunctionInvokeClient"] == 0x506ACA0
    # The empty Luau namespace contributes nothing.
    assert "Luau" not in grouped


def test_is_valid_accepts_real_shape_rejects_junk():
    assert internal_offsets._is_valid(_big_body(40)) is True
    assert internal_offsets._is_valid(b"<html>403 Forbidden</html>") is False
    assert internal_offsets._is_valid(SAMPLE) is False  # only 3 < MIN_VALID_ENTRIES
    assert internal_offsets._is_valid(None) is False


def test_bundled_baseline_parses():
    """The shipped baseline must parse to a healthy count so an offline first
    run still has usable internal offsets."""
    body = internal_offsets._read_file(internal_offsets.BUNDLED_BASELINE_PATH)
    assert body, "bundled baseline missing"
    assert len(internal_offsets.parse_internal_offsets(body)) >= internal_offsets.MIN_VALID_ENTRIES


def test_update_writes_cache_from_network(monkeypatch, tmp_path):
    body = _big_body(30)
    cache = tmp_path / "internal-offsets.hpp"
    monkeypatch.setattr(internal_offsets, "USER_CACHE_PATH", str(cache))
    monkeypatch.setattr(
        internal_offsets, "_iter_network_sources",
        lambda: iter([("robloxoffsets", lambda: body)]),
    )

    result = internal_offsets.update_internal_offsets()

    assert result["ok"] is True
    assert result["source"] == "robloxoffsets"
    assert result["count"] == 30
    assert cache.read_bytes() == body
    assert internal_offsets.get_status()["count"] == 30


def test_update_skips_invalid_body_then_uses_next_source(monkeypatch, tmp_path):
    good = _big_body(25)
    monkeypatch.setattr(internal_offsets, "USER_CACHE_PATH", str(tmp_path / "io.hpp"))
    monkeypatch.setattr(
        internal_offsets, "_iter_network_sources",
        lambda: iter([
            ("robloxoffsets", lambda: b"<html>403</html>"),   # invalid — skipped
            ("github_mirror", lambda: good),                   # valid — used
        ]),
    )

    result = internal_offsets.update_internal_offsets()

    assert result["ok"] is True
    assert result["source"] == "github_mirror"
    assert result["count"] == 25


def test_update_falls_back_to_local_when_network_down(monkeypatch, tmp_path):
    monkeypatch.setattr(internal_offsets, "USER_CACHE_PATH", str(tmp_path / "io.hpp"))
    monkeypatch.setattr(
        internal_offsets, "_iter_network_sources",
        lambda: iter([("robloxoffsets", lambda: None), ("github_mirror", lambda: None)]),
    )
    monkeypatch.setattr(internal_offsets, "_read_local_body", lambda: (_big_body(22), "bundled_baseline"))

    result = internal_offsets.update_internal_offsets()

    assert result["ok"] is True
    assert result["source"] == "bundled_baseline"
    assert result["count"] == 22


def test_update_reports_error_when_everything_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(internal_offsets, "USER_CACHE_PATH", str(tmp_path / "io.hpp"))
    monkeypatch.setattr(
        internal_offsets, "_iter_network_sources",
        lambda: iter([("robloxoffsets", lambda: None)]),
    )
    monkeypatch.setattr(internal_offsets, "_read_local_body", lambda: (None, ""))

    result = internal_offsets.update_internal_offsets()

    assert result["ok"] is False
    assert "error" in result


def test_primary_url_and_browser_ua():
    assert internal_offsets.INTERNAL_OFFSETS_URL == "https://robloxoffsets.com/internal-offsets.hpp"
    # robloxoffsets.com 403s non-browser UAs — the fetchers must present as a browser.
    assert internal_offsets._BROWSER_UA.startswith("Mozilla/5.0")
