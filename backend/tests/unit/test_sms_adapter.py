"""T108 配套单元测试：SMS HTTP 适配器——预置模板 / 字段映射 / 错误分类（respx 离线）。"""

from __future__ import annotations

import httpx
import pytest
import respx

from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.sms.http_generic import SMS_PRESETS, SmsHttpSender

GATEWAY = "https://sms.example.test/api/send"
TWILIO_SID = "AC123"
TWILIO_TOKEN = "tok-secret"


def generic_sender() -> SmsHttpSender:
    return SmsHttpSender(endpoint=GATEWAY, secret="bearer-secret")


class TestSend:
    @respx.mock
    def test_send_maps_fields_and_parses_message_id(self):
        route = respx.post(GATEWAY).mock(
            return_value=httpx.Response(200, json={"message_id": "gw-42", "status": "ok"})
        )
        result = generic_sender().send(phone_e164="+254700000000", text="你好", signature="外贸部")
        assert result.message_id == "gw-42"
        request = route.calls[0].request
        assert request.headers["Authorization"] == "Bearer bearer-secret"
        import json

        body = json.loads(request.content)
        assert body == {"to": "+254700000000", "text": "你好", "signature": "外贸部"}

    @respx.mock
    def test_twilio_preset_basic_auth_and_form_fields(self):
        preset = SMS_PRESETS["twilio"]
        endpoint = preset["endpoint"].replace("{account_sid}", TWILIO_SID)
        route = respx.post(endpoint).mock(return_value=httpx.Response(201, json={"sid": "SM123"}))
        sender = SmsHttpSender(
            endpoint=preset["endpoint"],
            auth_mode=preset["auth_mode"],
            username=TWILIO_SID,
            secret=TWILIO_TOKEN,
            phone_field=preset["phone_field"],
            text_field=preset["text_field"],
            signature_field=preset["signature_field"],
            from_field=preset["from_field"],
            sender_address="+12025550000",
            message_id_field=preset["message_id_field"],
        )
        result = sender.send(phone_e164="+254700000000", text="Hello")
        assert result.message_id == "SM123"
        import json

        body = json.loads(route.calls[0].request.content)
        assert body == {"To": "+254700000000", "Body": "Hello", "From": "+12025550000"}

    @respx.mock
    def test_auth_error_maps_and_redacts(self):
        respx.post(GATEWAY).mock(return_value=httpx.Response(401, text="bad token bearer-secret"))
        with pytest.raises(ProviderError) as excinfo:
            generic_sender().send(phone_e164="+1", text="x")
        assert excinfo.value.kind == ErrorKind.AUTH
        assert "bearer-secret" not in (excinfo.value.detail or "")

    @respx.mock
    def test_rate_limit_maps(self):
        respx.post(GATEWAY).mock(return_value=httpx.Response(429, json={}))
        with pytest.raises(ProviderError) as excinfo:
            generic_sender().send(phone_e164="+1", text="x")
        assert excinfo.value.kind == ErrorKind.RATE_LIMIT
        assert excinfo.value.retryable is True

    @respx.mock
    def test_server_error_maps(self):
        respx.post(GATEWAY).mock(return_value=httpx.Response(502, text="bad gateway"))
        with pytest.raises(ProviderError) as excinfo:
            generic_sender().send(phone_e164="+1", text="x")
        assert excinfo.value.kind == ErrorKind.SERVER

    @respx.mock
    def test_timeout_maps(self):
        respx.post(GATEWAY).mock(side_effect=httpx.ConnectTimeout("timed out"))
        with pytest.raises(ProviderError) as excinfo:
            generic_sender().send(phone_e164="+1", text="x")
        assert excinfo.value.kind == ErrorKind.TIMEOUT


class TestVerify:
    @respx.mock
    def test_verify_ok_on_reachable_gateway(self):
        respx.post(GATEWAY).mock(return_value=httpx.Response(405, text="method not allowed"))
        assert generic_sender().verify().ok is True  # 有响应即证明可达（401/403 除外）

    @respx.mock
    def test_verify_auth_denied(self):
        respx.post(GATEWAY).mock(return_value=httpx.Response(403, json={}))
        result = generic_sender().verify()
        assert result.ok is False
        assert "auth" in result.detail

    def test_verify_without_endpoint(self):
        result = SmsHttpSender(endpoint="").verify()
        assert result.ok is False
