"""假抓取器：按 URL 映射返回页面/注入失败，并记录调用（离线挖掘测试用）。"""

from __future__ import annotations

from typing import Any

from saler.core.leads.fetcher import FetchResult


class FakeFetcher:
    def __init__(
        self,
        pages: dict[str, str],
        failures: dict[str, str] | None = None,
    ) -> None:
        self.pages = pages
        self.failures = failures or {}
        self.calls: list[str] = []

    async def fetch(self, url: str, **_kwargs: Any) -> FetchResult:
        self.calls.append(url)
        if url in self.failures:
            return FetchResult(url=url, status=0, text="", error=self.failures[url])
        page = self.pages.get(url)
        if page is None:
            return FetchResult(url=url, status=404, text="", error="http_404")
        return FetchResult(url=url, status=200, text=page, error=None)

    async def aclose(self) -> None:
        return None
