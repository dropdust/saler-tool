"""结构化输出 schema（版本化，contracts/provider-adapters.md §1）。

注意：LLM 输出一律视为"候选/草稿"，落库时一律 review_status=pending / status=draft，
必须先经人工审核（FR-012/038）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NodeCandidate(BaseModel):
    node_type: Literal["product_line", "persona", "market", "org"]
    name: str
    attributes: dict = Field(default_factory=dict)
    confidence: float | None = None
    rationale: str | None = None


class EdgeCandidate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    relation_type: Literal[
        "product_fit_persona", "product_target_market", "org_in_market", "org_has_persona"
    ]


class SeedCandidate(BaseModel):
    """扩充候选种子：query 为中文母版检索意图；语言由管线固定为 zh，不由模型决定（FR-012①→②）。"""

    query: str
    product_line: str | None = None
    persona: str | None = None
    market: str | None = None
    priority: int = 2
    rationale: str | None = None


class SeedExpansionV1(BaseModel):
    nodes: list[NodeCandidate] = Field(default_factory=list)
    edges: list[EdgeCandidate] = Field(default_factory=list)
    seeds: list[SeedCandidate] = Field(default_factory=list)


class TranslationItem(BaseModel):
    source: str
    target: str


class SeedTranslationV1(BaseModel):
    items: list[TranslationItem] = Field(default_factory=list)


class ContentDraftV1(BaseModel):
    subject: str | None = None
    body_md: str


class ContentTranslationV1(BaseModel):
    subject: str | None = None
    body_md: str


# ---- JSON Schema 产物（供适配器 generate_structured 校验） ----

SEED_EXPANSION_V1_SCHEMA = SeedExpansionV1.model_json_schema(by_alias=True)
SEED_TRANSLATION_V1_SCHEMA = SeedTranslationV1.model_json_schema()
CONTENT_DRAFT_V1_SCHEMA = ContentDraftV1.model_json_schema()
CONTENT_TRANSLATION_V1_SCHEMA = ContentTranslationV1.model_json_schema()

# 通用"字符串数组"schema（translate 批量返回）
TRANSLATION_LIST_SCHEMA: dict = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "string"}}},
    "required": ["items"],
    "additionalProperties": False,
}
