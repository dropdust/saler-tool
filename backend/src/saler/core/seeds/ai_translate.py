"""AI 翻译服务（FR-009/012）：中文种子与词表 → 目标语言（全部待审核）。

- 翻译结果复用图谱词表术语（glossary），保持产品名/行业术语的多语言一致；
- 新建的种子/词条 source=llm、review_status=pending。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from saler.core.errors import Duplicate, ValidationFailed
from saler.core.graph import service as graph_service
from saler.core.seeds import service as seed_service
from saler.db.models import GraphNode, NodeTerm, Seed
from saler.jobs.engine import JobContext
from saler.providers.llm import call_log, telemetry
from saler.services.operation_log import log_op


def _glossary_for(db: Session, targets: list[str]) -> dict[str, dict[str, str]]:
    """目标语言术语表：节点中文名 → 该语言词条（用于翻译一致性）。"""
    rows = db.query(NodeTerm).filter(NodeTerm.lang.in_(targets), NodeTerm.review_status != "rejected").all()
    node_names = {node.id: node.name for node in db.query(GraphNode).all()}
    out: dict[str, dict[str, str]] = {}
    for term in rows:
        source_name = node_names.get(term.node_id)
        if source_name:
            out.setdefault(term.lang, {})[source_name] = term.term
    return out


async def run_translate_seeds(
    ctx: JobContext,
    session_factory: sessionmaker[Session],
    provider,
    *,
    payload: dict,
) -> dict:
    seed_ids = payload.get("seed_ids") or []
    targets = [t.strip() for t in (payload.get("targets") or []) if t and t.strip()]
    if not seed_ids or not targets:
        raise ValidationFailed("需要提供 seed_ids 与 targets")

    with session_factory() as db:
        seeds = db.query(Seed).filter(Seed.id.in_(seed_ids)).all()
        if not seeds:
            raise ValidationFailed("未找到任何种子")
        seed_info = [
            (s.id, s.query, s.lang, s.product_line_id, s.persona_id, s.market_id, s.priority) for s in seeds
        ]
        source_lang = "zh" if any((s.lang or "").startswith("zh") for s in seeds) else (seeds[0].lang or "zh")
        glossary = _glossary_for(db, targets)

    report: dict = {"created": 0, "skipped": 0, "by_lang": {}}
    batch_date = datetime.now(UTC).strftime("%Y%m%d")
    recorder = call_log.make_call_recorder(session_factory, job_id=ctx.job_id, operation="seed_translate")
    for lang in targets:
        await ctx.checkpoint()
        texts = [row[1] for row in seed_info]
        ctx.progress(phase=f"translating:{lang}", total=len(texts))
        recorder.phase = f"lang:{lang}"
        translated = await asyncio.to_thread(
            provider.translate,
            items=texts,
            source_lang=source_lang,
            target_lang=lang,
            glossary=glossary.get(lang),
            on_attempt=recorder,
        )
        created = skipped = 0
        with session_factory() as db:
            telemetry.record_from_provider(db, provider, operation="seed_translate")
            batch = f"llm-tr-{lang}-{batch_date}"
            for info, out in zip(seed_info, translated, strict=False):
                seed_id, _src, _slang, product_line_id, persona_id, market_id, priority = info
                text = (out or "").strip()
                if not text or db.query(Seed).filter_by(query=text).first():
                    skipped += 1
                    continue
                try:
                    seed_service.create_seed(
                        db,
                        query=text,
                        lang=lang,
                        product_line_id=product_line_id,
                        persona_id=persona_id,
                        market_id=market_id,
                        priority=priority,
                        batch=batch,
                        source="llm",
                        note=f"译自种子 #{seed_id}",
                    )
                    created += 1
                except (Duplicate, ValidationFailed):
                    skipped += 1
            log_op(
                db,
                "llm",
                f"种子翻译到 {lang}：新增 {created} 条（待审核）",
                ref_type="job",
                ref_id=ctx.job_id,
                payload={"lang": lang, "created": created, "skipped": skipped},
            )
        report["created"] += created
        report["skipped"] += skipped
        report["by_lang"][lang] = created
    ctx.progress(phase="done", **report)
    return report


async def run_translate_terms(
    ctx: JobContext,
    session_factory: sessionmaker[Session],
    provider,
    *,
    payload: dict,
) -> dict:
    node_ids = payload.get("node_ids") or []
    targets = [t.strip() for t in (payload.get("targets") or []) if t and t.strip()]
    if not node_ids or not targets:
        raise ValidationFailed("需要提供 node_ids 与 targets")

    with session_factory() as db:
        nodes = db.query(GraphNode).filter(GraphNode.id.in_(node_ids)).all()
        if not nodes:
            raise ValidationFailed("未找到任何图谱节点")
        node_info = [(n.id, n.name) for n in nodes]

    report: dict = {"created": 0, "skipped": 0, "by_lang": {}}
    recorder = call_log.make_call_recorder(session_factory, job_id=ctx.job_id, operation="term_translate")
    for lang in targets:
        await ctx.checkpoint()
        ctx.progress(phase=f"translating:{lang}", total=len(node_info))
        recorder.phase = f"lang:{lang}"
        translated = await asyncio.to_thread(
            provider.translate,
            items=[row[1] for row in node_info],
            source_lang="zh",
            target_lang=lang,
            on_attempt=recorder,
        )
        created = skipped = 0
        with session_factory() as db:
            telemetry.record_from_provider(db, provider, operation="term_translate")
            for (node_id, _name), out in zip(node_info, translated, strict=False):
                text = (out or "").strip()
                if not text:
                    skipped += 1
                    continue
                try:
                    graph_service.add_term(
                        db,
                        node_id=node_id,
                        lang=lang,
                        term=text,
                        term_type="name",
                        source="llm",
                        skip_duplicates=True,
                    )
                    created += 1
                except (Duplicate, ValidationFailed):
                    skipped += 1
            log_op(
                db,
                "llm",
                f"词表翻译到 {lang}：处理 {created} 条（待审核）",
                ref_type="job",
                ref_id=ctx.job_id,
                payload={"lang": lang, "created": created, "skipped": skipped},
            )
        report["created"] += created
        report["skipped"] += skipped
        report["by_lang"][lang] = created
    ctx.progress(phase="done", **report)
    return report
