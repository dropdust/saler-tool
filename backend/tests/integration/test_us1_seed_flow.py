"""T029 集成测试：US1 全流程 —— 建模→AI 扩充→审核→翻译→导出→回灌→统计。"""

from __future__ import annotations

import json

import pytest

from tests.conftest import wait_job


@pytest.fixture()
def fake_llm(monkeypatch):
    from tests.fixtures.fakes.llm_fake import FakeLLMProvider

    provider = FakeLLMProvider()
    monkeypatch.setattr(
        "saler.api.routes.ai.resolve_llm_provider",
        lambda db, provider_id=None: provider,
    )
    return provider


def test_full_seed_flow(client, fake_llm):
    # 1) 建模：产品线 + 市场
    product_line = client.post(
        "/api/v1/graph/nodes", json={"node_type": "product_line", "name": "电力金具"}
    ).json()
    market = client.post(
        "/api/v1/graph/nodes",
        json={"node_type": "market", "name": "肯尼亚", "region": "东非"},
    ).json()

    # 2) 手工种子
    manual = client.post(
        "/api/v1/seeds",
        json={
            "query": "power line hardware kenya",
            "market_id": market["id"],
            "batch": "manual-1",
        },
    )
    assert manual.status_code == 201

    # 3) AI 扩充（假 Provider，job 化）：产出中文母版候选
    resp = client.post(
        "/api/v1/ai/seeds/expand",
        json={"description": "电力金具出口", "count": 5, "from_node_ids": [product_line["id"]]},
    )
    assert resp.status_code == 202
    job = wait_job(client, resp.json()["job_id"])
    assert job["status"] == "completed", job
    assert job["result"]["seeds_created"] == 2

    # AI 产出全部待审核，且一律为中文母版（lang=zh），供审核后翻译
    queue = client.get("/api/v1/seeds/review-queue").json()
    assert queue["total"] == 2
    assert all(item["lang"] == "zh" for item in queue["items"])

    # 4) 审核：全部采纳
    ids = [item["id"] for item in queue["items"]]
    client.post("/api/v1/seeds/review", json={"ids": ids, "decision": "approve"})
    assert client.get("/api/v1/seeds/review-queue").json()["total"] == 0

    # 5) 已审核中文母版 → 目标语言翻译（分类随血缘继承）
    resp = client.post(
        "/api/v1/ai/seeds/translate", json={"seed_ids": ids, "targets": ["en", "ru"]}
    )
    translated_job = wait_job(client, resp.json()["job_id"])
    assert translated_job["result"]["created"] == 4
    assert translated_job["result"]["by_lang"] == {"en": 2, "ru": 2}

    # 译文同样进入待审核：未采纳前不可导出（先审后发的防线）
    translated_queue = client.get("/api/v1/seeds/review-queue").json()
    assert translated_queue["total"] == 4
    assert any(item["product_line_id"] == product_line["id"] for item in translated_queue["items"])
    exported_pending_only = client.post("/api/v1/seeds/export", json={"format": "csv"}).json()
    assert exported_pending_only["count"] == 3  # 手工 1 + 中文母版 2（已审核）
    client.post(
        "/api/v1/seeds/review",
        json={"ids": [item["id"] for item in translated_queue["items"]], "decision": "approve"},
    )

    # 6) 导出执行清单（默认仅已审核）
    exported = client.post("/api/v1/seeds/export", json={"format": "csv"}).json()
    assert exported["count"] >= 7
    with open(exported["path"], encoding="utf-8-sig") as handle:
        content = handle.read()
    assert "power line hardware kenya" in content

    # 7) 外部收割回灌 → 归因与产量
    harvest_line = json.dumps(
        {
            "saler.schema": "harvest_v1",
            "seed_query": "power line hardware kenya",
            "results": [{"url": "https://kplc.co.ke/contact", "title": "Contact Us"}],
        }
    )
    resp = client.post("/api/v1/seeds/ingest", json={"content": harvest_line})
    ingest_job = wait_job(client, resp.json()["job_id"])
    assert ingest_job["result"]["matched"] == 1
    assert ingest_job["result"]["new_domains"] == 1

    manual_seed = client.get(f"/api/v1/seeds/{manual.json()['id']}").json()
    assert manual_seed["status"] == "done"
    assert manual_seed["n_candidates"] == 1

    # 8) 统计与可视化数据
    stats = client.get("/api/v1/seeds/stats", params={"group_by": "market"}).json()
    kenya = next(row for row in stats if row["name"] == "肯尼亚")
    assert kenya["seeds"] >= 2

    overview = client.get("/api/v1/graph/overview").json()
    assert any(node["node_type"] == "org" for node in overview["nodes"])
