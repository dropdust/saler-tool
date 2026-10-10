"""检索扩充图谱（FR-013）：检索结果/目录 → 候选实体（org）与种子。

- 复用检索渠道链（T015/T056）与落库/审核管线（T036），产出**一律待审核**（source=search）；
- 提炼规则为启发式（标题归一化 + 组织名特征词），候选均带来源 URL 供人工核对；
- `seed.query` / `(node_type,name)` 唯一约束去重，重复项计入 skipped。
"""

from __future__ import annotations

import asyncio
import re

from sqlalchemy.orm import Session, sessionmaker

from saler.core.errors import Duplicate, ValidationFailed
from saler.core.graph import service as graph_service
from saler.core.seeds import service as seed_service
from saler.db.models import GraphNode
from saler.jobs.engine import JobContext
from saler.services.operation_log import log_op

#: 组织名特征词（公司/机构常见后缀与行业词）
ORG_HINT = re.compile(
    r"\b(ltd|limited|llc|inc|corp(?:oration)?|gmbh|s\.?a\.?|sas|bv|nv|pty|co\.?|company|group|"
    r"holdings?|industries|industrial|electric(?:al|ity)?|power|energy|switchgear|hardware|"
    r"trading|import(?:s|er)?|export(?:s|er)?|international|enterprises?|solutions|"
    r"technolog(?:y|ies)|engineering|contractors?|suppliers?|distributors?)\b",
    re.I,
)
#: 列表/导购/资讯页（非公司实体）
LIST_PAGE = re.compile(
    r"^\d|\b(best|top\s*\d|list|directory|guide|how\s+to|wiki|news|blog|jobs?|careers?)\b", re.I
)
GENERIC_DOMAINS = {
    "facebook.com", "linkedin.com", "twitter.com", "x.com", "instagram.com", "youtube.com",
    "wikipedia.org", "alibaba.com", "amazon.com", "indiamart.com", "bloomberg.com",
    "crunchbase.com", "made-in-china.com", "yellowpages.com", "yelu.com", "tiktok.com",
}
_SPLIT = re.compile(r"\s*[|｜–—-]\s+")


def site_name(url: str) -> str:
    host = (url or "").split("//")[-1].split("/")[0].split(":")[0].lower()
    return host[4:] if host.startswith("www.") else host


def clean_title(title: str) -> str | None:
    """标题归一化为候选公司名；列表/导购页返回 None。"""
    title = (title or "").strip()
    if not title or LIST_PAGE.search(title):
        return None
    segments = [seg.strip() for seg in _SPLIT.split(title) if seg.strip()]
    if not segments:
        return None
    for segment in segments:
        if ORG_HINT.search(segment):
            return segment.strip(" -|·—")
    return segments[0].strip(" -|·—") if len(segments[0]) <= 80 else None


def distill_orgs(results: list[tuple[str, list]], *, max_orgs: int) -> list[dict]:
    """检索结果 → 候选组织（去重、剔除通用域名与列表页）。"""
    orgs: list[dict] = []
    seen: set[str] = set()
    for query, items in results:
        for item in items:
            domain = site_name(getattr(item, "url", ""))
            if not domain or domain in GENERIC_DOMAINS or domain.endswith(".example"):
                continue
            name = clean_title(getattr(item, "title", ""))
            if not name or name.lower() in seen:
                continue
            if not ORG_HINT.search(name):
                continue
            seen.add(name.lower())
            orgs.append({"name": name, "url": item.url, "query": query, "domain": domain})
            if len(orgs) >= max_orgs:
                return orgs
    return orgs


def _market_context(db: Session, from_node_ids: list[int]) -> GraphNode | None:
    for node_id in from_node_ids:
        node = db.get(GraphNode, node_id)
        if node is not None and node.node_type == "market":
            return node
    return None


async def run_discover(
    ctx: JobContext,
    session_factory: sessionmaker[Session],
    search_provider,
    *,
    payload: dict,
) -> dict:
    queries = [q.strip() for q in (payload.get("queries") or []) if q and q.strip()]
    if not queries:
        raise ValidationFailed("请至少提供一个检索关键词")
    per_query = int(payload.get("per_query") or 10)
    lang = payload.get("lang") or "en"
    max_orgs = int(payload.get("max_orgs") or 20)
    max_seeds = int(payload.get("max_seeds") or 30)
    from_node_ids = payload.get("from_node_ids") or []

    ctx.progress(phase="searching", queried=0, total=len(queries))
    results: list[tuple[str, list]] = []
    for index, query in enumerate(queries, start=1):
        await ctx.checkpoint()
        items = await asyncio.to_thread(
            search_provider.search, query=query, count=per_query
        )
        results.append((query, items))
        ctx.log(f"检索「{query}」：{len(items)} 条结果")
        ctx.progress(phase="searching", queried=index, total=len(queries), found=sum(len(r[1]) for r in results))

    orgs = distill_orgs(results, max_orgs=max_orgs)
    ctx.progress(phase="distilling", candidates=len(orgs))

    nodes_created = nodes_skipped = edges_created = 0
    seeds_created = seeds_skipped = 0
    with session_factory() as db:
        market = _market_context(db, from_node_ids)
        org_nodes: list[tuple[dict, GraphNode]] = []
        for org in orgs:
            try:
                node = graph_service.create_node(
                    db,
                    node_type="org",
                    name=org["name"],
                    attributes={"website": org["url"], "source_query": org["query"]},
                    confidence=0.5,
                    evidence_url=org["url"],
                    source="search",
                    review_status="pending",
                )
                nodes_created += 1
                org_nodes.append((org, node))
            except Duplicate:
                nodes_skipped += 1
                existing = (
                    db.query(GraphNode)
                    .filter_by(node_type="org", name=org["name"])
                    .first()
                )
                if existing is not None:
                    org_nodes.append((org, existing))
        if market is not None:
            for _org, node in org_nodes:
                try:
                    graph_service.create_edge(
                        db,
                        from_node_id=market.id,
                        to_node_id=node.id,
                        relation_type="org_in_market",
                        source="search",
                        review_status="pending",
                    )
                    edges_created += 1
                except Duplicate:
                    pass

        # 种子：① 每个候选组织的联系检索；② 检索来源词本身
        seed_candidates: list[dict] = []
        for org in orgs:
            seed_candidates.append(
                {
                    "query": f'"{org["name"]}" contact',
                    "note": f"检索扩充：来源查询「{org['query']}」（{org['url']}）",
                }
            )
        for query in queries:
            seed_candidates.append({"query": query, "note": "检索扩充：来源关键词"})
        for candidate in seed_candidates:
            if seeds_created + seeds_skipped >= max_seeds:
                break
            try:
                seed_service.create_seed(
                    db,
                    query=candidate["query"],
                    lang=lang,
                    market_id=market.id if market is not None else None,
                    source="search",
                    review_status="pending",
                    confidence=0.5,
                    note=candidate["note"],
                )
                seeds_created += 1
            except Duplicate:
                seeds_skipped += 1

        log_op(
            db,
            "crawl",
            f"检索扩充：新增实体 {nodes_created}、关系 {edges_created}、种子 {seeds_created}（均待审核）",
            ref_type="job",
            ref_id=ctx.job_id,
            payload={"queries": queries},
        )

    ctx.progress(phase="done", nodes=nodes_created, seeds=seeds_created)
    return {
        "nodes_created": nodes_created,
        "nodes_skipped": nodes_skipped,
        "edges_created": edges_created,
        "seeds_created": seeds_created,
        "seeds_skipped": seeds_skipped,
    }
