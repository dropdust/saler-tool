"""LLM 调用明细（llm_call 表）：逐次尝试的输入、原始输出、修复链、耗时与用量。

- 适配器经 `on_attempt` 回调发出逐次尝试载荷（适配器自身不依赖 DB，同 telemetry 约定）；
- `event="start"` 先落一行"进行中"（ok=NULL）：请求已发出即可见，卡住时据此判断阻塞在哪一步；
  `event="finish"` 原位收口（成功/失败/超时），不新增行；缺省 event 视为 finish；
- 任务层用 `make_call_recorder(...)` 构造记录器：每个任务构造一次、贯穿整个任务，
  多次模型调用（如多语言循环）按 `recorder.phase` 标注上下文；
- 明细含完整 prompt/响应，按 `prune_calls` 滚动清理（维护任务启动时调用）；
  进程退出遗留的"进行中"行由 `close_stale_calls` 在启动对账时收口。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from saler.db.models import LlmCall

#: 明细保留策略：全量 prompt/响应体积大，默认比 operation_log 更保守
DEFAULT_KEEP_DAYS = 30
DEFAULT_KEEP_MAX = 10_000

#: 应用退出遗留行的收口说明（`close_stale_calls`）
STALE_DETAIL = "调用未完成（应用退出中断），无结果记录"


class CallRecorder:
    """把适配器的逐次尝试载荷组装成 llm_call 行。

    - `attempt == 1` 视为一次新的模型调用（call_index 自增），修复重试归属同一 call；
    - `start` 落"进行中"行（ok=None）并记住行号，`finish` 按 (call_index, attempt) 原位更新；
    - `phase` 可在任务循环中动态改写（如 `lang:en`），落库时读取当前值。
    """

    def __init__(self, session_factory: sessionmaker[Session], *, job_id: int | None, operation: str) -> None:
        self._session_factory = session_factory
        self.job_id = job_id
        self.operation = operation
        self.phase: str | None = None
        self._call_index = 0
        self._rows: dict[tuple[int, int], int] = {}  # (call_index, attempt) → 进行中行 id

    def __call__(self, payload: dict) -> None:
        if (payload.get("event") or "finish") == "start":
            self._start(payload)
        else:
            self._finish(payload)

    # ---- 事件 ----
    def _start(self, payload: dict) -> None:
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
            ok=None,  # 进行中：结果未知
            request_messages=payload.get("messages") or [],
        )
        with self._session_factory() as db:
            db.add(row)
            db.commit()
            self._rows[(row.call_index, attempt)] = row.id

    def _finish(self, payload: dict) -> None:
        attempt = int(payload.get("attempt") or 1)
        row_id = self._rows.pop((self._call_index, attempt), None)
        with self._session_factory() as db:
            row = db.get(LlmCall, row_id) if row_id is not None else None
            if row is None:  # 无对应 start（旧实现/脚本化替身只发 finish）→ 沿用旧口径补一行完整记录
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
                    request_messages=payload.get("messages") or [],
                )
                db.add(row)
            row.ok = bool(payload.get("ok"))
            row.error_kind = payload.get("error_kind")
            row.error_detail = payload.get("error_detail")
            row.response_text = payload.get("response_text")
            row.latency_ms = payload.get("latency_ms")
            row.usage = payload.get("usage")
            db.commit()


def close_stale_calls(db: Session) -> int:
    """启动对账：把上次进程遗留的"进行中"行（ok IS NULL）收口为失败并留痕。

    仅在启动时调用（此时不可能有真实进行中的调用）——避免明细里留下永久"进行中"的幽灵行。
    """
    rows = db.query(LlmCall).filter(LlmCall.ok.is_(None)).all()
    for row in rows:
        row.ok = False
        row.error_detail = STALE_DETAIL
    db.commit()
    return len(rows)


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
