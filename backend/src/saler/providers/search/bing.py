"""Bing 网页解析渠道（RSS 形态优先 + HTML 形态回退；004 R4）。

- **RSS 形态**：`?q=&format=rss&mkt=en-US&setlang=en`——免反爬标记、链接为直链；
  约 10 条上限、无分页、偶发空 XML（引号查询易失效）→ **空结果转 HTML 复核**，
  不直接判合法空（contract §4.2）。
- **HTML 形态**：`?q=&count=&mkt=en-US&cc=US&ensearch=1` + `Cookie: ENSEARCH=BENVER=1`；
  `li.b_algo` 解析；`ck/a` 的 `u=a1<base64url>` 离线还原（`&amp;` 先反转义）。
- **风控**：静默 captcha（HTTP 200 + `class="captcha"` + 0 结果）/"One last step" 插页 → blocked；
  落地 cn.bing.com → 经 www4.bing.com 重试一次，仍被地理重定向 → blocked（提示检查代理出口）。
"""

from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
from html import unescape
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlsplit

import httpx
from selectolax.lexbor import LexborHTMLParser

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.registry import ProviderManifest, registry
from saler.providers.search.base import SearchItem
from saler.providers.search.html_base import HTMLSearchEngine

BING_SEARCH_URL = "https://www.bing.com/search"
CN_RETRY_URL = "https://www4.bing.com/search"


def decode_bing_url(href: str) -> str | None:
    """还原 `bing.com/ck/a` 的 `u=a1<base64url>`；直链原样返回；不可用时 None。"""
    if not href:
        return None
    href = unescape(href).strip()
    parsed = urlsplit(href)
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower()
    if not host.endswith("bing.com") or parsed.path != "/ck/a":
        return href
    encoded = parse_qs(parsed.query).get("u", [""])[0]
    if len(encoded) < 4:
        return None
    body = encoded[2:].replace("-", "+").replace("_", "/")  # 剥 "a1" 前缀 → URL-safe base64
    body += "=" * ((4 - len(body) % 4) % 4)
    try:
        decoded = base64.b64decode(body).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    return decoded if decoded.lower().startswith(("http://", "https://")) else None


class BingHTMLEngine(HTMLSearchEngine):
    type_key = "bing_html"
    DEFAULT_BASE: ClassVar[str] = BING_SEARCH_URL

    # ---- RSS 形态 -------------------------------------------------------

    def search(
        self,
        *,
        query: str,
        count: int = 20,
        lang: str | None = None,
        country: str | None = None,
        timeout_s: float = 30,
    ) -> list[SearchItem]:
        """两级形态：RSS 优先；空结果（含空 XML）转 HTML 复核后再按纪律定论。"""
        client = self._client_for(timeout_s)
        items = self._search_rss(client, query, lang, timeout_s)
        if items:
            return items[:count]
        return self._search_html(client, query, count, lang, timeout_s, retried=False)

    def _search_rss(
        self, client: httpx.Client, query: str, lang: str | None, timeout_s: float
    ) -> list[SearchItem]:
        resp = self._request(
            client,
            self._base_url,
            params={"q": query, "format": "rss", "mkt": "en-US", "setlang": lang or "en"},
            timeout_s=timeout_s,
        )
        return self._parse_rss(resp.text)

    @staticmethod
    def _parse_rss(xml_text: str) -> list[SearchItem]:
        try:
            root = ET.fromstring(xml_text.encode("utf-8"))  # 带 XML 声明须以 bytes 解析
        except (ET.ParseError, ValueError):
            return []
        items: list[SearchItem] = []
        for node in root.iter("item"):
            title = (node.findtext("title") or "").strip()
            link = (node.findtext("link") or "").strip()
            snippet = (node.findtext("description") or "").strip()
            if title and link.lower().startswith(("http://", "https://")):
                items.append(SearchItem(title=title, url=link, snippet=snippet))
        return items

    # ---- HTML 形态 ------------------------------------------------------

    def _search_html(
        self,
        client: httpx.Client,
        query: str,
        count: int,
        lang: str | None,
        timeout_s: float,
        *,
        retried: bool,
    ) -> list[SearchItem]:
        params, headers = self._html_form(query, count, lang)
        url = CN_RETRY_URL if retried else self._base_url
        resp = self._request(client, url, params=params, headers=headers, timeout_s=timeout_s)
        if self._landed_on_cn(resp):
            if not retried:
                return self._search_html(client, query, count, lang, timeout_s, retried=True)
            raise ProviderError(
                ErrorKind.BLOCKED,
                "被重定向到 cn.bing.com（请检查代理出口）",
                provider=self.type_key,
            )
        self._check_blocked(resp)
        return self._resolve_results(resp.text)[:count]

    @staticmethod
    def _html_form(query: str, count: int, lang: str | None) -> tuple[dict[str, Any], dict[str, str]]:
        params: dict[str, Any] = {
            "q": query,
            "count": max(1, min(count, 50)),
            "mkt": "en-US",
            "cc": "US",
            "ensearch": "1",
        }
        if lang:
            params["setlang"] = lang
        return params, {"Cookie": "ENSEARCH=BENVER=1"}

    @staticmethod
    def _landed_on_cn(resp: httpx.Response) -> bool:
        return (urlsplit(str(resp.url)).hostname or "").lower().endswith("cn.bing.com")

    # ---- HTML 钩子 ------------------------------------------------------

    def _build_request(
        self, *, query: str, count: int, lang: str | None, country: str | None
    ) -> tuple[str, dict[str, Any], dict[str, str]]:
        params, headers = self._html_form(query, count, lang)
        return self._base_url, params, headers

    def _check_blocked(self, resp: httpx.Response) -> None:
        text = resp.text
        if 'class="captcha"' in text or "One last step" in text:
            raise ProviderError(
                ErrorKind.BLOCKED, "验证页（captcha / One last step）", provider=self.type_key
            )

    def _results_container_present(self, text: str) -> bool:
        # b_algo=结果容器；b_no=明确的"无结果"区块（合法空路径）
        return "b_algo" in text or "b_no" in text

    def _parse(self, text: str) -> list[SearchItem]:
        tree = LexborHTMLParser(text)
        items: list[SearchItem] = []
        for row in tree.css("li.b_algo"):
            link = row.css_first("h2 a")
            if link is None:
                continue
            url = decode_bing_url((link.attributes or {}).get("href", ""))
            title = link.text(strip=True)
            if not url or not title:
                continue
            snippet_node = row.css_first(".b_caption p") or row.css_first(".b_lineclamp2")
            snippet = snippet_node.text(strip=True) if snippet_node is not None else ""
            items.append(SearchItem(title=title, url=url, snippet=snippet))
        return items


MANIFEST = ProviderManifest(
    kind="search",
    type_key="bing_html",
    display_name="Bing（网页解析）",
    config_schema={"type": "object", "properties": {}},
    secret_fields=(),
    factory=BingHTMLEngine,
    preset={
        "endpoint": BING_SEARCH_URL,
        "note": "免密钥；免费渠道中最宽容（RSS 形态优先，约 10 条/页）",
        "apply_url": None,
        "access_mode": "html",
        "market": "全球（免费渠道首选）",
        "risk": "非官方接入：受风控影响（静默验证页/地理重定向），合规责任自担",
    },
)
registry.register(MANIFEST)
