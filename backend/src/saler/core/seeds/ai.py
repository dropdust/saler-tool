"""AI 种子扩充（FR-012①）：大模型知识图谱能力 → 候选节点/边/种子。

- 种子一律产出**中文母版**（lang=zh）：语言不由模型决定，审核通过后再经
  `ai_translate.run_translate_seeds` 翻译为目标语言版本（FR-012②）；
- 全部产出以 `source=llm`、`review_status=pending` 落库（必须人工审核后进入执行队列）；
- 提示词（006）：运行开始时读取有效模板（设置覆盖 or 注册表默认）经
  `core/prompts.registry.compose` 组合——默认路径与 005 前硬编码逐字等价（golden 锁定）。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from saler.core.errors import Duplicate, ValidationFailed
from saler.core.graph import service as graph_service
from saler.core.prompts import registry, store
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
        # 006：运行开始时定格有效模板（其后编辑只影响下一次运行；FR-007）
        template, _customized = store.get_effective(db, "seed_expand")

    prompt = registry.compose(
        "seed_expand",
        template,
        {"description": description, "existing_nodes": names_by_type, "count": count},
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
