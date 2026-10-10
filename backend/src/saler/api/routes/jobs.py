"""任务 API：列表 / 详情 / SSE 事件流 / 暂停恢复取消。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from saler.api.deps import get_session, paginate, pagination
from saler.api.errors import conflict, not_found
from saler.api.serializers import job_to_dict
from saler.db.models import Job
from saler.jobs.engine import TERMINAL_STATUSES

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_jobs(
    job_type: str | None = None,
    status: str | None = None,
    page_params: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_session),
) -> dict:
    page, page_size = page_params
    q = db.query(Job).order_by(Job.id.desc())
    if job_type:
        q = q.filter(Job.job_type == job_type)
    if status:
        q = q.filter(Job.status == status)
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
                event_name = "error" if job.status == "failed" else "done"
                yield {"event": event_name, "data": json.dumps(snapshot, ensure_ascii=False)}
                return
            while True:
                event = await queue.get()
                yield {"event": event.type, "data": json.dumps(event.data, ensure_ascii=False)}
                if event.type in ("done", "error"):
                    break
        finally:
            manager.bus.discard(job_id, queue)

    return EventSourceResponse(gen(), ping=30)


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
