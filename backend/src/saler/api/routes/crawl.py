"""挖掘任务与候选域名 API（FR-019~026）。

`crawl_job`（领域明细）与 `job`（任务台账）**全周期一致**（FR-019）：运行工厂在入口把明细
置 `running`（写 `started_at`），成功/失败/取消分别收口为 `completed`/`failed`/`cancelled`
（写 `finished_at`）；进程退出遗留的非终态由启动对账收口为 `interrupted`（jobs/reconcile.py）。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from saler.api.deps import get_session, paginate, pagination
from saler.api.errors import ApiError, not_found
from saler.api.serializers import crawl_job_to_dict
from saler.core.leads.crawl_engine import CrawlConfig, CrawlEngine
from saler.core.leads.fetcher import Fetcher
from saler.core.leads.search_setup import resolve_search_chain
from saler.db.models import CrawlJob
from saler.jobs.catalog import register_starter
from saler.jobs.engine import JobCancelled

router = APIRouter(tags=["crawl"])


def mark_crawl_detail(
    session_factory: sessionmaker[Session],
    crawl_job_id: int,
    status: str,
    *,
    stats: dict | None = None,
) -> None:
    """把挖掘领域明细推进到 `status`：running 写 started_at，终态写 finished_at（与状态同刻）。

    台账与明细同源推进是 FR-019 的硬要求——明细落后会让"挖掘任务页"显示与实际不符的状态。
    """
    with session_factory() as session:
        row = session.get(CrawlJob, crawl_job_id)
        if row is None:
            return
        row.status = status
        now = datetime.now(UTC)
        if status == "running":
            row.started_at = now
        else:
            row.finished_at = now
        if stats is not None:
            row.stats = stats
        session.commit()


class CrawlJobRequest(BaseModel):
    seed_ids: list[int] | None = None
    config: dict = Field(default_factory=dict)


def start_crawl_job(
    request: Request, db: Session, *, seed_ids: list[int] | None, config_raw: dict
) -> dict:
    """装配并启动一次挖掘（台账 + 明细）——原发端点与重跑 starter 共用同一路径。"""
    config = CrawlConfig.from_dict(config_raw)
    chain = resolve_search_chain(db, config, session_factory=request.app.state.session_factory)
    if chain is None:
        raise ApiError(
            409,
            "search_not_configured",
            "尚未配置检索渠道：请在「设置 → 检索渠道」中添加并启用（官方 API 或免密钥网页渠道均可）",
        )
    manager = request.app.state.job_manager
    record = CrawlJob(
        name="客户线索挖掘",
        scope={"seed_ids": seed_ids},
        config=config.to_dict(),
        status="queued",
    )
    db.add(record)
    db.commit()
    job_id = manager.create("crawl", name="客户线索挖掘", ref_type="crawl_job", ref_id=record.id)

    session_factory = request.app.state.session_factory

    async def run_job(ctx):
        mark_crawl_detail(session_factory, record.id, "running")  # 明细随台账进入运行态
        fetcher = Fetcher(
            proxy=config.proxy,
            timeout_s=config.timeout_s,
            per_host_delay_s=config.per_host_delay_s,
            respect_robots=config.respect_robots,
        )
        try:
            engine = CrawlEngine(session_factory, chain, fetcher, config=config)
            result = await engine.run(ctx, seed_ids=seed_ids, job_id=job_id)
        except (asyncio.CancelledError, JobCancelled):
            mark_crawl_detail(session_factory, record.id, "cancelled")  # 用户取消
            raise
        except Exception:
            mark_crawl_detail(session_factory, record.id, "failed")  # 运行出错
            raise
        else:
            mark_crawl_detail(session_factory, record.id, "completed", stats=result)
        finally:
            await fetcher.aclose()
        return result

    manager.start(job_id, run_job)
    return {"job_id": job_id, "crawl_job_id": record.id}


def _rerun_crawl(request: Request, db: Session, job) -> dict:
    """重跑 starter（契约 §3）：从原明细的 scope/config 复原，建新明细行并启动新任务。"""
    detail = db.get(CrawlJob, job.ref_id) if job.ref_id is not None else None
    if detail is None:
        raise ApiError(
            409,
            "not_rerunnable",
            "原挖掘明细已不存在，无法重新运行；请前往挖掘任务页重新发起",
        )
    return start_crawl_job(
        request,
        db,
        seed_ids=(detail.scope or {}).get("seed_ids"),
        config_raw=detail.config or {},
    )


register_starter("crawl", _rerun_crawl)


@router.post("/crawl/jobs", status_code=202)
async def create_crawl_job(
    payload: CrawlJobRequest, request: Request, db: Session = Depends(get_session)
) -> dict:
    return start_crawl_job(request, db, seed_ids=payload.seed_ids, config_raw=payload.config)


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
