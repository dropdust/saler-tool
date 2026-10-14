"""清理一次挖掘任务的检索链路产出（整批回退到任务前状态）。

场景：检索渠道返回"幌子结果"等污染（2026-10-14 事故：Bing 风控替换页把酒店/字典站
当成工业查询的检索结果入库）后，该任务产出的域名不可信，需要整批回退。

- **删除**：`domain.first_job_id = job_id` 的候选域名；`domain_seed_hit.job_id = job_id`
  的全部命中（含命中"预先存在域名"的假归因）；这些域名下的联系人；
  仅由这些域名撑起的公司（仍持有其他域名/联系人的公司保留；被发送台账引用的不删）。
- **复位**：任务时间窗内被置为 done 的种子 → pending（修复渠道后可重新执行），重算产量。
- **保留**：任务台账（job/crawl_job/operation_log）；"预先存在域名"被直接抓取得到的
  联系人与抓取状态（抓取不经过检索，不受幌子影响）。
- 默认干跑（apply=False）只统计不动数据。

用法：
    uv run python -m saler.services.purge_crawl_results --job-id 5          # 干跑
    uv run python -m saler.services.purge_crawl_results --job-id 5 --apply  # 执行
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import delete, func, update
from sqlalchemy.orm import Session

from saler.core.errors import ValidationFailed
from saler.core.seeds.yield_stats import recompute_seed_yield
from saler.db.models import (
    Company,
    Contact,
    Domain,
    DomainSeedHit,
    Job,
    Seed,
    SendRecord,
    Suppression,
)
from saler.jobs.engine import TERMINAL_STATUSES
from saler.services.operation_log import log_op


def purge_crawl_results(db: Session, *, job_id: int, apply: bool = False) -> dict:
    """统计（干跑）或执行清理；返回报告。"""
    job = db.get(Job, job_id)
    if job is None:
        raise ValidationFailed(f"任务不存在：#{job_id}")
    if job.status not in TERMINAL_STATUSES:
        raise ValidationFailed(f"任务 #{job_id} 仍在运行（{job.status}），拒绝清理")

    domain_ids = [
        row[0] for row in db.query(Domain.id).filter(Domain.first_job_id == job_id).all()
    ]
    hit_count = (
        db.query(func.count(DomainSeedHit.id)).filter(DomainSeedHit.job_id == job_id).scalar() or 0
    )
    hit_seed_ids = [
        row[0]
        for row in db.query(DomainSeedHit.seed_id)
        .filter(DomainSeedHit.job_id == job_id)
        .distinct()
        .all()
    ]

    contact_ids = [
        row[0] for row in db.query(Contact.id).filter(Contact.domain_id.in_(domain_ids)).all()
    ]
    protected_contact_ids = {
        row[0]
        for row in db.query(SendRecord.contact_id)
        .filter(SendRecord.contact_id.in_(contact_ids))
        .distinct()
        .all()
    } | {
        row[0]
        for row in db.query(Suppression.contact_id)
        .filter(Suppression.contact_id.in_(contact_ids))
        .distinct()
        .all()
    }
    contact_ids = [cid for cid in contact_ids if cid not in protected_contact_ids]

    # 被保护联系人（发送台账/黑名单引用）所属域名一并保留：联系人 provenance 不能悬空
    protected_domain_ids = {
        row[0]
        for row in db.query(Contact.domain_id)
        .filter(Contact.id.in_(protected_contact_ids), Contact.domain_id.is_not(None))
        .distinct()
        .all()
    }
    deleted_domain_ids = [did for did in domain_ids if did not in protected_domain_ids]

    company_ids = [
        row[0]
        for row in db.query(Domain.company_id)
        .filter(Domain.first_job_id == job_id, Domain.company_id.is_not(None))
        .distinct()
        .all()
    ]
    protected_company_ids = {
        row[0]
        for row in db.query(SendRecord.company_id)
        .filter(SendRecord.company_id.in_(company_ids))
        .distinct()
        .all()
    } | {
        row[0]
        for row in db.query(Suppression.company_id)
        .filter(Suppression.company_id.in_(company_ids))
        .distinct()
        .all()
    }
    kept_company_ids: set[int] = set(protected_company_ids)
    for company_id in company_ids:
        if company_id in protected_company_ids:
            continue
        has_remaining_domain = (
            db.query(Domain.id)
            .filter(Domain.company_id == company_id, ~Domain.id.in_(deleted_domain_ids))
            .first()
            is not None
        )
        has_remaining_contact = (
            db.query(Contact.id)
            .filter(Contact.company_id == company_id, ~Contact.id.in_(contact_ids))
            .first()
            is not None
        )
        if has_remaining_domain or has_remaining_contact:
            kept_company_ids.add(company_id)
    deletable_company_ids = [cid for cid in company_ids if cid not in kept_company_ids]

    window_start = job.started_at or job.created_at
    window_end = job.finished_at or job.created_at
    seed_ids_to_reset = [
        row[0]
        for row in db.query(Seed.id)
        .filter(Seed.status == "done", Seed.last_run_at >= window_start, Seed.last_run_at <= window_end)
        .all()
    ]

    report = {
        "job_id": job_id,
        "applied": apply,
        "domains": len(deleted_domain_ids),
        "domains_protected": len(protected_domain_ids),
        "seed_hits": int(hit_count),
        "contacts": len(contact_ids),
        "contacts_protected": len(protected_contact_ids),
        "companies": len(deletable_company_ids),
        "companies_kept": len(kept_company_ids),
        "seeds_reset": len(seed_ids_to_reset),
    }

    if not apply:
        return report

    if contact_ids:
        db.execute(delete(Contact).where(Contact.id.in_(contact_ids)))
    db.execute(delete(DomainSeedHit).where(DomainSeedHit.job_id == job_id))
    if deleted_domain_ids:
        db.execute(delete(Domain).where(Domain.id.in_(deleted_domain_ids)))
    if deletable_company_ids:
        db.execute(delete(Company).where(Company.id.in_(deletable_company_ids)))
    if seed_ids_to_reset:
        db.execute(
            update(Seed)
            .where(Seed.id.in_(seed_ids_to_reset))
            .values(status="pending", last_run_at=None)
        )
    db.flush()
    recompute_seed_yield(db, sorted(set(seed_ids_to_reset) | set(hit_seed_ids)))
    log_op(
        db,
        "system",
        f"清理任务 #{job_id} 的检索产出：域名 {report['domains']}、命中 {report['seed_hits']}、"
        f"联系人 {report['contacts']}、公司 {report['companies']}、复位种子 {report['seeds_reset']}",
        ref_type="job",
        ref_id=job_id,
        level="warn",
        payload=report,
    )
    db.commit()
    return report


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="清理一次挖掘任务的检索链路产出（默认干跑，--apply 才执行）"
    )
    parser.add_argument("--job-id", type=int, required=True, help="通用任务台账 id（domain.first_job_id）")
    parser.add_argument("--apply", action="store_true", help="真正执行（默认只统计）")
    parser.add_argument("--data-dir", default=None, help="数据目录（默认 SALER_DATA_DIR/平台目录）")
    args = parser.parse_args(argv)

    from sqlalchemy import create_engine

    from saler.db.session import apply_sqlite_pragmas
    from saler.services.datadir import db_path, resolve_data_dir

    data_dir = Path(args.data_dir) if args.data_dir else resolve_data_dir()
    path = db_path(data_dir)
    if not path.exists():
        print(f"数据库不存在：{path}", file=sys.stderr)
        return 2
    engine = create_engine(
        f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 30}
    )
    apply_sqlite_pragmas(engine)
    with Session(engine) as db:
        report = purge_crawl_results(db, job_id=args.job_id, apply=args.apply)
    print(f"数据目录：{data_dir}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.apply:
        print("（干跑完成；加 --apply 执行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
