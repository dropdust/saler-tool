"""检索适配器契约（contracts/provider-adapters.md §2）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from saler.providers.llm.base import TestResult


@dataclass
class SearchItem:
    title: str
    url: str
    snippet: str = ""


class SearchProvider(Protocol):
    type_key: str

    def search(
        self,
        *,
        query: str,
        count: int = 20,
        lang: str | None = None,
        country: str | None = None,
        timeout_s: float = 30,
    ) -> list[SearchItem]: ...

    def test_connection(self) -> TestResult: ...
