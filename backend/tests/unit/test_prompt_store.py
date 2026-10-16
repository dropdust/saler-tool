"""T297 单元测试：模板库存取服务（默认回退 / 创建即生效 / 名称与容量规则 / 删除回退 / 脏数据防御）。

对应 data-model.md §1（模板库版）与契约 §7：行不存在或 active_id 悬空 → 生效内置默认；
创建/更新内容经 registry 校验（errors 阻断为 ValidationFailed，warnings 随返回）；
删除生效模板自动回退默认；两功能库互相独立。
"""

from __future__ import annotations

import pytest

from saler.core.errors import NotFound, ValidationFailed
from saler.core.prompts import registry, store
from saler.db.models import AppSetting
from saler.services import settings_service

SEED_OK = "自定义指令 {description} {existing_nodes} {count} {output_contract}"


class TestEffective:
    def test_default_when_no_row(self, db):
        content, customized = store.get_effective(db, "seed_expand")
        assert content == registry.get_feature("seed_expand").default_template
        assert customized is False
        assert store.get_active(db, "seed_expand") is None

    def test_create_activates_by_default(self, db):
        warnings = store.create(db, "seed_expand", name="东非市场", content=SEED_OK)
        assert warnings == []
        content, customized = store.get_effective(db, "seed_expand")
        assert content == SEED_OK and customized is True
        active = store.get_active(db, "seed_expand")
        assert active is not None and active["name"] == "东非市场"

    def test_create_without_activate(self, db):
        store.create(db, "seed_expand", name="备用", content=SEED_OK, activate=False)
        _, customized = store.get_effective(db, "seed_expand")
        assert customized is False
        items, active_id = store.list_templates(db, "seed_expand")
        assert len(items) == 1 and active_id is None

    def test_activate_switches_and_null_restores_default(self, db):
        store.create(db, "seed_expand", name="A", content=SEED_OK)
        items, _ = store.list_templates(db, "seed_expand")
        store.create(db, "seed_expand", name="B", content=SEED_OK + "\nB")

        store.activate(db, "seed_expand", items[0]["id"])
        content, customized = store.get_effective(db, "seed_expand")
        assert content == SEED_OK and customized is True

        store.activate(db, "seed_expand", None)  # 恢复默认：模板库保留
        content, customized = store.get_effective(db, "seed_expand")
        assert content == registry.get_feature("seed_expand").default_template
        assert customized is False
        kept, _ = store.list_templates(db, "seed_expand")
        assert len(kept) == 2


class TestCreateRules:
    def test_empty_and_too_long_content_blocked(self, db):
        with pytest.raises(ValidationFailed):
            store.create(db, "seed_expand", name="X", content="   ")
        with pytest.raises(ValidationFailed):
            store.create(db, "seed_expand", name="X", content="x" * 8001)
        # 阻断不落库
        assert db.get(AppSetting, store.key_for("seed_expand")) is None

    def test_name_rules(self, db):
        with pytest.raises(ValidationFailed, match="不能为空"):
            store.create(db, "seed_expand", name="  ", content=SEED_OK)
        with pytest.raises(ValidationFailed, match="过长"):
            store.create(db, "seed_expand", name="长" * 61, content=SEED_OK)
        store.create(db, "seed_expand", name="东非市场", content=SEED_OK)
        with pytest.raises(ValidationFailed, match="已存在"):
            store.create(db, "seed_expand", name="  东非市场  ", content=SEED_OK)
        items, _ = store.list_templates(db, "seed_expand")
        assert items[0]["name"] == "东非市场"  # strip 后入库

    def test_capacity_limit(self, db):
        for i in range(store.MAX_TEMPLATES):
            store.create(db, "seed_expand", name=f"t{i}", content=SEED_OK, activate=False)
        with pytest.raises(ValidationFailed, match="上限"):
            store.create(db, "seed_expand", name="overflow", content=SEED_OK, activate=False)

    def test_warnings_returned_without_blocking(self, db):
        warnings = store.create(db, "seed_expand", name="缺省", content="只有一句指令")
        codes = sorted(w["code"] for w in warnings)
        assert codes == [
            "missing_output_contract",
            "missing_variable",
            "missing_variable",
            "missing_variable",
        ]
        _, customized = store.get_effective(db, "seed_expand")
        assert customized is True  # 警告不阻断


class TestUpdateAndDelete:
    def test_update_content_and_rename(self, db):
        store.create(db, "seed_expand", name="A", content=SEED_OK)
        items, _ = store.list_templates(db, "seed_expand")
        tid = items[0]["id"]

        warnings = store.update(db, "seed_expand", tid, name="A2", content=SEED_OK + "\n新增")
        assert warnings == []
        active = store.get_active(db, "seed_expand")
        assert active is not None and active["name"] == "A2" and active["content"].endswith("新增")

    def test_update_rename_conflicts_and_unknown_id(self, db):
        store.create(db, "seed_expand", name="A", content=SEED_OK, activate=False)
        store.create(db, "seed_expand", name="B", content=SEED_OK)
        items, _ = store.list_templates(db, "seed_expand")
        a_id = next(it["id"] for it in items if it["name"] == "A")

        with pytest.raises(ValidationFailed, match="已存在"):
            store.update(db, "seed_expand", a_id, name="B")
        with pytest.raises(ValidationFailed):
            store.update(db, "seed_expand", a_id, content="   ")
        with pytest.raises(NotFound):
            store.update(db, "seed_expand", "t_nope", name="X")
        # 改写自身原名不冲突
        store.update(db, "seed_expand", a_id, name="A")

    def test_delete_active_falls_back_to_default(self, db):
        store.create(db, "seed_expand", name="A", content=SEED_OK)
        store.create(db, "seed_expand", name="B", content=SEED_OK + "\nB", activate=False)
        items, active_id = store.list_templates(db, "seed_expand")
        a_id = next(it["id"] for it in items if it["name"] == "A")
        assert active_id == a_id

        store.delete(db, "seed_expand", a_id)
        content, customized = store.get_effective(db, "seed_expand")
        assert content == registry.get_feature("seed_expand").default_template
        assert customized is False
        kept, active_after = store.list_templates(db, "seed_expand")
        assert len(kept) == 1 and active_after is None  # B 仍在，生效回退默认

    def test_delete_non_active_keeps_active(self, db):
        store.create(db, "seed_expand", name="A", content=SEED_OK, activate=False)
        store.create(db, "seed_expand", name="B", content=SEED_OK + "\nB")
        items, _ = store.list_templates(db, "seed_expand")
        a_id = next(it["id"] for it in items if it["name"] == "A")

        store.delete(db, "seed_expand", a_id)
        content, customized = store.get_effective(db, "seed_expand")
        assert content == SEED_OK + "\nB" and customized is True

        with pytest.raises(NotFound):
            store.delete(db, "seed_expand", a_id)

    def test_activate_unknown_id_raises(self, db):
        with pytest.raises(NotFound):
            store.activate(db, "seed_expand", "t_nope")


class TestIndependenceAndDirtyData:
    def test_features_are_independent(self, db):
        store.create(db, "seed_expand", name="扩充用", content=SEED_OK)
        _, draft_customized = store.get_effective(db, "content_draft")
        assert draft_customized is False
        draft_items, _ = store.list_templates(db, "content_draft")
        assert draft_items == []

    def test_dirty_row_shapes_fall_back_safely(self, db):
        settings_service.set_value(db, "prompt_templates_seed_expand", {"oops": True})
        content, customized = store.get_effective(db, "seed_expand")
        assert content == registry.get_feature("seed_expand").default_template
        assert customized is False

        # 条目形状非法 → 被丢弃；active_id 悬空 → 视为默认
        settings_service.set_value(
            db,
            "prompt_templates_seed_expand",
            {
                "active_id": "t_gone",
                "items": [
                    {"id": "", "name": "n", "content": "c"},
                    {"id": "t_ok", "name": 3, "content": "c"},
                    "not-a-dict",
                ],
            },
        )
        items, active_id = store.list_templates(db, "seed_expand")
        assert items == [] and active_id is None
        _, customized = store.get_effective(db, "seed_expand")
        assert customized is False

    def test_item_updated_at_written(self, db):
        store.create(db, "seed_expand", name="A", content=SEED_OK)
        items, _ = store.list_templates(db, "seed_expand")
        assert items[0]["updated_at"]  # 非空 ISO 字符串
