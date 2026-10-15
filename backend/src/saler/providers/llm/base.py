"""LLM 适配器契约（contracts/provider-adapters.md §1）。

`on_attempt` 载荷带 `event`：`"start"`（请求即将发出，ok/latency/输出为空）与
`"finish"`（本次尝试结束）；缺省视为 finish。任务层据此先落"进行中"行、再原位收口。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass
class TestResult:
    ok: bool
    detail: str = ""
    models: list[str] | None = None
    kind: str | None = None  # 失败类别（ErrorKind.value；供渠道运行时记账，004 T211）


class LLMProvider(Protocol):
    type_key: str

    def test_connection(self) -> TestResult: ...

    def generate_structured(
        self,
        *,
        prompt: str,
        schema: dict,
        system: str | None = None,
        max_repair_attempts: int = 2,
        timeout_s: float = 120,
        deadline_s: float = 300,
        on_attempt: Callable[[dict], None] | None = None,
    ) -> dict: ...

    def translate(
        self,
        *,
        items: list[str],
        source_lang: str,
        target_lang: str,
        glossary: dict[str, str] | None = None,
        timeout_s: float = 120,
        deadline_s: float = 300,
        on_attempt: Callable[[dict], None] | None = None,
    ) -> list[str]: ...

    def complete(self, *, prompt: str, system: str | None = None, timeout_s: float = 120) -> str: ...
