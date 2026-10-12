"""T202/T211 契约测试：检索渠道路由（类型值域、免密钥保存、预置端点形状、测试端点记账）。

行为锁定基线：本文件先于装配去硬编码重构书写（书写即绿），重构与后续任务
（T211/T217/T220）只做增量扩展；本文件不锁"注册表精确集合"，避免新增渠道误红。
"""

from __future__ import annotations

import httpx
import respx

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

    def test_presets_cover_registry_with_full_fields(self, client):
        """T217：预置端点由 registry 派生（单一数据源）；needs_key 为派生值。"""
        import saler.providers.search  # noqa: F401
        from saler.providers.registry import registry

        body = client.get("/api/v1/search/presets").json()
        registered = {m.type_key for m in registry.by_kind("search")}
        assert len(registered) >= 9  # 3 需密钥 + 6 免密钥
        assert set(body["presets"]) == registered
        full = {"display", "endpoint", "needs_key", "note", "apply_url", "access_mode", "market", "risk"}
        for m in registry.by_kind("search"):
            preset = body["presets"][m.type_key]
            assert full <= set(preset), m.type_key
            assert preset["needs_key"] == bool(m.secret_fields), m.type_key
            if m.secret_fields:
                assert preset["apply_url"], m.type_key
            if preset["access_mode"] == "html":
                assert preset["risk"], m.type_key


class TestProviderTestEndpoint:
    """T211：手工测试与任务执行同口径记账（health/last_error_*/used_today；contract §3）。"""

    DDG_URL = "https://html.duckduckgo.com/html/"
    DDG_LITE = "https://lite.duckduckgo.com/lite/"
    NORMAL_HTML = '<html><body><a class="result__a" href="https://ok.example/">Ok</a></body></html>'

    @respx.mock
    def test_failure_writes_kind_health_and_usage(self, client, session_factory):
        from saler.db.models import SearchProvider

        row = client.post("/api/v1/search/providers", json={"type_key": "ddg_html", "name": "DDG"}).json()
        respx.get(self.DDG_URL).mock(return_value=httpx.Response(202, text=""))
        respx.get(self.DDG_LITE).mock(return_value=httpx.Response(403))
        body = client.post(f"/api/v1/search/providers/{row['id']}/test").json()
        assert body["ok"] is False and "[blocked]" in body["detail"]
        with session_factory() as session:
            db_row = session.get(SearchProvider, row["id"])
            assert db_row.health == "failing"
            assert db_row.last_error_kind == "blocked"
            assert db_row.last_error_at is not None
            assert db_row.used_today == 1  # 手动测试同口径计数

    @respx.mock
    def test_success_writes_healthy_and_clears_error(self, client, session_factory):
        from saler.db.models import SearchProvider

        row = client.post("/api/v1/search/providers", json={"type_key": "ddg_html", "name": "DDG2"}).json()
        respx.get(self.DDG_URL).mock(return_value=httpx.Response(200, text=self.NORMAL_HTML))
        body = client.post(f"/api/v1/search/providers/{row['id']}/test").json()
        assert body["ok"] is True
        with session_factory() as session:
            db_row = session.get(SearchProvider, row["id"])
            assert db_row.health == "healthy"
            assert db_row.last_error_kind is None and db_row.last_error_at is None
            assert db_row.used_today == 1

    @respx.mock
    def test_response_exposes_last_error_fields(self, client):
        """T220：行响应暴露 last_error_kind/at（US3 风险透明呈现的数据源）。"""
        row = client.post("/api/v1/search/providers", json={"type_key": "ddg_html", "name": "DDG3"}).json()
        respx.get(self.DDG_URL).mock(return_value=httpx.Response(202, text=""))
        respx.get(self.DDG_LITE).mock(return_value=httpx.Response(403))
        client.post(f"/api/v1/search/providers/{row['id']}/test")
        listed = next(r for r in client.get("/api/v1/search/providers").json() if r["id"] == row["id"])
        assert listed["last_error_kind"] == "blocked"
        assert listed["last_error_at"]
