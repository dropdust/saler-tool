"""AI 种子扩充（FR-012①）：大模型知识图谱能力 → 候选节点/边/种子。

- 种子一律产出**中文母版**（lang=zh）：语言不由模型决定，审核通过后再经
  `ai_translate.run_translate_seeds` 翻译为目标语言版本（FR-012②）；
- 全部产出以 `source=llm`、`review_status=pending` 落库（必须人工审核后进入执行队列）。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from saler.core.errors import Duplicate, ValidationFailed
from saler.core.graph import service as graph_service
from saler.core.seeds import service as seed_service
from saler.db.models import GraphNode, Seed
from saler.jobs.engine import JobContext
from saler.providers.llm import call_log, telemetry
from saler.providers.llm.schemas import SEED_EXPANSION_V1_SCHEMA
from saler.services.operation_log import log_op

NODE_TYPE_LABELS = {
    "product_line": "产品线",
    "persona": "客户角色",
    "market": "市场/国家",
    "org": "具名机构实体",
}

#: 扩充候选种子的固定语言：中文母版（翻译为目标语言是审核后的独立步骤，FR-012②）
MASTER_LANG = "zh"


def build_expansion_prompt(
    *,
    description: str | None,
    node_names_by_type: dict[str, list[str]],
    count: int,
) -> str:
    parts = [
        "你是 B2B 外贸获客的市场调研助手。请基于你的知识图谱能力，"
        "为下列业务扩张目标市场的『爬虫种子』（检索意图）与具名机构实体。",
    ]
    if description:
        parts.append(f"业务描述：{description.strip()}")
    for node_type in ("product_line", "persona", "market"):
        names = node_names_by_type.get(node_type, [])
        if names:
            parts.append(f"已有{NODE_TYPE_LABELS[node_type]}：{'、'.join(names[:80])}")
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


async def run_expansion(
    ctx: JobContext,
    session_factory: sessionmaker[Session],
    provider,
    *,
    payload: dict,
) -> dict:
    description = payload.get("description")
    from_node_ids = payload.get("from_node_ids") or []
    count = int(payload.get("count") or 20)

    with session_factory() as db:
        names_by_type: dict[str, list[str]] = {k: [] for k in NODE_TYPE_LABELS}
        for node_id in from_node_ids:
            node = db.get(GraphNode, node_id)
            if node is not None:
                names_by_type[node.node_type].append(node.name)
        for node_type in ("product_line", "persona", "market"):
            rows = (
                db.query(GraphNode)
                .filter_by(node_type=node_type, status="active")
                .limit(60)
                .all()
            )
            for row in rows:
                if row.name not in names_by_type[node_type]:
                    names_by_type[node_type].append(row.name)

    prompt = build_expansion_prompt(
        description=description, node_names_by_type=names_by_type, count=count
    )
    ctx.progress(phase="calling_llm")
    ctx.log("调用大模型进行知识图谱扩充（结果将进入待审核）…")
    recorder = call_log.make_call_recorder(
        session_factory, job_id=ctx.job_id, operation="seed_expand"
    )
    data = await asyncio.to_thread(
        provider.generate_structured,
        prompt=prompt,
        schema=SEED_EXPANSION_V1_SCHEMA,
        on_attempt=recorder,
    )
    await ctx.checkpoint()

    report: dict = {
        "nodes_created": 0,
        "edges_created": 0,
        "seeds_created": 0,
        "skipped": {"nodes": 0, "edges": 0, "seeds": 0},
    }
    batch = f"llm-{datetime.now(UTC).strftime('%Y%m%d')}"
    with session_factory() as db:
        telemetry.record_from_provider(db, provider, operation="seed_expand")
        existing: dict[tuple[str, str], int] = {
            (node.node_type, node.name): node.id for node in db.query(GraphNode).all()
        }
        for cand in data.get("nodes", []):
            node_type = (cand.get("node_type") or "").strip()
            name = (cand.get("name") or "").strip()
            if node_type not in NODE_TYPE_LABELS or not name:
                report["skipped"]["nodes"] += 1
                continue
            if (node_type, name) in existing:
                report["skipped"]["nodes"] += 1
                continue
            try:
                node = graph_service.create_node(
                    db,
                    node_type=node_type,
                    name=name,
                    attributes=cand.get("attributes") or {},
                    confidence=cand.get("confidence"),
                    source="llm",
                )
                existing[(node_type, name)] = node.id
                report["nodes_created"] += 1
            except Duplicate:
                report["skipped"]["nodes"] += 1

        name_to_id: dict[str, int] = {}
        for (_node_type, name), node_id in existing.items():
            name_to_id.setdefault(name, node_id)

        for cand in data.get("edges", []):
            from_id = name_to_id.get((cand.get("from") or "").strip())
            to_id = name_to_id.get((cand.get("to") or "").strip())
            if not from_id or not to_id:
                report["skipped"]["edges"] += 1
                continue
            try:
                graph_service.create_edge(
                    db,
                    from_node_id=from_id,
                    to_node_id=to_id,
                    relation_type=cand.get("relation_type"),
                    source="llm",
                )
                report["edges_created"] += 1
            except (Duplicate, ValidationFailed):
                report["skipped"]["edges"] += 1

        for cand in data.get("seeds", []):
            query = (cand.get("query") or "").strip()
            if not query or db.query(Seed).filter_by(query=query).first():
                report["skipped"]["seeds"] += 1
                continue
            try:
                seed_service.create_seed(
                    db,
                    query=query,
                    lang=MASTER_LANG,
                    priority=int(cand.get("priority") or 2),
                    product_line_id=name_to_id.get((cand.get("product_line") or "").strip()),
                    persona_id=name_to_id.get((cand.get("persona") or "").strip()),
                    market_id=name_to_id.get((cand.get("market") or "").strip()),
                    batch=batch,
                    source="llm",
                    note=cand.get("rationale"),
                )
                report["seeds_created"] += 1
            except (Duplicate, ValidationFailed):
                report["skipped"]["seeds"] += 1

        log_op(
            db,
            "llm",
            f"AI 扩充：新增节点 {report['nodes_created']}、关系 {report['edges_created']}、"
            f"中文母版种子 {report['seeds_created']}（全部待审核）",
            ref_type="job",
            ref_id=ctx.job_id,
            payload=report,
        )
    ctx.progress(phase="done", **report)
    return report
