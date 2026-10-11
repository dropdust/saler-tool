"""种子 API：CRUD / 批量 / 审核 / 统计 / 导出 / 回灌 / 校验（FR-010~016/018）。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from saler.api.deps import get_session, paginate, pagination
from saler.api.errors import unprocessable
from saler.api.serializers import seed_to_dict
from saler.core.leads.search_setup import resolve_search_chain
from saler.core.seeds import service as seed_service
from saler.core.seeds.discover import run_discover
from saler.core.seeds.verifiers import run_validation
from saler.services import export_seeds
from saler.services.ingest_harvest import run_ingest

router = APIRouter(prefix="/seeds", tags=["seeds"])


class SeedCreate(BaseModel):
    query: str
    lang: str = "en"
    product_line_id: int | None = None
    persona_id: int | None = None
    market_id: int | None = None
    priority: int = 2
    batch: str | None = None
    template: str | None = None
    source_node_id: int | None = None
    source: str = "manual"
    confidence: float | None = None
    note: str | None = None


class SeedUpdate(BaseModel):
    lang: str | None = None
    priority: int | None = None
    batch: str | None = None
    template: str | None = None
    note: str | None = None
    status: str | None = None
    product_line_id: int | None = None
    persona_id: int | None = None
    market_id: int | None = None
    source_node_id: int | None = None
    confidence: float | None = None


class BulkSeeds(BaseModel):
    items: list[SeedCreate]


class ReviewDecision(BaseModel):
    ids: list[int]
    decision: Literal["approve", "reject"]


class ExportRequest(BaseModel):
    format: Literal["txt", "csv"] = "txt"
    batch: str | None = None
    status: str | None = None
    review_status: str | None = "approved"
    market_id: int | None = None
    lang: str | None = None
    source: str | None = None
    max_priority: int | None = None
    limit: int | None = None


class IngestRequest(BaseModel):
    content: str | None = None
    path: str | None = None


class ValidateRequest(BaseModel):
    seed_ids: list[int] = Field(default_factory=list)
    node_ids: list[int] = Field(default_factory=list)


@router.get("")
def list_seeds(
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
    page_params: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_session),
) -> dict:
    page, page_size = page_params
    result = paginate(
        seed_service.list_seeds(
            db,
            status=status,
            source=source,
            review_status=review_status,
            batch=batch,
            lang=lang,
            market_id=market_id,
            product_line_id=product_line_id,
            persona_id=persona_id,
            q=q,
            sort=sort,
        ),
        page,
        page_size,
    )
    result["items"] = [seed_to_dict(seed) for seed in result["items"]]
    return result


@router.get("/review-queue")
def review_queue(
    page_params: tuple[int, int] = Depends(pagination), db: Session = Depends(get_session)
) -> dict:
    page, page_size = page_params
    result = paginate(seed_service.list_seeds(db, review_status="pending"), page, page_size)
    result["items"] = [seed_to_dict(seed) for seed in result["items"]]
    return result


@router.get("/stats")
def stats(group_by: str = "batch", db: Session = Depends(get_session)) -> list[dict]:
    return seed_service.stats(db, group_by=group_by)


@router.get("/langs")
def seed_langs(db: Session = Depends(get_session)) -> list[str]:
    """语言筛选选项数据源（003）：库内去重精确取值（升序，含非标准代码）。声明须先于 /{seed_id}。"""
    return seed_service.distinct_langs(db)


@router.post("", status_code=201)
def create_seed(payload: SeedCreate, db: Session = Depends(get_session)) -> dict:
    return seed_to_dict(seed_service.create_seed(db, **payload.model_dump()))


@router.post("/bulk")
def bulk_create(payload: BulkSeeds, db: Session = Depends(get_session)) -> dict:
    return seed_service.bulk_create(db, [item.model_dump() for item in payload.items])


@router.post("/review")
def review(payload: ReviewDecision, db: Session = Depends(get_session)) -> dict:
    count = seed_service.review(db, ids=payload.ids, decision=payload.decision)
    return {"updated": count}


@router.post("/export")
def export(payload: ExportRequest, request: Request, db: Session = Depends(get_session)) -> dict:
    data_dir = request.app.state.data_dir or Path.cwd()
    out_dir = Path(data_dir) / "exports"
    return export_seeds.export_seeds(
        db,
        fmt=payload.format,
        out_dir=out_dir,
        batch=payload.batch,
        status=payload.status,
        review_status=payload.review_status,
        market_id=payload.market_id,
        lang=payload.lang,
        source=payload.source,
        max_priority=payload.max_priority,
        limit=payload.limit,
    )


@router.post("/ingest", status_code=202)
async def ingest(payload: IngestRequest, request: Request) -> dict:
    manager = request.app.state.job_manager
    job_id = manager.create("ingest_harvest", name="回灌收割结果", params=payload.model_dump())
    manager.start(
        job_id,
        lambda ctx: run_ingest(
            ctx,
            request.app.state.session_factory,
            payload=payload.model_dump(),
        ),
    )
    return {"job_id": job_id}


@router.post("/validate", status_code=202)
async def validate(payload: ValidateRequest, request: Request) -> dict:
    manager = request.app.state.job_manager
    job_id = manager.create("seed_validate", name="外部来源校验", params=payload.model_dump())
    manager.start(
        job_id,
        lambda ctx: run_validation(
            ctx,
            request.app.state.session_factory,
            payload=payload.model_dump(),
            delay_s=1.0,
        ),
    )
    return {"job_id": job_id}


class DiscoverRequest(BaseModel):
    queries: list[str] = Field(min_length=1)
    from_node_ids: list[int] = Field(default_factory=list)
    per_query: int = 10
    lang: str = "en"
    max_orgs: int = 20
    max_seeds: int = 30


@router.post("/discover", status_code=202)
async def discover(payload: DiscoverRequest, request: Request, db: Session = Depends(get_session)) -> dict:
    """检索扩充图谱（FR-013）：关键词 → 检索渠道 → 候选实体/种子（全部进入待审核）。"""
    chain = resolve_search_chain(db)
    if chain is None:
        raise unprocessable("尚未配置可用的检索渠道：请先在「设置 → 检索渠道」添加并启用")
    manager = request.app.state.job_manager
    job_id = manager.create("seed_discover", name="检索扩充图谱", params=payload.model_dump())
    manager.start(
        job_id,
        lambda ctx: run_discover(
            ctx, request.app.state.session_factory, chain, payload=payload.model_dump()
        ),
    )
    return {"job_id": job_id}


@router.get("/{seed_id}")
def get_seed(seed_id: int, db: Session = Depends(get_session)) -> dict:
    return seed_to_dict(seed_service.get_seed(db, seed_id))


@router.put("/{seed_id}")
def update_seed(seed_id: int, payload: SeedUpdate, db: Session = Depends(get_session)) -> dict:
    return seed_to_dict(
        seed_service.update_seed(db, seed_id, **payload.model_dump(exclude_none=True))
    )


@router.delete("/{seed_id}")
def disable_seed(seed_id: int, db: Session = Depends(get_session)) -> dict:
    seed_service.disable_seed(db, seed_id)
    return {"ok": True}
