"""短信适配器：HTTP API + 用户自备凭证（contracts/provider-adapters.md §4）。

首批配置模板：Twilio（国际）与通用 HTTP 网关（自建/其他服务商）。
同步接口：任务层经 ``asyncio.to_thread(...)`` 调用。
"""

from __future__ import annotations

import uuid

import httpx

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.llm.base import TestResult
from saler.providers.registry import ProviderManifest, registry
from saler.providers.sms.base import SmsSendResult
from saler.security.redact import register_secret_value, scrub_text

DEFAULT_UA = "SalerTool/0.1 (local desktop campaign sender)"

#: 服务商预置模板（UI 一键填充；字段均可再改）
SMS_PRESETS: dict[str, dict] = {
    "twilio": {
        "display": "Twilio（国际）",
        "method": "POST",
        "endpoint": "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
        "auth_mode": "basic",
        "phone_field": "To",
        "text_field": "Body",
        "signature_field": None,
        "from_field": "From",
        "message_id_field": "sid",
        "note": "账号 SID 作登录名、Auth Token 作密钥；国内号码需短信签名报备",
    },
    "generic": {
        "display": "通用 HTTP 网关",
        "method": "POST",
        "endpoint": "",
        "auth_mode": "bearer",
        "phone_field": "to",
        "text_field": "text",
        "signature_field": "signature",
        "from_field": None,
        "message_id_field": "message_id",
        "note": "任意 HTTP 短信网关：Bearer 密钥 + JSON 表单；字段名按网关文档调整",
    },
}


class SmsHttpSender:
    """SMS 发送器：verify / send。"""

    def __init__(
        self,
        *,
        endpoint: str,
        method: str = "POST",
        auth_mode: str = "bearer",
        username: str | None = None,
        secret: str | None = None,
        phone_field: str = "to",
        text_field: str = "text",
        signature_field: str | None = "signature",
        from_field: str | None = None,
        sender_address: str | None = None,
        message_id_field: str = "message_id",
        extra_fields: dict | None = None,
        headers: dict | None = None,
        timeout_s: float = 30,
        client_factory=None,
    ) -> None:
        self.endpoint = endpoint
        self.method = (method or "POST").upper()
        self.auth_mode = (auth_mode or "bearer").lower()
        self.username = username
        self.secret = secret
        self.phone_field = phone_field
        self.text_field = text_field
        self.signature_field = signature_field
        self.from_field = from_field
        self.sender_address = sender_address
        self.message_id_field = message_id_field
        self.extra_fields = dict(extra_fields or {})
        self.headers = dict(headers or {})
        self.timeout_s = timeout_s
        self._client_factory = client_factory or self._default_client
        register_secret_value(secret)

    # ---------- 公开接口 ----------

    def verify(self) -> TestResult:
        if not self.endpoint:
            return TestResult(ok=False, detail="未配置短信网关地址（endpoint）")
        try:
            with self._client(timeout_s=min(self.timeout_s, 15)) as client:
                resp = client.request(self.method, self._resolve_endpoint(), **self._request_kwargs())
            if resp.status_code in (401, 403):
                return TestResult(ok=False, detail=f"auth: 凭证被拒（HTTP {resp.status_code}）")
            return TestResult(ok=True, detail=f"网关可达（HTTP {resp.status_code}）")
        except Exception as exc:  # noqa: BLE001 —— 测试端点给可读原因
            err = self._map_exception(exc)
            return TestResult(ok=False, detail=f"{err.kind.value}: {scrub_text(str(err))}")

    def send(
        self, *, phone_e164: str, text: str, signature: str | None = None, timeout_s: float = 30
    ) -> SmsSendResult:
        if not self.endpoint:
            raise ProviderError(ErrorKind.AUTH, "未配置短信网关地址（endpoint）", provider="sms")
        payload: dict[str, str] = {self.phone_field: phone_e164, self.text_field: text}
        if signature and self.signature_field:
            payload[self.signature_field] = signature
        if self.sender_address and self.from_field:
            payload[self.from_field] = self.sender_address
        payload.update(self.extra_fields)
        try:
            with self._client(timeout_s=timeout_s) as client:
                resp = client.request(
                    self.method, self._resolve_endpoint(), json=payload, **self._request_kwargs()
                )
        except Exception as exc:  # noqa: BLE001
            raise self._map_exception(exc) from exc
        if resp.status_code >= 400:
            raise self._map_http(resp)
        try:
            data = resp.json()
        except ValueError:
            data = {}
        message_id = str(data.get(self.message_id_field) or f"sms-{uuid.uuid4().hex[:12]}")
        return SmsSendResult(message_id=message_id)

    # ---------- 内部 ----------

    def _default_client(self, *, timeout_s: float) -> httpx.Client:
        return httpx.Client(timeout=timeout_s, trust_env=False, follow_redirects=True)

    def _client(self, *, timeout_s: float):
        return self._client_factory(timeout_s=timeout_s)

    def _resolve_endpoint(self) -> str:
        return self.endpoint.replace("{account_sid}", self.username or "")

    def _request_kwargs(self) -> dict:
        headers = {"User-Agent": DEFAULT_UA, **self.headers}
        kwargs: dict = {"headers": headers}
        if self.auth_mode == "basic":
            kwargs["auth"] = (self.username or "", self.secret or "")
        elif self.auth_mode == "bearer" and self.secret:
            headers["Authorization"] = f"Bearer {self.secret}"
        return kwargs

    def _map_http(self, resp: httpx.Response) -> ProviderError:
        detail = scrub_text(resp.text)[:500]
        if resp.status_code in (401, 403):
            return ProviderError(ErrorKind.AUTH, f"短信网关凭证被拒（HTTP {resp.status_code}）", detail=detail)
        if resp.status_code == 402:
            return ProviderError(ErrorKind.QUOTA, "短信额度不足（HTTP 402）", detail=detail)
        if resp.status_code == 429:
            return ProviderError(ErrorKind.RATE_LIMIT, "短信网关限流（HTTP 429）", detail=detail)
        if resp.status_code >= 500:
            return ProviderError(ErrorKind.SERVER, f"短信网关服务端错误（HTTP {resp.status_code}）", detail=detail)
        return ProviderError(ErrorKind.AUTH, f"短信网关拒绝请求（HTTP {resp.status_code}）", detail=detail)

    def _map_exception(self, exc: Exception) -> ProviderError:
        if isinstance(exc, ProviderError):
            return exc
        detail = scrub_text(str(exc))[:500]
        if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
            return ProviderError(ErrorKind.TIMEOUT, "短信网关超时", detail=detail)
        if isinstance(exc, httpx.TransportError):
            return ProviderError(ErrorKind.NETWORK, "短信网关连接失败", detail=detail)
        return ProviderError(ErrorKind.NETWORK, f"短信发送未知错误：{type(exc).__name__}", detail=detail)


def create_sms_sender(
    *, config: dict | None = None, secret: str | None = None, identity: dict | None = None
) -> SmsHttpSender:
    """注册表工厂：config.preset 提供模板默认值，显式字段优先。"""
    config = dict(config or {})
    identity = identity or {}
    preset_key = config.get("preset") or "generic"
    preset = SMS_PRESETS.get(preset_key, {})
    merged = {**{k: v for k, v in preset.items() if k not in ("display", "note")}, **config}
    return SmsHttpSender(
        endpoint=merged.get("endpoint") or "",
        method=merged.get("method") or "POST",
        auth_mode=merged.get("auth_mode") or "bearer",
        username=merged.get("username"),
        secret=secret,
        phone_field=merged.get("phone_field") or "to",
        text_field=merged.get("text_field") or "text",
        signature_field=merged.get("signature_field"),
        from_field=merged.get("from_field"),
        sender_address=identity.get("from_addr") or identity.get("sender"),
        message_id_field=merged.get("message_id_field") or "message_id",
        extra_fields=merged.get("extra_fields") or {},
        headers=merged.get("headers") or {},
    )


MANIFEST = ProviderManifest(
    kind="sms",
    type_key="http_generic",
    display_name="HTTP 短信网关（Twilio / 通用）",
    config_schema={
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "title": "服务商模板",
                "enum": list(SMS_PRESETS.keys()),
                "default": "generic",
            },
            "endpoint": {"type": "string", "title": "网关地址"},
            "method": {"type": "string", "title": "请求方法", "default": "POST"},
            "auth_mode": {"type": "string", "title": "认证方式", "enum": ["bearer", "basic"]},
            "username": {"type": "string", "title": "账号（Basic 认证/Twilio SID）"},
            "secret": {"type": "string", "title": "密钥/令牌", "format": "password"},
            "phone_field": {"type": "string", "title": "号码字段名"},
            "text_field": {"type": "string", "title": "正文字段名"},
            "signature_field": {"type": "string", "title": "签名字段名（可空）"},
            "message_id_field": {"type": "string", "title": "响应中消息 ID 字段"},
        },
        "required": ["endpoint", "secret"],
    },
    secret_fields=("secret",),
    factory=create_sms_sender,
)
registry.register(MANIFEST)
