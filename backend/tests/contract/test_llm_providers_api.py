"""T076 契约测试：LLM providers CRUD + 连通测试（密钥只写不读回，FR-006/030）。"""

from __future__ import annotations

import json


def _create(client, **overrides):
    payload = {
        "name": "DeepSeek",
        "provider_type": "openai_compatible",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "api_key": "sk-test-secret-123456",
        "params": {"supports_json_schema": False},
    }
    payload.update(overrides)
    resp = client.post("/api/v1/llm/providers", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestProviderCrud:
    def test_create_returns_public_shape_without_secret(self, client):
        body = _create(client)
        assert body["name"] == "DeepSeek"
        assert body["health"] == "unknown"
        assert body["is_default"] is True  # 首个服务自动设为默认
        dumped = json.dumps(body)
        assert "sk-test-secret-123456" not in dumped
        assert "api_key" not in body
        assert "secret" not in body

    def test_update_without_api_key_keeps_existing_secret(self, client, session_factory):
        created = _create(client)
        resp = client.put(
            f"/api/v1/llm/providers/{created['id']}", json={"model": "deepseek-reasoner"}
        )
        assert resp.status_code == 200
        assert resp.json()["model"] == "deepseek-reasoner"

        from saler.db.models import LlmProvider

        with session_factory() as db:
            row = db.get(LlmProvider, created["id"])
            assert row.secret_encrypted == "sk-test-secret-123456"  # 留空则保留原密钥

    def test_update_api_key_replaces_secret(self, client, session_factory):
        created = _create(client)
        client.put(f"/api/v1/llm/providers/{created['id']}", json={"api_key": "sk-new-9876543210"})

        from saler.db.models import LlmProvider

        with session_factory() as db:
            row = db.get(LlmProvider, created["id"])
            assert row.secret_encrypted == "sk-new-9876543210"

    def test_default_switch_is_exclusive(self, client):
        _create(client)
        second = _create(client, name="Kimi", base_url="https://api.moonshot.cn/v1")
        assert second["is_default"] is False

        resp = client.put(f"/api/v1/llm/providers/{second['id']}", json={"is_default": True})
        assert resp.json()["is_default"] is True
        flags = {row["name"]: row["is_default"] for row in client.get("/api/v1/llm/providers").json()}
        assert flags == {"DeepSeek": False, "Kimi": True}

    def test_delete(self, client):
        created = _create(client)
        assert client.delete(f"/api/v1/llm/providers/{created['id']}").status_code == 200
        assert client.get("/api/v1/llm/providers").json() == []

    def test_presets_endpoint(self, client):
        body = client.get("/api/v1/llm/presets").json()
        assert "deepseek" in body["presets"]
        assert body["presets"]["deepseek"]["base_url"] == "https://api.deepseek.com"
        assert body["config_schema"]["properties"]["base_url"]


class TestConnectionTest:
    def test_test_endpoint_success_updates_health(self, client, monkeypatch):
        created = _create(client)

        def fake_run(_row):
            from saler.providers.llm.base import TestResult

            return TestResult(ok=True, detail="fake ok", models=["m1", "m2"])

        monkeypatch.setattr("saler.api.routes.llm.run_connection_test", fake_run)
        resp = client.post(f"/api/v1/llm/providers/{created['id']}/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["models"] == ["m1", "m2"]

        row = client.get("/api/v1/llm/providers").json()[0]
        assert row["health"] == "healthy"
        assert row["last_test_at"] is not None

    def test_test_endpoint_failure_marks_failing(self, client, monkeypatch):
        created = _create(client)

        def fake_run(_row):
            from saler.providers.llm.base import TestResult

            return TestResult(ok=False, detail="[auth] bad key")

        monkeypatch.setattr("saler.api.routes.llm.run_connection_test", fake_run)
        body = client.post(f"/api/v1/llm/providers/{created['id']}/test").json()
        assert body["ok"] is False
        assert "auth" in body["detail"]
        assert client.get("/api/v1/llm/providers").json()[0]["health"] == "failing"


class TestAiGate:
    def test_expand_without_provider_returns_409(self, client):
        resp = client.post("/api/v1/ai/seeds/expand", json={"description": "任何行业"})
        assert resp.status_code == 409
        assert resp.json()["code"] == "llm_not_configured"
