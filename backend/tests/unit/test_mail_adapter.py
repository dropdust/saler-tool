"""T105 单元测试：SMTP 适配器——出信构造 / 错误分类映射 / 脱敏（FR-040~043）。

离线：以假 aiosmtplib.SMTP 类注入（不触网）。
"""

from __future__ import annotations

import aiosmtplib
import pytest

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.mail.base import OutgoingMail
from saler.providers.mail.smtp import SmtpMailSender

SECRET = "s3cret-app-password"


class FakeSMTP:
    """aiosmtplib.SMTP 替身：async 上下文管理器，可注入连接/登录/发送失败。"""

    instances: list[FakeSMTP] = []
    fail_connect: Exception | None = None
    fail_login: Exception | None = None
    fail_send: Exception | None = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.logged_in: tuple[str, str] | None = None
        self.sent: list = []
        FakeSMTP.instances.append(self)

    async def __aenter__(self):
        if FakeSMTP.fail_connect is not None:
            raise FakeSMTP.fail_connect
        return self

    async def __aexit__(self, *exc):
        return False

    async def login(self, username: str, password: str):
        if FakeSMTP.fail_login is not None:
            raise FakeSMTP.fail_login
        self.logged_in = (username, password)

    async def send_message(self, message):
        if FakeSMTP.fail_send is not None:
            raise FakeSMTP.fail_send
        self.sent.append(message)


@pytest.fixture(autouse=True)
def _reset_fake():
    FakeSMTP.instances = []
    FakeSMTP.fail_connect = None
    FakeSMTP.fail_login = None
    FakeSMTP.fail_send = None
    yield


def make_sender(**overrides) -> SmtpMailSender:
    kwargs = {
        "host": "smtp.example.com",
        "port": 465,
        "security": "ssl",
        "username": "alice@example.com",
        "secret": SECRET,
        "from_name": "Alice",
        "from_addr": "alice@example.com",
        "reply_to": "sales@example.com",
    }
    kwargs.update(overrides)
    return SmtpMailSender(smtp_class=FakeSMTP, **kwargs)


def out_mail(**overrides) -> OutgoingMail:
    kwargs = {
        "from_name": "Alice",
        "from_addr": "alice@example.com",
        "to": "bob@buyer.example",
        "subject": "Power fittings catalog",
        "body_text": "Hello Bob",
        "body_html": "<p>Hello Bob</p>",
    }
    kwargs.update(overrides)
    return OutgoingMail(**kwargs)


class TestSend:
    def test_send_builds_message_and_returns_id(self):
        sender = make_sender()
        result = sender.send(message=out_mail())
        assert result.message_id  # 非空
        smtp = FakeSMTP.instances[0]
        assert smtp.logged_in == ("alice@example.com", SECRET)
        message = smtp.sent[0]
        assert message["To"] == "bob@buyer.example"
        assert message["Subject"] == "Power fittings catalog"
        assert "alice@example.com" in message["From"]
        assert "Alice" in message["From"]
        assert message["Reply-To"] == "sales@example.com"

    def test_send_uses_starttls_and_plain_port_config(self):
        sender = make_sender(security="starttls", port=587)
        sender.send(message=out_mail())
        smtp = FakeSMTP.instances[0]
        assert smtp.kwargs["hostname"] == "smtp.example.com"
        assert smtp.kwargs["port"] == 587
        assert smtp.kwargs.get("start_tls") is True
        assert smtp.kwargs.get("use_tls") in (False, None)

    def test_auth_error_maps_and_redacts_secret(self):
        FakeSMTP.fail_login = aiosmtplib.SMTPAuthenticationError(535, b"bad credentials")
        sender = make_sender()
        with pytest.raises(ProviderError) as excinfo:
            sender.send(message=out_mail())
        err = excinfo.value
        assert err.kind == ErrorKind.AUTH
        assert err.retryable is False
        assert SECRET not in str(err)
        assert SECRET not in (err.detail or "")

    def test_recipient_refused_maps(self):
        FakeSMTP.fail_send = aiosmtplib.SMTPRecipientsRefused(
            {"bob@buyer.example": (550, b"no such user")}
        )
        with pytest.raises(ProviderError) as excinfo:
            make_sender().send(message=out_mail())
        assert excinfo.value.kind == ErrorKind.RECIPIENT_REJECTED
        assert excinfo.value.retryable is False

    def test_timeout_maps(self):
        FakeSMTP.fail_login = TimeoutError()
        with pytest.raises(ProviderError) as excinfo:
            make_sender().send(message=out_mail())
        assert excinfo.value.kind == ErrorKind.TIMEOUT
        assert excinfo.value.retryable is True

    def test_connect_failure_maps_network(self):
        FakeSMTP.fail_connect = OSError("connection refused")
        with pytest.raises(ProviderError) as excinfo:
            make_sender().send(message=out_mail())
        assert excinfo.value.kind == ErrorKind.NETWORK
        assert excinfo.value.retryable is True

    def test_server_error_maps(self):
        FakeSMTP.fail_send = aiosmtplib.SMTPResponseException(451, b"try later")
        with pytest.raises(ProviderError) as excinfo:
            make_sender().send(message=out_mail())
        assert excinfo.value.kind == ErrorKind.SERVER
        assert excinfo.value.retryable is True


class TestVerify:
    def test_verify_ok(self):
        result = make_sender().verify()
        assert result.ok is True
        assert "smtp.example.com" in result.detail

    def test_verify_auth_failure_returns_not_ok_without_secret(self):
        FakeSMTP.fail_login = aiosmtplib.SMTPAuthenticationError(535, b"invalid")
        result = make_sender().verify()
        assert result.ok is False
        assert "auth" in result.detail
        assert SECRET not in result.detail

    def test_verify_network_failure(self):
        FakeSMTP.fail_connect = OSError("no route")
        result = make_sender().verify()
        assert result.ok is False


class TestLimits:
    def test_send_limit_hint_from_config(self):
        assert make_sender(limit_hint=500).send_limit_hint() == 500

    def test_send_limit_hint_none_by_default(self):
        assert make_sender().send_limit_hint() is None
