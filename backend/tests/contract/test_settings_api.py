"""T153 契约测试（002-frontend-theme）：ui_theme 设置键——默认/写入/值域拒绝/读取归一。
T280 扩展（006）：通用 PUT 拒绝 prompt_template* 键（域校验守卫；模板库存取层自 T297 起自带）。
T297 修订：delete_value 随模板库改造移除（恢复默认=切换生效而非删行），对应用例删除。

对应 FR-005/006（偏好记忆与回退）与 contracts/theme-contract.md §1：
- 无行时 GET 返回默认 "light"；
- PUT 写入往返（dark→light）；
- 非法值（blue/数字/None/大写）→ 400 bad_request 且不落库；
- 存储侧非法值（手工改库）读取一律归一为 "light"。
"""

from __future__ import annotations

from saler.db.models import AppSetting
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


class TestPromptTemplateKeyGuard:
    """T280（006）：通用设置端点不得写入提示词模板键（防绕过 /ai/prompts 域校验）。"""

    def test_generic_put_rejects_prompt_key_when_absent(self, client):
        resp = client.put(
            "/api/v1/settings", json={"values": {"prompt_template_seed_expand": {"content": "x"}}}
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "bad_request"
        assert "AI 提示词" in body["message"]

    def test_generic_put_rejects_even_after_row_exists(self, client, db):
        # 行存在后 is_known_key 会放行——守卫必须先于它（防脏形状写入；复数键同样命中前缀）
        settings_service.set_value(db, "prompt_templates_content_draft", {"active_id": None, "items": []})
        resp = client.put(
            "/api/v1/settings",
            json={"values": {"prompt_templates_content_draft": {"active_id": None, "items": []}}},
        )
        assert resp.status_code == 400
        assert db.get(AppSetting, "prompt_templates_content_draft").value == {
            "active_id": None,
            "items": [],
        }
