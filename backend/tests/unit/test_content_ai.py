"""T288 单元测试：AI 起草运行接入组合管线（自定义模板生效 / 默认等价 / 两功能独立）。

- 自定义模板经模板库 `store.create(..., activate=True)` 预置，运行开始定格生效模板；
- 渲染语义：`{brief}`→「业务要点：…」、`{tone}` 两态、`{{company_name}}`/`{{signature}}` 豁免；
- 默认路径 == registry 默认组合（逐字等价由 test_prompt_registry 的 golden 锁定）。
"""

from __future__ import annotations

from saler.core.content import service as content_service
from saler.core.content.ai import run_content_draft
from saler.core.prompts import registry, store
from saler.db.models import ContentVariant
from tests.fixtures.fakes.llm_fake import FakeLLMProvider


class _Ctx:
    """JobContext 轻量替身（不触真实 job 表）。"""

    job_id = None

    def __init__(self) -> None:
        self.progress_calls: list[dict] = []
        self.logs: list[str] = []

    def progress(self, **data) -> None:
        self.progress_calls.append(data)

    def log(self, message: str, **_kwargs) -> None:
        self.logs.append(message)

    async def checkpoint(self) -> None:
        return None


def _draft_script() -> list[dict]:
    return [{"subject": "肯尼亚电力金具供应", "body_md": "尊敬的 {{company_name}}，……\n{{signature}}"}]


def _make_theme(session_factory, name: str = "验收主题") -> int:
    with session_factory() as db:
        theme = content_service.create_theme(db, name=name, content_type="email", master_lang="zh")
        return theme.id


async def test_draft_uses_customized_template_with_variables(session_factory):
    theme_id = _make_theme(session_factory)
    with session_factory() as db:
        store.create(
            db,
            "content_draft",
            name="写作规范",
            content=(
                "自定义写作指令（类型：{content_type}，语言：{language}）。\n{brief}\n{tone}\n"
                "{output_contract}\n首段必须以一句话概括价值主张；落款 {{signature}} 保留。"
            ),
        )

    provider = FakeLLMProvider(script=_draft_script())
    result = await run_content_draft(
        _Ctx(),
        session_factory,
        provider,
        payload={"theme_id": theme_id, "brief": "向肯尼亚输电线路承包商介绍电力金具", "tone": None},
    )

    prompt = provider.calls[0]["prompt"]
    assert prompt.startswith("自定义写作指令（类型：email，语言：zh）。")
    assert "业务要点：向肯尼亚输电线路承包商介绍电力金具" in prompt
    assert "语气：专业、克制、以价值为先。" in prompt  # tone 缺省渲染
    assert "首段必须以一句话概括价值主张；" in prompt  # 自定义约束在途
    assert "{{signature}}" in prompt  # 双花括号豁免（未误替换）
    assert registry.get_feature("content_draft").output_contract in prompt
    for token in ("{brief}", "{tone}", "{content_type}", "{language}", "{output_contract}"):
        assert token not in prompt

    with session_factory() as db:
        variant = db.get(ContentVariant, result["variant_id"])
        assert variant is not None
        version = content_service.get_current_version(db, variant)
        assert version is not None and version.subject == "肯尼亚电力金具供应"


async def test_draft_tone_value_renders_with_period(session_factory):
    theme_id = _make_theme(session_factory, name="语气主题")
    provider = FakeLLMProvider(script=_draft_script())
    await run_content_draft(
        _Ctx(),
        session_factory,
        provider,
        payload={"theme_id": theme_id, "brief": "电力金具", "tone": "热情"},
    )
    assert "语气：热情。" in provider.calls[0]["prompt"]


async def test_draft_default_path_composes_registry_default(session_factory):
    theme_id = _make_theme(session_factory, name="默认主题")
    provider = FakeLLMProvider(script=_draft_script())
    await run_content_draft(
        _Ctx(),
        session_factory,
        provider,
        payload={"theme_id": theme_id, "brief": "电力金具出口", "tone": None},
    )
    expected = registry.compose(
        "content_draft",
        registry.get_feature("content_draft").default_template,
        {"brief": "电力金具出口", "tone": None, "content_type": "email", "language": "zh"},
    )
    assert provider.calls[0]["prompt"] == expected


async def test_features_are_independent(session_factory):
    """扩充模板库变更不影响起草运行（起草仍走默认）。"""
    theme_id = _make_theme(session_factory, name="独立主题")
    with session_factory() as db:
        store.create(
            db,
            "seed_expand",
            name="扩充专用",
            content="扩充自定义 {description} {existing_nodes} {count} {output_contract}",
        )

    provider = FakeLLMProvider(script=_draft_script())
    await run_content_draft(
        _Ctx(),
        session_factory,
        provider,
        payload={"theme_id": theme_id, "brief": "电力金具", "tone": None},
    )
    expected = registry.compose(
        "content_draft",
        registry.get_feature("content_draft").default_template,
        {"brief": "电力金具", "tone": None, "content_type": "email", "language": "zh"},
    )
    assert provider.calls[0]["prompt"] == expected
