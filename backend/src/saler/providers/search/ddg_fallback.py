"""DuckDuckGo HTML 兜底适配器（非官方端点；004 R5 加固）。

研究结论（001 research §7；004 R5）：
- 202/403/429 与"蜜罐页"（HTTP 200 返回诱饵内容）都必须按失败处理，绝不当作正常结果
  ——否则会向线索库写入脏数据；
- 2025/2026 生态：无浏览器头会得到约 14KB 检测页 → 请求携带桌面浏览器 UA + `Referer`；
- `lite.duckduckgo.com/lite/` 更宽容 → html 形态判定软封禁时**回退一次**；
- 0 结果纪律（contract §4.2）：无结果链接且无"无结果"标记 → 软封禁（blocked）；
  有明确无结果标记 → 合法空结果。

保持独立实现（不复用 `html_base` 编排）：本渠道为既有兜底路径，加固面限于
UA/Referer、形态回退与空结果纪律；节流与 UA 池取值与 `html_base` 同规则。
"""

from __future__ import annotations

import random
from time import monotonic, sleep
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from selectolax.lexbor import LexborHTMLParser

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.llm.base import TestResult
from saler.providers.registry import ProviderManifest, registry
from saler.providers.search._common import build_client, map_http_error
from saler.providers.search.base import SearchItem
from saler.providers.search.html_base import BROWSER_UA_POOL, DEFAULT_INTERVAL_S

DEFAULT_BASE = "https://html.duckduckgo.com/html/"
LITE_BASE = "https://lite.duckduckgo.com/lite/"
REFERER = "https://duckduckgo.com/"
REDIRECT_HOST = "duckduckgo.com"
LEGAL_EMPTY_MARKERS = ("no results", "没有找到")


class DuckDuckGoFallbackProvider:
    type_key = "ddg_html"

    def __init__(
        self,
        *,
        proxy: str | None = None,
        base_url: str = DEFAULT_BASE,
        client: httpx.Client | None = None,
        params: dict | None = None,  # 渠道级参数（interval_s；装配统一注入）
    ) -> None:
        self._proxy = proxy
        self._base_url = base_url
        self._client = client
        self._params = dict(params or {})
        try:
            self._interval_s = float(self._params.get("interval_s", DEFAULT_INTERVAL_S))
        except (TypeError, ValueError):
            self._interval_s = DEFAULT_INTERVAL_S
        self._last_request_at: float | None = None

    def _client_for(self, timeout_s: float) -> httpx.Client:
        return self._client or build_client(timeout_s=timeout_s, proxy=self._proxy)

    def _headers(self) -> dict[str, str]:
        # 浏览器头（2025/2026 生态：无浏览器头会得到检测页而非结果）
        return {
            "User-Agent": random.choice(BROWSER_UA_POOL),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": REFERER,
        }

    def _throttle(self) -> None:
        """引擎实例级最小间隔（与 html_base 同规则）；interval_s<=0 显式关闭。"""
        if self._interval_s <= 0:
            return
        now = monotonic()
        if self._last_request_at is not None:
            wait = self._interval_s + random.uniform(0, 1.5) - (now - self._last_request_at)
            if wait > 0:
                sleep(wait)
        self._last_request_at = monotonic()

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
        """html 形态优先；判定软封禁时 lite 形态回退一次；仍有错则抛首个错误。"""
        client = self._client_for(timeout_s)
        errors: list[ProviderError] = []
        for base_url, link_selector, snippet_selector in (
            (self._base_url, "a.result__a", ".result__snippet"),
            (LITE_BASE, "a.result-link", ".result-snippet"),
        ):
            try:
                return self._fetch(client, base_url, query, link_selector, snippet_selector, count, timeout_s)
            except ProviderError as exc:
                errors.append(exc)
        raise errors[0]

    def _fetch(
        self,
        client: httpx.Client,
        base_url: str,
        query: str,
        link_selector: str,
        snippet_selector: str,
        count: int,
        timeout_s: float,
    ) -> list[SearchItem]:
        self._throttle()
        try:
            resp = client.get(
                base_url, params={"q": query}, headers=self._headers(), timeout=timeout_s
            )
        except Exception as exc:  # noqa: BLE001 - 统一映射为 ProviderError
            raise map_http_error(exc, status=None, provider=self.type_key) from exc

        if resp.status_code in (202, 403):
            raise ProviderError(
                ErrorKind.BLOCKED, f"DDG 软封禁（HTTP {resp.status_code}）", provider=self.type_key
            )
        if resp.status_code == 429:
            raise ProviderError(ErrorKind.RATE_LIMIT, "DDG 限流（HTTP 429）", provider=self.type_key)
        if resp.status_code >= 400:
            raise map_http_error(None, status=resp.status_code, provider=self.type_key)

        html = resp.text
        if "anomaly" in html.lower():
            raise ProviderError(ErrorKind.BLOCKED, "DDG 返回蜜罐页（anomaly）", provider=self.type_key)

        items = self._parse(html, link_selector, snippet_selector)
        if items:
            return items[:count]
        if any(marker in html.lower() for marker in LEGAL_EMPTY_MARKERS):
            return []  # 明确的"无结果"页 → 合法空（contract §4.2）
        raise ProviderError(
            ErrorKind.BLOCKED, "DDG 未解析到结果（疑似软封禁/检测页）", provider=self.type_key
        )

    def _parse(self, html: str, link_selector: str, snippet_selector: str) -> list[SearchItem]:
        tree = LexborHTMLParser(html)
        links = tree.css(link_selector)
        snippets = tree.css(snippet_selector)
        items: list[SearchItem] = []
        for index, node in enumerate(links):
            href: str = (node.attributes or {}).get("href", "")
            url = self._decode_href(href)
            if not url:
                continue
            snippet = snippets[index].text(strip=True) if index < len(snippets) else ""
            items.append(SearchItem(title=node.text(strip=True), url=url, snippet=snippet))
        return items

    def test_connection(self) -> TestResult:
        try:
            self.search(query="connectivity test", count=1, timeout_s=15)
            return TestResult(ok=True, detail="连接成功")
        except ProviderError as exc:
            return TestResult(ok=False, detail=f"[{exc.kind.value}] {exc}", kind=exc.kind.value)


MANIFEST = ProviderManifest(
    kind="search",
    type_key="ddg_html",
    display_name="DuckDuckGo（非官方兜底）",
    config_schema={"type": "object", "properties": {}},
    secret_fields=(),
    factory=DuckDuckGoFallbackProvider,
    preset={
        "endpoint": DEFAULT_BASE,
        "note": "免密钥（非官方端点）；软封禁风险高，仅作最后兜底；lite 形态自动回退一次",
        "apply_url": None,
        "access_mode": "html",
        "market": "隐私场景 / 最后兜底",
        "risk": "非官方接入：202/403/蜜罐页常见，绝不写脏数据；合规责任自担",
    },
)
registry.register(MANIFEST)
