"""T283→T298 契约测试（006 契约 §1~§4，模板库版）：列表/详情/创建/更新/删除/切换生效。

- §1 列表（active_id/active_name/template_count）与 §2 详情（templates 全文）形状；
- §3a 创建（名称/容量/内容规则 → 400；warnings 不阻断）；§3b 更新（内容/改名）；
  §3c 删除（删除生效模板 → 服务端回退默认）；§4 切换生效（null=恢复默认，库保留）；
- 未知 feature/模板 → 404；两功能互相独立。
（§5 辅助端点契约由 T291 在本文件增补。）
"""

from __future__ import annotations

from saler.core.prompts import registry, store

SEED_OK = "自定义指令 {description} {existing_nodes} {count} {output_contract}"


def _create(client, **overrides):
    payload = {"name": "东非市场", "content": SEED_OK}
    payload.update(overrides)
    return client.post("/api/v1/ai/prompts/seed_expand/templates", json=payload)


class TestPromptList:
    def test_list_shape_order_and_default_state(self, client):
        body = client.get("/api/v1/ai/prompts").json()
        assert [item["feature"] for item in body["items"]] == ["seed_expand", "content_draft"]
        for item in body["items"]:
            assert item["label"]
            assert item["customized"] is False
            assert item["active_id"] is None
            assert item["active_name"] is None
            assert item["template_count"] == 0

    def test_list_reflects_active_state(self, client):
        _create(client)
        _create(client, name="备用", activate=False)
        items = {item["feature"]: item for item in client.get("/api/v1/ai/prompts").json()["items"]}
        assert items["seed_expand"]["customized"] is True
        assert items["seed_expand"]["active_name"] == "东非市场"
        assert items["seed_expand"]["active_id"] is not None
        assert items["seed_expand"]["template_count"] == 2
        assert items["content_draft"]["customized"] is False


class TestPromptDetail:
    def test_detail_shape_default(self, client):
        body = client.get("/api/v1/ai/prompts/seed_expand").json()
        spec = registry.get_feature("seed_expand")
        assert body["feature"] == "seed_expand"
        assert body["label"] == "AI 扩充（种子扩充）"
        assert body["default_content"] == spec.default_template
        assert body["active_id"] is None and body["active_name"] is None
        assert body["customized"] is False
        assert body["templates"] == []
        assert body["max_length"] == 8000
        assert body["max_name_length"] == store.NAME_MAX_LENGTH
        assert body["max_templates"] == store.MAX_TEMPLATES
        assert [v["name"] for v in body["variables"]] == ["description", "existing_nodes", "count"]
        assert [v["name"] for v in body["reserved_variables"]] == ["output_contract"]
        assert body["output_contract"] == spec.output_contract

    def test_detail_lists_templates_with_full_content(self, client):
        _create(client)
        _create(client, name="展会渠道", content=SEED_OK + "\n展会", activate=False)
        body = client.get("/api/v1/ai/prompts/seed_expand").json()
        assert [t["name"] for t in body["templates"]] == ["东非市场", "展会渠道"]
        assert body["templates"][1]["content"].endswith("展会")
        assert body["templates"][0]["updated_at"]  # 非空 ISO 字符串

    def test_detail_for_draft_variables(self, client):
        body = client.get("/api/v1/ai/prompts/content_draft").json()
        assert [v["name"] for v in body["variables"]] == ["brief", "tone", "content_type", "language"]

    def test_unknown_feature_404(self, client):
        resp = client.get("/api/v1/ai/prompts/nope")
        assert resp.status_code == 404
        assert resp.json()["code"] == "not_found"


class TestCreateTemplate:
    def test_create_activates_and_returns_warnings_clean(self, client):
        resp = _create(client)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["customized"] is True
        assert body["active_name"] == "东非市场"
        assert body["warnings"] == []
        assert len(body["templates"]) == 1

    def test_create_without_activate(self, client):
        body = _create(client, activate=False).json()
        assert body["customized"] is False
        assert len(body["templates"]) == 1

    def test_create_warnings_do_not_block(self, client):
        body = _create(client, content="只有一句指令").json()
        codes = sorted(w["code"] for w in body["warnings"])
        assert codes == [
            "missing_output_contract",
            "missing_variable",
            "missing_variable",
            "missing_variable",
        ]
        assert body["customized"] is True  # 警告不阻断

    def test_create_validation_400s(self, client):
        cases = [
            {"content": "   "},  # 空内容
            {"content": "x" * 8001},  # 超长
            {"name": "  "},  # 空名
            {"name": "长" * 61},  # 名过长
        ]
        for override in cases:
            resp = _create(client, **override)
            assert resp.status_code == 400, f"{override} 应被拒绝"
            assert resp.json()["code"] == "bad_request"
        # 阻断不落库
        assert client.get("/api/v1/ai/prompts/seed_expand").json()["templates"] == []

    def test_create_duplicate_name_400(self, client):
        _create(client)
        resp = _create(client, name="  东非市场  ")
        assert resp.status_code == 400
        assert "已存在" in resp.json()["message"]

    def test_create_unknown_feature_404(self, client):
        resp = client.post("/api/v1/ai/prompts/nope/templates", json={"name": "x", "content": "y"})
        assert resp.status_code == 404


class TestUpdateTemplate:
    def _active_id(self, client, feature="seed_expand"):
        return client.get(f"/api/v1/ai/prompts/{feature}").json()["active_id"]

    def test_update_content_reflects_on_active(self, client):
        _create(client)
        tid = self._active_id(client)
        resp = client.put(
            f"/api/v1/ai/prompts/seed_expand/templates/{tid}",
            json={"content": SEED_OK + "\n新增要求"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["warnings"] == []
        assert next(t for t in body["templates"] if t["id"] == tid)["content"].endswith("新增要求")

    def test_rename_and_conflicts(self, client):
        _create(client)
        _create(client, name="展会渠道", activate=False)
        tid = next(
            t["id"] for t in client.get("/api/v1/ai/prompts/seed_expand").json()["templates"]
            if t["name"] == "展会渠道"
        )
        ok = client.put(f"/api/v1/ai/prompts/seed_expand/templates/{tid}", json={"name": "展会"})
        assert ok.status_code == 200
        assert ok.json()["active_name"] == "东非市场"  # 改名非生效模板不动生效

        dup = client.put(f"/api/v1/ai/prompts/seed_expand/templates/{tid}", json={"name": "东非市场"})
        assert dup.status_code == 400 and "已存在" in dup.json()["message"]

    def test_update_requires_a_field_and_unknown_id_404(self, client):
        _create(client)
        tid = self._active_id(client)
        empty = client.put(f"/api/v1/ai/prompts/seed_expand/templates/{tid}", json={})
        assert empty.status_code == 400
        missing = client.put("/api/v1/ai/prompts/seed_expand/templates/t_nope", json={"name": "x"})
        assert missing.status_code == 404
        assert missing.json()["code"] == "not_found"


class TestDeleteAndActivate:
    def test_delete_active_falls_back_to_default_and_keeps_others(self, client):
        _create(client)
        _create(client, name="展会渠道", content=SEED_OK + "\n展会", activate=False)
        detail = client.get("/api/v1/ai/prompts/seed_expand").json()
        active_id = detail["active_id"]

        resp = client.delete(f"/api/v1/ai/prompts/seed_expand/templates/{active_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["active_id"] is None
        assert body["active_name"] is None
        assert body["customized"] is False
        assert [t["name"] for t in body["templates"]] == ["展会渠道"]

    def test_delete_unknown_404(self, client):
        resp = client.delete("/api/v1/ai/prompts/seed_expand/templates/t_nope")
        assert resp.status_code == 404

    def test_activate_switch_and_restore_default(self, client):
        _create(client)
        _create(client, name="展会渠道", content=SEED_OK + "\n展会")
        templates = client.get("/api/v1/ai/prompts/seed_expand").json()["templates"]
        first = next(t["id"] for t in templates if t["name"] == "东非市场")

        resp = client.put("/api/v1/ai/prompts/seed_expand/active", json={"id": first})
        assert resp.status_code == 200
        assert resp.json()["active_name"] == "东非市场"

        restored = client.put("/api/v1/ai/prompts/seed_expand/active", json={"id": None})
        assert restored.status_code == 200
        body = restored.json()
        assert body["active_id"] is None and body["customized"] is False
        assert len(body["templates"]) == 2  # 库保留

        again = client.put("/api/v1/ai/prompts/seed_expand/active", json={"id": None})
        assert again.status_code == 200  # 幂等

    def test_activate_unknown_id_404(self, client):
        resp = client.put("/api/v1/ai/prompts/seed_expand/active", json={"id": "t_nope"})
        assert resp.status_code == 404
        assert resp.json()["code"] == "not_found"


class TestIndependence:
    def test_features_are_independent(self, client):
        _create(client)
        draft = client.get("/api/v1/ai/prompts/content_draft").json()
        assert draft["customized"] is False and draft["templates"] == []
        # 起草侧操作不影响扩充侧
        client.put("/api/v1/ai/prompts/content_draft/active", json={"id": None})
        seed = client.get("/api/v1/ai/prompts/seed_expand").json()
        assert seed["active_name"] == "东非市场"
