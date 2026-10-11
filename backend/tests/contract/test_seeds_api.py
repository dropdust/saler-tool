"""T026 契约测试：图谱/种子 API（唯一约束、审核流转、批量、导出、回灌）。"""

from __future__ import annotations

import json

from tests.conftest import wait_job


def _mk_node(client, node_type: str, name: str, **extra):
    resp = client.post("/api/v1/graph/nodes", json={"node_type": node_type, "name": name, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestNodes:
    def test_create_and_duplicate(self, client):
        node = _mk_node(client, "product_line", "紧固件")
        assert node["review_status"] == "approved"
        assert node["source"] == "manual"
        resp = client.post(
            "/api/v1/graph/nodes", json={"node_type": "product_line", "name": "紧固件"}
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "conflict"

    def test_invalid_type_rejected(self, client):
        resp = client.post("/api/v1/graph/nodes", json={"node_type": "bogus", "name": "x"})
        assert resp.status_code == 422

    def test_llm_source_pending_and_review_flow(self, client):
        node = _mk_node(client, "org", "Fake Utility Co", source="llm", confidence=0.7)
        assert node["review_status"] == "pending"
        resp = client.post(
            "/api/v1/graph/review",
            json={"target": "node", "ids": [node["id"]], "decision": "approve"},
        )
        assert resp.json()["updated"] == 1
        got = client.get(f"/api/v1/graph/nodes/{node['id']}").json()
        assert got["review_status"] == "approved"

    def test_terms_and_edges_uniqueness(self, client):
        a = _mk_node(client, "org", "Org A")
        b = _mk_node(client, "market", "Kenya")
        term = client.post(
            f"/api/v1/graph/nodes/{a['id']}/terms", json={"lang": "zh", "term": "A公司"}
        )
        assert term.status_code == 201
        dup = client.post(
            f"/api/v1/graph/nodes/{a['id']}/terms", json={"lang": "zh", "term": "A公司"}
        )
        assert dup.status_code == 409
        edge = client.post(
            "/api/v1/graph/edges",
            json={"from_node_id": a["id"], "to_node_id": b["id"], "relation_type": "org_in_market"},
        )
        assert edge.status_code == 201
        dup_edge = client.post(
            "/api/v1/graph/edges",
            json={"from_node_id": a["id"], "to_node_id": b["id"], "relation_type": "org_in_market"},
        )
        assert dup_edge.status_code == 409

    def test_merge_nodes_moves_refs(self, client):
        target = _mk_node(client, "org", "Kenya Power")
        dup = _mk_node(client, "org", "KPLC")
        client.post(f"/api/v1/graph/nodes/{dup['id']}/terms", json={"lang": "zh", "term": "肯尼亚电力"})
        seed = client.post(
            "/api/v1/seeds", json={"query": "KPLC contact", "source_node_id": dup["id"]}
        ).json()
        resp = client.post(
            "/api/v1/graph/nodes/merge",
            json={"target_id": target["id"], "source_ids": [dup["id"]]},
        )
        assert resp.status_code == 200
        assert client.get(f"/api/v1/seeds/{seed['id']}").json()["source_node_id"] == target["id"]
        assert len(client.get(f"/api/v1/graph/nodes/{target['id']}/terms").json()) == 1

    def test_overview_payload(self, client):
        product_line = _mk_node(client, "product_line", "金具")
        persona = _mk_node(client, "persona", "公用事业")
        market = _mk_node(client, "market", "肯尼亚", region="东非")
        client.post(
            "/api/v1/seeds",
            json={
                "query": "q1",
                "product_line_id": product_line["id"],
                "persona_id": persona["id"],
                "market_id": market["id"],
                "batch": "b1",
            },
        )
        payload = client.get("/api/v1/graph/overview", params={"batch": "b1"}).json()
        names = {n["name"] for n in payload["nodes"]}
        assert {"金具", "公用事业", "肯尼亚"} <= names
        assert "seed_cooccur" in {e["relation_type"] for e in payload["edges"]}
        counts = {n["name"]: n["counts"] for n in payload["nodes"]}
        assert counts["金具"]["seeds"] == 1


class TestSeeds:
    def test_create_and_duplicate_conflict(self, client):
        first = client.post("/api/v1/seeds", json={"query": "power fittings supplier"})
        assert first.status_code == 201
        duplicate = client.post("/api/v1/seeds", json={"query": "power fittings supplier"})
        assert duplicate.status_code == 409

    def test_bulk_create_report(self, client):
        payload = {"items": [{"query": "a"}, {"query": "a"}, {"query": ""}]}
        report = client.post("/api/v1/seeds/bulk", json=payload).json()
        assert report["created"] == 1
        assert report["duplicates"] == ["a"]
        assert len(report["errors"]) == 1

    def test_review_queue_and_decisions(self, client):
        seed = client.post(
            "/api/v1/seeds", json={"query": "llm seed", "source": "llm"}
        ).json()
        assert seed["review_status"] == "pending"
        assert client.get("/api/v1/seeds/review-queue").json()["total"] == 1
        client.post("/api/v1/seeds/review", json={"ids": [seed["id"]], "decision": "approve"})
        assert client.get("/api/v1/seeds/review-queue").json()["total"] == 0

    def test_invalid_status_update_rejected(self, client):
        seed = client.post("/api/v1/seeds", json={"query": "x1"}).json()
        resp = client.put(f"/api/v1/seeds/{seed['id']}", json={"status": "nope"})
        assert resp.status_code == 422

    def test_delete_is_disable(self, client):
        seed = client.post("/api/v1/seeds", json={"query": "x2"}).json()
        client.delete(f"/api/v1/seeds/{seed['id']}")
        assert client.get(f"/api/v1/seeds/{seed['id']}").json()["status"] == "invalid"

    def test_export_csv_and_txt(self, client):
        product_line = _mk_node(client, "product_line", "金具")
        client.post(
            "/api/v1/seeds",
            json={"query": "exp1", "product_line_id": product_line["id"], "batch": "eb"},
        )
        csv_result = client.post(
            "/api/v1/seeds/export", json={"format": "csv", "batch": "eb"}
        ).json()
        assert csv_result["count"] == 1 and csv_result["path"].endswith(".csv")
        with open(csv_result["path"], encoding="utf-8-sig") as handle:
            content = handle.read()
        assert "query," in content and "exp1" in content and "金具" in content

        txt_result = client.post(
            "/api/v1/seeds/export", json={"format": "txt", "batch": "eb"}
        ).json()
        with open(txt_result["path"], encoding="utf-8") as handle:
            lines = handle.read().strip().splitlines()
        assert lines[-1] == "exp1"

    def test_ingest_updates_seed_status_and_yield(self, client):
        seed = client.post("/api/v1/seeds", json={"query": "ingest seed"}).json()
        line = json.dumps(
            {
                "saler.schema": "harvest_v1",
                "seed_query": "ingest seed",
                "results": [
                    {"url": "https://acme.co.ke/contact", "title": "Contact"},
                    {"url": "https://acme.co.ke/about", "title": "About"},
                ],
            }
        )
        resp = client.post("/api/v1/seeds/ingest", json={"content": line})
        assert resp.status_code == 202
        job = wait_job(client, resp.json()["job_id"])
        assert job["status"] == "completed", job
        assert job["result"]["matched"] == 1
        assert job["result"]["new_domains"] == 1
        got = client.get(f"/api/v1/seeds/{seed['id']}").json()
        assert got["status"] == "done"
        assert got["n_candidates"] == 1

    def test_ingest_unmatched_reported(self, client):
        line = json.dumps(
            {"saler.schema": "harvest_v1", "seed_query": "no such seed", "results": []}
        )
        resp = client.post("/api/v1/seeds/ingest", json={"content": line})
        job = wait_job(client, resp.json()["job_id"])
        assert job["result"]["unmatched_queries"] == ["no such seed"]


class TestSeedLangsEndpoint:
    """T178 契约测试：GET /seeds/langs——库内语言取值（筛选选项全覆盖的数据源，FR-001/006）。"""

    def test_empty_library_returns_empty_list(self, client):
        assert client.get("/api/v1/seeds/langs").json() == []

    def test_distinct_sorted_exact_values(self, client):
        for query, lang in [("q-en", "en"), ("q-ru-1", "ru"), ("q-ru-2", "ru"), ("q-zh", "zh")]:
            resp = client.post("/api/v1/seeds", json={"query": query, "lang": lang})
            assert resp.status_code == 201, resp.text
        assert client.get("/api/v1/seeds/langs").json() == ["en", "ru", "zh"]
