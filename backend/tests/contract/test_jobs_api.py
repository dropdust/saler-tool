"""T227 任务契约基座：多状态过滤 / 未知状态 422 / SSE 终态快照映射 / interrupted 控制拒绝。

对应契约 §1（过滤扩展）与 §2（状态值域 + 快照映射修正）；data-model.md §1 状态机。
SSE 用例沿用 test_sse_flow.py 的 httpx.AsyncClient 流式模式（TestClient 缓冲读取会等待流耗尽）。
"""

from __future__ import annotations

import asyncio
import json

import httpx

from saler.db.models import Job
from tests.conftest import wait_job


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


# ---------- 重跑（契约 §3：三守卫 + 成功 + 新任务元数据） ----------


def test_rerun_missing_job_404(client):
    assert client.post("/api/v1/jobs/404/rerun").status_code == 404


def test_rerun_type_without_starter_409(client, session_factory):
    (job_id,) = _seed_jobs(session_factory, [("campaign_send", "failed")])
    resp = client.post(f"/api/v1/jobs/{job_id}/rerun")
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["code"] == "not_rerunnable"
    assert "重新运行" in body["message"] and "重新发起" in body["message"]  # 附后续指引语义


def test_rerun_non_terminal_409(client, session_factory):
    (job_id,) = _seed_jobs(session_factory, [("company_import", "running")])
    resp = client.post(f"/api/v1/jobs/{job_id}/rerun")
    assert resp.status_code == 409 and resp.json()["code"] == "not_terminal"


def test_rerun_completed_409(client, session_factory):
    (job_id,) = _seed_jobs(session_factory, [("company_import", "completed")])
    resp = client.post(f"/api/v1/jobs/{job_id}/rerun")
    assert resp.status_code == 409 and resp.json()["code"] == "already_completed"


def test_rerun_import_rebuilds_request_and_drops_old_payload(client, session_factory):
    """以原 `params` 重建请求；新任务**不复制** progress/result/error（哨兵值验证）。"""
    with session_factory() as db:
        original = Job(
            job_type="ingest_harvest",
            name="回灌收割结果",
            status="failed",
            params={"path": "/nonexistent/rerun.csv", "content": None},
            progress={"phase": "SENTINEL-PROGRESS"},
            result={"rows": 999},
            error="SENTINEL-ERROR",
        )
        db.add(original)
        db.commit()
        original_id = original.id

    resp = client.post(f"/api/v1/jobs/{original_id}/rerun")
    assert resp.status_code == 202, resp.text
    new_id = resp.json()["job_id"]
    assert new_id != original_id

    row = wait_job(client, new_id)  # 坏路径必然失败，但失败是"它自己"的
    assert row["job_type"] == "ingest_harvest" and row["name"] == "回灌收割结果"
    assert row["result"] is None
    assert "SENTINEL" not in json.dumps(row, ensure_ascii=False)
    with session_factory() as db:  # params 不进 API 负载（可能含整份名单内容）→ 落库侧核对
        rerun = db.get(Job, new_id)
        assert rerun.params == {"path": "/nonexistent/rerun.csv", "content": None}
        assert rerun.progress == {} and rerun.result is None
        assert "SENTINEL" not in (rerun.error or "")  # 失败原因是它自己的


def test_rerun_failed_harvest_after_fix_end_to_end(client, session_factory, tmp_path):
    """真实起点：回灌失败（文件缺失）→ 补上文件 → 重跑同参数并完成（用户主动操作）。"""
    harvest = tmp_path / "harvest.jsonl"
    failed = client.post("/api/v1/seeds/ingest", json={"path": str(harvest)})
    assert failed.status_code == 202
    original = wait_job(client, failed.json()["job_id"])
    assert original["status"] == "failed"

    harvest.write_text(
        '{"seed_query": "rerun 电力金具", "results": [{"url": "https://r.example.com/", "title": "R"}]}\n',
        encoding="utf-8",
    )
    resp = client.post(f"/api/v1/jobs/{original['id']}/rerun")
    assert resp.status_code == 202, resp.text
    rerun = wait_job(client, resp.json()["job_id"])
    assert rerun["status"] == "completed"
    assert rerun["job_type"] == "ingest_harvest" and rerun["name"] == original["name"]
    assert rerun["id"] != original["id"]
    with session_factory() as db:  # params 不进 API 负载 → 落库侧核对"原样重建"
        assert db.get(Job, rerun["id"]).params["path"] == str(harvest)
