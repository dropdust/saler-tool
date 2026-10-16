"""T283 契约测试（006 契约 §1~§4）：提示词模板 列表/详情/保存/恢复默认。

- 列表固定顺序与形状；详情含变量目录/保留槽位/固定段；
- 保存：空/超长 → 400 bad_request（消息含额度）；warnings 三码不阻断；未知功能 404；
- 恢复默认：返回默认全文、幂等；两功能互不影响。
（§5 辅助端点契约由 T291 在本文件增补。）
"""

from __future__ import annotations

from saler.core.prompts import registry

SEED_CUSTOM = "自定义指令 {description} {existing_nodes} {count} {output_contract}"


class TestPromptList:
    def test_list_shape_order_and_default_state(self, client):
        body = client.get("/api/v1/ai/prompts").json()
        assert [item["feature"] for item in body["items"]] == ["seed_expand", "content_draft"]
        for item in body["items"]:
            assert item["label"]
            assert item["customized"] is False
            assert item["updated_at"] is None

    def test_list_reflects_customized_state(self, client):
        client.put("/api/v1/ai/prompts/seed_expand", json={"content": SEED_CUSTOM})
        items = {item["feature"]: item for item in client.get("/api/v1/ai/prompts").json()["items"]}
        assert items["seed_expand"]["customized"] is True
        assert items["seed_expand"]["updated_at"] is not None
        assert items["content_draft"]["customized"] is False


class TestPromptDetail:
    def test_detail_shape_default(self, client):
        body = client.get("/api/v1/ai/prompts/seed_expand").json()
        spec = registry.get_feature("seed_expand")
        assert body["feature"] == "seed_expand"
        assert body["label"] == "AI 扩充（种子扩充）"
        assert body["content"] == spec.default_template
        assert body["default_content"] == spec.default_template
        assert body["customized"] is False
        assert body["updated_at"] is None
        assert body["max_length"] == 8000
        assert [v["name"] for v in body["variables"]] == ["description", "existing_nodes", "count"]
        assert [v["name"] for v in body["reserved_variables"]] == ["output_contract"]
        assert body["reserved_variables"][0]["render"]
        assert body["output_contract"] == spec.output_contract

    def test_detail_for_draft_variables(self, client):
        body = client.get("/api/v1/ai/prompts/content_draft").json()
        assert [v["name"] for v in body["variables"]] == ["brief", "tone", "content_type", "language"]

    def test_unknown_feature_404(self, client):
        resp = client.get("/api/v1/ai/prompts/nope")
        assert resp.status_code == 404
        assert resp.json()["code"] == "not_found"


class TestPromptSave:
    def test_save_roundtrip_no_warnings(self, client):
        resp = client.put("/api/v1/ai/prompts/seed_expand", json={"content": SEED_CUSTOM})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["customized"] is True
        assert body["content"] == SEED_CUSTOM
        assert body["warnings"] == []
        assert body["updated_at"] is not None
        # 详情回读一致
        back = client.get("/api/v1/ai/prompts/seed_expand").json()
        assert back["content"] == SEED_CUSTOM
        assert back["default_content"] == registry.get_feature("seed_expand").default_template

    def test_save_warning_codes_with_double_brace_exemption(self, client):
        content = "指令 {descriptoin} 落款 {{signature}}"  # 未知变量 + 缺 3 数据变量 + 缺槽位
        body = client.put("/api/v1/ai/prompts/seed_expand", json={"content": content}).json()
        codes = [w["code"] for w in body["warnings"]]
        assert codes.count("unknown_variable") == 1
        assert codes.count("missing_variable") == 3
        assert "missing_output_contract" in codes
        unknown = [w for w in body["warnings"] if w["code"] == "unknown_variable"]
        assert "descriptoin" in unknown[0]["message"]

    def test_save_empty_400_bad_request(self, client):
        resp = client.put("/api/v1/ai/prompts/seed_expand", json={"content": "   \n "})
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "bad_request"
        assert "不能为空" in body["message"]
        # 不落库
        assert client.get("/api/v1/ai/prompts/seed_expand").json()["customized"] is False

    def test_save_too_long_400_with_quota(self, client):
        resp = client.put("/api/v1/ai/prompts/content_draft", json={"content": "x" * 8001})
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "bad_request"
        assert "8000" in body["message"]

    def test_save_unknown_feature_404(self, client):
        resp = client.put("/api/v1/ai/prompts/nope", json={"content": "x"})
        assert resp.status_code == 404

    def test_features_independent(self, client):
        client.put("/api/v1/ai/prompts/seed_expand", json={"content": SEED_CUSTOM})
        assert client.get("/api/v1/ai/prompts/content_draft").json()["customized"] is False


class TestPromptReset:
    def test_reset_returns_default_and_is_idempotent(self, client):
        client.put("/api/v1/ai/prompts/seed_expand", json={"content": SEED_CUSTOM})
        resp = client.post("/api/v1/ai/prompts/seed_expand/reset")
        assert resp.status_code == 200
        body = resp.json()
        assert body["customized"] is False
        assert body["content"] == body["default_content"]
        assert body["updated_at"] is None

        again = client.post("/api/v1/ai/prompts/seed_expand/reset")
        assert again.status_code == 200
        assert again.json()["customized"] is False

    def test_reset_unknown_feature_404(self, client):
        assert client.post("/api/v1/ai/prompts/nope/reset").status_code == 404
