"""Google 网页解析渠道（004 R3）。

- 请求：`/search?q=&hl=&gl=&start=0&pws=0`——**不使用已失效的 `num`**（约 2025-09 起固定
  10 条/页）；携带 `CONSENT`/`SOCS` cookie 避开 EEA 同意插页。
- 链接还原：旧式 `/url?q=` **离线**解码；新式 `/goto?url=<签名 token>` 无法离线解析——
  逐条跟随一次 302（计入引擎节流；R3），仍不可还原的条目**丢弃**（FR-004 边界，不写包装链接）。
- 风控（判失败）：落地 `/sorry` 或 consent.google.com；HTTP 200 也按**正文嗅探**
  （"unusual traffic"/"not a robot"/中文"异常流量"）；429 归类限流；广告多启发式过滤
  （`data-text-ad`、`.uEierd`、`aclk` 链接）。
- 诚实定位：2025 起纯 HTML 成功率受 JS 渲染门槛影响——高风险渠道、尽力而为
  （preset.risk 明示；失败由自动切换兜底；R12）。
"""

from __future__ import annotations

from html import unescape
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlsplit

import httpx
from selectolax.lexbor import LexborHTMLParser

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.registry import ProviderManifest, registry
from saler.providers.search.base import SearchItem
from saler.providers.search.html_base import HTMLSearchEngine

GOOGLE_SEARCH_URL = "https://www.google.com/search"
CONSENT_COOKIE = "CONSENT=PENDING+987; SOCS=CAESHAgBEhIaAB"


def decode_google_href(href: str) -> str | None:
    """离线还原 Google 结果链接。

    - `/url?q=<urlencoded>` → 离线解码目标；
    - 非 google.com 直链 → 原样；
    - `/goto?url=<签名>` → 保留原样（由 `_resolve_goto` 跟随一次 302）；
    - 其余 google.com 内部链接 → None（丢弃）。
    """
    if not href:
        return None
    href = unescape(href).strip()
    if href.startswith("/"):
        href = "https://www.google.com" + href  # 相对包装链接（/url?…、/goto?…）先补全
    parsed = urlsplit(href)
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower()
    if not host.endswith("google.com"):
        return href
    if parsed.path == "/url":
        target = parse_qs(parsed.query).get("q", [""])[0]
        return target if target.lower().startswith(("http://", "https://")) else None
    if parsed.path.startswith("/goto"):
        return href
    return None


class GoogleHTMLEngine(HTMLSearchEngine):
    type_key = "google_html"
    DEFAULT_BASE: ClassVar[str] = GOOGLE_SEARCH_URL

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
        url, params, headers = self._build_request(
            query=query, count=count, lang=lang, country=country
        )
        resp = self._request(client, url, params=params, headers=headers, timeout_s=timeout_s)
        self._check_landed(resp)
        self._check_blocked(resp)
        items = self._resolve_results(resp.text)[:count]
        return self._resolve_goto(client, items, timeout_s)

    # ---- 钩子 -----------------------------------------------------------

    def _build_request(
        self, *, query: str, count: int, lang: str | None, country: str | None
    ) -> tuple[str, dict[str, Any], dict[str, str]]:
        params: dict[str, Any] = {"q": query, "start": "0", "pws": "0", "hl": lang or "en"}
        if country:
            params["gl"] = country.lower()
        return self._base_url, params, {"Cookie": CONSENT_COOKIE}

    def _check_landed(self, resp: httpx.Response) -> None:
        parsed = urlsplit(str(resp.url))
        host = (parsed.hostname or "").lower()
        if parsed.path.startswith("/sorry") or host.endswith("consent.google.com"):
            raise ProviderError(
                ErrorKind.BLOCKED, "Google 拦截页（sorry/consent 落地）", provider=self.type_key
            )

    def _check_blocked(self, resp: httpx.Response) -> None:
        text = resp.text
        low = text.lower()
        if (
            "unusual traffic" in low
            or "not a robot" in low
            or "我们的系统检测到您的计算机网络中存在异常流量" in text
        ):
            raise ProviderError(
                ErrorKind.BLOCKED, "Google 异常流量/人机校验页（正文嗅探）", provider=self.type_key
            )

    def _results_container_present(self, text: str) -> bool:
        return 'id="rso"' in text or 'id="search"' in text

    def _parse(self, text: str) -> list[SearchItem]:
        tree = LexborHTMLParser(text)
        items: list[SearchItem] = []
        seen: set[tuple[str, str]] = set()
        for row in tree.css("#rso div[data-hveid]"):
            attrs = row.attributes or {}
            if "data-text-ad" in attrs or row.css_first("[data-text-ad]") is not None:
                continue
            if row.css_first(".uEierd") is not None:
                continue
            link = None
            for anchor in row.css("a"):
                if anchor.css_first("h3") is not None:
                    link = anchor
                    break
            if link is None:
                continue
            if any("/aclk" in ((a.attributes or {}).get("href") or "") for a in row.css("a")):
                continue
            h3 = link.css_first("h3")
            title = h3.text(strip=True) if h3 is not None else ""
            url = decode_google_href((link.attributes or {}).get("href", ""))
            if not title or url is None:
                continue
            key = (title, url)
            if key in seen:
                continue
            seen.add(key)
            snippet_node = row.css_first(".VwiC3b") or row.css_first(".st")
            snippet = snippet_node.text(strip=True) if snippet_node is not None else ""
            items.append(SearchItem(title=title, url=url, snippet=snippet))
        return items

    # ---- /goto 跟随一次 --------------------------------------------------

    def _resolve_goto(
        self, client: httpx.Client, items: list[SearchItem], timeout_s: float
    ) -> list[SearchItem]:
        resolved: list[SearchItem] = []
        for item in items:
            if not self._is_goto_url(item.url):
                resolved.append(item)
                continue
            try:
                resp = self._request(client, item.url, timeout_s=timeout_s)
            except ProviderError:
                continue  # 无法还原 → 丢弃该条（FR-004 边界）
            final = str(resp.url)
            if self._is_goto_url(final):
                continue
            resolved.append(SearchItem(title=item.title, url=final, snippet=item.snippet))
        return resolved

    @staticmethod
    def _is_goto_url(url: str) -> bool:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        return host.endswith("google.com") and parsed.path.startswith("/goto")


MANIFEST = ProviderManifest(
    kind="search",
    type_key="google_html",
    display_name="Google（网页解析）",
    config_schema={"type": "object", "properties": {}},
    secret_fields=(),
    factory=GoogleHTMLEngine,
    preset={
        "endpoint": GOOGLE_SEARCH_URL,
        "note": "免密钥；全球覆盖最强，但纯 HTML 成功率受 JS 渲染门槛影响（尽力而为）",
        "apply_url": None,
        "access_mode": "html",
        "market": "全球",
        "risk": "高风险渠道：风控严格（sorry/异常流量页）、失败自动切换；非官方接入，合规责任自担",
    },
)
registry.register(MANIFEST)
