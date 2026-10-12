"""Wikipedia 官方免密钥检索渠道（MediaWiki Action API；004 R7）。

- 端点：`{lang}.wikipedia.org/w/api.php?action=query&list=search`——
  `srsearch` / `srlimit`（clamp ≤50）/ `srprop=snippet` / `format=json&formatversion=2`；
  语言版本由渠道 `params.lang`（默认 `en`）决定，`search(lang=...)` 调用方提供时覆盖
  （多市场用法；`base_url` 自定义时不动子域）。
- 结果：条目粒度（title/snippet/pageid）；URL 直接构造 `/wiki/{title}`；snippet 为
  含标签 HTML → 清洗为纯文本。
- **UA 为描述性字符串**（Wikimedia 政策强制；匿名/伪造 UA 可能 403）：`SalerTool/<版本> (…)`；
  可经 `params.contact` 追加联系信息（指向项目主页/邮箱；项目取得公开主页后应设为默认）。
- 429 尊重限流归类（Retry-After 由退避/切换链路处置）。
- 定位警示（runte 实测）：命中具模糊性（缩写/母公司/近名误配），**不得用于自动否定**。

该渠道为**官方 API**（非网页解析）：复用基类 HTTP/节流/错误映射，search() 覆写为 JSON 路径。
"""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version
from typing import Any, ClassVar
from urllib.parse import quote

from selectolax.lexbor import LexborHTMLParser

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.registry import ProviderManifest, registry
from saler.providers.search.base import SearchItem
from saler.providers.search.html_base import HTMLSearchEngine

DEFAULT_LANG = "en"
WIKI_API_TEMPLATE = "https://{lang}.wikipedia.org/w/api.php"


def _saler_version() -> str:
    try:
        return version("saler")
    except PackageNotFoundError:  # 源码直跑等场景
        return "0.1"


def build_user_agent(contact: str | None = None) -> str:
    """Wikimedia 政策要求的描述性 UA；contact 指向项目主页/邮箱（可选）。"""
    ua = f"SalerTool/{_saler_version()} (local desktop lead-discovery app)"
    return f"{ua} {contact}" if contact else ua


class WikipediaEngine(HTMLSearchEngine):
    type_key = "wikipedia"
    DEFAULT_BASE: ClassVar[str] = WIKI_API_TEMPLATE.format(lang=DEFAULT_LANG)

    def __init__(self, **kwargs: Any) -> None:
        self._custom_base = kwargs.get("base_url") is not None
        super().__init__(**kwargs)
        self._contact = str(self._params.get("contact") or "").strip() or None

    def _user_agent(self) -> str:
        return build_user_agent(self._contact)

    def _api_url(self, lang: str) -> str:
        if self._custom_base:
            return self._base_url
        return WIKI_API_TEMPLATE.format(lang=lang)

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
        api_lang = lang or str(self._params.get("lang") or DEFAULT_LANG)
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": str(max(1, min(count, 50))),
            "srprop": "snippet",
            "format": "json",
            "formatversion": "2",
        }
        resp = self._request(
            client,
            self._api_url(api_lang),
            params=params,
            headers={"Accept": "application/json"},
            timeout_s=timeout_s,
        )
        try:
            data = json.loads(resp.text)
        except ValueError as exc:
            raise ProviderError(ErrorKind.SERVER, f"响应非 JSON：{exc}", provider=self.type_key) from exc
        rows = ((data.get("query") or {}).get("search")) or []
        items: list[SearchItem] = []
        for row in rows:
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            items.append(
                SearchItem(
                    title=title,
                    url=f"https://{api_lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='()')}",
                    snippet=self._clean_snippet(str(row.get("snippet") or "")),
                )
            )
        return items[:count]

    @staticmethod
    def _clean_snippet(html: str) -> str:
        if not html:
            return ""
        node = LexborHTMLParser(f"<div>{html}</div>").css_first("div")
        raw = node.text() if node is not None else html
        return " ".join(raw.split())

    def _map_http_status(self, status: int) -> ProviderError:
        if status == 429:
            return ProviderError(ErrorKind.RATE_LIMIT, f"HTTP 429（{self.type_key}）", provider=self.type_key)
        return ProviderError(ErrorKind.SERVER, f"HTTP {status}（{self.type_key}）", provider=self.type_key)


MANIFEST = ProviderManifest(
    kind="search",
    type_key="wikipedia",
    display_name="Wikipedia（官方免费 API）",
    config_schema={"type": "object", "properties": {}},
    secret_fields=(),
    factory=WikipediaEngine,
    preset={
        "endpoint": WIKI_API_TEMPLATE.format(lang=DEFAULT_LANG),
        "note": "官方免密钥检索接口（语言版本可配，默认 en）；结果具模糊性（缩写/母公司误配），定位为机构资料与佐证",
        "apply_url": None,
        "access_mode": "official_api",
        "market": "机构资料检索与佐证（不得用于自动否定）",
        "risk": "命中为模糊匹配，'查不到 ≠ 机构为假'；描述性 UA 与礼貌节流为使用前提",
    },
)
registry.register(MANIFEST)
