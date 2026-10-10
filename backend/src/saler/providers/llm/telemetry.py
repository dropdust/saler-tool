"""AI 调用遥测（T137）：各 provider/model 的尝试/修复/失败率记录入 operation_log。

任务层在每次 `generate_structured` 后调用 `record_from_provider`（适配器本身不依赖 DB）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from saler.db.models import OperationLog
from saler.services.operation_log import log_op


def record_from_provider(db: Session, provider, *, operation: str, ok: bool | None = None) -> dict | None:
    """读取适配器的 last_stats 并写入遥测记录；无统计（如假 provider）时跳过。"""
    stats = getattr(provider, "last_stats", None)
    if not stats:
        return None
    provider_name = getattr(provider, "provider_name", None) or getattr(provider, "type_key", "llm")
    model = getattr(provider, "model", "") or ""
    succeeded = stats.get("ok", False) if ok is None else ok
    payload = {
        "provider": provider_name,
        "model": model,
        "operation": operation,
        "attempts": stats.get("attempts", 0),
        "repair_attempts": stats.get("repair_attempts", 0),
        "ok": bool(succeeded),
        "error_kind": stats.get("error_kind"),
    }
    log_op(
        db,
        "llm",
        f"AI 调用：{provider_name}/{model} {operation} "
        f"尝试 {payload['attempts']} 次{'（含修复 ' + str(payload['repair_attempts']) + ' 次）' if payload['repair_attempts'] else ''}"
        f" → {'成功' if payload['ok'] else '失败(' + str(payload['error_kind']) + ')'}",
        payload=payload,
    )
    return payload


def snapshot(db: Session, *, days: int = 7) -> list[dict]:
    """最近 N 天的重试率快照（按 provider/model 聚合，自 operation_log 推导）。"""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = (
        db.query(OperationLog)
        .filter(OperationLog.job_type == "llm", OperationLog.ts >= cutoff)
        .all()
    )
    buckets: dict[tuple[str, str], dict] = {}
    for row in rows:
        payload = row.payload or {}
        if "attempts" not in payload:
            continue
        key = (str(payload.get("provider")), str(payload.get("model")))
        bucket = buckets.setdefault(
            key, {"provider": key[0], "model": key[1], "calls": 0, "retried_calls": 0, "failed_calls": 0}
        )
        bucket["calls"] += 1
        if payload.get("repair_attempts") or (payload.get("attempts") or 0) > 1:
            bucket["retried_calls"] += 1
        if not payload.get("ok"):
            bucket["failed_calls"] += 1
    out = []
    for bucket in buckets.values():
        bucket["retry_rate"] = round(bucket["retried_calls"] / bucket["calls"], 3) if bucket["calls"] else 0.0
        bucket["failure_rate"] = round(bucket["failed_calls"] / bucket["calls"], 3) if bucket["calls"] else 0.0
        out.append(bucket)
    return sorted(out, key=lambda item: item["calls"], reverse=True)
