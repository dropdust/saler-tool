"""图谱服务：节点/词表/关系 CRUD、合并、停用、审核、可视化数据（FR-007~011/017）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from saler.core.errors import Duplicate, NotFound, ValidationFailed
from saler.db.models import GraphEdge, GraphNode, NodeTerm, Seed
from saler.db.models.graph import NODE_TYPES, RELATION_TYPES, REVIEW_STATUSES

TERM_TYPES = ("name", "alias", "synonym", "term")


def _default_review(source: str) -> str:
    return "approved" if source in ("manual", "import") else "pending"


# ---------- 节点 ----------


def create_node(
    db: Session,
    *,
    node_type: str,
    name: str,
    region: str | None = None,
    attributes: dict | None = None,
    confidence: float | None = None,
    evidence_url: str | None = None,
    parent_id: int | None = None,
    source: str = "manual",
    review_status: str | None = None,
) -> GraphNode:
    name = (name or "").strip()
    if node_type not in NODE_TYPES:
        raise ValidationFailed(f"非法节点类型：{node_type}")
    if not name:
        raise ValidationFailed("节点名称不能为空")
    if db.query(GraphNode).filter_by(node_type=node_type, name=name).first():
        raise Duplicate(f"同类型下已存在同名节点：{name}")
    node = GraphNode(
        node_type=node_type,
        name=name,
        region=region,
        attributes=attributes or {},
        confidence=confidence,
        evidence_url=evidence_url,
        parent_id=parent_id,
        source=source,
        review_status=review_status or _default_review(source),
    )
    db.add(node)
    db.commit()
    return node


def get_node(db: Session, node_id: int) -> GraphNode:
    node = db.get(GraphNode, node_id)
    if node is None:
        raise NotFound("图谱节点")
    return node


def list_nodes(
    db: Session,
    *,
    node_type: str | None = None,
    review_status: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> Query:
    query = db.query(GraphNode)
    if node_type:
        query = query.filter(GraphNode.node_type == node_type)
    if review_status:
        query = query.filter(GraphNode.review_status == review_status)
    if status:
        query = query.filter(GraphNode.status == status)
    if q:
        query = query.filter(GraphNode.name.contains(q))
    return query.order_by(GraphNode.node_type.asc(), GraphNode.id.asc())


def update_node(db: Session, node_id: int, **fields: Any) -> GraphNode:
    node = get_node(db, node_id)
    allowed = {"name", "region", "attributes", "confidence", "evidence_url", "parent_id", "status", "review_status"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValidationFailed(f"不允许修改字段：{sorted(unknown)}")
    new_name = fields.get("name")
    if new_name and new_name != node.name:
        if db.query(GraphNode).filter(
            GraphNode.node_type == node.node_type,
            GraphNode.name == new_name.strip(),
            GraphNode.id != node.id,
        ).first():
            raise Duplicate(f"同类型下已存在同名节点：{new_name}")
        fields["name"] = new_name.strip()
    for key, value in fields.items():
        if value is not None:
            setattr(node, key, value)
    db.commit()
    return node


def disable_node(db: Session, node_id: int) -> GraphNode:
    node = get_node(db, node_id)
    node.status = "disabled"
    db.commit()
    return node


def merge_nodes(db: Session, *, target_id: int, source_ids: list[int]) -> dict:
    """把 source 节点并入 target：词表/关系/种子引用全部转移后删除 source。"""
    target = get_node(db, target_id)
    moved_terms = moved_edges = moved_seeds = 0
    for source_id in source_ids:
        if source_id == target_id:
            continue
        source = get_node(db, source_id)
        if source.node_type != target.node_type:
            raise ValidationFailed(f"只能合并同类型节点：{source.name} 与 {target.name}")
        # 词表
        for term in db.query(NodeTerm).filter_by(node_id=source.id).all():
            exists = (
                db.query(NodeTerm)
                .filter_by(node_id=target.id, lang=term.lang, term_type=term.term_type, term=term.term)
                .first()
            )
            if exists:
                db.delete(term)
            else:
                term.node_id = target.id
                moved_terms += 1
        # 关系（去重）
        for edge in db.query(GraphEdge).filter(
            (GraphEdge.from_node_id == source.id) | (GraphEdge.to_node_id == source.id)
        ).all():
            new_from = target.id if edge.from_node_id == source.id else edge.from_node_id
            new_to = target.id if edge.to_node_id == source.id else edge.to_node_id
            if new_from == new_to:
                db.delete(edge)
                continue
            dup = (
                db.query(GraphEdge)
                .filter_by(from_node_id=new_from, to_node_id=new_to, relation_type=edge.relation_type)
                .first()
            )
            if dup and dup.id != edge.id:
                db.delete(edge)
            else:
                edge.from_node_id, edge.to_node_id = new_from, new_to
                moved_edges += 1
        # 种子引用
        for field_name in ("product_line_id", "persona_id", "market_id", "source_node_id"):
            col = getattr(Seed, field_name)
            moved_seeds += (
                db.query(Seed).filter(col == source.id).update({col: target.id}, synchronize_session=False)
            )
        db.delete(source)
    db.commit()
    return {"terms_moved": moved_terms, "edges_moved": moved_edges, "seeds_moved": moved_seeds}


# ---------- 词表 ----------


def add_term(
    db: Session,
    *,
    node_id: int,
    lang: str,
    term: str,
    term_type: str = "name",
    source: str = "manual",
    review_status: str | None = None,
    skip_duplicates: bool = False,
) -> NodeTerm:
    get_node(db, node_id)
    term = (term or "").strip()
    if not term:
        raise ValidationFailed("词条不能为空")
    if term_type not in TERM_TYPES:
        raise ValidationFailed(f"非法词条类型：{term_type}")
    exists = (
        db.query(NodeTerm)
        .filter_by(node_id=node_id, lang=lang, term_type=term_type, term=term)
        .first()
    )
    if exists:
        if skip_duplicates:
            return exists
        raise Duplicate(f"词条已存在：{term}")
    row = NodeTerm(
        node_id=node_id,
        lang=lang,
        term=term,
        term_type=term_type,
        source=source,
        review_status=review_status or _default_review(source),
    )
    db.add(row)
    db.commit()
    return row


def get_term(db: Session, term_id: int) -> NodeTerm:
    row = db.get(NodeTerm, term_id)
    if row is None:
        raise NotFound("词条")
    return row


def update_term(db: Session, term_id: int, **fields: Any) -> NodeTerm:
    row = get_term(db, term_id)
    allowed = {"term", "term_type", "lang", "source", "review_status"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValidationFailed(f"不允许修改字段：{sorted(unknown)}")
    for key, value in fields.items():
        if value is not None:
            setattr(row, key, value)
    db.commit()
    return row


def delete_term(db: Session, term_id: int) -> None:
    db.delete(get_term(db, term_id))
    db.commit()


# ---------- 关系 ----------


def create_edge(
    db: Session,
    *,
    from_node_id: int,
    to_node_id: int,
    relation_type: str,
    source: str = "manual",
    review_status: str | None = None,
) -> GraphEdge:
    if relation_type not in RELATION_TYPES:
        raise ValidationFailed(f"非法关系类型：{relation_type}")
    get_node(db, from_node_id)
    get_node(db, to_node_id)
    exists = (
        db.query(GraphEdge)
        .filter_by(from_node_id=from_node_id, to_node_id=to_node_id, relation_type=relation_type)
        .first()
    )
    if exists:
        raise Duplicate("关系已存在")
    edge = GraphEdge(
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        relation_type=relation_type,
        source=source,
        review_status=review_status or _default_review(source),
    )
    db.add(edge)
    db.commit()
    return edge


def delete_edge(db: Session, edge_id: int) -> None:
    edge = db.get(GraphEdge, edge_id)
    if edge is None:
        raise NotFound("关系")
    db.delete(edge)
    db.commit()


# ---------- 审核 ----------


def review(db: Session, *, target: str, ids: list[int], decision: str) -> int:
    """采纳/拒绝（target: node / term / edge）。"""
    if decision not in ("approve", "reject"):
        raise ValidationFailed("decision 必须为 approve 或 reject")
    status = "approved" if decision == "approve" else "rejected"
    model = {"node": GraphNode, "term": NodeTerm, "edge": GraphEdge}.get(target)
    if model is None:
        raise ValidationFailed(f"非法审核对象：{target}")
    count = db.query(model).filter(model.id.in_(ids)).update(
        {model.review_status: status}, synchronize_session=False
    )
    db.commit()
    return count


def is_review_status(value: str) -> bool:
    return value in REVIEW_STATUSES


# ---------- 可视化数据（FR-017） ----------


def overview(db: Session, *, batch: str | None = None, market_id: int | None = None) -> dict:
    """结构 + 实体两视图共用数据：节点产量着色 + 显式/共现关系。"""
    nodes = db.query(GraphNode).filter(GraphNode.status == "active").all()
    included = {node.id for node in nodes}

    seed_query = db.query(Seed)
    if batch:
        seed_query = seed_query.filter(Seed.batch == batch)
    if market_id:
        seed_query = seed_query.filter(Seed.market_id == market_id)
    seeds = seed_query.all()

    agg: dict[int, dict[str, int]] = {}
    derived: dict[tuple[int, int, str], int] = {}
    for seed in seeds:
        dims = [seed.product_line_id, seed.persona_id, seed.market_id, seed.source_node_id]
        for node_id in dims:
            if node_id and node_id in included:
                row = agg.setdefault(node_id, {"seeds": 0, "done": 0, "candidates": 0, "contacts": 0})
                row["seeds"] += 1
                if seed.status == "done":
                    row["done"] += 1
                row["candidates"] += seed.n_candidates
                row["contacts"] += seed.n_contacts
        if seed.product_line_id and seed.persona_id:
            key = (seed.product_line_id, seed.persona_id, "seed_cooccur")
            derived[key] = derived.get(key, 0) + 1
        if seed.persona_id and seed.market_id:
            key = (seed.persona_id, seed.market_id, "seed_cooccur")
            derived[key] = derived.get(key, 0) + 1

    edges_payload = [
        {"source": src, "target": dst, "relation_type": rel, "weight": weight}
        for (src, dst, rel), weight in derived.items()
        if src in included and dst in included
    ]
    for edge in db.query(GraphEdge).all():
        if edge.from_node_id in included and edge.to_node_id in included:
            edges_payload.append(
                {
                    "source": edge.from_node_id,
                    "target": edge.to_node_id,
                    "relation_type": edge.relation_type,
                    "weight": 1,
                }
            )

    zero = {"seeds": 0, "done": 0, "candidates": 0, "contacts": 0}
    return {
        "nodes": [
            {
                "id": node.id,
                "node_type": node.node_type,
                "name": node.name,
                "region": node.region,
                "review_status": node.review_status,
                "counts": agg.get(node.id, zero),
            }
            for node in nodes
        ],
        "edges": edges_payload,
    }


def node_seed_counts(db: Session, node_ids: list[int]) -> dict[int, int]:
    """辅助：节点被多少条种子引用。"""
    result: dict[int, int] = {}
    for node_id in node_ids:
        result[node_id] = (
            db.query(func.count(Seed.id))
            .filter(
                (Seed.product_line_id == node_id)
                | (Seed.persona_id == node_id)
                | (Seed.market_id == node_id)
                | (Seed.source_node_id == node_id)
            )
            .scalar()
            or 0
        )
    return result
