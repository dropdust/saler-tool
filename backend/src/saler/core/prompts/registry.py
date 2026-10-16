"""提示词注册表（006）：功能定义、变量渲染、组合与校验。

纯函数模块：不依赖 FastAPI/DB（宪法 II）。

- 默认模板由 006 前的硬编码提示词（`core/seeds/ai.py:build_expansion_prompt` /
  `core/content/ai.py:_build_draft_prompt`）机械重构而成：固定部分抽出为
  `output_contract`（机器解析依赖，不可编辑），动态数据处换成变量 token。
  **默认模板的组合结果与 legacy 构建函数逐字相等**（golden 单测锁定，SC-002）。
- 变量语法 `{name}`（精确 token 替换）：空值变量独占整行时整行省略（复现 legacy
  "无条件不生成该行" 的语义）；`{{...}}`（内容占位符）不扫描也不替换（research R2）。
- 结构槽位 `{output_contract}`：模板缺失时组合期自动补于末尾（FR-004 兜底）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: 模板长度上限（字符；contract §3——超限拒绝保存并显示额度）
MAX_TEMPLATE_LENGTH = 8000

#: 渲染用节点类型标签（与 `core/seeds/ai.py:NODE_TYPE_LABELS` 一致；一致性由单测锁定防漂移）
SEED_NODE_LABELS = {
    "product_line": "产品线",
    "persona": "客户角色",
    "market": "市场/国家",
}


@dataclass(frozen=True)
class PromptVariable:
    """可编辑数据变量：渲染语义（render）与"未引用后果"（missing_hint）都面向用户展示。"""

    name: str
    label: str
    render: str
    missing_hint: str


@dataclass(frozen=True)
class PromptFeature:
    key: str
    label: str
    default_template: str
    output_contract: str
    variables: tuple[PromptVariable, ...]


#: 保留槽位（不可编辑）：编辑器与 API 以 reserved_variables 呈现
RESERVED_OUTPUT_CONTRACT = PromptVariable(
    name="output_contract",
    label="输出结构槽位",
    render="替换为固定段原文（不可编辑；缺失时运行期自动补于末尾）",
    missing_hint="",
)

SEED_EXPAND = PromptFeature(
    key="seed_expand",
    label="AI 扩充（种子扩充）",
    default_template=(
        "你是 B2B 外贸获客的市场调研助手。请基于你的知识图谱能力，"
        "为下列业务扩张目标市场的『爬虫种子』（检索意图）与具名机构实体。\n"
        "{description}\n"
        "{existing_nodes}\n"
        "{output_contract}\n"
        "要求：seeds 约 {count} 条，query 一律为中文母版表述（如「电力金具 电气承包 肯尼亚」），"
        "表达检索意图即可，勿堆砌英文关键词；"
        '具名机构实体的 query 为「"机构名" 联系方式」形式，机构名保留原文、不翻译；'
        "org 优先列举真实存在的买方组织（各国电网公司、输配电运营商、EPC 总包、"
        "电气/紧固件经销商、展会与行业协会等）。"
        "中文母版经人工审核后由系统翻译为各目标语言版本。"
    ),
    output_contract=(
        "输出 JSON，结构：\n"
        "- nodes[]: {node_type: product_line|persona|market|org, name, attributes(对象), "
        "confidence(0-1), rationale}\n"
        "- edges[]: {from(节点名), to(节点名), relation_type: product_fit_persona|"
        "product_target_market|org_in_market|org_has_persona}\n"
        "- seeds[]: {query(中文检索意图), product_line(节点名,可选), persona(节点名,可选), "
        "market(节点名,可选), priority(1-3), rationale}"
    ),
    variables=(
        PromptVariable(
            name="description",
            label="业务描述",
            render="有值 →「业务描述：…」；未填 → 整行省略",
            missing_hint="表单中的业务描述",
        ),
        PromptVariable(
            name="existing_nodes",
            label="已有节点名单",
            render="按产品线/客户角色/市场（国家）逐行「已有X：A、B」（每类最多 80 个）；空 → 整行省略",
            missing_hint="表单的参考节点与已有节点名单",
        ),
        PromptVariable(
            name="count",
            label="候选数量",
            render="纯数字（表单的候选数量，缺省 20）",
            missing_hint="表单的候选数量",
        ),
    ),
)

CONTENT_DRAFT = PromptFeature(
    key="content_draft",
    label="AI 起草（内容母版）",
    default_template=(
        "你是资深外贸销售文案专家。请为下列业务撰写一条{content_type}（语言：{language}）文案。\n"
        "{brief}\n"
        "{tone}\n"
        "{output_contract}\n"
        "要求：正文可使用 {{company_name}} 之类的变量占位符（收件人维度个性化）；"
        "不要编造具体价格与交期；落款处使用 {{signature}} 占位。"
    ),
    output_contract='输出 JSON：{"subject": "主题行（如适用）", "body_md": "Markdown 正文"}。',
    variables=(
        PromptVariable(
            name="brief",
            label="业务要点",
            render="「业务要点：…」",
            missing_hint="表单的业务要点",
        ),
        PromptVariable(
            name="tone",
            label="语气",
            render="「语气：…。」；未填 →「语气：专业、克制、以价值为先。」",
            missing_hint="表单的语气（缺省语气文本也不再发送）",
        ),
        PromptVariable(
            name="content_type",
            label="内容类型",
            render="主题的内容类型名（纯值，如「开发信」）",
            missing_hint="主题的内容类型",
        ),
        PromptVariable(
            name="language",
            label="语言",
            render="母版语言代码（纯值，如 zh）",
            missing_hint="母版语言",
        ),
    ),
)

#: 功能清单（顺序即 API 列表顺序：contract §1）
FEATURES: dict[str, PromptFeature] = {
    SEED_EXPAND.key: SEED_EXPAND,
    CONTENT_DRAFT.key: CONTENT_DRAFT,
}

#: 全部已知 token 名（跨功能）——只做识别，替换按功能白名单（他功能 token 原样保留）
_TOKEN_RE = re.compile(r"\{(description|existing_nodes|count|brief|tone|content_type|language|output_contract)\}")

#: 未知变量扫描：排除 `{{...}}`（内容占位符豁免，research R2）
_UNKNOWN_RE = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")


def get_feature(key: str) -> PromptFeature | None:
    return FEATURES.get(key)


# ---- 渲染 ----

def _render_values(feature: PromptFeature, context: dict) -> dict[str, str]:
    """按 data-model.md §2.2 的渲染语义表产出各变量的替换值（逐条与 legacy 行为对齐）。"""
    if feature.key == "seed_expand":
        values: dict[str, str] = {}
        raw_description = context.get("description")
        # legacy 语义：真值判断用原文（纯空白 → 仍生成「业务描述：」空标签行），strip 在标签内
        values["description"] = (
            f"业务描述：{str(raw_description).strip()}" if raw_description else ""
        )
        by_type = context.get("existing_nodes") or {}
        lines = []
        for node_type in ("product_line", "persona", "market"):
            names = [str(n) for n in (by_type.get(node_type) or []) if str(n)]
            if names:
                lines.append(f"已有{SEED_NODE_LABELS[node_type]}：{'、'.join(names[:80])}")
        values["existing_nodes"] = "\n".join(lines)
        # legacy 语义：payload 侧 `int(count or 20)`——0/None 一律回落 20
        values["count"] = str(context.get("count") or 20)
        return values
    if feature.key == "content_draft":
        # legacy 语义：真值判断与取值都用原文（f"{tone or 缺省}"），不做 strip
        raw_tone = context.get("tone")
        tone_text = str(raw_tone) if raw_tone else "专业、克制、以价值为先"
        return {
            "brief": f"业务要点：{context.get('brief') or ''}",
            "tone": f"语气：{tone_text}。",
            "content_type": str(context.get("content_type") or ""),
            "language": str(context.get("language") or ""),
        }
    return {}


def _drop_standalone_line(text: str, token: str) -> str:
    """空值变量独占整行 → 整行（含换行）省略（复现 legacy 的不生成该行语义）。"""
    escaped = re.escape(token)
    text = re.sub(rf"(?m)^[ \t]*{escaped}[ \t]*\n", "", text)
    return re.sub(rf"(?m)^[ \t]*{escaped}[ \t]*$", "", text)


def compose(feature_key: str, template: str, context: dict) -> str:
    """组合用户消息：变量替换（单次扫描，替换值不再被重扫）+ 结构槽位处理。

    - 已知变量：空值独占整行时整行省略，其余精确 token 替换；
    - `{output_contract}`：模板内存在 → 原位替换为固定段；缺失 → 末尾自动补充；
    - 他功能变量与未知 token：原样透传。
    """
    feature = FEATURES[feature_key]
    values = _render_values(feature, context)

    text = template
    for var in feature.variables:
        if not values.get(var.name):
            text = _drop_standalone_line(text, "{" + var.name + "}")

    known_names = {var.name for var in feature.variables}
    contract = feature.output_contract
    has_slot = "{output_contract}" in text

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name == "output_contract":
            return contract
        if name in known_names:
            return values[name]
        return match.group(0)  # 他功能的 token：本功能不负责替换

    text = _TOKEN_RE.sub(_sub, text)
    if not has_slot:
        text = text.rstrip("\n") + "\n\n" + contract
    return text


# ---- 校验 ----

def validate_template(feature_key: str, content: str) -> dict:
    """保存校验（contract §7）：空/超长 → errors（不产生 warnings）；其余 → warnings 不阻断。"""
    feature = FEATURES[feature_key]
    if not content.strip():
        return {"errors": ["提示词不能为空"], "warnings": []}
    if len(content) > MAX_TEMPLATE_LENGTH:
        return {
            "errors": [f"提示词超过长度上限（{len(content)}/{MAX_TEMPLATE_LENGTH} 字符）"],
            "warnings": [],
        }

    warnings: list[dict] = []
    known = {var.name for var in feature.variables} | {"output_contract"}

    unknown: list[str] = []
    for match in _UNKNOWN_RE.finditer(content):
        name = match.group(1)
        if name not in known and name not in unknown:
            unknown.append(name)
    for name in unknown:
        warnings.append(
            {
                "code": "unknown_variable",
                "message": f"未识别的变量 {{{name}}}：该处将按原文发送，建议改名或删除",
            }
        )

    for var in feature.variables:
        if "{" + var.name + "}" not in content:
            warnings.append(
                {
                    "code": "missing_variable",
                    "message": f"未引用 {{{var.name}}}（{var.label}）：{var.missing_hint}将不再发送给模型",
                }
            )

    if "{output_contract}" not in content:
        warnings.append(
            {
                "code": "missing_output_contract",
                "message": "未包含 {output_contract} 输出结构槽位：运行时会自动补充在末尾",
            }
        )

    return {"errors": [], "warnings": warnings}
