"""T202 契约测试：检索渠道路由（类型值域、免密钥保存、预置端点形状）。

行为锁定基线：本文件先于装配去硬编码重构书写（书写即绿），重构与后续任务
（T211/T217/T220）只做增量扩展；本文件不锁"注册表精确集合"，避免新增渠道误红。
"""

from __future__ import annotations

PRESET_LEGACY_KEYS = {"display", "endpoint", "needs_key", "note"}


class TestProviderCreate:
    def test_unknown_type_key_rejected(self, client):
        resp = client.post("/api/v1/search/providers", json={"type_key": "bogus", "name": "假的"})
        assert resp.status_code == 422
        assert resp.json()["code"] == "unprocessable"

    def test_no_key_type_savable_without_key(self, client):
        resp = client.post("/api/v1/search/providers", json={"type_key": "ddg_html", "name": "DDG 兜底"})
        assert resp.status_code == 201, resp.text
        row = resp.json()
        assert row["type_key"] == "ddg_html"
        assert row["health"] == "unknown"
        # 密钥只写不读回
        assert "secret_encrypted" not in row and "api_key" not in row

    def test_keyed_type_saved_with_placeholder(self, client):
        resp = client.post(
            "/api/v1/search/providers",
            json={"type_key": "serper", "name": "Serper 主渠道", "api_key": "k-placeholder"},
        )
        assert resp.status_code == 201, resp.text
        assert "secret_encrypted" not in resp.json()

    def test_list_ordered_by_priority(self, client):
        client.post("/api/v1/search/providers", json={"type_key": "ddg_html", "name": "B", "priority": 200})
        client.post("/api/v1/search/providers", json={"type_key": "ddg_html", "name": "A", "priority": 10})
        rows = client.get("/api/v1/search/providers").json()
        assert [r["name"] for r in rows] == ["A", "B"]


class TestPresetsEndpoint:
    def test_presets_shape_and_legacy_keys(self, client):
        body = client.get("/api/v1/search/presets").json()
        assert set(body) == {"presets", "config_schemas"}
        presets = body["presets"]
        assert {"brave", "serper", "tavily", "ddg_html"} <= set(presets)
        for key, preset in presets.items():
            assert PRESET_LEGACY_KEYS <= set(preset), key
            assert isinstance(preset["needs_key"], bool)

    def test_config_schemas_derived_from_registry(self, client):
        body = client.get("/api/v1/search/presets").json()
        assert "serper" in body["config_schemas"]
        assert body["config_schemas"]["serper"].get("required") == ["api_key"]
