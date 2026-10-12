"""检索渠道运行时记账（004 R9）：按尝试记录用量/健康/最近失败——测试与任务同口径。

- **providers 层零 DB 依赖**：本模块位于 core/leads，以 `RecordingSearchAdapter` 按
  `SearchProvider` Protocol 代理包装真实适配器（`SearchFailover` 零改动）；
- `SearchStatsRecorder` 以 session_factory 开短事务写回 `search_provider` 行；
- `used_today` 按日重置累加（对齐 `core/sending/channel_service` 语义）；
- 成功：`health=healthy` 且清空 `last_error_kind/at`；失败：`health=failing` 并记 kind/at。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from saler.db.models import SearchProvider
from saler.providers.errors import ProviderError
from saler.providers.llm.base import TestResult
from saler.providers.search.base import SearchItem


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def apply_attempt(row: SearchProvider, *, ok: bool, error_kind: str | None = None) -> None:
    """在既有行对象上应用一次尝试（调用方负责 commit；路由测试端点同口径复用）。"""
    if row.used_today_date != _today():
        row.used_today = 0
        row.used_today_date = _today()
    row.used_today = (row.used_today or 0) + 1
    if ok:
        row.health = "healthy"
        row.last_error_kind = None
        row.last_error_at = None
    else:
        row.health = "failing"
        row.last_error_kind = error_kind
        row.last_error_at = datetime.now(UTC)


class SearchStatsRecorder:
    """以 session_factory 开短事务将尝试写回行；session_factory=None → no-op（测试友好）。"""

    def __init__(self, session_factory: Callable[[], Any] | None) -> None:
        self._session_factory = session_factory

    def record_attempt(self, row_id: int, *, ok: bool, error: ProviderError | None = None) -> None:
        if self._session_factory is None:
            return
        with self._session_factory() as session:
            row = session.get(SearchProvider, row_id)
            if row is None:
                return
            apply_attempt(row, ok=ok, error_kind=error.kind.value if error is not None else None)
            session.commit()


class RecordingSearchAdapter:
    """代理包装：转发 `search`/`test_connection` 并按尝试记账（实现 SearchProvider Protocol）。"""

    def __init__(self, inner: Any, *, row_id: int, recorder: SearchStatsRecorder) -> None:
        self._inner = inner
        self._row_id = row_id
        self._recorder = recorder
        self.type_key = getattr(inner, "type_key", "?")

    def search(self, **kwargs: Any) -> list[SearchItem]:
        try:
            items = self._inner.search(**kwargs)
        except ProviderError as exc:
            self._recorder.record_attempt(self._row_id, ok=False, error=exc)
            raise
        self._recorder.record_attempt(self._row_id, ok=True)
        return items

    def test_connection(self) -> TestResult:
        # 渠道"测试"按钮走路由端点（同口径在路由层写入）；此处仅转发
        return self._inner.test_connection()
