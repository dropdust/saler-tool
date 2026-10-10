"""短信发送适配器契约（contracts/provider-adapters.md §4）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from saler.providers.llm.base import TestResult


@dataclass
class SmsSendResult:
    message_id: str


class SMSSender(Protocol):
    def verify(self) -> TestResult: ...

    def send(
        self,
        *,
        phone_e164: str,
        text: str,
        signature: str | None = None,
        timeout_s: float = 30,
    ) -> SmsSendResult: ...
