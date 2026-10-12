"""Mojeek 网页解析渠道（004 R6）。

- 请求：`www.mojeek.com/search?q=`；解析 `ul.results-standard > li`——
  标题 `a.title`、摘要 `p.s`；链接优先取 `a.ob` 的 href（独立索引直链为主，
  个别包装形态按标准离线还原后仍不可用则丢弃该条）。
- 风控：HTTP 403（基类 4xx 归类）与 200 页面的 `403 - Forbidden` 标题标记（社区实证形态）→ blocked。
- 官方 Web Search API 为付费计量（Personal 档 £1/千次、仅试用额度）——不在免密钥范围；
  需要高稳定性的用户可自行申请（preset.note 注明）。
"""

from __future__ import annotations

from typing import Any, ClassVar
from urllib.parse import urljoin

import httpx
from selectolax.lexbor import LexborHTMLParser

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.registry import ProviderManifest, registry
from saler.providers.search.base import SearchItem
from saler.providers.search.html_base import HTMLSearchEngine

MOJEEK_SEARCH_URL = "https://www.mojeek.com/search"
MOJEEK_ORIGIN = "https://www.mojeek.com/"


class MojeekHTMLEngine(HTMLSearchEngine):
    type_key = "mojeek_html"
    DEFAULT_BASE: ClassVar[str] = MOJEEK_SEARCH_URL

    # ---- 钩子 -----------------------------------------------------------

    def _build_request(
        self, *, query: str, count: int, lang: str | None, country: str | None
    ) -> tuple[str, dict[str, Any], dict[str, str]]:
        return self._base_url, {"q": query}, {}

    def _check_blocked(self, resp: httpx.Response) -> None:
        text = resp.text
        # T214 真实验收发现：Mojeek 以 HTTP 200 返回 <title>Captcha</title> 挑战页
        if "<title>Captcha" in text:
            raise ProviderError(
                ErrorKind.BLOCKED, "Mojeek 验证页（Captcha，200 承载）", provider=self.type_key
            )
        if "403 - Forbidden" in text:
            raise ProviderError(
                ErrorKind.BLOCKED, "403 - Forbidden 页（200 承载）", provider=self.type_key
            )

    def _results_container_present(self, text: str) -> bool:
        # results-standard=结果容器；"No results"=明确无结果区块（合法空路径）
        return "results-standard" in text or "No results" in text

    def _parse(self, text: str) -> list[SearchItem]:
        tree = LexborHTMLParser(text)
        items: list[SearchItem] = []
        for row in tree.css("ul.results-standard li"):
            title_node = row.css_first("a.title") or row.css_first("h2 a")
            if title_node is None:
                continue
            ob_node = row.css_first("a.ob")
            href = (ob_node or title_node).attributes.get("href", "")
            url = urljoin(MOJEEK_ORIGIN, (href or "").strip())
            title = title_node.text(strip=True)
            if not title or not url.lower().startswith(("http://", "https://")):
                continue
            snippet_node = row.css_first("p.s")
            snippet = snippet_node.text(strip=True) if snippet_node is not None else ""
            items.append(SearchItem(title=title, url=url, snippet=snippet))
        return items


MANIFEST = ProviderManifest(
    kind="search",
    type_key="mojeek_html",
    display_name="Mojeek（网页解析）",
    config_schema={"type": "object", "properties": {}},
    secret_fields=(),
    factory=MojeekHTMLEngine,
    preset={
        "endpoint": MOJEEK_SEARCH_URL,
        "note": "免密钥；英国独立索引（非 Google/Bing 转售），结果多样性补充；官方 API 为付费计量、仅试用",
        "apply_url": None,
        "access_mode": "html",
        "market": "英国独立索引 / 欧美补充",
        "risk": "非官方接入：受风控影响（403），合规责任自担",
    },
)
registry.register(MANIFEST)
