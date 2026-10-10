"""T021 SSE 集成测试：快照 + 实时事件 + 终态关闭。"""

from __future__ import annotations

import asyncio
import json

import httpx


async def _stream_events(ac: httpx.AsyncClient, job_id: int) -> tuple[list[str], list[dict]]:
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


async def test_sse_live_event_flow(engine, session_factory):
    from saler.api.main import create_app

    app = create_app(engine=engine, session_factory=session_factory, token="t")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"X-App-Token": "t"}, timeout=10
    ) as ac:
        manager = app.state.job_manager
        job_id = manager.create("test", name="sse")

        async def work(ctx):
            ctx.log("开始处理")
            ctx.progress(done=1, total=1)
            return {"ok": True}

        manager.start(job_id, work)
        events, payloads = await asyncio.wait_for(_stream_events(ac, job_id), timeout=10)
        assert "done" in events
        assert any(p.get("result", {}).get("ok") for p in payloads if isinstance(p, dict))


async def test_sse_terminal_snapshot(engine, session_factory):
    """订阅已终态任务：立即返回快照 + 终态事件。"""
    from saler.api.main import create_app

    app = create_app(engine=engine, session_factory=session_factory, token="t")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"X-App-Token": "t"}, timeout=10
    ) as ac:
        manager = app.state.job_manager
        job_id = manager.create("test")

        async def work(ctx):
            return {"done": True}

        manager.start(job_id, work)
        deadline = asyncio.get_running_loop().time() + 5
        while manager.get_status(job_id) != "completed":
            assert asyncio.get_running_loop().time() < deadline
            await asyncio.sleep(0.02)
        events, payloads = await asyncio.wait_for(_stream_events(ac, job_id), timeout=10)
        assert events[0] == "progress"
        assert "done" in events
