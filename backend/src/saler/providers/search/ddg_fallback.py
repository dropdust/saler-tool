"""DuckDuckGo HTML 兜底适配器（非官方端点）。

研究结论（research.md §7）：202/403/429 与"蜜罐页"（HTTP 200 返回诱饵内容）都必须
按失败处理，绝不当作正常结果——否则会向线索库写入脏数据。
"""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

import httpx
from selectolax.lexbor import LexborHTMLParser

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.llm.base import TestResult
from saler.providers.registry import ProviderManifest, registry
from saler.providers.search._common import DEFAULT_UA, build_client, map_http_error
from saler.providers.search.base import SearchItem

DEFAULT_BASE = "https://html.duckduckgo.com/html/"
REDIRECT_HOST = "duckduckgo.com"


class DuckDuckGoFallbackProvider:
    type_key = "ddg_html"

    def __init__(
        self,
        *,
        proxy: str | None = None,
        base_url: str = DEFAULT_BASE,
        client: httpx.Client | None = None,
        params: dict | None = None,  # 渠道级参数（装配统一注入；本适配器暂不读取）
    ) -> None:
        self._proxy = proxy
        self._base_url = base_url
        self._client = client

    def _client_for(self, timeout_s: float) -> httpx.Client:
        return self._client or build_client(timeout_s=timeout_s, proxy=self._proxy)

    @staticmethod
    def _decode_href(href: str) -> str | None:
        if not href:
            return None
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(href)
        if parsed.netloc.endswith(REDIRECT_HOST) and parsed.path.startswith("/l/"):
            uddg = parse_qs(parsed.query).get("uddg")
            return unquote(uddg[0]) if uddg else None
        if parsed.scheme in ("http", "https"):
            return href
        return None

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
        try:
            resp = client.get(
                self._base_url,
                params={"q": query},
                headers={"User-Agent": DEFAULT_UA},
            )
        except Exception as exc:  # noqa: BLE001
            raise map_http_error(exc, status=None, provider="ddg_html") from exc

        if resp.status_code in (202, 403):
            raise ProviderError(
                ErrorKind.BLOCKED, f"DDG 软封禁（HTTP {resp.status_code}）", provider="ddg_html"
            )
        if resp.status_code == 429:
            raise ProviderError(ErrorKind.RATE_LIMIT, "DDG 限流（HTTP 429）", provider="ddg_html")
        if resp.status_code >= 400:
            raise map_http_error(None, status=resp.status_code, provider="ddg_html")

        html = resp.text
        if "anomaly" in html.lower():
            raise ProviderError(ErrorKind.BLOCKED, "DDG 返回蜜罐页（anomaly）", provider="ddg_html")

        tree = LexborHTMLParser(html)
        items: list[SearchItem] = []
        for node in tree.css("a.result__a"):
            href: str = (node.attributes or {}).get("href", "")
            url = self._decode_href(href)
            if url:
                items.append(SearchItem(title=node.text(strip=True), url=url, snippet=""))
        if not items:
            raise ProviderError(
                ErrorKind.BLOCKED, "DDG 未解析到结果（疑似软封禁）", provider="ddg_html"
            )
        return items[:count]

    def test_connection(self) -> TestResult:
        try:
            self.search(query="connectivity test", count=1, timeout_s=15)
            return TestResult(ok=True, detail="连接成功")
        except ProviderError as exc:
            return TestResult(ok=False, detail=f"[{exc.kind.value}] {exc}")


MANIFEST = ProviderManifest(
    kind="search",
    type_key="ddg_html",
    display_name="DuckDuckGo（非官方兜底）",
    config_schema={"type": "object", "properties": {}},
    secret_fields=(),
    factory=DuckDuckGoFallbackProvider,
)
registry.register(MANIFEST)
