"""抓取层：httpx 异步 + 礼貌策略（FR-025）。

- 单站最小间隔、显式代理（trust_env=False，代理只走用户配置）；
- robots.txt 默认遵循（可配置关闭，合规责任提示见设置页）；
- 重试 1 次（网络类错误），响应体截断防内存膨胀。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

DEFAULT_UA = "SalerTool/0.1 (local desktop lead discovery; contact pages only)"


@dataclass
class FetchResult:
    url: str
    status: int
    text: str
    error: str | None = None
    content_type: str | None = None


class Fetcher:
    def __init__(
        self,
        *,
        proxy: str | None = None,
        timeout_s: float = 20.0,
        per_host_delay_s: float = 1.0,
        respect_robots: bool = True,
        user_agent: str = DEFAULT_UA,
        max_bytes: int = 1_500_000,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._client = client or httpx.AsyncClient(
            timeout=timeout_s,
            proxy=proxy or None,
            trust_env=False,
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        )
        self._delay = max(0.0, per_host_delay_s)
        self._respect_robots = respect_robots
        self._max_bytes = max_bytes
        self._last_fetch: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser] = {}
        self._throttle_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _throttle(self, host: str) -> None:
        async with self._throttle_lock:
            now = time.monotonic()
            wait = self._delay - (now - self._last_fetch.get(host, 0.0))
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_fetch[host] = time.monotonic()

    async def _robots_allows(self, url: str) -> bool:
        if not self._respect_robots:
            return True
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        parser = self._robots.get(origin)
        if parser is None:
            parser = RobotFileParser()
            try:
                resp = await self._client.get(f"{origin}/robots.txt", timeout=5)
                parser.parse(resp.text.splitlines() if resp.status_code == 200 else [])
            except httpx.HTTPError:
                parser.parse([])  # robots 不可得 → 视为允许（与浏览器行为一致）
            self._robots[origin] = parser
        return parser.can_fetch(self._user_agent, url)

    async def fetch(self, url: str) -> FetchResult:
        host = urlparse(url).netloc
        if not await self._robots_allows(url):
            return FetchResult(url=url, status=0, text="", error="robots_disallowed")
        last_error = "unreachable"
        for attempt in range(2):
            await self._throttle(host)
            try:
                resp = await self._client.get(url)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt == 0:
                    await asyncio.sleep(0.5)
                continue
            content_type = resp.headers.get("content-type", "")
            if resp.status_code >= 400:
                return FetchResult(
                    url=url,
                    status=resp.status_code,
                    text="",
                    error=f"http_{resp.status_code}",
                    content_type=content_type,
                )
            return FetchResult(
                url=url,
                status=resp.status_code,
                text=resp.text[: self._max_bytes],
                content_type=content_type,
            )
        return FetchResult(url=url, status=0, text="", error=last_error)
