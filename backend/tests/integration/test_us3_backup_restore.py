"""T078 集成测试：S2 大模型配置流程 + S11 备份→恢复（API 全链路，FR-004/030）。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import saler.db.models  # noqa: F401
from saler.db.base import Base
from saler.db.session import make_engine
from saler.services.datadir import db_path


@pytest.fixture()
def data_client(data_dir):
    """引擎指向 data_dir/saler.db 的客户端（备份/恢复与同一数据目录联动）。"""
    from saler.api.main import create_app

    engine = make_engine(db_path(data_dir))
    Base.metadata.create_all(engine)
    app = create_app(engine=engine, token="t", data_dir=data_dir)
    with TestClient(app, headers={"X-App-Token": "t"}) as client:
        yield client
    engine.dispose()


def _wait_job_allow_gone(client: TestClient, job_id: int, timeout: float = 15.0):
    """恢复会替换整个数据库：任务记录可能被就地带回（completed）或不可见（None）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/v1/jobs/{job_id}")
        if resp.status_code == 404:
            return None
        data = resp.json()
        if data["status"] in ("completed", "failed", "cancelled"):
            return data
        time.sleep(0.05)
    raise AssertionError(f"任务 {job_id} 超时未完成")


def test_s2_configure_and_test_flow(data_client, monkeypatch):
    created = data_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Qwen",
            "provider_type": "openai_compatible",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-plus",
            "api_key": "sk-qwen-test-000111",
            "params": {"supports_json_schema": True},
        },
    ).json()
    assert created["is_default"] is True

    from saler.providers.llm.base import TestResult

    monkeypatch.setattr(
        "saler.api.routes.llm.run_connection_test",
        lambda row: TestResult(ok=True, detail="ok", models=["qwen-plus"]),
    )
    body = data_client.post(f"/api/v1/llm/providers/{created['id']}/test").json()
    assert body["ok"] is True
    row = data_client.get("/api/v1/llm/providers").json()[0]
    assert row["health"] == "healthy"


def test_s11_backup_then_restore_via_api(data_client, data_dir):
    # 1) 备份前造数据
    data_client.post("/api/v1/graph/nodes", json={"node_type": "market", "name": "肯尼亚"})
    data_client.post("/api/v1/seeds", json={"query": "ke seed", "batch": "s11"})

    # 2) 创建备份（job）
    resp = data_client.post("/api/v1/backups", json={})
    assert resp.status_code == 202
    job = _wait_job_allow_gone(data_client, resp.json()["job_id"])
    assert job is not None and job["status"] == "completed", job
    archive = job["result"]["path"]
    assert Path(archive).exists()

    listing = data_client.get("/api/v1/backups").json()
    assert any(item["path"] == archive for item in listing["items"])
    assert data_client.post("/api/v1/backups/validate", json={"path": archive}).json()["ok"] is True

    # 3) 备份后新增数据（恢复后应消失）
    data_client.post("/api/v1/seeds", json={"query": "post-backup seed", "batch": "s11"})
    assert data_client.get("/api/v1/seeds").json()["total"] == 2

    # 4) 恢复（job；整库替换后任务记录也可能不可见）
    resp = data_client.post("/api/v1/restore", json={"path": archive})
    assert resp.status_code == 202
    outcome = _wait_job_allow_gone(data_client, resp.json()["job_id"])
    assert outcome is None or outcome["status"] == "completed"

    # 5) 数据回到备份时点
    seeds = data_client.get("/api/v1/seeds").json()
    queries = {item["query"] for item in seeds["items"]}
    assert "ke seed" in queries
    assert "post-backup seed" not in queries
    assert data_client.get("/api/v1/backups").status_code == 200


def test_restore_rejects_bad_file_via_api(data_client, tmp_path):
    bogus = tmp_path / "bad.zip"
    bogus.write_bytes(b"nope")
    resp = data_client.post("/api/v1/restore", json={"path": str(bogus)})
    assert resp.status_code == 202
    job = _wait_job_allow_gone(data_client, resp.json()["job_id"])
    assert job["status"] == "failed"
    assert job["error"]


def test_export_all_via_api(data_client, data_dir):
    data_client.post("/api/v1/seeds", json={"query": "export-all seed"})
    resp = data_client.post("/api/v1/export/all", json={})
    assert resp.status_code == 202
    job = _wait_job_allow_gone(data_client, resp.json()["job_id"])
    assert job["status"] == "completed"
    assert Path(job["result"]["path"]).exists()
