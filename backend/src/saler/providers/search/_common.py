"""检索适配器共用：HTTP 客户端构建、错误分类、幌子结果判定、预置模板。"""

from __future__ import annotations

import re
from typing import Any

import httpx

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.search.base import SearchItem

DEFAULT_UA = "SalerTool/0.1 (local desktop lead discovery)"

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_BOOLEAN_OPERATORS = {"or", "and", "not"}
#: 无空格文字（CJK/假名/谚文）逐字重叠率过高，不参与词面判定
_CJK_FLOOR = 0x2E80


def query_terms(query: str) -> set[str]:
    """提取用于相关性判定的实词：小写、≥3 字符、剔除 -排除词/布尔算符/CJK 片段。"""
    terms: set[str] = set()
    for raw in (query or "").split():
        if raw.startswith("-"):
            continue  # -排除词：不是期望出现的内容
        for word in _WORD_RE.findall(raw.lower()):
            if len(word) >= 3 and word not in _BOOLEAN_OPERATORS and all(
                ord(ch) < _CJK_FLOOR for ch in word
            ):
                terms.add(word)
    return terms


def looks_like_decoy(query: str, items: list[SearchItem]) -> bool:
    """幌子结果判定（Bing 风控实证：页面回显查询词正确、条目却属于别的查询）。

    规则保守：提取不到实词或无条目时不下结论；仅当全部条目与查询零词面重叠时判为幌子。
    词面 = 分词后的前缀匹配（"poles"≈"pole"；"online" 不算 "line"——纯子串匹配会漏判）。
    """
    terms = query_terms(query)
    if not terms or not items:
        return False
    for item in items:
        tokens = _WORD_RE.findall(f"{item.title} {item.url} {item.snippet}".lower())
        if any(token.startswith(term) for term in terms for token in tokens):
            return False
    return True


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
