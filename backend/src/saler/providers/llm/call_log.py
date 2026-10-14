"""LLM 调用明细（llm_call 表）：逐次尝试的输入、原始输出、修复链、耗时与用量。

- 适配器经 `on_attempt` 回调发出逐次尝试载荷（适配器自身不依赖 DB，同 telemetry 约定）；
- 任务层用 `make_call_recorder(...)` 构造记录器：每个任务构造一次、贯穿整个任务，
  多次模型调用（如多语言循环）按 `recorder.phase` 标注上下文；
- 明细含完整 prompt/响应，按 `prune_calls` 滚动清理（维护任务启动时调用）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from saler.db.models import LlmCall

#: 明细保留策略：全量 prompt/响应体积大，默认比 operation_log 更保守
DEFAULT_KEEP_DAYS = 30
DEFAULT_KEEP_MAX = 10_000


class CallRecorder:
    """把适配器的逐次尝试载荷组装成 llm_call 行。

    - `attempt == 1` 视为一次新的模型调用（call_index 自增），修复重试归属同一 call；
    - `phase` 可在任务循环中动态改写（如 `lang:en`），落库时读取当前值。
    """

    def __init__(self, session_factory: sessionmaker[Session], *, job_id: int | None, operation: str) -> None:
        self._session_factory = session_factory
        self.job_id = job_id
        self.operation = operation
        self.phase: str | None = None
        self._call_index = 0

    def __call__(self, payload: dict) -> None:
        attempt = int(payload.get("attempt") or 1)
        if attempt == 1:
            self._call_index += 1
        row = LlmCall(
            job_id=self.job_id,
            call_index=max(self._call_index, 1),
            phase=self.phase,
            operation=self.operation,
            provider=str(payload.get("provider") or ""),
            model=str(payload.get("model") or ""),
            attempt=attempt,
            ok=bool(payload.get("ok")),
            error_kind=payload.get("error_kind"),
            error_detail=payload.get("error_detail"),
            request_messages=payload.get("messages") or [],
            response_text=payload.get("response_text"),
            latency_ms=payload.get("latency_ms"),
            usage=payload.get("usage"),
        )
        with self._session_factory() as db:
            db.add(row)
            db.commit()


def make_call_recorder(
    session_factory: sessionmaker[Session], *, job_id: int | None, operation: str
) -> CallRecorder:
    return CallRecorder(session_factory, job_id=job_id, operation=operation)


def list_calls(
    db: Session,
    *,
    job_id: int | None = None,
    operation: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[LlmCall]]:
    """按任务/操作查询明细（新→旧）。返回 (总数, 当页行)。"""
    q = db.query(LlmCall)
    if job_id is not None:
        q = q.filter(LlmCall.job_id == job_id)
    if operation:
        q = q.filter(LlmCall.operation == operation)
    total = q.count()
    rows = q.order_by(LlmCall.id.desc()).limit(limit).offset(offset).all()
    return total, rows


def prune_calls(
    db: Session,
    *,
    keep_days: int = DEFAULT_KEEP_DAYS,
    keep_max: int = DEFAULT_KEEP_MAX,
) -> int:
    """滚动清理：先按时间，再按总量上限。返回删除条数。"""
    cutoff = datetime.now(UTC) - timedelta(days=keep_days)
    removed = db.query(LlmCall).filter(LlmCall.ts < cutoff).delete()
    total = db.query(LlmCall).count()
    if total > keep_max:
        oldest_ids = [
            row[0] for row in db.query(LlmCall.id).order_by(LlmCall.id.asc()).limit(total - keep_max).all()
        ]
        if oldest_ids:
            removed += db.query(LlmCall).filter(LlmCall.id.in_(oldest_ids)).delete(synchronize_session=False)
    db.commit()
    return removed
