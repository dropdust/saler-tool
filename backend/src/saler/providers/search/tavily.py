"""Tavily 适配器（AI 检索优化；月度免费额度）。"""

from __future__ import annotations

from typing import Any

import httpx

from saler.providers.errors import ProviderError
from saler.providers.llm.base import TestResult
from saler.providers.registry import ProviderManifest, registry
from saler.providers.search._common import build_client, request_json
from saler.providers.search.base import SearchItem

DEFAULT_BASE = "https://api.tavily.com"


class TavilySearchProvider:
    type_key = "tavily"

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
        body: dict[str, Any] = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max(1, min(count, 20)),
        }
        data = request_json(
            client,
            "POST",
            f"{self._base_url}/search",
            provider="tavily",
            json=body,
            headers={"Content-Type": "application/json"},
        )
        return [
            SearchItem(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
            )
            for item in (data.get("results") or [])
            if item.get("url")
        ]

    def test_connection(self) -> TestResult:
        try:
            self.search(query="connectivity test", count=1, timeout_s=15)
            return TestResult(ok=True, detail="连接成功")
        except ProviderError as exc:
            return TestResult(ok=False, detail=f"[{exc.kind.value}] {exc}", kind=exc.kind.value)


MANIFEST = ProviderManifest(
    kind="search",
    type_key="tavily",
    display_name="Tavily（AI 检索）",
    config_schema={
        "type": "object",
        "properties": {"api_key": {"type": "string", "title": "API 密钥", "format": "password"}},
        "required": ["api_key"],
    },
    secret_fields=("api_key",),
    factory=TavilySearchProvider,
    preset={
        "endpoint": DEFAULT_BASE,
        "note": "1,000 信用/月自动续（免绑卡）；面向 AI 检索优化",
        "apply_url": "https://app.tavily.com",
        "access_mode": "official_api",
        "market": "全球（AI 检索优化）",
        "risk": "月度信用用尽即停；密钥前缀 tvly-，用后请勿泄露",
    },
)
registry.register(MANIFEST)
