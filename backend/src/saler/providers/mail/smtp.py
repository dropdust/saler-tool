"""SMTP 邮件适配器（contracts/provider-adapters.md §3；aiosmtplib）。

同步接口：任务层经 ``asyncio.to_thread(...)`` 调用（与 LLM 适配器同约定）。
错误按统一分类抛出 ProviderError；异常文本经密钥脱敏（FR-006）。
"""

from __future__ import annotations

import asyncio
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import aiosmtplib
from loguru import logger

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.llm.base import TestResult
from saler.providers.mail.base import OutgoingMail, SendResult
from saler.providers.registry import ProviderManifest, registry
from saler.security.redact import register_secret_value, scrub_text

SECURITY_MODES = ("ssl", "starttls", "plain")


class SmtpMailSender:
    """SMTP 发送器：verify（连通+认证）/ send / send_limit_hint。"""

    def __init__(
        self,
        *,
        host: str,
        port: int = 465,
        security: str = "ssl",
        username: str | None = None,
        secret: str | None = None,
        from_name: str = "",
        from_addr: str = "",
        reply_to: str | None = None,
        limit_hint: int | None = None,
        timeout_s: float = 60,
        smtp_class=None,
    ) -> None:
        self.host = host
        self.port = port
        self.security = (security or "ssl").lower()
        self.username = username
        self.secret = secret
        self.from_name = from_name
        self.from_addr = from_addr or (username or "")
        self.reply_to = reply_to
        self.limit_hint = limit_hint
        self.timeout_s = timeout_s
        self._smtp_class = smtp_class or aiosmtplib.SMTP
        register_secret_value(secret)  # 任何异常文本中的密钥都将被脱敏

    # ---------- 公开接口 ----------

    def verify(self) -> TestResult:
        try:
            self._run(self._verify_async(self.timeout_s))
            return TestResult(ok=True, detail=f"SMTP 连接与认证成功（{self.host}:{self.port}）")
        except Exception as exc:  # noqa: BLE001 —— 测试端点必须给出可读原因而非 500
            err = self._map_exception(exc)
            logger.debug("SMTP verify 失败：{}", scrub_text(str(err)))
            return TestResult(ok=False, detail=f"{err.kind.value}: {scrub_text(str(err))}")

    def send(self, *, message: OutgoingMail, timeout_s: float = 60) -> SendResult:
        return self._run(self._send_async(message, timeout_s))

    def send_limit_hint(self) -> int | None:
        return self.limit_hint

    # ---------- 内部 ----------

    def _run(self, coro):
        try:
            return asyncio.run(coro)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 —— 统一分类
            raise self._map_exception(exc) from exc

    def _client_kwargs(self, timeout_s: float) -> dict:
        use_tls = self.security in ("ssl", "tls", "tls_ssl")
        start_tls = self.security in ("starttls", "start_tls")
        kwargs: dict = {
            "hostname": self.host,
            "port": self.port,
            "timeout": timeout_s,
            "use_tls": use_tls,
        }
        if start_tls:
            kwargs["start_tls"] = True
        return kwargs

    async def _login(self, client) -> None:
        if self.username:
            await client.login(self.username, self.secret or "")

    async def _verify_async(self, timeout_s: float) -> None:
        async with self._smtp_class(**self._client_kwargs(timeout_s)) as client:
            await self._login(client)  # 进入即连接（TLS 握手），退出即 QUIT

    async def _send_async(self, message: OutgoingMail, timeout_s: float) -> SendResult:
        msg = self._build_message(message)
        async with self._smtp_class(**self._client_kwargs(timeout_s)) as client:
            await self._login(client)
            await client.send_message(msg)
        return SendResult(message_id=str(msg["Message-ID"]))

    def _build_message(self, m: OutgoingMail) -> EmailMessage:
        msg = EmailMessage()
        from_name = m.from_name or self.from_name
        from_addr = m.from_addr or self.from_addr
        msg["From"] = formataddr((from_name, from_addr)) if from_name else from_addr
        msg["To"] = m.to
        msg["Subject"] = m.subject
        msg["Message-ID"] = make_msgid()
        reply_to = m.reply_to or self.reply_to
        if reply_to:
            msg["Reply-To"] = reply_to
        for key, value in (m.headers or {}).items():
            msg[key] = value
        if m.body_html and not m.body_text:
            msg.set_content(m.body_html, subtype="html")
        else:
            msg.set_content(m.body_text or "")
            if m.body_html:
                msg.add_alternative(m.body_html, subtype="html")
        return msg

    def _map_exception(self, exc: Exception) -> ProviderError:
        if isinstance(exc, ProviderError):
            return exc
        detail = scrub_text(str(exc))[:500]
        if isinstance(exc, aiosmtplib.SMTPAuthenticationError):
            return ProviderError(
                ErrorKind.AUTH, f"SMTP 认证失败（{self.host}）：请检查账号与授权码", detail=detail
            )
        if isinstance(exc, (aiosmtplib.SMTPRecipientsRefused, aiosmtplib.SMTPRecipientRefused)):
            return ProviderError(
                ErrorKind.RECIPIENT_REJECTED, "收件人被拒（SMTP 550 等）", detail=detail
            )
        if isinstance(exc, aiosmtplib.SMTPSenderRefused):
            return ProviderError(ErrorKind.AUTH, "发件人被拒（发件域策略）", detail=detail)
        if isinstance(exc, (aiosmtplib.SMTPTimeoutError, TimeoutError, asyncio.TimeoutError)):
            return ProviderError(ErrorKind.TIMEOUT, f"SMTP 超时（{self.host}）", detail=detail)
        if isinstance(exc, (aiosmtplib.SMTPServerDisconnected, ConnectionError, OSError)):
            return ProviderError(
                ErrorKind.NETWORK, f"SMTP 连接失败（{self.host}:{self.port}）", detail=detail
            )
        if isinstance(exc, aiosmtplib.SMTPResponseException):
            return ProviderError(
                ErrorKind.SERVER, f"SMTP 服务端错误（{getattr(exc, 'code', '?')}）", detail=detail
            )
        return ProviderError(ErrorKind.NETWORK, f"SMTP 未知错误：{type(exc).__name__}", detail=detail)


def create_smtp_sender(
    *, config: dict | None = None, secret: str | None = None, identity: dict | None = None
) -> SmtpMailSender:
    """注册表工厂：由通道 config/secret/identity 构造适配器。"""
    config = config or {}
    identity = identity or {}
    return SmtpMailSender(
        host=config.get("host") or "",
        port=int(config.get("port") or 465),
        security=str(config.get("security") or "ssl"),
        username=config.get("username"),
        secret=secret,
        from_name=identity.get("from_name") or "",
        from_addr=identity.get("from_addr") or config.get("username") or "",
        reply_to=identity.get("reply_to"),
        limit_hint=config.get("send_limit_hint"),
    )


MANIFEST = ProviderManifest(
    kind="mail",
    type_key="smtp",
    display_name="SMTP 邮箱（自有发信服务器）",
    config_schema={
        "type": "object",
        "properties": {
            "host": {"type": "string", "title": "SMTP 服务器", "examples": ["smtp.qq.com"]},
            "port": {"type": "integer", "title": "端口", "default": 465},
            "security": {
                "type": "string",
                "title": "加密方式",
                "enum": list(SECURITY_MODES),
                "default": "ssl",
            },
            "username": {"type": "string", "title": "登录账号"},
            "secret": {
                "type": "string",
                "title": "授权码/密码",
                "format": "password",
                "description": "多数邮箱需使用「授权码」而非登录密码",
            },
            "send_limit_hint": {
                "type": "integer",
                "title": "服务商建议日上限（可选）",
            },
        },
        "required": ["host", "port", "username", "secret"],
    },
    secret_fields=("secret",),
    factory=create_smtp_sender,
)
registry.register(MANIFEST)
