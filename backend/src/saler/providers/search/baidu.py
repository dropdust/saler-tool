"""百度网页解析渠道（004 R2）。

- 请求：`/s?wd=&pn=&rn=&ie=utf-8&oe=utf-8`；桌面浏览器 UA + `Accept-Language: zh-CN`；
  首次请求先 GET 首页种 cookie（BAIDUID）——**cookie 与 UA 配对，实例内 UA 固定不轮换**
  （`ab` cookie 由 UA 派生，轮换即失配；R2）。
- 解析：`#content_left` 下 `.result`/`.c-container`；标题 `h3 a`；
  **真实链接由结果块 `mu` 属性（备选 `data-landurl`）离线还原**，绝不逐条跟随 `link?url=`；
  摘要 `.c-abstract`；广告过滤（`data-tuiguang` / `data-cs='ad'` / `.ec-tuiguang`）。
- 风控（判失败，绝不写数据）：落地 wappass.baidu.com / verify.baidu.com、
  页面含"百度安全验证"/"网络不给力"、HTTP 480。
"""

from __future__ import annotations

import random
from typing import Any, ClassVar
from urllib.parse import urlsplit

import httpx
from selectolax.lexbor import LexborHTMLParser

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.registry import ProviderManifest, registry
from saler.providers.search.base import SearchItem
from saler.providers.search.html_base import BROWSER_UA_POOL, HTMLSearchEngine

BAIDU_SEARCH_URL = "https://www.baidu.com/s"
BAIDU_HOME_URL = "https://www.baidu.com/"
VERIFY_HOSTS = ("wappass.baidu.com", "verify.baidu.com")


class BaiduHTMLEngine(HTMLSearchEngine):
    type_key = "baidu_html"
    DEFAULT_BASE: ClassVar[str] = BAIDU_SEARCH_URL
    accept_language: ClassVar[str] = "zh-CN,zh;q=0.9"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._fixed_ua = random.choice(BROWSER_UA_POOL)  # 与 cookie 配对，实例内固定
        self._seeded = False

    def _user_agent(self) -> str:
        return self._fixed_ua

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
        self._ensure_seed(client, timeout_s)
        return super().search(
            query=query, count=count, lang=lang, country=country, timeout_s=timeout_s
        )

    def _ensure_seed(self, client: httpx.Client, timeout_s: float) -> None:
        """首次请求种 BAIDUID（缺失/过期是检测触发点；R2）。"""
        if self._seeded:
            return
        self._request(client, BAIDU_HOME_URL, timeout_s=timeout_s)
        self._seeded = True

    # ---- 钩子 -----------------------------------------------------------

    def _build_request(
        self, *, query: str, count: int, lang: str | None, country: str | None
    ) -> tuple[str, dict[str, Any], dict[str, str]]:
        params = {
            "wd": query,
            "pn": "0",
            "rn": str(max(1, min(count, 50))),
            "ie": "utf-8",
            "oe": "utf-8",
        }
        return self._base_url, params, {}

    def _check_landed(self, resp: httpx.Response) -> None:
        host = (urlsplit(str(resp.url)).hostname or "").lower()
        if host.endswith(VERIFY_HOSTS):
            raise ProviderError(
                ErrorKind.BLOCKED, "落地百度安全验证页（wappass/verify）", provider=self.type_key
            )

    def _check_blocked(self, resp: httpx.Response) -> None:
        text = resp.text
        if "百度安全验证" in text or "网络不给力" in text:
            raise ProviderError(
                ErrorKind.BLOCKED, "百度风控页标记（安全验证/网络不给力）", provider=self.type_key
            )

    def _map_http_status(self, status: int) -> ProviderError:
        if status == 480:  # 百度验证码状态码（R2）
            return ProviderError(
                ErrorKind.BLOCKED, f"HTTP 480（{self.type_key}，验证码状态）", provider=self.type_key
            )
        return super()._map_http_status(status)

    def _results_container_present(self, text: str) -> bool:
        return 'id="content_left"' in text

    def _parse(self, text: str) -> list[SearchItem]:
        tree = LexborHTMLParser(text)
        container = tree.css_first("#content_left")
        if container is None:
            return []
        items: list[SearchItem] = []
        seen: set[tuple[str, str]] = set()
        # 注意：selectolax 逗号选择器对同块双类名（.result.c-container）会重复返回，
        # 故分开取并集后按 (title, url) 去重（不依赖节点对象身份）。
        for row in [*container.css(".result"), *container.css(".c-container")]:
            attrs = row.attributes or {}
            if "data-tuiguang" in attrs or attrs.get("data-cs") == "ad":
                continue
            if row.css_first(".ec-tuiguang") is not None:
                continue
            link = row.css_first("h3 a")
            if link is None:
                continue
            url = (attrs.get("mu") or attrs.get("data-landurl") or "").strip()
            title = link.text(strip=True)
            if not title or not url.lower().startswith(("http://", "https://")):
                continue
            key = (title, url)
            if key in seen:
                continue
            seen.add(key)
            snippet_node = row.css_first(".c-abstract")
            snippet = snippet_node.text(strip=True) if snippet_node is not None else ""
            items.append(SearchItem(title=title, url=url, snippet=snippet))
        return items


MANIFEST = ProviderManifest(
    kind="search",
    type_key="baidu_html",
    display_name="百度（网页解析）",
    config_schema={"type": "object", "properties": {}},
    secret_fields=(),
    factory=BaiduHTMLEngine,
    preset={
        "endpoint": BAIDU_SEARCH_URL,
        "note": "免密钥；中文市场主力（验证码较常见，建议配合代理出口）",
        "apply_url": None,
        "access_mode": "html",
        "market": "中文市场",
        "risk": "非官方接入：验证码/风控常见；按服务商条款抓取的责任在用户",
    },
)
registry.register(MANIFEST)
