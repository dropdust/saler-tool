"""T028 单元测试：AI 扩充/翻译落库（中文母版、全部 pending、query 去重、glossary、错误传递）。"""

from __future__ import annotations

import pytest

from saler.core.graph import service as graph_service
from saler.core.seeds import service as seed_service
from saler.core.seeds.ai import run_expansion
from saler.core.seeds.ai_translate import run_translate_seeds, run_translate_terms
from saler.db.models import GraphNode, NodeTerm, Seed
from saler.providers.errors import ErrorKind, ProviderError
from tests.fixtures.fakes.llm_fake import FakeLLMProvider, default_expansion


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


async def test_expansion_persists_pending_and_dedupes(session_factory):
    report = await run_expansion(
        _Ctx(), session_factory, FakeLLMProvider(), payload={"description": "紧固件出口", "count": 5}
    )
    assert report["nodes_created"] == 2
    assert report["edges_created"] == 1
    assert report["seeds_created"] == 2

    with session_factory() as db:
        for node in db.query(GraphNode).all():
            assert node.review_status == "pending"
            assert node.source == "llm"
        for seed in db.query(Seed).all():
            assert seed.review_status == "pending"
            assert seed.source == "llm"
            assert seed.batch.startswith("llm-")
            assert seed.lang == "zh"  # 扩充产出一律中文母版，待审核后翻译
        entity_seed = db.query(Seed).filter_by(query='"Fake Utility Co" 联系方式').one()
        assert entity_seed.persona_id is not None  # 分类引用已解析

    report2 = await run_expansion(_Ctx(), session_factory, FakeLLMProvider(), payload={})
    assert report2["seeds_created"] == 0
    assert report2["skipped"]["seeds"] == 2


async def test_expansion_seeds_are_chinese_masters(session_factory):
    """扩充提示词要求中文母版；模型输出带的 lang 字段被忽略，落库固定 lang=zh（FR-012 ①）。"""
    provider = FakeLLMProvider(
        script=[{**default_expansion(), "seeds": [{"query": "金具 经销商 东非", "lang": "en"}]}]
    )
    report = await run_expansion(_Ctx(), session_factory, provider, payload={"count": 3})
    assert report["seeds_created"] == 1

    with session_factory() as db:
        seed = db.query(Seed).one()
        assert seed.lang == "zh"
        assert seed.review_status == "pending"

    prompt = provider.calls[0]["prompt"]
    assert "中文母版" in prompt
    assert '"lang"' not in prompt  # 种子结构不再由模型决定语言


async def test_expansion_prompt_no_longer_requests_target_langs(session_factory):
    """目标语言不进扩充提示词：翻译为审核后的独立步骤（FR-012 ②）。"""
    provider = FakeLLMProvider()
    await run_expansion(_Ctx(), session_factory, provider, payload={"langs": ["en", "ru"]})
    prompt = provider.calls[0]["prompt"]
    assert "种子语言" not in prompt


async def test_expansion_provider_error_propagates(session_factory):
    provider = FakeLLMProvider(script=[ProviderError(ErrorKind.AUTH, "bad key")])
    with pytest.raises(ProviderError):
        await run_expansion(_Ctx(), session_factory, provider, payload={})


async def test_expansion_uses_customized_template_with_variables(session_factory):
    """T284：运行开始读取有效模板并组合——自定义文本 + 变量替换 + 固定段在位。"""
    from saler.core.prompts import registry, store

    with session_factory() as db:
        store.create(
            db,
            "seed_expand",
            name="自定义",
            content="自定义角色指令。\n{description}\n{existing_nodes}\n{output_contract}\n请产出约 {count} 条。",
            activate=True,
        )

    provider = FakeLLMProvider()
    await run_expansion(
        _Ctx(), session_factory, provider, payload={"description": "紧固件出口", "count": 6}
    )

    prompt = provider.calls[0]["prompt"]
    assert prompt.startswith("自定义角色指令。")
    assert "业务描述：紧固件出口" in prompt
    assert "请产出约 6 条。" in prompt
    assert registry.get_feature("seed_expand").output_contract in prompt
    assert "{description}" not in prompt and "{count}" not in prompt and "{existing_nodes}" not in prompt


async def test_expansion_default_path_composes_registry_default(session_factory):
    """T284：未自定义 → 有效模板 = 注册表默认（组合经 run 管线；逐字等价由 golden 单测锁定）。"""
    from saler.core.prompts import registry

    provider = FakeLLMProvider()
    await run_expansion(_Ctx(), session_factory, provider, payload={"description": "X", "count": 8})

    expected = registry.compose(
        "seed_expand",
        registry.get_feature("seed_expand").default_template,
        {"description": "X", "existing_nodes": {}, "count": 8},
    )
    assert provider.calls[0]["prompt"] == expected


async def test_expansion_prompt_snapshot_isolated_from_midrun_switch(session_factory):
    """T296 边界：运行开始时定格的提示词快照——运行中切换生效模板不影响在途运行。

    在模型调用进行中（provider.generate_structured 内部）新建并切换生效模板，
    在途 prompt 必须仍为开始时的快照；下一次运行才使用新模板（FR-007/契约 §6）。
    """
    from saler.core.prompts import store

    with session_factory() as db:
        store.create(
            db,
            "seed_expand",
            name="A 版",
            content="A 指令 {description} {existing_nodes} {count} {output_contract}",
        )

    provider = FakeLLMProvider()
    original = provider.generate_structured

    def generate_with_switch(*, prompt: str, **kwargs):
        with session_factory() as db:
            store.create(
                db,
                "seed_expand",
                name="B 版",
                content="B 指令 {description} {existing_nodes} {count} {output_contract}",
            )
        return original(prompt=prompt, **kwargs)

    provider.generate_structured = generate_with_switch  # type: ignore[method-assign]
    await run_expansion(_Ctx(), session_factory, provider, payload={"description": "X", "count": 3})
    assert provider.calls[0]["prompt"].startswith("A 指令")  # 在途快照不受切换影响

    # 下一次运行使用新生效模板（B 版）
    provider2 = FakeLLMProvider()
    await run_expansion(_Ctx(), session_factory, provider2, payload={"description": "X", "count": 3})
    assert provider2.calls[0]["prompt"].startswith("B 指令")


async def test_translate_seeds_creates_pending_variants_with_glossary(session_factory):
    with session_factory() as db:
        product_line = graph_service.create_node(db, node_type="product_line", name="金具")
        source_seed = seed_service.create_seed(
            db, query="电力金具 供应商", lang="zh", product_line_id=product_line.id
        )
        graph_service.add_term(db, node_id=product_line.id, lang="en", term="Power Fittings")

    provider = FakeLLMProvider()
    report = await run_translate_seeds(
        _Ctx(),
        session_factory,
        provider,
        payload={"seed_ids": [source_seed.id], "targets": ["en", "ru"]},
    )
    assert report["created"] == 2
    assert report["by_lang"] == {"en": 1, "ru": 1}
    assert provider.calls[0]["glossary"] == {"金具": "Power Fittings"}

    with session_factory() as db:
        en_seed = db.query(Seed).filter_by(query="[en] 电力金具 供应商").one()
        assert en_seed.lang == "en"
        assert en_seed.review_status == "pending"
        assert en_seed.product_line_id == product_line.id
        assert "译自种子" in (en_seed.note or "")


async def test_translate_seeds_requires_targets(session_factory):
    from saler.core.errors import ValidationFailed

    with pytest.raises(ValidationFailed):
        await run_translate_seeds(_Ctx(), session_factory, FakeLLMProvider(), payload={})


async def test_translate_terms(session_factory):
    with session_factory() as db:
        market = graph_service.create_node(db, node_type="market", name="肯尼亚")

    report = await run_translate_terms(
        _Ctx(),
        session_factory,
        FakeLLMProvider(),
        payload={"node_ids": [market.id], "targets": ["en"]},
    )
    assert report["created"] == 1
    with session_factory() as db:
        term = db.query(NodeTerm).one()
        assert term.lang == "en"
        assert term.term == "[en] 肯尼亚"
        assert term.review_status == "pending"
        assert term.source == "llm"
