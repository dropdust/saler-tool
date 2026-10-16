"""T279 单元测试：提示词注册表（渲染语义 / legacy 逐字等价 / 槽位兜底 / 校验警告）。

golden 基准：下附 `_legacy_seed_prompt` / `_legacy_draft_prompt` 为 006 前
`core/seeds/ai.py:build_expansion_prompt` 与 `core/content/ai.py:_build_draft_prompt`
的逐字拷贝（冻结历史）——默认模板组合结果必须与之逐字相等（SC-002 回归口径）。
"""

from __future__ import annotations

import pytest

from saler.core.prompts import registry


def _legacy_seed_prompt(
    *, description: str | None, node_names_by_type: dict[str, list[str]], count: int
) -> str:
    node_type_labels = {
        "product_line": "产品线",
        "persona": "客户角色",
        "market": "市场/国家",
        "org": "具名机构实体",
    }
    parts = [
        "你是 B2B 外贸获客的市场调研助手。请基于你的知识图谱能力，"
        "为下列业务扩张目标市场的『爬虫种子』（检索意图）与具名机构实体。",
    ]
    if description:
        parts.append(f"业务描述：{description.strip()}")
    for node_type in ("product_line", "persona", "market"):
        names = node_names_by_type.get(node_type, [])
        if names:
            parts.append(f"已有{node_type_labels[node_type]}：{'、'.join(names[:80])}")
    parts.append(
        "输出 JSON，结构：\n"
        "- nodes[]: {node_type: product_line|persona|market|org, name, attributes(对象), "
        "confidence(0-1), rationale}\n"
        "- edges[]: {from(节点名), to(节点名), relation_type: product_fit_persona|"
        "product_target_market|org_in_market|org_has_persona}\n"
        "- seeds[]: {query(中文检索意图), product_line(节点名,可选), persona(节点名,可选), "
        "market(节点名,可选), priority(1-3), rationale}\n"
        f"要求：seeds 约 {count} 条，query 一律为中文母版表述（如「电力金具 电气承包 肯尼亚」），"
        "表达检索意图即可，勿堆砌英文关键词；"
        "具名机构实体的 query 为「\"机构名\" 联系方式」形式，机构名保留原文、不翻译；"
        "org 优先列举真实存在的买方组织（各国电网公司、输配电运营商、EPC 总包、"
        "电气/紧固件经销商、展会与行业协会等）。"
        "中文母版经人工审核后由系统翻译为各目标语言版本。"
    )
    return "\n".join(parts)


def _legacy_draft_prompt(*, content_type: str, brief: str, tone: str | None, language: str) -> str:
    return (
        f"你是资深外贸销售文案专家。请为下列业务撰写一条{content_type}（语言：{language}）文案。\n"
        f"业务要点：{brief}\n"
        f"语气：{tone or '专业、克制、以价值为先'}。\n"
        '输出 JSON：{"subject": "主题行（如适用）", "body_md": "Markdown 正文"}。\n'
        "要求：正文可使用 {{company_name}} 之类的变量占位符（收件人维度个性化）；"
        "不要编造具体价格与交期；落款处使用 {{signature}} 占位。"
    )


SEED_DEFAULT = registry.get_feature("seed_expand").default_template
DRAFT_DEFAULT = registry.get_feature("content_draft").default_template
SEED_CONTRACT = registry.get_feature("seed_expand").output_contract
DRAFT_CONTRACT = registry.get_feature("content_draft").output_contract


class TestFeatureCatalog:
    def test_features_and_labels(self):
        assert list(registry.FEATURES) == ["seed_expand", "content_draft"]
        assert registry.get_feature("seed_expand").label == "AI 扩充（种子扩充）"
        assert registry.get_feature("content_draft").label == "AI 起草（内容母版）"
        assert registry.MAX_TEMPLATE_LENGTH == 8000
        assert registry.get_feature("nope") is None

    def test_variable_sets(self):
        assert [v.name for v in registry.get_feature("seed_expand").variables] == [
            "description",
            "existing_nodes",
            "count",
        ]
        assert [v.name for v in registry.get_feature("content_draft").variables] == [
            "brief",
            "tone",
            "content_type",
            "language",
        ]
        assert registry.get_feature("seed_expand").variables[0].label == "业务描述"
        assert registry.RESERVED_OUTPUT_CONTRACT.name == "output_contract"

    def test_render_labels_match_seeds_module(self):
        from saler.core.seeds.ai import NODE_TYPE_LABELS

        for key, label in registry.SEED_NODE_LABELS.items():
            assert NODE_TYPE_LABELS[key] == label


class TestGoldenEquivalence:
    """默认模板组合结果与 legacy 构建函数逐字相等（SC-002）。"""

    @pytest.mark.parametrize(
        "ctx",
        [
            {
                "description": "紧固件出口",
                "existing_nodes": {
                    "product_line": ["电力金具"],
                    "persona": ["公用事业"],
                    "market": ["肯尼亚"],
                },
                "count": 20,
            },
            {"description": None, "existing_nodes": {}, "count": 5},
            {"description": "  电力金具  ", "existing_nodes": {"persona": []}, "count": 7},
            {"description": "", "existing_nodes": {"market": ["肯尼亚", "坦桑尼亚"]}, "count": 30},
            {"description": "   ", "existing_nodes": {"org": ["肯尼亚电力公司"]}, "count": 10},
            {
                "description": "输配电",
                "existing_nodes": {
                    "product_line": ["电力金具", "紧固件"],
                    "persona": ["公用事业", "EPC"],
                    "market": ["肯尼亚"],
                },
                "count": 40,
            },
        ],
    )
    def test_seed_default_composition_equals_legacy(self, ctx):
        expected = _legacy_seed_prompt(
            description=ctx["description"],
            node_names_by_type=ctx["existing_nodes"],
            count=ctx["count"],
        )
        assert registry.compose("seed_expand", SEED_DEFAULT, ctx) == expected

    @pytest.mark.parametrize(
        "ctx",
        [
            {
                "content_type": "开发信",
                "brief": "向肯尼亚输电线路承包商介绍电力金具",
                "tone": None,
                "language": "zh",
            },
            {"content_type": "产品介绍", "brief": "紧固件", "tone": "热情", "language": "en"},
            {"content_type": "开发信", "brief": "电力金具", "tone": "  ", "language": "zh"},
        ],
    )
    def test_draft_default_composition_equals_legacy(self, ctx):
        assert registry.compose("content_draft", DRAFT_DEFAULT, ctx) == _legacy_draft_prompt(**ctx)


class TestRenderSemantics:
    def test_existing_nodes_order_labels_separators(self):
        text = registry.compose(
            "seed_expand",
            "{existing_nodes}",
            {
                "existing_nodes": {"persona": ["乙", "甲"], "product_line": ["A"], "market": ["肯"]},
                "count": 1,
            },
        )
        assert text == "已有产品线：A\n已有客户角色：乙、甲\n已有市场/国家：肯\n\n" + SEED_CONTRACT

    def test_existing_nodes_80_limit_per_type(self):
        names = [f"n{i}" for i in range(90)]
        text = registry.compose("seed_expand", "{existing_nodes}", {"existing_nodes": {"product_line": names}})
        assert text == "已有产品线：" + "、".join(names[:80]) + "\n\n" + SEED_CONTRACT

    def test_tone_default_renders_with_period(self):
        out = registry.compose("content_draft", "{tone}", {"tone": None})
        assert out == "语气：专业、克制、以价值为先。\n\n" + DRAFT_CONTRACT

    def test_replaced_value_not_rescanned(self):
        out = registry.compose(
            "seed_expand", "{description}\n{count}", {"description": "含 {count} 字样", "count": 2}
        )
        assert out == "业务描述：含 {count} 字样\n2\n\n" + SEED_CONTRACT

    def test_double_braces_untouched_and_foreign_tokens_kept(self):
        out = registry.compose("seed_expand", "落款 {{signature}} 与 {brief}", {"description": None})
        assert out == "落款 {{signature}} 与 {brief}\n\n" + SEED_CONTRACT


class TestSlotHandling:
    def test_slot_replaced_in_place(self):
        out = registry.compose("content_draft", "A\n{output_contract}\nB", {"brief": "b"})
        assert out == "A\n" + DRAFT_CONTRACT + "\nB"

    def test_missing_slot_appends_contract_at_end(self):
        out = registry.compose("seed_expand", "自定义指令 {count} 条", {"count": 3})
        assert out == "自定义指令 3 条\n\n" + SEED_CONTRACT


class TestValidate:
    def test_empty_blocked_without_warnings(self):
        result = registry.validate_template("seed_expand", "   \n  ")
        assert result["errors"] == ["提示词不能为空"]
        assert result["warnings"] == []

    def test_too_long_blocked_with_quota_in_message(self):
        result = registry.validate_template("content_draft", "x" * (registry.MAX_TEMPLATE_LENGTH + 1))
        assert result["warnings"] == []
        assert registry.MAX_TEMPLATE_LENGTH and str(registry.MAX_TEMPLATE_LENGTH) in result["errors"][0]

    def test_unknown_variable_warned_and_double_braces_exempt(self):
        tpl = (
            "你是助手 {descriptoin} 落款 {{signature}} {output_contract} "
            "{description} {existing_nodes} {count}"
        )
        result = registry.validate_template("seed_expand", tpl)
        assert result["errors"] == []
        unknown = [w for w in result["warnings"] if w["code"] == "unknown_variable"]
        assert len(unknown) == 1
        assert "descriptoin" in unknown[0]["message"]
        assert "{{signature}}" not in unknown[0]["message"]

    def test_missing_variables_and_slot_warned(self):
        result = registry.validate_template("seed_expand", "只有一句指令")
        assert result["errors"] == []
        codes = sorted(w["code"] for w in result["warnings"])
        assert codes == [
            "missing_output_contract",
            "missing_variable",
            "missing_variable",
            "missing_variable",
        ]

    def test_default_templates_pass_clean(self):
        for key in registry.FEATURES:
            result = registry.validate_template(key, registry.get_feature(key).default_template)
            assert result == {"errors": [], "warnings": []}
