"""启动对账：进程退出遗留的非终态任务 → `interrupted`（005-T246 / FR-017）。

- 语义：`interrupted` 区别于 `failed`（运行出错）与 `cancelled`（用户操作）——它只由本模块写入；
- 只改状态、绝不重放：对外调用（检索/抓取/发送/模型）不因对账自动重发，重跑一律用户点击触发；
- 幂等：非终态集合（queued/running/paused）一次收口后再次执行为空操作，且不重写首次的
  `finished_at`；终态一律不动（防"退出瞬间恰逢完成"被误标）；
- 挖掘任务联动其领域明细 `crawl_job`（`job.ref_type='crawl_job'`），保证台账与明细全周期一致。
"""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.orm import Session, sessionmaker

from saler.db.models import CrawlJob, Job
from saler.jobs.engine import JOB_STATUSES, TERMINAL_STATUSES

#: 非终态集合由 engine 的单一事实源派生（新增状态时不必改这里）
NON_TERMINAL_STATUSES = tuple(status for status in JOB_STATUSES if status not in TERMINAL_STATUSES)


def reconcile_interrupted_jobs(session_factory: sessionmaker[Session]) -> dict:
    """把进程退出遗留的非终态任务与对应挖掘明细收口为 `interrupted`（幂等）。

    返回 `{"jobs": 收口任务数, "crawl_jobs": 联动明细数}`；应用启动时调用一次（create_app）。
    """
    now = datetime.now(UTC)
    with session_factory() as db:
        rows = db.query(Job).filter(Job.status.in_(NON_TERMINAL_STATUSES)).all()
        crawl_job_ids: list[int] = []
        for job in rows:
            job.status = "interrupted"
            job.finished_at = now
            if job.ref_type == "crawl_job" and job.ref_id is not None:
                crawl_job_ids.append(job.ref_id)
        crawl_jobs = 0
        if crawl_job_ids:  # 只收口仍未终态的明细；终态明细（如用户已取消）不动
            crawl_jobs = (
                db.query(CrawlJob)
                .filter(CrawlJob.id.in_(crawl_job_ids), CrawlJob.status.in_(NON_TERMINAL_STATUSES))
                .update({"status": "interrupted", "finished_at": now}, synchronize_session=False)
            )
        db.commit()
    report = {"jobs": len(rows), "crawl_jobs": crawl_jobs}
    if report["jobs"] or report["crawl_jobs"]:
        logger.info(f"启动对账：收口 {report['jobs']} 个中断任务、{report['crawl_jobs']} 条挖掘明细")
    return report
