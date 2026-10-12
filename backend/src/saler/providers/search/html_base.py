"""HTML 网页解析型检索渠道共基类（百度 / Google / Bing / Mojeek；004 R12）。

共性收敛（research R12 / contract §4）：
- 浏览器 UA 池轮换 + Accept-Language（子类可覆盖，如百度 zh-CN）；
- 引擎实例级最小请求间隔（`params.interval_s`，默认 2.0s + 0~1.5s 抖动）；
- **安全失败编排**（FR-007~009）：
  非 2xx → 状态归类（429=限流 / 其余 4xx=风控封禁 / 5xx=服务端）；
  风控标记（子类 `_check_blocked`）→ blocked；
  结果容器整体缺失 → blocked（疑似伪装页/软封禁，无法与改版区分，保守处理）；
  容器存在但解析异常 → parse（结构改版，立即切换）；
  无标记且结构正常 → 合法空结果。

会话与 cookie：同一引擎实例复用持久 client（httpx cookie jar），
支撑百度 BAIDUID 等"cookie 与 UA 配对"场景（R2）。
"""

from __future__ import annotations

import random
from time import monotonic, sleep
from typing import Any, ClassVar

import httpx

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.llm.base import TestResult
from saler.providers.search._common import build_client, map_http_error
from saler.providers.search.base import SearchItem

# 桌面浏览器 UA 池（轮换；runte 经验与同类实现同法）
BROWSER_UA_POOL: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
)

DEFAULT_INTERVAL_S = 2.0
JITTER_MAX_S = 1.5


class HTMLSearchEngine:
    """网页解析型检索渠道基类：子类实现 `_build_request` / `_parse` / `_results_container_present`。"""

    type_key: ClassVar[str] = "html"
    DEFAULT_BASE: ClassVar[str] = ""
    accept_language: ClassVar[str] = "en-US,en;q=0.9"

    def __init__(
        self,
        *,
        proxy: str | None = None,
        base_url: str | None = None,
        client: httpx.Client | None = None,
        params: dict | None = None,
    ) -> None:
        self._proxy = proxy
        self._client = client
        self._params = dict(params or {})
        try:
            self._interval_s = float(self._params.get("interval_s", DEFAULT_INTERVAL_S))
        except (TypeError, ValueError):
            self._interval_s = DEFAULT_INTERVAL_S
        self._base_url = base_url or self.DEFAULT_BASE
        self._session_client: httpx.Client | None = None
        self._last_request_at: float | None = None

    # ---- HTTP 与节流 ---------------------------------------------------

    def _client_for(self, timeout_s: float) -> httpx.Client:
        """复用注入 client；否则建立并保活会话 client（cookie jar 持久，R2）。"""
        if self._client is not None:
            return self._client
        if self._session_client is None:
            self._session_client = build_client(timeout_s=timeout_s, proxy=self._proxy)
        return self._session_client

    def _user_agent(self) -> str:
        """默认轮换 UA；要求 cookie 与 UA 配对的引擎（百度）覆盖为实例固定值。"""
        return random.choice(BROWSER_UA_POOL)

    def _throttle(self) -> None:
        """引擎实例级最小间隔 + 0~JITTER_MAX_S 抖动；链接还原等附加请求同池计数。"""
        now = monotonic()
        if self._last_request_at is not None:
            wait = self._interval_s + random.uniform(0, JITTER_MAX_S) - (now - self._last_request_at)
            if wait > 0:
                sleep(wait)
        self._last_request_at = monotonic()

    def _request(
        self,
        client: httpx.Client,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
        timeout_s: float = 30,
    ) -> httpx.Response:
        hdrs = {
            "User-Agent": self._user_agent(),
            "Accept-Language": self.accept_language,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        hdrs.update(headers or {})
        self._throttle()
        try:
            resp = client.request(method, url, params=params, headers=hdrs, timeout=timeout_s)
        except Exception as exc:  # noqa: BLE001 — 统一映射为 ProviderError
            raise map_http_error(exc, status=None, provider=self.type_key) from exc
        if resp.status_code >= 400:
            raise self._map_http_status(resp.status_code)
        return resp

    def _map_http_status(self, status: int) -> ProviderError:
        """网页端状态归类：429 限流 / 其余 4xx 风控封禁 / 5xx 服务端（子类可覆盖，如百度 480）。"""
        if status == 429:
            return ProviderError(ErrorKind.RATE_LIMIT, f"HTTP 429（{self.type_key}）", provider=self.type_key)
        if 400 <= status < 500:
            return ProviderError(ErrorKind.BLOCKED, f"HTTP {status}（{self.type_key}）", provider=self.type_key)
        return ProviderError(ErrorKind.SERVER, f"HTTP {status}（{self.type_key}）", provider=self.type_key)

    # ---- 子类钩子 -------------------------------------------------------

    def _build_request(
        self, *, query: str, count: int, lang: str | None, country: str | None
    ) -> tuple[str, dict[str, Any], dict[str, str]]:
        raise NotImplementedError

    def _results_container_present(self, text: str) -> bool:
        """结果容器（或明确"无结果"区块）是否在页面中——伪装/软封禁页的保守判据。"""
        raise NotImplementedError

    def _parse(self, text: str) -> list[SearchItem]:
        raise NotImplementedError

    def _check_blocked(self, resp: httpx.Response) -> None:
        """正文/标记级风控判定；命中 raise ProviderError(BLOCKED)。默认无。"""

    def _check_landed(self, resp: httpx.Response) -> None:
        """落地页/重定向判定（最终 URL 域、地理重定向等）；默认无。"""

    # ---- 编排 -----------------------------------------------------------

    def _resolve_results(self, text: str) -> list[SearchItem]:
        """解析 + 空结果纪律三分支（contract §4.2）。"""
        container = self._results_container_present(text)
        if container:
            try:
                items = self._parse(text)
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001 — 容器在但条目不可读 → parse（结构改版）
                raise ProviderError(
                    ErrorKind.PARSE,
                    f"页面结构变化：{type(exc).__name__}: {exc}",
                    provider=self.type_key,
                ) from exc
            return items  # 有结果直返；空 = 结构正常、确无结果 → 合法空
        raise ProviderError(
            ErrorKind.BLOCKED, "结果容器缺失（疑似伪装页/软封禁）", provider=self.type_key
        )

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
        return self._resolve_results(resp.text)[:count]

    def test_connection(self) -> TestResult:
        try:
            self.search(query="connectivity test", count=1, timeout_s=15)
            return TestResult(ok=True, detail="连接成功")
        except ProviderError as exc:
            return TestResult(ok=False, detail=f"[{exc.kind.value}] {exc}")
