"""检索适配器共用：HTTP 客户端构建、错误分类、预置模板。"""

from __future__ import annotations

from typing import Any

import httpx

from saler.providers.errors import ErrorKind, ProviderError

DEFAULT_UA = "SalerTool/0.1 (local desktop lead discovery)"

# 首批支持的渠道（UI 预置；绑定用户自备密钥）
SEARCH_PRESETS: dict[str, dict[str, Any]] = {
    "brave": {
        "display": "Brave Search",
        "endpoint": "https://api.search.brave.com/res/v1",
        "needs_key": True,
        "note": "免费额度需绑卡；ToS 对存储结果有限制，请阅读条款",
    },
    "serper": {
        "display": "Serper.dev（Google SERP）",
        "endpoint": "https://google.serper.dev",
        "needs_key": True,
        "note": "注册赠 2500 次、免绑卡；接入最简",
    },
    "tavily": {
        "display": "Tavily（AI 检索）",
        "endpoint": "https://api.tavily.com",
        "needs_key": True,
        "note": "每月 1000 信用自动续",
    },
    "ddg_html": {
        "display": "DuckDuckGo（非官方，最后兜底）",
        "endpoint": "https://html.duckduckgo.com/html/",
        "needs_key": False,
        "note": "非官方端点，软封禁风险高，仅作最后兜底",
    },
}


def build_client(*, timeout_s: float, proxy: str | None = None) -> httpx.Client:
    # trust_env=False：代理只走显式配置（回环/本机服务不被环境变量劫持）
    return httpx.Client(
        timeout=timeout_s, proxy=proxy or None, trust_env=False, follow_redirects=True
    )


def map_http_error(exc: Exception | None, *, status: int | None, provider: str) -> ProviderError:
    if status is not None:
        if status in (401, 403):
            kind = ErrorKind.AUTH
        elif status == 402:
            kind = ErrorKind.QUOTA
        elif status == 429:
            kind = ErrorKind.RATE_LIMIT
        elif 400 <= status < 500:
            kind = ErrorKind.AUTH
        else:
            kind = ErrorKind.SERVER
        return ProviderError(kind, f"HTTP {status}（{provider}）", provider=provider)
    if isinstance(exc, httpx.TimeoutException):
        return ProviderError(ErrorKind.TIMEOUT, str(exc), provider=provider)
    if isinstance(exc, httpx.TransportError):
        return ProviderError(ErrorKind.NETWORK, str(exc), provider=provider)
    return ProviderError(
        ErrorKind.NETWORK, f"{type(exc).__name__}: {exc}" if exc else "unknown", provider=provider
    )


def request_json(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    provider: str,
    **kwargs: Any,
) -> dict:
    try:
        resp = client.request(method, url, **kwargs)
    except Exception as exc:  # noqa: BLE001 - 统一映射为 ProviderError
        raise map_http_error(exc, status=None, provider=provider) from exc
    if resp.status_code >= 400:
        raise map_http_error(None, status=resp.status_code, provider=provider)
    try:
        return resp.json()
    except ValueError as exc:
        raise ProviderError(ErrorKind.SERVER, f"响应非 JSON：{exc}", provider=provider) from exc
