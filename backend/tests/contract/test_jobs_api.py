"""T227 任务契约基座：多状态过滤 / 未知状态 422 / SSE 终态快照映射 / interrupted 控制拒绝。

对应契约 §1（过滤扩展）与 §2（状态值域 + 快照映射修正）；data-model.md §1 状态机。
SSE 用例沿用 test_sse_flow.py 的 httpx.AsyncClient 流式模式（TestClient 缓冲读取会等待流耗尽）。
"""

from __future__ import annotations

import asyncio
import json

import httpx

from saler.db.models import Job


def _seed_jobs(session_factory, specs: list[tuple[str, str]]) -> list[int]:
    ids: list[int] = []
    with session_factory() as db:
        for job_type, status in specs:
            row = Job(job_type=job_type, name=f"{job_type}-{status}", status=status)
            db.add(row)
            db.commit()
            ids.append(row.id)
    return ids


async def _sse_events(ac: httpx.AsyncClient, job_id: int) -> tuple[list[str], list[dict]]:
    """读取一个已终态任务的事件流（快照 + 终态事件后即断）。"""
    events: list[str] = []
    payloads: list[dict] = []
    current: str | None = None
    async with ac.stream("GET", f"/api/v1/jobs/{job_id}/events") as resp:
        assert resp.status_code == 200, await resp.aread()
        async for line in resp.aiter_lines():
            if line.startswith("event:"):
                current = line.split(":", 1)[1].strip()
                events.append(current)
            elif line.startswith("data:") and current:
                payloads.append(json.loads(line.split(":", 1)[1].strip()))
                if current in ("done", "error"):
                    break
    return events, payloads


def _make_async_app(engine, session_factory):
    from saler.api.main import create_app

    return create_app(engine=engine, session_factory=session_factory, token="t")


# ---------- 多状态过滤（契约 §1） ----------


def test_list_jobs_multi_status_filter(client, session_factory):
    _seed_jobs(
        session_factory,
        [("t", "queued"), ("t", "running"), ("t", "paused"), ("t", "completed"), ("t", "failed")],
    )
    resp = client.get("/api/v1/jobs", params={"status": "running,paused,queued"})
    assert resp.status_code == 200, resp.text
    statuses = {item["status"] for item in resp.json()["items"]}
    assert statuses == {"queued", "running", "paused"}


def test_list_jobs_multi_status_ignores_blank_tokens(client, session_factory):
    _seed_jobs(session_factory, [("t", "running"), ("t", "completed")])
    resp = client.get("/api/v1/jobs", params={"status": " running , ,paused "})
    assert resp.status_code == 200, resp.text
    statuses = {item["status"] for item in resp.json()["items"]}
    assert statuses == {"running"}


def test_list_jobs_single_status_compat(client, session_factory):
    _seed_jobs(session_factory, [("t", "running"), ("t", "completed")])
    resp = client.get("/api/v1/jobs", params={"status": "running"})
    assert resp.status_code == 200, resp.text
    statuses = {item["status"] for item in resp.json()["items"]}
    assert statuses == {"running"}


def test_list_jobs_unknown_status_422(client):
    resp = client.get("/api/v1/jobs", params={"status": "running,bogus"})
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["code"] == "unprocessable"
    assert "bogus" in body["message"]


# ---------- SSE 终态快照映射（契约 §2 修正） ----------


async def _stream_terminal(engine, session_factory, job_type: str, status: str):
    app = _make_async_app(engine, session_factory)
    transport = httpx.ASGITransport(app=app)
    (job_id,) = _seed_jobs(session_factory, [(job_type, status)])
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"X-App-Token": "t"}, timeout=10
    ) as ac:
        return await asyncio.wait_for(_sse_events(ac, job_id), timeout=10)


async def test_sse_snapshot_completed_emits_done(engine, session_factory):
    events, payloads = await _stream_terminal(engine, session_factory, "t", "completed")
    assert events[0] == "progress"
    assert payloads[0]["snapshot"]["status"] == "completed"
    assert events[-1] == "done"


async def test_sse_snapshot_failed_emits_error_job_failed(engine, session_factory):
    events, payloads = await _stream_terminal(engine, session_factory, "t", "failed")
    assert events[0] == "progress"
    assert payloads[0]["snapshot"]["status"] == "failed"
    assert events[-1] == "error"
    assert payloads[-1]["code"] == "job_failed"


async def test_sse_snapshot_cancelled_emits_error_cancelled(engine, session_factory):
    events, payloads = await _stream_terminal(engine, session_factory, "crawl", "cancelled")
    assert events[0] == "progress"
    assert payloads[0]["snapshot"]["status"] == "cancelled"
    assert events[-1] == "error"
    assert payloads[-1]["code"] == "cancelled"


async def test_sse_snapshot_interrupted_emits_error_interrupted(engine, session_factory):
    events, payloads = await _stream_terminal(engine, session_factory, "crawl", "interrupted")
    assert events[0] == "progress"
    assert payloads[0]["snapshot"]["status"] == "interrupted"
    assert events[-1] == "error"
    assert payloads[-1]["code"] == "interrupted"
    assert "中断" in payloads[-1]["message"]


# ---------- interrupted 为终态：控制操作一律 409 ----------


def test_interrupted_rejects_control(client, session_factory):
    (job_id,) = _seed_jobs(session_factory, [("crawl", "interrupted")])
    for action in ("pause", "resume", "cancel"):
        resp = client.post(f"/api/v1/jobs/{job_id}/{action}")
        assert resp.status_code == 409, f"{action}: {resp.text}"
