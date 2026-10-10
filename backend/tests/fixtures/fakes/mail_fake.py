"""假邮件发送器：记录出信，可注入失败。"""

from __future__ import annotations

from saler.providers.llm.base import TestResult
from saler.providers.mail.base import OutgoingMail, SendResult


class FakeMailSender:
    def __init__(self) -> None:
        self.sent: list[OutgoingMail] = []
        self.healthy = True
        self.fail_next: Exception | None = None

    def verify(self) -> TestResult:
        return TestResult(ok=self.healthy, detail="fake mail ok")

    def send(self, *, message: OutgoingMail, timeout_s: float = 60) -> SendResult:
        if self.fail_next is not None:
            exc, self.fail_next = self.fail_next, None
            raise exc
        self.sent.append(message)
        return SendResult(message_id=f"fake-mail-{len(self.sent)}")

    def send_limit_hint(self) -> int | None:
        return None
