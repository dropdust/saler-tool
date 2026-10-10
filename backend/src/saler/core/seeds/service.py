"""种子服务：CRUD / 批量 / 状态机 / 审核 / 统计（FR-010/015）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Query, Session

from saler.core.errors import Duplicate, NotFound, ValidationFailed
from saler.db.models import GraphNode, Seed
from saler.db.models.seeds import SEED_STATUSES

SORTS = {
    "priority": (Seed.priority.asc(), Seed.id.asc()),
    "yield": (Seed.n_contacts.desc(), Seed.n_candidates.desc(), Seed.id.asc()),
    "created": (Seed.id.desc(),),
}


def _default_review(source: str) -> str:
    return "approved" if source in ("manual", "import") else "pending"


def create_seed(
    db: Session,
    *,
    query: str,
    lang: str = "en",
    product_line_id: int | None = None,
    persona_id: int | None = None,
    market_id: int | None = None,
    priority: int = 2,
    batch: str | None = None,
    template: str | None = None,
    source_node_id: int | None = None,
    source: str = "manual",
    confidence: float | None = None,
    review_status: str | None = None,
    note: str | None = None,
) -> Seed:
    query = (query or "").strip()
    if not query:
        raise ValidationFailed("搜索词不能为空")
    if priority not in (1, 2, 3):
        raise ValidationFailed("优先级必须为 1/2/3")
    if db.query(Seed).filter_by(query=query).first():
        raise Duplicate(f"种子已存在（搜索词唯一）：{query}")
    seed = Seed(
        query=query,
        lang=lang,
        product_line_id=product_line_id,
        persona_id=persona_id,
        market_id=market_id,
        priority=priority,
        batch=batch,
        template=template,
        source_node_id=source_node_id,
        source=source,
        confidence=confidence,
        review_status=review_status or _default_review(source),
        note=note,
    )
    db.add(seed)
    db.commit()
    return seed


def bulk_create(db: Session, items: list[dict]) -> dict:
    """批量导入：逐条校验，重复与错误不阻塞其余（报告式返回）。"""
    created, duplicates, errors = 0, [], []
    for index, item in enumerate(items):
        try:
            create_seed(db, **item)
            created += 1
        except Duplicate:
            duplicates.append(item.get("query"))
        except (ValidationFailed, TypeError) as exc:
            errors.append({"index": index, "query": item.get("query"), "error": str(exc)})
    return {"created": created, "duplicates": duplicates, "errors": errors}


def get_seed(db: Session, seed_id: int) -> Seed:
    seed = db.get(Seed, seed_id)
    if seed is None:
        raise NotFound("种子")
    return seed


def list_seeds(
    db: Session,
    *,
    status: str | None = None,
    source: str | None = None,
    review_status: str | None = None,
    batch: str | None = None,
    lang: str | None = None,
    market_id: int | None = None,
    product_line_id: int | None = None,
    persona_id: int | None = None,
    q: str | None = None,
    sort: str = "priority",
) -> Query:
    query = db.query(Seed)
    if status:
        query = query.filter(Seed.status == status)
    if source:
        query = query.filter(Seed.source == source)
    if review_status:
        query = query.filter(Seed.review_status == review_status)
    if batch:
        query = query.filter(Seed.batch == batch)
    if lang:
        query = query.filter(Seed.lang == lang)
    if market_id:
        query = query.filter(Seed.market_id == market_id)
    if product_line_id:
        query = query.filter(Seed.product_line_id == product_line_id)
    if persona_id:
        query = query.filter(Seed.persona_id == persona_id)
    if q:
        query = query.filter(Seed.query.contains(q))
    order = SORTS.get(sort) or SORTS["priority"]
    return query.order_by(*order)


def update_seed(db: Session, seed_id: int, **fields: Any) -> Seed:
    seed = get_seed(db, seed_id)
    allowed = {
        "lang", "priority", "batch", "template", "note", "status",
        "product_line_id", "persona_id", "market_id", "source_node_id", "confidence",
    }
    unknown = set(fields) - allowed
    if unknown:
        raise ValidationFailed(f"不允许修改字段：{sorted(unknown)}")
    if fields.get("status") and fields["status"] not in SEED_STATUSES:
        raise ValidationFailed(f"非法状态：{fields['status']}")
    if fields.get("priority") is not None and fields["priority"] not in (1, 2, 3):
        raise ValidationFailed("优先级必须为 1/2/3")
    for key, value in fields.items():
        if value is not None:
            setattr(seed, key, value)
    db.commit()
    return seed


def disable_seed(db: Session, seed_id: int) -> Seed:
    """删除语义 = 置为失效（保留产量历史）。"""
    seed = get_seed(db, seed_id)
    seed.status = "invalid"
    db.commit()
    return seed


def review(db: Session, *, ids: list[int], decision: str) -> int:
    if decision not in ("approve", "reject"):
        raise ValidationFailed("decision 必须为 approve 或 reject")
    status = "approved" if decision == "approve" else "rejected"
    count = (
        db.query(Seed)
        .filter(Seed.id.in_(ids))
        .update({Seed.review_status: status}, synchronize_session=False)
    )
    db.commit()
    return count


def stats(db: Session, *, group_by: str = "batch") -> list[dict]:
    """按 批次 / 产品线 / 客户角色 / 市场 汇总产量（COUNT 口径见 data-model.md）。"""

    def _row(key: Any, name: str | None, seeds: int, done: Any, candidates: Any, contacts: Any) -> dict:
        return {
            "key": key,
            "name": name if name is not None else (key if key is not None else "(未分组)"),
            "seeds": int(seeds or 0),
            "done": int(done or 0),
            "candidates": int(candidates or 0),
            "contacts": int(contacts or 0),
        }

    done_sum = func.sum(case((Seed.status == "done", 1), else_=0))
    columns = [func.count(Seed.id), done_sum, func.sum(Seed.n_candidates), func.sum(Seed.n_contacts)]

    if group_by == "batch":
        rows = db.query(Seed.batch, *columns).group_by(Seed.batch).all()
        return [_row(r[0], r[0], *r[1:]) for r in rows]

    dim = {
        "product_line": (Seed.product_line_id, "产品线"),
        "persona": (Seed.persona_id, "客户角色"),
        "market": (Seed.market_id, "市场"),
    }.get(group_by)
    if dim is None:
        raise ValidationFailed(f"非法分组：{group_by}")
    col = dim[0]
    rows = (
        db.query(col, GraphNode.name, *columns)
        .outerjoin(GraphNode, col == GraphNode.id)
        .group_by(col)
        .all()
    )
    return [_row(r[0], r[1] or "(未归类)", *r[2:]) for r in rows]
