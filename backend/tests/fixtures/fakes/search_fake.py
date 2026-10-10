"""假检索 Provider：按查询词返回预置结果。"""

from __future__ import annotations

from saler.providers.llm.base import TestResult
from saler.providers.search.base import SearchItem


class FakeSearchProvider:
    type_key = "fake"

    def __init__(self, results_by_query: dict[str, list[dict]] | None = None) -> None:
        self.results_by_query = results_by_query or {}
        self.calls: list[str] = []
        self.fail_next: Exception | None = None

    def search(
        self,
        *,
        query: str,
        count: int = 20,
        lang: str | None = None,
        country: str | None = None,
        timeout_s: float = 30,
    ) -> list[SearchItem]:
        self.calls.append(query)
        if self.fail_next is not None:
            exc, self.fail_next = self.fail_next, None
            raise exc
        rows = self.results_by_query.get(query, self.results_by_query.get("*", []))
        return [
            SearchItem(
                title=row.get("title", ""), url=row["url"], snippet=row.get("snippet", "")
            )
            for row in rows[:count]
        ]

    def test_connection(self) -> TestResult:
        return TestResult(ok=True, detail="fake search ok")
