"""Serper.dev 适配器（Google SERP 转售；注册最简、按量便宜）。"""

from __future__ import annotations

from typing import Any

import httpx

from saler.providers.errors import ProviderError
from saler.providers.llm.base import TestResult
from saler.providers.registry import ProviderManifest, registry
from saler.providers.search._common import build_client, request_json
from saler.providers.search.base import SearchItem

DEFAULT_BASE = "https://google.serper.dev"


class SerperSearchProvider:
    type_key = "serper"

    def __init__(
        self,
        *,
        api_key: str,
        proxy: str | None = None,
        base_url: str = DEFAULT_BASE,
        client: httpx.Client | None = None,
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
        body: dict[str, Any] = {"q": query, "num": max(1, min(count, 100))}
        if country:
            body["gl"] = country.lower()
        if lang:
            body["hl"] = lang
        data = request_json(
            client,
            "POST",
            f"{self._base_url}/search",
            provider="serper",
            json=body,
            headers={"X-API-KEY": self._api_key, "Content-Type": "application/json"},
        )
        return [
            SearchItem(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
            )
            for item in (data.get("organic") or [])
            if item.get("link")
        ]

    def test_connection(self) -> TestResult:
        try:
            self.search(query="connectivity test", count=1, timeout_s=15)
            return TestResult(ok=True, detail="连接成功")
        except ProviderError as exc:
            return TestResult(ok=False, detail=f"[{exc.kind.value}] {exc}")


MANIFEST = ProviderManifest(
    kind="search",
    type_key="serper",
    display_name="Serper.dev（Google SERP）",
    config_schema={
        "type": "object",
        "properties": {"api_key": {"type": "string", "title": "API 密钥", "format": "password"}},
        "required": ["api_key"],
    },
    secret_fields=("api_key",),
    factory=SerperSearchProvider,
)
registry.register(MANIFEST)
