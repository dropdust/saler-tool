"""T215 契约测试：渠道预置元数据完整性（动态遍历 registry；contract §1/§6）。

动态断言——对**当时已注册**的全部检索类型成立；新增渠道无需改本文件。
"""

from __future__ import annotations

import saler.providers.search  # noqa: F401  # 触发全部注册
from saler.providers.registry import registry


def _search_manifests():
    return registry.by_kind("search")


class TestPresetCompleteness:
    def test_every_type_has_complete_preset(self):
        for m in _search_manifests():
            assert m.preset is not None, f"{m.type_key} 缺 preset"
            assert m.preset.get("endpoint"), m.type_key
            assert m.preset.get("note"), m.type_key
            assert m.preset.get("access_mode") in ("official_api", "html"), m.type_key
            assert m.preset.get("market"), m.type_key

    def test_keyed_types_have_apply_url(self):
        """FR-013：需密钥类型 ⇒ 官方申请地址必须提供（SC-005 的后端锁定）。"""
        for m in _search_manifests():
            if m.secret_fields:
                assert m.preset.get("apply_url"), f"{m.type_key} 需密钥但缺 apply_url"

    def test_html_types_have_risk(self):
        """FR-020：网页解析型 ⇒ 风险提示必须提供。"""
        for m in _search_manifests():
            if m.preset["access_mode"] == "html":
                assert m.preset.get("risk"), m.type_key

    def test_needs_key_is_not_handwritten(self):
        """needs_key 为派生值（secret_fields 判定），不得手写进 preset。"""
        for m in _search_manifests():
            assert "needs_key" not in (m.preset or {}), m.type_key
