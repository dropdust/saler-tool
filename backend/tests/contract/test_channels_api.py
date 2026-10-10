"""T104 契约测试：通道 CRUD（secret 只写不读回）/ 连通测试 / 用量与限额结构（FR-040~044）。

假适配器经 Provider Registry 注入（离线）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from saler.providers.llm.base import TestResult
from saler.providers.registry import ProviderManifest, registry
from tests.fixtures.fakes.mail_fake import FakeMailSender

SECRET = "app-password-123"

MAIL_PAYLOAD = {
    "name": "主发件箱-Alice",
    "channel_type": "email",
    "config": {
        "provider": "fake_mail_api_test",
        "host": "smtp.example.com",
        "port": 465,
        "security": "ssl",
        "username": "alice@example.com",
    },
    "identity": {
        "from_name": "Alice",
        "from_addr": "alice@example.com",
        "reply_to": "sales@example.com",
        "signature": "Alice｜销售一部",
    },
    "secret": SECRET,
    "daily_limit": 100,
    "rate_per_minute": 10,
    "concurrency": 2,
}


@pytest.fixture()
def fake_mail() -> FakeMailSender:
    sender = FakeMailSender()
    registry.register(
        ProviderManifest(
            kind="mail",
            type_key="fake_mail_api_test",
            display_name="假邮箱（测试）",
            config_schema={"type": "object", "properties": {"host": {"type": "string"}}},
            secret_fields=("secret",),
            factory=lambda **kwargs: sender,
        )
    )
    return sender


def _create(client, **overrides) -> dict:
    payload = {**MAIL_PAYLOAD, **overrides}
    resp = client.post("/api/v1/channels", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCrud:
    def test_create_returns_no_secret_material(self, client, fake_mail):
        data = _create(client)
        assert data["name"] == "主发件箱-Alice"
        assert data["channel_type"] == "email"
        assert data["secret_set"] is True
        assert "secret" not in data and "secret_encrypted" not in data
        assert SECRET not in str(data)

    def test_list_and_get_never_expose_secret(self, client, db, fake_mail):
        data = _create(client)
        for resp in (
            client.get("/api/v1/channels"),
            client.get(f"/api/v1/channels/{data['id']}"),
        ):
            assert resp.status_code == 200, resp.text
            assert SECRET not in resp.text

    def test_put_updates_fields_and_keeps_secret_when_absent(self, client, db, fake_mail):
        data = _create(client)
        resp = client.put(
            f"/api/v1/channels/{data['id']}",
            json={"daily_limit": 50, "identity": {"from_name": "Alice-2", "from_addr": "alice@example.com"}},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["daily_limit"] == 50
        assert resp.json()["secret_set"] is True
        from saler.db.models import Channel

        row = db.get(Channel, data["id"])
        assert row.secret_encrypted == SECRET  # 库内可解密核对（接口层不回显）

    def test_put_with_new_secret_replaces(self, client, db, fake_mail):
        data = _create(client)
        client.put(f"/api/v1/channels/{data['id']}", json={"secret": "new-secret-456"})
        from saler.db.models import Channel

        assert db.get(Channel, data["id"]).secret_encrypted == "new-secret-456"

    def test_delete(self, client, fake_mail):
        data = _create(client)
        assert client.delete(f"/api/v1/channels/{data['id']}").status_code == 200
        assert client.get(f"/api/v1/channels/{data['id']}").status_code == 404

    def test_duplicate_name_rejected(self, client, fake_mail):
        _create(client)
        resp = client.post("/api/v1/channels", json=MAIL_PAYLOAD)
        assert resp.status_code in (409, 422)

    def test_unknown_provider_rejected(self, client, fake_mail):
        resp = client.post(
            "/api/v1/channels",
            json={**MAIL_PAYLOAD, "config": {**MAIL_PAYLOAD["config"], "provider": "nope"}},
        )
        assert resp.status_code == 422

    def test_social_channel_not_enabled_in_v1(self, client, fake_mail):
        resp = client.post(
            "/api/v1/channels", json={**MAIL_PAYLOAD, "channel_type": "social"}
        )
        assert resp.status_code == 422

    def test_invalid_limits_rejected(self, client, fake_mail):
        resp = client.post("/api/v1/channels", json={**MAIL_PAYLOAD, "daily_limit": -1})
        assert resp.status_code == 422


class TestTestEndpoint:
    def test_test_ok_updates_health(self, client, fake_mail):
        data = _create(client)
        resp = client.post(f"/api/v1/channels/{data['id']}/test")
        assert resp.status_code == 200, resp.text
        assert resp.json()["ok"] is True
        row = client.get(f"/api/v1/channels/{data['id']}").json()
        assert row["health"] == "healthy"
        assert row["last_check_at"] is not None
        assert "ok" in (row["last_check_result"] or "")

    def test_test_failure_marks_failing(self, client, fake_mail):
        fake_mail.healthy = False
        data = _create(client)
        resp = client.post(f"/api/v1/channels/{data['id']}/test")
        assert resp.json()["ok"] is False
        assert client.get(f"/api/v1/channels/{data['id']}").json()["health"] == "failing"

    def test_test_result_never_contains_secret(self, client, fake_mail):
        _create(client)

        class LeakySender(FakeMailSender):
            def verify(self) -> TestResult:
                return TestResult(ok=False, detail=f"auth failed for {SECRET}")

        registry.register(
            ProviderManifest(
                kind="mail",
                type_key="fake_mail_leaky",
                display_name="泄密假邮箱",
                factory=lambda **kwargs: LeakySender(),
            )
        )
        data2 = _create(client, name="泄密通道", config={**MAIL_PAYLOAD["config"], "provider": "fake_mail_leaky"})
        resp = client.post(f"/api/v1/channels/{data2['id']}/test")
        assert resp.status_code == 200
        assert SECRET not in resp.text


class TestUsage:
    def test_usage_structure(self, client, fake_mail):
        data = _create(client)
        resp = client.get(f"/api/v1/channels/{data['id']}/usage")
        assert resp.status_code == 200, resp.text
        usage = resp.json()
        for key in (
            "used_today",
            "daily_limit",
            "rate_per_minute",
            "concurrency",
            "remaining_today",
            "total_sent",
            "health",
            "status",
            "last_check_at",
            "last_check_result",
        ):
            assert key in usage, key
        assert usage["used_today"] == 0
        assert usage["remaining_today"] == 100

    def test_usage_cross_day_reset(self, client, db, fake_mail):
        data = _create(client)
        from saler.db.models import Channel

        row = db.get(Channel, data["id"])
        row.used_today = 37
        row.used_today_date = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
        db.commit()
        usage = client.get(f"/api/v1/channels/{data['id']}/usage").json()
        assert usage["used_today"] == 0
        assert usage["remaining_today"] == 100


class TestProvidersManifest:
    def test_lists_mail_and_sms_manifests(self, client):
        resp = client.get("/api/v1/channels/providers")
        assert resp.status_code == 200, resp.text
        kinds = {item["kind"] for item in resp.json()}
        assert kinds == {"mail", "sms"}
        smtp = next(item for item in resp.json() if item["type_key"] == "smtp")
        assert "config_schema" in smtp and smtp["config_schema"]
        sms = next(item for item in resp.json() if item["type_key"] == "http_generic")
        assert sms["presets"], "短信服务商预置模板缺失"
