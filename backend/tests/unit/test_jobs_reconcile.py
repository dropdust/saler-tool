"""启动对账（005-T246）：进程退出遗留的非终态任务 → interrupted（幂等，只改状态）。

覆盖：非终态三态收口 + finished_at、终态一律不动（防"退出瞬间恰逢完成"误标）、
crawl_job 明细联动、幂等（已收口的不重写时间）、create_app 装配点
（dev / 桌面 / --server / 测试四入口同覆盖——对账只改状态，绝不自动重放对外调用）。
"""

from __future__ import annotations

from datetime import UTC, datetime

from saler.api.main import create_app
from saler.db.models import CrawlJob, Job
from saler.jobs.reconcile import reconcile_interrupted_jobs

DONE_AT = datetime(2026, 10, 15, 1, 0, tzinfo=UTC)


def _job(status: str, *, ref_type: str | None = None, ref_id: int | None = None) -> Job:
    return Job(job_type="crawl", name="任务", status=status, ref_type=ref_type, ref_id=ref_id)


def test_non_terminal_jobs_become_interrupted_with_finished_at(session_factory):
    with session_factory() as db:
        db.add_all([_job("queued"), _job("running"), _job("paused")])
        db.commit()

    report = reconcile_interrupted_jobs(session_factory)
    assert report["jobs"] == 3
    with session_factory() as db:
        rows = db.query(Job).order_by(Job.id).all()
    assert [row.status for row in rows] == ["interrupted"] * 3
    assert all(row.finished_at is not None for row in rows)


def test_terminal_jobs_untouched(session_factory):
    statuses = ("completed", "failed", "cancelled", "interrupted")
    with session_factory() as db:
        for status in statuses:
            job = _job(status)
            job.finished_at = DONE_AT
            db.add(job)
        db.commit()

    assert reconcile_interrupted_jobs(session_factory) == {"jobs": 0, "crawl_jobs": 0}
    with session_factory() as db:
        rows = db.query(Job).order_by(Job.id).all()
    assert [row.status for row in rows] == list(statuses)
    assert all(row.finished_at == DONE_AT.replace(tzinfo=None) for row in rows)  # 时间不被改写


def test_crawl_job_detail_follows_only_when_non_terminal(session_factory):
    with session_factory() as db:
        record = CrawlJob(name="挖掘", status="running")
        settled = CrawlJob(name="已取消的挖掘", status="cancelled")
        db.add_all([record, settled])
        db.commit()
        db.add_all(
            [
                _job("running", ref_type="crawl_job", ref_id=record.id),
                _job("running", ref_type="crawl_job", ref_id=settled.id),
                _job("running"),  # 无 ref 的任务不误伤任何明细
            ]
        )
        db.commit()
        record_id, settled_id = record.id, settled.id

    report = reconcile_interrupted_jobs(session_factory)
    assert report == {"jobs": 3, "crawl_jobs": 1}
    with session_factory() as db:
        followed = db.get(CrawlJob, record_id)
        untouched = db.get(CrawlJob, settled_id)
    assert followed.status == "interrupted" and followed.finished_at is not None
    assert untouched.status == "cancelled" and untouched.finished_at is None


def test_idempotent_and_keeps_first_finished_at(session_factory):
    with session_factory() as db:
        db.add(_job("running"))
        db.commit()

    assert reconcile_interrupted_jobs(session_factory)["jobs"] == 1
    with session_factory() as db:
        stamp = db.query(Job).one().finished_at

    assert reconcile_interrupted_jobs(session_factory) == {"jobs": 0, "crawl_jobs": 0}
    with session_factory() as db:
        assert db.query(Job).one().finished_at == stamp


def test_create_app_runs_reconcile(engine, session_factory, data_dir):
    """装配点：应用创建即对账（四个入口都经 create_app）——重启后不再有"永远在跑"的任务。"""
    with session_factory() as db:
        db.add(_job("running"))
        db.commit()

    create_app(engine=engine, session_factory=session_factory, token="t", data_dir=data_dir)

    with session_factory() as db:
        assert db.query(Job).one().status == "interrupted"
