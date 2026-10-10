"""假短信发送器：记录出信，可注入失败。"""

from __future__ import annotations

from saler.providers.llm.base import TestResult
from saler.providers.sms.base import SmsSendResult


class FakeSMSSender:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.healthy = True
        self.fail_next: Exception | None = None

    def verify(self) -> TestResult:
        return TestResult(ok=self.healthy, detail="fake sms ok")

    def send(
        self, *, phone_e164: str, text: str, signature: str | None = None, timeout_s: float = 30
    ) -> SmsSendResult:
        if self.fail_next is not None:
            exc, self.fail_next = self.fail_next, None
            raise exc
        self.sent.append({"phone": phone_e164, "text": text, "signature": signature})
        return SmsSendResult(message_id=f"fake-sms-{len(self.sent)}")
