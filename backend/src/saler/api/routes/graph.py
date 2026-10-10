"""图谱 API：节点 / 词表 / 关系 / 可视化数据 / 审核（FR-007~011/017）。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from saler.api.deps import get_session, paginate, pagination
from saler.api.serializers import edge_to_dict, node_to_dict, term_to_dict
from saler.core.graph import service as graph_service

router = APIRouter(prefix="/graph", tags=["graph"])


class NodeCreate(BaseModel):
    node_type: str
    name: str
    region: str | None = None
    attributes: dict = Field(default_factory=dict)
    parent_id: int | None = None
    confidence: float | None = None
    evidence_url: str | None = None
    source: str = "manual"


class NodeUpdate(BaseModel):
    name: str | None = None
    region: str | None = None
    attributes: dict | None = None
    parent_id: int | None = None
    confidence: float | None = None
    evidence_url: str | None = None
    status: str | None = None
    review_status: str | None = None


class MergeRequest(BaseModel):
    target_id: int
    source_ids: list[int]


class TermCreate(BaseModel):
    lang: str
    term: str
    term_type: str = "name"
    source: str = "manual"


class TermUpdate(BaseModel):
    term: str | None = None
    term_type: str | None = None
    lang: str | None = None
    review_status: str | None = None


class EdgeCreate(BaseModel):
    from_node_id: int
    to_node_id: int
    relation_type: str
    source: str = "manual"


class ReviewRequest(BaseModel):
    target: Literal["node", "term", "edge"]
    ids: list[int]
    decision: Literal["approve", "reject"]


@router.get("/nodes")
def list_nodes(
    node_type: str | None = None,
    review_status: str | None = None,
    status: str | None = None,
    q: str | None = None,
    page_params: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_session),
) -> dict:
    page, page_size = page_params
    result = paginate(
        graph_service.list_nodes(
            db, node_type=node_type, review_status=review_status, status=status, q=q
        ),
        page,
        page_size,
    )
    result["items"] = [node_to_dict(node) for node in result["items"]]
    return result


@router.post("/nodes", status_code=201)
def create_node(payload: NodeCreate, db: Session = Depends(get_session)) -> dict:
    return node_to_dict(graph_service.create_node(db, **payload.model_dump()))


@router.get("/nodes/{node_id}")
def get_node(node_id: int, db: Session = Depends(get_session)) -> dict:
    return node_to_dict(graph_service.get_node(db, node_id))


@router.put("/nodes/{node_id}")
def update_node(node_id: int, payload: NodeUpdate, db: Session = Depends(get_session)) -> dict:
    fields = payload.model_dump(exclude_none=True)
    return node_to_dict(graph_service.update_node(db, node_id, **fields))


@router.delete("/nodes/{node_id}")
def disable_node(node_id: int, db: Session = Depends(get_session)) -> dict:
    graph_service.disable_node(db, node_id)
    return {"ok": True}


@router.post("/nodes/merge")
def merge_nodes(payload: MergeRequest, db: Session = Depends(get_session)) -> dict:
    return graph_service.merge_nodes(
        db, target_id=payload.target_id, source_ids=payload.source_ids
    )


@router.get("/nodes/{node_id}/terms")
def list_terms(node_id: int, db: Session = Depends(get_session)) -> list[dict]:
    rows = (
        db.query(graph_service.NodeTerm)
        .filter_by(node_id=node_id)
        .order_by(graph_service.NodeTerm.id.asc())
        .all()
    )
    return [term_to_dict(row) for row in rows]


@router.post("/nodes/{node_id}/terms", status_code=201)
def add_term(node_id: int, payload: TermCreate, db: Session = Depends(get_session)) -> dict:
    return term_to_dict(graph_service.add_term(db, node_id=node_id, **payload.model_dump()))


@router.put("/terms/{term_id}")
def update_term(term_id: int, payload: TermUpdate, db: Session = Depends(get_session)) -> dict:
    return term_to_dict(
        graph_service.update_term(db, term_id, **payload.model_dump(exclude_none=True))
    )


@router.delete("/terms/{term_id}")
def delete_term(term_id: int, db: Session = Depends(get_session)) -> dict:
    graph_service.delete_term(db, term_id)
    return {"ok": True}


@router.get("/edges")
def list_edges(
    from_node_id: int | None = None,
    to_node_id: int | None = None,
    db: Session = Depends(get_session),
) -> list[dict]:
    query = db.query(graph_service.GraphEdge)
    if from_node_id:
        query = query.filter(graph_service.GraphEdge.from_node_id == from_node_id)
    if to_node_id:
        query = query.filter(graph_service.GraphEdge.to_node_id == to_node_id)
    return [edge_to_dict(row) for row in query.order_by(graph_service.GraphEdge.id.asc()).all()]


@router.post("/edges", status_code=201)
def create_edge(payload: EdgeCreate, db: Session = Depends(get_session)) -> dict:
    return edge_to_dict(graph_service.create_edge(db, **payload.model_dump()))


@router.delete("/edges/{edge_id}")
def delete_edge(edge_id: int, db: Session = Depends(get_session)) -> dict:
    graph_service.delete_edge(db, edge_id)
    return {"ok": True}


@router.get("/overview")
def overview(
    batch: str | None = None,
    market_id: int | None = None,
    db: Session = Depends(get_session),
) -> dict:
    return graph_service.overview(db, batch=batch, market_id=market_id)


@router.post("/review")
def review(payload: ReviewRequest, db: Session = Depends(get_session)) -> dict:
    count = graph_service.review(
        db, target=payload.target, ids=payload.ids, decision=payload.decision
    )
    return {"updated": count}
