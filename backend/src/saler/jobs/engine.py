"""任务引擎：创建/执行/暂停/恢复/取消，状态持久化于 `job` 表。

- 任务协程运行在 API 事件循环上；`JobContext.checkpoint()` 为协作点
  （处理暂停与取消，任务循环必须周期性调用）。
- SSE 事件经 `EventBus` 推送；终态（completed/failed/cancelled）后不再接收新事件。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session, sessionmaker

from saler.db.models import Job
from saler.jobs.events import EventBus, JobEvent

TERMINAL_STATUSES = ("completed", "failed", "cancelled")


class JobCancelled(Exception):
    """协作式取消信号。"""


class JobContext:
    def __init__(self, manager: JobManager, job_id: int) -> None:
        self.manager = manager
        self.job_id = job_id

    def log(self, message: str, *, level: str = "info", **extra: Any) -> None:
        self.manager.bus.publish(
            self.job_id, JobEvent("log", {"level": level, "message": message, **extra})
        )

    def progress(self, **data: Any) -> None:
        self.manager.update_progress(self.job_id, data)
        self.manager.bus.publish(self.job_id, JobEvent("progress", data))

    async def checkpoint(self) -> None:
        """协作点：暂停时挂起等待，取消时抛出 JobCancelled。"""
        while True:
            with self.manager.session_factory() as db:
                job = db.get(Job, self.job_id)
                status = job.status if job is not None else "cancelled"
            if status == "cancelled":
                raise JobCancelled()
            if status != "paused":
                return
            await asyncio.sleep(0.25)


class JobManager:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory
        self.bus = EventBus()
        self._tasks: dict[int, asyncio.Task] = {}

    # ---------- 台账 ----------
    def create(
        self,
        job_type: str,
        *,
        name: str | None = None,
        params: dict | None = None,
        ref_type: str | None = None,
        ref_id: int | None = None,
    ) -> int:
        with self.session_factory() as db:
            job = Job(
                job_type=job_type,
                name=name,
                params=params or {},
                ref_type=ref_type,
                ref_id=ref_id,
            )
            db.add(job)
            db.commit()
            return job.id

    def _set_status(self, job_id: int, status: str, **fields: Any) -> None:
        with self.session_factory() as db:
            job = db.get(Job, job_id)
            if job is None:
                return
            job.status = status
            if status == "running" and job.started_at is None:
                job.started_at = datetime.now(UTC)
            if status in TERMINAL_STATUSES:
                job.finished_at = datetime.now(UTC)
            for key, value in fields.items():
                setattr(job, key, value)
            db.commit()

    def update_progress(self, job_id: int, data: dict) -> None:
        with self.session_factory() as db:
            job = db.get(Job, job_id)
            if job is None:
                return
            job.progress = {**(job.progress or {}), **data}
            db.commit()

    def get_status(self, job_id: int) -> str | None:
        with self.session_factory() as db:
            job = db.get(Job, job_id)
            return job.status if job is not None else None

    # ---------- 执行 ----------
    def start(
        self,
        job_id: int,
        factory: Callable[[JobContext], Awaitable[dict | None]],
    ) -> None:
        self.bus.subscribe(job_id)  # 先建事件缓冲，避免订阅前的早期事件丢失
        loop = asyncio.get_running_loop()
        self._tasks[job_id] = loop.create_task(self._run(job_id, factory))

    async def _run(self, job_id: int, factory: Callable[[JobContext], Awaitable[dict | None]]) -> None:
        self._set_status(job_id, "running")
        ctx = JobContext(self, job_id)
        try:
            result = await factory(ctx)
            self._set_status(job_id, "completed", result=result or {})
            self.bus.publish(job_id, JobEvent("done", {"result": result or {}}))
        except (asyncio.CancelledError, JobCancelled):
            self._set_status(job_id, "cancelled")
            self.bus.publish(job_id, JobEvent("error", {"code": "cancelled", "message": "任务已取消"}))
        except Exception as exc:  # noqa: BLE001 - 任务边界必须兜底
            logger.exception(f"任务 {job_id} 失败")
            message = f"{type(exc).__name__}: {exc}"
            self._set_status(job_id, "failed", error=message)
            self.bus.publish(job_id, JobEvent("error", {"code": "job_failed", "message": message}))
        finally:
            self._tasks.pop(job_id, None)

    # ---------- 控制 ----------
    def pause(self, job_id: int) -> bool:
        if self.get_status(job_id) == "running":
            self._set_status(job_id, "paused")
            return True
        return False

    def resume(self, job_id: int) -> bool:
        if self.get_status(job_id) == "paused":
            self._set_status(job_id, "running")
            return True
        return False

    def cancel(self, job_id: int) -> bool:
        status = self.get_status(job_id)
        if status in TERMINAL_STATUSES or status is None:
            return False
        self._set_status(job_id, "cancelled")
        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            task.cancel()
        return True
