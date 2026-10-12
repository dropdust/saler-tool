"""T200 单元测试：ProviderManifest 可选 preset 元数据通道（research R8）。"""

from __future__ import annotations

from saler.providers.registry import ProviderManifest, ProviderRegistry


class TestManifestPreset:
    def test_preset_defaults_to_none(self):
        m = ProviderManifest(kind="search", type_key="x", display_name="X")
        assert m.preset is None

    def test_preset_roundtrip(self):
        preset = {
            "endpoint": "https://example.com/search",
            "note": "免密钥",
            "apply_url": None,
            "access_mode": "html",
            "market": "全球",
            "risk": "非官方接入",
        }
        m = ProviderManifest(kind="search", type_key="y", display_name="Y", preset=preset)
        assert m.preset == preset

    def test_by_kind_is_stable_sorted(self):
        reg = ProviderRegistry()
        reg.register(ProviderManifest(kind="search", type_key="b", display_name="B"))
        reg.register(ProviderManifest(kind="search", type_key="a", display_name="A"))
        reg.register(ProviderManifest(kind="llm", type_key="c", display_name="C"))
        assert [m.type_key for m in reg.by_kind("search")] == ["a", "b"]
