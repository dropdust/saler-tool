"""T281 单元测试：模板存取服务（无行回默认 / 保存即自定义 / 重置幂等 / 两功能独立）。

对应 data-model.md §1：行存在 = 已自定义；恢复默认 = 删行；保存经 registry 校验
（errors 阻断为 ValidationFailed，warnings 随返回值交由调用方呈现）。
"""

from __future__ import annotations

import pytest

from saler.core.errors import ValidationFailed
from saler.core.prompts import registry, store
from saler.db.models import AppSetting


class TestEffectiveTemplate:
    def test_default_when_no_row(self, db):
        content, customized = store.get_effective(db, "seed_expand")
        assert content == registry.get_feature("seed_expand").default_template
        assert customized is False

    def test_save_then_effective_is_customized(self, db):
        warnings = store.save(db, "seed_expand", "自定义指令 {description} {output_contract} {existing_nodes} {count}")
        assert warnings == []
        assert db.get(AppSetting, "prompt_template_seed_expand").value == {
            "content": "自定义指令 {description} {output_contract} {existing_nodes} {count}"
        }
        content, customized = store.get_effective(db, "seed_expand")
        assert content == "自定义指令 {description} {output_contract} {existing_nodes} {count}"
        assert customized is True

    def test_save_empty_raises_and_does_not_persist(self, db):
        with pytest.raises(ValidationFailed):
            store.save(db, "content_draft", "   ")
        _, customized = store.get_effective(db, "content_draft")
        assert customized is False

    def test_save_returns_warnings_without_blocking(self, db):
        warnings = store.save(db, "seed_expand", "只有一句指令")
        codes = sorted(w["code"] for w in warnings)
        assert codes == [
            "missing_output_contract",
            "missing_variable",
            "missing_variable",
            "missing_variable",
        ]
        _, customized = store.get_effective(db, "seed_expand")
        assert customized is True  # 警告不阻断保存

    def test_dirty_row_without_content_falls_back_to_default(self, db):
        # 手工改库等脏数据：行存在但 content 缺失 → 读取回落默认（防脏数据外溢）
        from saler.services import settings_service

        settings_service.set_value(db, "prompt_template_seed_expand", {"oops": True})
        content, customized = store.get_effective(db, "seed_expand")
        assert content == registry.get_feature("seed_expand").default_template
        assert customized is False


class TestResetAndIndependence:
    def test_reset_removes_row_and_is_idempotent(self, db):
        store.save(db, "seed_expand", "自定义 {count} {description} {existing_nodes} {output_contract}")
        store.reset(db, "seed_expand")
        assert db.get(AppSetting, "prompt_template_seed_expand") is None
        content, customized = store.get_effective(db, "seed_expand")
        assert customized is False and content == registry.get_feature("seed_expand").default_template

        store.reset(db, "seed_expand")  # 幂等
        assert db.get(AppSetting, "prompt_template_seed_expand") is None

    def test_features_are_independent(self, db):
        store.save(db, "seed_expand", "扩充自定义 {description} {existing_nodes} {count} {output_contract}")
        _, draft_customized = store.get_effective(db, "content_draft")
        assert draft_customized is False

        store.reset(db, "content_draft")  # 对未自定义功能重置：无副作用
        _, seed_still = store.get_effective(db, "seed_expand")
        assert seed_still is True
