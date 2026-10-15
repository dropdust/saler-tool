"""任务 API：列表 / 详情 / SSE 事件流 / 暂停恢复取消 / 重跑。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from saler.api.deps import get_session, paginate, pagination
from saler.api.errors import conflict, not_found, unprocessable
from saler.api.serializers import job_to_dict
from saler.db.models import Job
from saler.jobs.catalog import get_starter
from saler.jobs.engine import JOB_STATUSES, TERMINAL_STATUSES

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_jobs(
    job_type: str | None = None,
    status: str | None = None,
    page_params: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_session),
) -> dict:
    """任务列表。`status` 支持逗号多值（`running,paused,queued`）；未知状态值 422（契约 §1）。"""
    page, page_size = page_params
    q = db.query(Job).order_by(Job.id.desc())
    if job_type:
        q = q.filter(Job.job_type == job_type)
    if status:
        statuses = [token.strip() for token in status.split(",")]
        statuses = [token for token in statuses if token]
        unknown = [token for token in statuses if token not in JOB_STATUSES]
        if unknown:
            raise unprocessable(f"未知任务状态：{', '.join(unknown)}（可选：{', '.join(JOB_STATUSES)}）")
        if statuses:
            q = q.filter(Job.status.in_(statuses))
    result = paginate(q, page, page_size)
    result["items"] = [job_to_dict(j) for j in result["items"]]
    return result


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_session)) -> dict:
    job = db.get(Job, job_id)
    if job is None:
        raise not_found("任务")
    return job_to_dict(job)


@router.get("/{job_id}/events")
async def job_events(job_id: int, request: Request, db: Session = Depends(get_session)):
    """SSE 事件流：先发快照，再转发实时事件；终态任务直接返回快照。"""
    job = db.get(Job, job_id)
    if job is None:
        raise not_found("任务")
    manager = request.app.state.job_manager
    snapshot = job_to_dict(job)
    terminal = job.status in TERMINAL_STATUSES
    queue = manager.bus.subscribe(job_id)

    async def gen():
        try:
            yield {"event": "progress", "data": json.dumps({"snapshot": snapshot}, ensure_ascii=False)}
            if terminal:
                yield _terminal_event(job.status, snapshot)
                return
            while True:
                event = await queue.get()
                yield {"event": event.type, "data": json.dumps(event.data, ensure_ascii=False)}
                if event.type in ("done", "error"):
                    break
        finally:
            manager.bus.discard(job_id, queue)

    return EventSourceResponse(gen(), ping=30)


_TERMINAL_ERROR_CODES = {
    "failed": "job_failed",
    "cancelled": "cancelled",
    "interrupted": "interrupted",
}
_TERMINAL_ERROR_MESSAGES = {
    "failed": "任务失败",
    "cancelled": "任务已取消",
    "interrupted": "应用退出导致任务中断",
}


def _terminal_event(status: str, snapshot: dict) -> dict:
    """终态快照分派（契约 §2 修正）：completed → done（载荷=快照，含 result）；
    其余终态 → error(code)——修正前除 failed 外一律发 done，已取消/已中断被订阅方误示为"完成"。
    """
    if status == "completed":
        return {"event": "done", "data": json.dumps(snapshot, ensure_ascii=False)}
    code = _TERMINAL_ERROR_CODES.get(status, "job_failed")
    message = _TERMINAL_ERROR_MESSAGES.get(status, "任务已结束")
    return {"event": "error", "data": json.dumps({"code": code, "message": message}, ensure_ascii=False)}


def _control(job_id: int, request: Request, action: str) -> dict:
    manager = request.app.state.job_manager
    ok = getattr(manager, action)(job_id)
    if not ok:
        status = manager.get_status(job_id)
        if status is None:
            raise not_found("任务")
        raise conflict(f"当前状态（{status}）不允许 {action}")
    return {"ok": True, "status": manager.get_status(job_id)}


@router.post("/{job_id}/pause")
def pause_job(job_id: int, request: Request) -> dict:
    return _control(job_id, request, "pause")


@router.post("/{job_id}/resume")
def resume_job(job_id: int, request: Request) -> dict:
    return _control(job_id, request, "resume")


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, request: Request) -> dict:
    return _control(job_id, request, "cancel")


@router.post("/{job_id}/rerun", status_code=202)
async def rerun_job(job_id: int, request: Request, db: Session = Depends(get_session)) -> dict:
    """重新运行一个**已失败/已取消/已中断**的可重跑任务（契约 §3）。

    - 重跑可能触发检索/写入，属用户主动操作；服务端绝不自动重跑（启动对账只改状态）；
    - starter 负责重建执行上下文（crawl 从 CrawlJob.scope/config 复原并建新明细，
      回灌/导入以原 params 重建请求）；新任务不复制 progress/result/error。
    """
    job = db.get(Job, job_id)
    if job is None:
        raise not_found("任务")
    starter = get_starter(job.job_type)
    if starter is None:
        raise conflict(
            "该任务类型不支持重新运行；请前往相关页面检查后重新发起",
            code="not_rerunnable",
        )
    if job.status not in TERMINAL_STATUSES:
        raise conflict(f"任务尚未结束（{job.status}），无法重新运行", code="not_terminal")
    if job.status == "completed":
        raise conflict("任务已完成，无需重新运行", code="already_completed")
    return starter(request, db, job)
