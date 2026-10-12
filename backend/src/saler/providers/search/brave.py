"""Brave Search 适配器（首批检索渠道）。"""

from __future__ import annotations

from typing import Any

import httpx

from saler.providers.errors import ProviderError
from saler.providers.llm.base import TestResult
from saler.providers.registry import ProviderManifest, registry
from saler.providers.search._common import build_client, request_json
from saler.providers.search.base import SearchItem

DEFAULT_BASE = "https://api.search.brave.com/res/v1"


class BraveSearchProvider:
    type_key = "brave"

    def __init__(
        self,
        *,
        api_key: str,
        proxy: str | None = None,
        base_url: str = DEFAULT_BASE,
        client: httpx.Client | None = None,
        params: dict | None = None,  # 渠道级参数（装配统一注入；本适配器暂不读取）
    ) -> None:
        self._api_key = api_key
        self._proxy = proxy
        self._base_url = base_url.rstrip("/")
        self._client = client

    def _client_for(self, timeout_s: float) -> httpx.Client:
        return self._client or build_client(timeout_s=timeout_s, proxy=self._proxy)

    def search(
        self,
        *,
        query: str,
        count: int = 20,
        lang: str | None = None,
        country: str | None = None,
        timeout_s: float = 30,
    ) -> list[SearchItem]:
        client = self._client_for(timeout_s)
        params: dict[str, Any] = {"q": query, "count": max(1, min(count, 20))}
        if country:
            params["country"] = country.lower()
        if lang:
            params["search_lang"] = lang
        data = request_json(
            client,
            "GET",
            f"{self._base_url}/web/search",
            provider="brave",
            params=params,
            headers={"X-Subscription-Token": self._api_key, "Accept": "application/json"},
        )
        results = ((data.get("web") or {}).get("results")) or []
        return [
            SearchItem(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", ""),
            )
            for item in results
            if item.get("url")
        ]

    def test_connection(self) -> TestResult:
        try:
            self.search(query="connectivity test", count=1, timeout_s=15)
            return TestResult(ok=True, detail="连接成功")
        except ProviderError as exc:
            return TestResult(ok=False, detail=f"[{exc.kind.value}] {exc}")


MANIFEST = ProviderManifest(
    kind="search",
    type_key="brave",
    display_name="Brave Search",
    config_schema={
        "type": "object",
        "properties": {"api_key": {"type": "string", "title": "API 密钥", "format": "password"}},
        "required": ["api_key"],
    },
    secret_fields=("api_key",),
    factory=BraveSearchProvider,
)
registry.register(MANIFEST)
