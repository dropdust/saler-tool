"""挖掘任务与候选域名 API（FR-019~026）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from saler.api.deps import get_session, paginate, pagination
from saler.api.errors import ApiError, not_found
from saler.api.serializers import crawl_job_to_dict
from saler.core.leads.crawl_engine import CrawlConfig, CrawlEngine
from saler.core.leads.fetcher import Fetcher
from saler.core.leads.search_setup import resolve_search_chain
from saler.db.models import CrawlJob

router = APIRouter(tags=["crawl"])


class CrawlJobRequest(BaseModel):
    seed_ids: list[int] | None = None
    config: dict = Field(default_factory=dict)


@router.post("/crawl/jobs", status_code=202)
async def create_crawl_job(
    payload: CrawlJobRequest, request: Request, db: Session = Depends(get_session)
) -> dict:
    config = CrawlConfig.from_dict(payload.config)
    chain = resolve_search_chain(db, config, session_factory=request.app.state.session_factory)
    if chain is None:
        raise ApiError(
            409,
            "search_not_configured",
            "尚未配置检索渠道：请在「设置 → 检索渠道」中添加并启用（Brave / Serper / Tavily / DDG）",
        )
    manager = request.app.state.job_manager
    record = CrawlJob(
        name="客户线索挖掘",
        scope={"seed_ids": payload.seed_ids},
        config=config.to_dict(),
        status="queued",
    )
    db.add(record)
    db.commit()
    job_id = manager.create("crawl", name="客户线索挖掘", ref_type="crawl_job", ref_id=record.id)

    async def run_job(ctx):
        fetcher = Fetcher(
            proxy=config.proxy,
            timeout_s=config.timeout_s,
            per_host_delay_s=config.per_host_delay_s,
            respect_robots=config.respect_robots,
        )
        try:
            engine = CrawlEngine(
                request.app.state.session_factory, chain, fetcher, config=config
            )
            result = await engine.run(ctx, seed_ids=payload.seed_ids, job_id=job_id)
        finally:
            await fetcher.aclose()
        with request.app.state.session_factory() as session:
            row = session.get(CrawlJob, record.id)
            if row is not None:
                row.status = "completed"
                row.stats = result
                session.commit()
        return result

    manager.start(job_id, run_job)
    return {"job_id": job_id, "crawl_job_id": record.id}


@router.get("/crawl/jobs")
def list_crawl_jobs(
    page_params: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_session),
) -> dict:
    page, page_size = page_params
    result = paginate(db.query(CrawlJob).order_by(CrawlJob.id.desc()), page, page_size)
    result["items"] = [crawl_job_to_dict(row) for row in result["items"]]
    return result


@router.get("/crawl/jobs/{crawl_job_id}")
def get_crawl_job(crawl_job_id: int, db: Session = Depends(get_session)) -> dict:
    row = db.get(CrawlJob, crawl_job_id)
    if row is None:
        raise not_found("挖掘任务")
    return crawl_job_to_dict(row)
