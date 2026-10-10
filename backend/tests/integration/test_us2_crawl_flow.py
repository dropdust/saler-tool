"""T051 集成测试：S6/S7（API 全链路）——挖掘→线索修订→排除→导出→导入。"""

from __future__ import annotations

from tests.conftest import wait_job
from tests.fixtures.fakes.fetcher_fake import FakeFetcher
from tests.fixtures.fakes.search_fake import FakeSearchProvider

ACME_HOME = (
    '<html lang="en"><head><title>Acme Kenya</title></head><body>'
    '<a href="/contact">Contact</a><a href="mailto:sales@acme.co.ke">m</a></body></html>'
)
ACME_CONTACT = '<html lang="en"><body><a href="https://wa.me/254712345678">wa</a></body></html>'
BETA_HOME = '<html lang="sw"><body><p>info@beta.com</p></body></html>'

PAGES = {
    "https://acme.co.ke/": ACME_HOME,
    "https://acme.co.ke/contact": ACME_CONTACT,
    "https://beta.com/": BETA_HOME,
}
SEARCH_RESULTS = {
    "power fittings contractor kenya": [
        {"url": "https://acme.co.ke/", "title": "Acme Kenya"},
        {"url": "https://beta.com/", "title": "Beta"},
    ]
}


def _inject_offline_pipeline(monkeypatch) -> FakeFetcher:
    fetcher = FakeFetcher(PAGES)
    monkeypatch.setattr(
        "saler.api.routes.crawl.resolve_search_chain",
        lambda db, config: FakeSearchProvider(SEARCH_RESULTS),
    )
    monkeypatch.setattr("saler.api.routes.crawl.Fetcher", lambda **_kwargs: fetcher)
    return fetcher


def test_crawl_without_search_provider_is_409(client):
    client.post("/api/v1/seeds", json={"query": "q", "batch": "s6"})
    resp = client.post("/api/v1/crawl/jobs", json={})
    assert resp.status_code == 409
    assert resp.json()["code"] == "search_not_configured"


def test_s6_s7_full_flow(client, monkeypatch, data_dir):
    _inject_offline_pipeline(monkeypatch)

    seed = client.post(
        "/api/v1/seeds",
        json={"query": "power fittings contractor kenya", "batch": "s6", "priority": 1},
    ).json()

    # ---- S6：挖掘任务（job）----
    resp = client.post("/api/v1/crawl/jobs", json={"seed_ids": [seed["id"]]})
    assert resp.status_code == 202
    job = wait_job(client, resp.json()["job_id"])
    assert job["status"] == "completed", job
    assert job["result"]["domains_done"] == 2

    # 种子状态与产量
    updated_seed = client.get(f"/api/v1/seeds/{seed['id']}").json()
    assert updated_seed["status"] == "done"
    assert updated_seed["n_candidates"] == 2

    # ---- S7：线索修订 ----
    domains = client.get("/api/v1/domains").json()
    assert domains["total"] == 2
    acme_domain = next(d for d in domains["items"] if d["domain"] == "acme.co.ke")
    assert acme_domain["status"] == "done"
    assert acme_domain["country"] == "ke"

    companies = client.get("/api/v1/companies").json()
    acme = next(c for c in companies["items"] if c["domain"] == "acme.co.ke")
    contacts = client.get(f"/api/v1/companies/{acme['id']}/contacts").json()
    emails = {c["value_normalized"] for c in contacts if c["type"] == "email"}
    assert "sales@acme.co.ke" in emails

    # 人工补录 + 状态推进
    added = client.post(
        f"/api/v1/companies/{acme['id']}/contacts",
        json={"type": "email", "value": "Purchase@acme.co.ke", "category": "procurement"},
    )
    assert added.status_code == 201
    assert added.json()["value_normalized"] == "purchase@acme.co.ke"
    client.put(f"/api/v1/companies/{acme['id']}", json={"status": "replied", "tags": ["vip"]})
    assert client.get(f"/api/v1/companies/{acme['id']}").json()["status"] == "replied"

    # ---- 排除规则：过滤无关站点 ----
    client.post(
        "/api/v1/exclusion-rules",
        json={"rule_type": "keyword", "pattern": "beta", "note": "示例：过滤无关站"},
    )
    applied = client.post("/api/v1/exclusion-rules/apply").json()
    assert applied["excluded"] >= 1
    beta = client.get("/api/v1/domains", params={"q": "beta.com"}).json()["items"][0]
    assert beta["is_excluded"] is True

    # ---- 导出（被排除者单独列出，不进入买家主表）----
    exported = client.post("/api/v1/companies/export", json={"format": "csv"}).json()
    with open(exported["path"], encoding="utf-8-sig") as handle:
        content = handle.read()
    assert "sales@acme.co.ke" in content
    assert "info@beta.com" not in content  # 已排除，不进买家列表

    # ---- 导入既有名单：黑名单联动 ----
    client.post("/api/v1/suppressions", json={"scope": "email", "target_value": "blocked@x.com", "reason": "unsubscribed"})
    csv_content = (
        "email,phone,company_name,domain,country,language,tags,note\n"
        "blocked@x.com,,,,,,\n"
        "alice@importer.co.ke,+254700000001,Importer Ltd,importer.co.ke,ke,en,vip,展会\n"
    )
    resp = client.post("/api/v1/companies/import", json={"content": csv_content})
    assert resp.status_code == 202
    job = wait_job(client, resp.json()["job_id"])
    assert job["status"] == "completed"
    report = job["result"]
    assert report["new_companies"] >= 1
    assert report["suppressed"] == 1
    blocked = client.get("/api/v1/companies", params={"q": "Importer"}).json()
    assert blocked["total"] >= 1
