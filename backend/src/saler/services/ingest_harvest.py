"""外部收割结果回灌（contracts/data-exchange.md §2；FR-016）。

支持 harvest_v1 JSONL（每行一条查询结果）与 csv（query,url,title,snippet）。
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from saler.core.errors import ValidationFailed
from saler.core.leads import domain_service
from saler.core.seeds.yield_stats import recompute_seed_yield
from saler.db.models import DomainSeedHit, Seed
from saler.jobs.engine import JobContext
from saler.services.operation_log import log_op

MAX_UNMATCHED_REPORTED = 100


def ingest_harvest_text(db: Session, text: str, *, job_id: int | None = None) -> dict:
    report: dict = {
        "matched": 0,
        "unmatched_queries": [],
        "new_domains": 0,
        "dup_domains": 0,
        "errors": [],
    }
    affected_seeds: set[int] = set()
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            entries = _parse_line(line, first_content_line=(report["matched"] == 0 and line_no <= 1))
        except Exception as exc:  # noqa: BLE001
            report["errors"].append({"line": line_no, "error": f"{type(exc).__name__}: {exc}"})
            continue
        for seed_query, results in entries:
            seed = db.query(Seed).filter_by(query=(seed_query or "").strip()).first()
            if seed is None:
                if len(report["unmatched_queries"]) < MAX_UNMATCHED_REPORTED:
                    report["unmatched_queries"].append(seed_query)
                continue
            report["matched"] += 1
            for item in results:
                url = (item or {}).get("url") or ""
                normalized = domain_service.normalize_domain(url)
                if normalized is None:
                    continue
                domain_row, created = domain_service.get_or_create_domain(
                    db,
                    domain=normalized,
                    homepage_url=url,
                    title=(item or {}).get("title"),
                    snippet=(item or {}).get("snippet"),
                    source="harvest",
                    job_id=job_id,
                )
                if created:
                    report["new_domains"] += 1
                else:
                    report["dup_domains"] += 1
                exists = (
                    db.query(DomainSeedHit)
                    .filter_by(domain_id=domain_row.id, seed_id=seed.id)
                    .first()
                )
                if exists is None:
                    db.add(DomainSeedHit(domain_id=domain_row.id, seed_id=seed.id, job_id=job_id))
                    db.commit()
            seed.status = "done"
            seed.last_run_at = datetime.now(UTC)
            db.commit()
            affected_seeds.add(seed.id)
    if affected_seeds:
        recompute_seed_yield(db, sorted(affected_seeds))
    return report


def _parse_line(line: str, *, first_content_line: bool) -> list[tuple[str, list[dict]]]:
    """返回 [(seed_query, results)]；csv 解析失败时向上抛给调用方记账。"""
    if line.startswith("{"):
        obj = json.loads(line)
        return [(obj.get("seed_query"), list(obj.get("results") or []))]
    reader = csv.reader([line])
    row = next(reader)
    if first_content_line and row and row[0].strip().lower() == "query":
        return []  # csv 表头
    if len(row) < 2:
        raise ValueError("csv 列数不足（需要 query,url[,title,snippet]）")
    result = {
        "url": row[1],
        "title": row[2] if len(row) > 2 else "",
        "snippet": row[3] if len(row) > 3 else "",
    }
    return [(row[0], [result])]


async def run_ingest(
    ctx: JobContext,
    session_factory: sessionmaker[Session],
    *,
    payload: dict,
) -> dict:
    content = payload.get("content")
    path = payload.get("path")
    if not content and not path:
        raise ValidationFailed("需要提供 content 或 path")
    if not content:
        ctx.log(f"读取回灌文件：{path}")
        content = Path(path).read_text(encoding="utf-8")
    if not (content or "").strip():
        raise ValidationFailed("回灌内容为空")
    ctx.progress(phase="parsing")
    with session_factory() as db:
        report = ingest_harvest_text(db, content, job_id=ctx.job_id)
        log_op(
            db,
            "ingest",
            f"回灌完成：匹配 {report['matched']} 个查询，新增域名 {report['new_domains']}，"
            f"未匹配 {len(report['unmatched_queries'])}",
            ref_type="job",
            ref_id=ctx.job_id,
            payload={k: v for k, v in report.items() if k != "unmatched_queries"},
        )
    ctx.progress(phase="done", **{k: v for k, v in report.items() if k != "unmatched_queries"})
    return report
