"""域名溯源出口契约测试：列表带命中计数、详情带命中明细（query 词/任务/首次命中时间）。"""

from __future__ import annotations

from saler.db.models import Domain, DomainSeedHit, Job, Seed


def _seed_hits_fixture(session_factory) -> dict:
    with session_factory() as db:
        job = Job(job_type="crawl", name="客户线索挖掘", status="completed")
        db.add(job)
        db.commit()
        domain = Domain(
            domain="booking.example",
            homepage_url="https://booking.example/",
            source="search",
            status="pending",
            first_job_id=job.id,
        )
        other = Domain(domain="imported.example", source="import", status="pending")
        db.add_all([domain, other])
        db.commit()
        seed_a = Seed(
            query='"pole line hardware" distributor contact',
            lang="en",
            source="import",
            review_status="approved",
        )
        seed_b = Seed(
            query='"hex nuts" distributor OR importer qatar',
            lang="en",
            source="import",
            review_status="approved",
        )
        db.add_all([seed_a, seed_b])
        db.commit()
        db.add_all(
            [
                DomainSeedHit(domain_id=domain.id, seed_id=seed_a.id, job_id=job.id),
                DomainSeedHit(domain_id=domain.id, seed_id=seed_b.id, job_id=job.id),
            ]
        )
        db.commit()
        return {"domain_id": domain.id, "other_id": other.id, "job_id": job.id}


class TestDomainProvenance:
    def test_list_includes_seed_hits_count(self, client, session_factory):
        _seed_hits_fixture(session_factory)
        resp = client.get("/api/v1/domains")
        assert resp.status_code == 200
        rows = {row["domain"]: row for row in resp.json()["items"]}
        assert rows["booking.example"]["seed_hits_count"] == 2
        assert rows["imported.example"]["seed_hits_count"] == 0

    def test_detail_lists_hits_with_query_job_and_time(self, client, session_factory):
        ids = _seed_hits_fixture(session_factory)
        got = client.get(f"/api/v1/domains/{ids['domain_id']}").json()
        assert got["seed_hits_count"] == 2
        queries = [hit["query"] for hit in got["seed_hits"]]
        assert '"pole line hardware" distributor contact' in queries
        assert all(hit["job_id"] == ids["job_id"] for hit in got["seed_hits"])
        assert all(hit["first_seen_at"] for hit in got["seed_hits"])

    def test_detail_without_hits_returns_empty_list(self, client, session_factory):
        ids = _seed_hits_fixture(session_factory)
        got = client.get(f"/api/v1/domains/{ids['other_id']}").json()
        assert got["seed_hits"] == []
        assert got["seed_hits_count"] == 0
