"""T210 单元测试：检索渠道运行时记账（R9）——按尝试用量/健康/最近失败（测试与任务同口径）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from saler.db.models import SearchProvider
from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.search.base import SearchItem


def _mk_row(session_factory, **kwargs) -> int:
    with session_factory() as session:
        row = SearchProvider(type_key="ddg_html", name="测试渠道", **kwargs)
        session.add(row)
        session.commit()
        return row.id


def _get_row(session_factory, row_id) -> SearchProvider:
    with session_factory() as session:
        return session.get(SearchProvider, row_id)


class TestRecorder:
    def test_success_bumps_usage_and_marks_healthy(self, session_factory):
        from saler.core.leads.search_stats import SearchStatsRecorder

        row_id = _mk_row(session_factory)
        rec = SearchStatsRecorder(session_factory)
        rec.record_attempt(row_id, ok=True)
        rec.record_attempt(row_id, ok=True)
        row = _get_row(session_factory, row_id)
        assert row.used_today == 2
        assert row.health == "healthy"
        assert row.last_error_kind is None and row.last_error_at is None

    def test_failure_records_kind_then_success_clears(self, session_factory):
        from saler.core.leads.search_stats import SearchStatsRecorder

        row_id = _mk_row(session_factory)
        rec = SearchStatsRecorder(session_factory)
        rec.record_attempt(row_id, ok=False, error=ProviderError(ErrorKind.RATE_LIMIT, "429"))
        row = _get_row(session_factory, row_id)
        assert row.used_today == 1
        assert row.health == "failing"
        assert row.last_error_kind == "rate_limit"
        assert row.last_error_at is not None
        rec.record_attempt(row_id, ok=True)
        row = _get_row(session_factory, row_id)
        assert row.health == "healthy"
        assert row.last_error_kind is None and row.last_error_at is None

    def test_day_rollover_resets_counter(self, session_factory):
        from saler.core.leads.search_stats import SearchStatsRecorder

        yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
        row_id = _mk_row(session_factory, used_today=5, used_today_date=yesterday)
        SearchStatsRecorder(session_factory).record_attempt(row_id, ok=True)
        row = _get_row(session_factory, row_id)
        assert row.used_today == 1
        assert row.used_today_date == datetime.now(UTC).date().isoformat()

    def test_none_session_factory_is_noop(self):
        from saler.core.leads.search_stats import SearchStatsRecorder

        SearchStatsRecorder(None).record_attempt(999, ok=True)  # 不抛错

    def test_unknown_row_is_noop(self, session_factory):
        from saler.core.leads.search_stats import SearchStatsRecorder

        SearchStatsRecorder(session_factory).record_attempt(424242, ok=False)  # 行不存在不抛错


class _FakeAdapter:
    type_key = "fake"

    def __init__(self, *, error: Exception | None = None, items: list | None = None):
        self._error = error
        self._items = items or []

    def search(self, **kwargs):
        if self._error is not None:
            raise self._error
        return self._items

    def test_connection(self):
        return "TC"


class TestRecordingAdapter:
    def test_success_records_and_returns(self, session_factory):
        from saler.core.leads.search_stats import RecordingSearchAdapter, SearchStatsRecorder

        row_id = _mk_row(session_factory)
        items = [SearchItem(title="t", url="https://x/", snippet="")]
        adapter = RecordingSearchAdapter(
            _FakeAdapter(items=items), row_id=row_id, recorder=SearchStatsRecorder(session_factory)
        )
        assert adapter.search(query="q") == items
        assert adapter.type_key == "fake"  # 转发内部 type_key
        row = _get_row(session_factory, row_id)
        assert row.used_today == 1 and row.health == "healthy"

    def test_failure_records_and_reraises(self, session_factory):
        from saler.core.leads.search_stats import RecordingSearchAdapter, SearchStatsRecorder

        row_id = _mk_row(session_factory)
        err = ProviderError(ErrorKind.BLOCKED, "风控页")
        adapter = RecordingSearchAdapter(
            _FakeAdapter(error=err), row_id=row_id, recorder=SearchStatsRecorder(session_factory)
        )
        with pytest.raises(ProviderError):
            adapter.search(query="q")
        row = _get_row(session_factory, row_id)
        assert row.health == "failing" and row.last_error_kind == "blocked"

    def test_test_connection_delegates(self, session_factory):
        from saler.core.leads.search_stats import RecordingSearchAdapter, SearchStatsRecorder

        row_id = _mk_row(session_factory)
        adapter = RecordingSearchAdapter(
            _FakeAdapter(), row_id=row_id, recorder=SearchStatsRecorder(session_factory)
        )
        assert adapter.test_connection() == "TC"
