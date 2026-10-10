"""操作日志（FR-026）：写入（自动脱敏）/ 查询 / 容量滚动清理。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from saler.db.models import OperationLog
from saler.security.redact import redact

DEFAULT_KEEP_DAYS = 30
DEFAULT_KEEP_MAX = 500_000


def log_op(
    db: Session,
    job_type: str,
    message: str,
    *,
    ref_type: str | None = None,
    ref_id: int | None = None,
    level: str = "info",
    payload: dict[str, Any] | None = None,
) -> OperationLog:
    entry = OperationLog(
        job_type=job_type,
        message=message,
        level=level,
        ref_type=ref_type,
        ref_id=ref_id,
        payload=redact(payload) if payload is not None else None,
    )
    db.add(entry)
    db.commit()
    return entry


def query_logs(
    db: Session,
    *,
    ref_type: str | None = None,
    ref_id: int | None = None,
    level: str | None = None,
    job_type: str | None = None,
    limit: int = 200,
) -> list[OperationLog]:
    q = db.query(OperationLog).order_by(OperationLog.ts.desc())
    if ref_type is not None:
        q = q.filter(OperationLog.ref_type == ref_type)
    if ref_id is not None:
        q = q.filter(OperationLog.ref_id == ref_id)
    if level:
        q = q.filter(OperationLog.level == level)
    if job_type:
        q = q.filter(OperationLog.job_type == job_type)
    return q.limit(limit).all()


def prune_logs(
    db: Session,
    *,
    keep_days: int = DEFAULT_KEEP_DAYS,
    keep_max: int = DEFAULT_KEEP_MAX,
) -> int:
    """滚动清理：先按时间，再按总量上限。返回删除条数。"""
    cutoff = datetime.now(UTC) - timedelta(days=keep_days)
    removed = db.query(OperationLog).filter(OperationLog.ts < cutoff).delete()
    total = db.query(OperationLog).count()
    if total > keep_max:
        oldest_ids = [
            row[0]
            for row in db.query(OperationLog.id)
            .order_by(OperationLog.ts.asc())
            .limit(total - keep_max)
            .all()
        ]
        if oldest_ids:
            removed += (
                db.query(OperationLog)
                .filter(OperationLog.id.in_(oldest_ids))
                .delete(synchronize_session=False)
            )
    db.commit()
    return removed
