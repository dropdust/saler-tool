"""T021 任务引擎测试：状态机 / 暂停恢复 / 取消 / 事件。"""

from __future__ import annotations

import asyncio

import pytest

from saler.db.models import Job


def _status(manager, job_id: int) -> str:
    with manager.session_factory() as db:
        job = db.get(Job, job_id)
        assert job is not None
        return job.status


async def _wait_status(manager, job_id: int, status: str, timeout: float = 3.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if _status(manager, job_id) == status:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"任务 {job_id} 未在超时内到达 {status}（当前 {_status(manager, job_id)}）")


@pytest.fixture()
def manager(session_factory):
    from saler.jobs.engine import JobManager

    return JobManager(session_factory)


async def test_job_completes_with_result_and_progress(manager):
    job_id = manager.create("test", name="完成")

    async def work(ctx):
        ctx.progress(done=1, total=2)
        return {"ok": True}

    manager.start(job_id, work)
    await _wait_status(manager, job_id, "completed")
    with manager.session_factory() as db:
        job = db.get(Job, job_id)
        assert job.result == {"ok": True}
        assert job.progress["done"] == 1


async def test_job_failure_marks_failed(manager):
    job_id = manager.create("test")

    async def work(ctx):
        raise ValueError("boom")

    manager.start(job_id, work)
    await _wait_status(manager, job_id, "failed")
    with manager.session_factory() as db:
        assert "boom" in (db.get(Job, job_id).error or "")


async def test_pause_blocks_progress_until_resume(manager):
    job_id = manager.create("test")
    progressed: list[int] = []

    async def work(ctx):
        for i in range(20):
            await ctx.checkpoint()
            progressed.append(i)
            await asyncio.sleep(0.01)
        return {"n": len(progressed)}

    manager.start(job_id, work)
    await asyncio.sleep(0.08)
    assert manager.pause(job_id) is True
    await _wait_status(manager, job_id, "paused")
    await asyncio.sleep(0.05)
    count_at_pause = len(progressed)
    await asyncio.sleep(0.15)
    assert len(progressed) <= count_at_pause + 1  # 暂停期间不再推进
    assert manager.resume(job_id) is True
    await _wait_status(manager, job_id, "completed", timeout=5)
    assert len(progressed) == 20


async def test_cancel(manager):
    job_id = manager.create("test")

    async def work(ctx):
        while True:
            await ctx.checkpoint()
            await asyncio.sleep(0.01)

    manager.start(job_id, work)
    await asyncio.sleep(0.05)
    assert manager.cancel(job_id) is True
    await _wait_status(manager, job_id, "cancelled")


async def test_events_published_in_order(manager):
    job_id = manager.create("test")
    queue = manager.bus.subscribe(job_id)

    async def work(ctx):
        ctx.log("hello")
        ctx.progress(step=1)
        return {}

    manager.start(job_id, work)
    received = []
    while True:
        event = await asyncio.wait_for(queue.get(), timeout=3)
        received.append(event.type)
        if event.type == "done":
            break
    assert "log" in received
    assert "progress" in received
    assert received[-1] == "done"
