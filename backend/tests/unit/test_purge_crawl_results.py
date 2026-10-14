"""清理服务单测：整批回退一次挖掘任务的检索产出（幌子污染事故 2026-10-14 的工具化）。"""

from __future__ import annotations

from datetime import datetime

import pytest

from saler.core.errors import ValidationFailed
from saler.db.models import (
    Campaign,
    Company,
    Contact,
    Domain,
    DomainSeedHit,
    Job,
    OperationLog,
    Seed,
    SendRecord,
    Suppression,
)
from saler.services.purge_crawl_results import purge_crawl_results

WINDOW_START = datetime(2026, 10, 14, 3, 31)
WINDOW_END = datetime(2026, 10, 14, 8, 19)


def _scenario(session_factory) -> dict:
    """预存导入域名 A（保留）；幌子域名 B（整家删除）；幌子域名 C + 导入域名 D 同居公司 C（保留）。"""
    with session_factory() as db:
        job = Job(
            job_type="crawl",
            name="客户线索挖掘",
            status="completed",
            started_at=WINDOW_START,
            finished_at=WINDOW_END,
        )
        db.add(job)
        db.commit()

        company_a = Company(name="Import A", source="import")
        company_b = Company(name="Junk B", source="crawl")
        company_c = Company(name="Mixed C", source="crawl")
        db.add_all([company_a, company_b, company_c])
        db.commit()

        domain_a = Domain(domain="import-a.example", status="done", company_id=company_a.id)
        domain_b = Domain(
            domain="junk-b.example", status="done", company_id=company_b.id, first_job_id=job.id
        )
        domain_c = Domain(
            domain="junk-c.example", status="done", company_id=company_c.id, first_job_id=job.id
        )
        domain_d = Domain(domain="import-d.example", status="done", company_id=company_c.id)
        db.add_all([domain_a, domain_b, domain_c, domain_d])
        db.commit()

        def _contact(company, domain, value):
            row = Contact(
                company_id=company.id,
                domain_id=domain.id,
                type="email",
                value=value,
                value_normalized=value,
            )
            db.add(row)
            return row

        _contact(company_a, domain_a, "a@import-a.example")
        contact_b1 = _contact(company_b, domain_b, "b1@junk-b.example")
        contact_b2 = _contact(company_b, domain_b, "b2@junk-b.example")
        _contact(company_c, domain_d, "d@import-d.example")
        db.commit()

        seed_in = Seed(
            query="q-in-window",
            status="done",
            last_run_at=datetime(2026, 10, 14, 4, 0),
            n_candidates=2,
        )
        seed_out = Seed(query="q-out-window", status="done", last_run_at=datetime(2026, 10, 13, 10, 0))
        seed_pending = Seed(query="q-pending")
        db.add_all([seed_in, seed_out, seed_pending])
        db.commit()

        db.add_all(
            [
                DomainSeedHit(domain_id=domain_b.id, seed_id=seed_in.id, job_id=job.id),
                # 假归因：幌子结果"命中"了预先存在的导入域名
                DomainSeedHit(domain_id=domain_a.id, seed_id=seed_in.id, job_id=job.id),
                DomainSeedHit(domain_id=domain_b.id, seed_id=seed_out.id, job_id=job.id),
            ]
        )
        db.commit()
        return {
            "job": job.id,
            "company_b": company_b.id,
            "contact_b1": contact_b1.id,
            "contact_b2": contact_b2.id,
        }


def test_dry_run_reports_counts_without_touching_data(session_factory):
    ids = _scenario(session_factory)
    with session_factory() as db:
        report = purge_crawl_results(db, job_id=ids["job"], apply=False)
    assert report == {
        "job_id": ids["job"],
        "applied": False,
        "domains": 2,
        "domains_protected": 0,
        "seed_hits": 3,
        "contacts": 2,
        "contacts_protected": 0,
        "companies": 1,
        "companies_kept": 1,
        "seeds_reset": 1,
    }
    with session_factory() as db:
        assert db.query(Domain).count() == 4
        assert db.query(Contact).count() == 4
        assert db.query(DomainSeedHit).count() == 3


def test_apply_removes_junk_and_resets_in_window_seeds(session_factory):
    ids = _scenario(session_factory)
    with session_factory() as db:
        report = purge_crawl_results(db, job_id=ids["job"], apply=True)
        assert report["applied"] is True
    with session_factory() as db:
        assert {row.domain for row in db.query(Domain).all()} == {
            "import-a.example",
            "import-d.example",
        }
        assert {row.name for row in db.query(Company).all()} == {"Import A", "Mixed C"}
        assert {row.value for row in db.query(Contact).all()} == {
            "a@import-a.example",
            "d@import-d.example",
        }
        assert db.query(DomainSeedHit).filter_by(job_id=ids["job"]).count() == 0

        seed_in = db.query(Seed).filter_by(query="q-in-window").one()
        assert seed_in.status == "pending" and seed_in.last_run_at is None
        assert seed_in.n_candidates == 0  # 假归因删除后重算
        seed_out = db.query(Seed).filter_by(query="q-out-window").one()
        assert seed_out.status == "done"  # 窗口外状态不动
        assert db.query(Seed).filter_by(query="q-pending").one().status == "pending"

        logs = db.query(OperationLog).filter_by(job_type="system", level="warn").all()
        assert any("清理任务" in row.message for row in logs)


def test_refuses_running_job(session_factory):
    with session_factory() as db:
        job = Job(job_type="crawl", name="运行中", status="running")
        db.add(job)
        db.commit()
        with pytest.raises(ValidationFailed):
            purge_crawl_results(db, job_id=job.id, apply=False)


def test_send_record_and_suppression_protect_from_deletion(session_factory):
    ids = _scenario(session_factory)
    with session_factory() as db:
        campaign = Campaign(name="C1")
        db.add(campaign)
        db.commit()
        db.add(
            SendRecord(
                campaign_id=campaign.id,
                round_no=1,
                company_id=ids["company_b"],
                contact_id=ids["contact_b1"],
                contact_value="b1@junk-b.example",
            )
        )
        db.add(
            Suppression(
                scope="email",
                target_value="b2@junk-b.example",
                contact_id=ids["contact_b2"],
                reason="manual",
            )
        )
        db.commit()
        report = purge_crawl_results(db, job_id=ids["job"], apply=True)
    assert report["contacts"] == 0 and report["contacts_protected"] == 2
    # 被保护联系人所属域名一并保留（FK/语义），公司随域名保留
    assert report["domains"] == 1 and report["domains_protected"] == 1
    assert report["companies"] == 0 and report["companies_kept"] == 2
    with session_factory() as db:
        assert db.get(Contact, ids["contact_b1"]) is not None
        assert db.get(Company, ids["company_b"]) is not None
        assert db.query(Domain).filter_by(domain="junk-b.example").count() == 1
        assert db.query(Domain).filter_by(domain="junk-c.example").count() == 0
