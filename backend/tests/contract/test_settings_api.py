"""T153 契约测试（002-frontend-theme）：ui_theme 设置键——默认/写入/值域拒绝/读取归一。

对应 FR-005/006（偏好记忆与回退）与 contracts/theme-contract.md §1：
- 无行时 GET 返回默认 "light"；
- PUT 写入往返（dark→light）；
- 非法值（blue/数字/None/大写）→ 400 bad_request 且不落库；
- 存储侧非法值（手工改库）读取一律归一为 "light"。
"""

from __future__ import annotations

from saler.services import settings_service


class TestUiThemeKey:
    def test_default_is_light(self, client):
        body = client.get("/api/v1/settings").json()
        assert body["ui_theme"] == "light"

    def test_put_roundtrip(self, client):
        resp = client.put("/api/v1/settings", json={"values": {"ui_theme": "dark"}})
        assert resp.status_code == 200, resp.text
        assert resp.json()["ui_theme"] == "dark"
        assert client.get("/api/v1/settings").json()["ui_theme"] == "dark"

        back = client.put("/api/v1/settings", json={"values": {"ui_theme": "light"}})
        assert back.status_code == 200, back.text
        assert back.json()["ui_theme"] == "light"

    def test_invalid_values_rejected_and_not_persisted(self, client):
        for bad in ("blue", 123, None, "DARK"):
            resp = client.put("/api/v1/settings", json={"values": {"ui_theme": bad}})
            assert resp.status_code == 400, f"{bad!r} 应被拒绝"
            body = resp.json()
            assert body["code"] == "bad_request"
            assert "light/dark" in body["message"]
        # 非法值不落库：读取仍为默认
        assert client.get("/api/v1/settings").json()["ui_theme"] == "light"

    def test_stored_invalid_value_normalized_on_read(self, client, db):
        # 绕过 API 校验直写 KV（模拟手工改库/历史脏数据）
        settings_service.set_value(db, "ui_theme", "blue")
        assert client.get("/api/v1/settings").json()["ui_theme"] == "light"
        settings_service.set_value(db, "ui_theme", "DARK")
        assert client.get("/api/v1/settings").json()["ui_theme"] == "light"
