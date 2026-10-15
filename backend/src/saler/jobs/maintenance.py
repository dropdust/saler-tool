"""维护任务（T136）：操作日志滚动清理 + LLM 调用明细清理 + 备份提醒。

在应用启动时调用（桌面壳 `_build_app`）；无后台调度器，避免常驻负担。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy.orm import Session

from saler.db.models import BackupRecord
from saler.providers.llm import call_log
from saler.services.operation_log import log_op, prune_logs

BACKUP_REMIND_DAYS = 7


def backup_due(db: Session, *, days: int = BACKUP_REMIND_DAYS) -> bool:
    """最近一次备份距今超过 days 天（或从未备份）→ 需要提醒。"""
    latest = db.query(BackupRecord).order_by(BackupRecord.created_at.desc()).first()
    if latest is None or latest.created_at is None:
        return True
    created = latest.created_at
    if created.tzinfo is None:  # SQLite 存朴素 UTC
        created = created.replace(tzinfo=UTC)
    return datetime.now(UTC) - created > timedelta(days=days)


def run_maintenance(
    db: Session, *, keep_days: int = 30, keep_max: int = 500_000, remind_days: int = BACKUP_REMIND_DAYS
) -> dict:
    removed = prune_logs(db, keep_days=keep_days, keep_max=keep_max)
    if removed:
        logger.info(f"维护：清理操作日志 {removed} 条")
    calls_removed = call_log.prune_calls(db, keep_days=keep_days)
    if calls_removed:
        logger.info(f"维护：清理 LLM 调用明细 {calls_removed} 条")
    # 启动对账：上次进程退出遗留的"进行中"行收口（此时不可能有真实进行中的调用）
    stale_closed = call_log.close_stale_calls(db)
    if stale_closed:
        logger.info(f"维护：收口上次退出遗留的进行中调用 {stale_closed} 条")
    due = backup_due(db, days=remind_days)
    if due:
        log_op(
            db,
            "system",
            f"备份提醒：超过 {remind_days} 天未备份（或从未备份），建议在「设置 → 备份与数据」生成归档",
            level="warn",
        )
    return {
        "logs_removed": removed,
        "llm_calls_removed": calls_removed,
        "llm_calls_closed": stale_closed,
        "backup_due": due,
    }
