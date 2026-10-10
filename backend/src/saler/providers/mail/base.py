"""邮件发送适配器契约（contracts/provider-adapters.md §3）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from saler.providers.llm.base import TestResult


@dataclass
class OutgoingMail:
    from_name: str
    from_addr: str
    to: str
    subject: str
    reply_to: str | None = None
    body_text: str | None = None
    body_html: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class SendResult:
    message_id: str


class MailSender(Protocol):
    def verify(self) -> TestResult: ...

    def send(self, *, message: OutgoingMail, timeout_s: float = 60) -> SendResult: ...

    def send_limit_hint(self) -> int | None: ...
