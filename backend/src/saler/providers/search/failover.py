"""检索渠道故障转移（research.md §7）：按用户配置的优先级逐一尝试。

命中限流/封禁/网络错误 → 自动切换下一渠道；全部失败 → 抛出最后一个错误，
由任务层暂停并提示用户在「设置 → 检索渠道」中补充/调整配置。
"""

from __future__ import annotations

from typing import Any

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.llm.base import TestResult
from saler.providers.search.base import SearchItem


class SearchFailover:
    def __init__(self, providers: list) -> None:
        self._providers = list(providers)

    @property
    def provider_count(self) -> int:
        return len(self._providers)

    def search(self, **kwargs: Any) -> list[SearchItem]:
        if not self._providers:
            raise ProviderError(ErrorKind.AUTH, "未配置可用的检索渠道")
        last: ProviderError | None = None
        for provider in self._providers:
            try:
                return provider.search(**kwargs)
            except ProviderError as exc:
                last = exc
                continue
        assert last is not None
        raise last

    def test_connection(self) -> TestResult:
        details = []
        any_ok = False
        for provider in self._providers:
            result = provider.test_connection()
            any_ok = any_ok or result.ok
            details.append(f"{getattr(provider, 'type_key', '?')}: {'OK' if result.ok else result.detail}")
        return TestResult(ok=any_ok, detail="；".join(details) or "无渠道")
