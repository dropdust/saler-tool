"""T106 集成测试：S9 通道配置 → 连通测试 → 测试发送 → 限额与多通道用量（FR-039~044）。

全程离线：假邮件适配器经 Provider Registry 注入。
"""

from __future__ import annotations

import pytest

from saler.providers.registry import ProviderManifest, registry
from tests.fixtures.fakes.mail_fake import FakeMailSender

SECRET = "app-password-123"


@pytest.fixture()
def fake_mail() -> FakeMailSender:
    sender = FakeMailSender()
    registry.register(
        ProviderManifest(
            kind="mail",
            type_key="fake_mail_flow",
            display_name="假邮箱（S9）",
            secret_fields=("secret",),
            factory=lambda **kwargs: sender,
        )
    )
    return sender


def _channel_payload(name: str, addr: str) -> dict:
    return {
        "name": name,
        "channel_type": "email",
        "config": {
            "provider": "fake_mail_flow",
            "host": "smtp.example.com",
            "port": 465,
            "security": "ssl",
            "username": addr,
        },
        "identity": {"from_name": "Alice", "from_addr": addr, "reply_to": addr, "signature": "Alice｜外贸部"},
        "secret": SECRET,
        "daily_limit": 100,
        "rate_per_minute": 10,
        "concurrency": 1,
    }


def _create_theme_and_variant(db, *, body: str) -> tuple[int, int]:
    from saler.core.content import service as content_service

    theme = content_service.create_theme(db, name="S9 测试主题", content_type="email", master_lang="zh")
    variant = content_service.create_variant(
        db,
        theme_id=theme.id,
        lang="zh",
        subject="你好 {{company_name}}",
        body_md=body,
    )
    return theme.id, variant.id


def test_s9_channel_flow(client, db, fake_mail):
    # ① 登记邮箱通道并测试连通
    resp = client.post("/api/v1/channels", json=_channel_payload("主发件箱", "alice@example.com"))
    assert resp.status_code == 201, resp.text
    channel_id = resp.json()["id"]
    assert resp.json()["secret_set"] is True

    test_resp = client.post(f"/api/v1/channels/{channel_id}/test")
    assert test_resp.json()["ok"] is True
    assert client.get(f"/api/v1/channels/{channel_id}").json()["health"] == "healthy"

    # ② 通道级测试发送（不占日限额）
    send_resp = client.post(
        f"/api/v1/channels/{channel_id}/test-send", json={"to": "me@example.com"}
    )
    assert send_resp.status_code == 200, send_resp.text
    assert send_resp.json()["ok"] is True
    assert len(fake_mail.sent) == 1
    assert fake_mail.sent[0].to == "me@example.com"
    usage = client.get(f"/api/v1/channels/{channel_id}/usage").json()
    assert usage["total_sent"] == 1
    assert usage["used_today"] == 0  # 测试发送不消耗计划额度

    # ②b 内容版本测试发送（FR-039：真实内容 + 变量渲染）
    _, variant_id = _create_theme_and_variant(db, body="你好 {{company_name}}，欢迎垂询。")
    content_send = client.post(
        f"/api/v1/content/variants/{variant_id}/test-send",
        json={"channel_id": channel_id, "to": "me@example.com", "vars": {"company_name": "ACME"}},
    )
    assert content_send.status_code == 200, content_send.text
    assert len(fake_mail.sent) == 2
    assert "ACME" in fake_mail.sent[1].body_text
    assert "ACME" in (fake_mail.sent[1].subject or "")

    # ③ 调整每日上限
    client.put(f"/api/v1/channels/{channel_id}", json={"daily_limit": 20})
    usage = client.get(f"/api/v1/channels/{channel_id}/usage").json()
    assert usage["daily_limit"] == 20
    assert usage["remaining_today"] == 20

    # ④ 第二个发件邮箱并存，用量各自独立
    resp2 = client.post("/api/v1/channels", json=_channel_payload("备用发件箱", "backup@example.com"))
    assert resp2.status_code == 201, resp2.text
    channel2_id = resp2.json()["id"]
    usage2 = client.get(f"/api/v1/channels/{channel2_id}/usage").json()
    assert usage2["used_today"] == 0 and usage2["total_sent"] == 0
    assert usage["total_sent"] == 2  # 第一通道不受影响

    # 失败发送不留半状态：注入失败 → 台账提示错误且健康标记 failing 由人工测试更新
    fake_mail.fail_next = RuntimeError("boom")
    failed = client.post(f"/api/v1/channels/{channel_id}/test-send", json={"to": "me@example.com"})
    assert failed.status_code == 200
    assert failed.json()["ok"] is False
    # 全部响应中不出现密钥明文
    for path in (f"/api/v1/channels/{channel_id}", f"/api/v1/channels/{channel_id}/usage", "/api/v1/channels"):
        assert SECRET not in client.get(path).text


def test_daily_quota_is_recorded_by_sending_layer(client, db, fake_mail):
    """发送层记账（供 US6 发送引擎复用）：record_sent 消耗日限额并跨日重置。"""
    from saler.core.sending import channel_service

    resp = client.post("/api/v1/channels", json=_channel_payload("记账通道", "a@example.com"))
    channel_id = resp.json()["id"]
    channel = channel_service.get_channel(db, channel_id)

    channel_service.record_sent(db, channel, count=3)
    assert channel_service.get_channel(db, channel_id).used_today == 3

    # 跨日后再记一笔 → 自动重置为 1
    from datetime import UTC, datetime, timedelta

    row = channel_service.get_channel(db, channel_id)
    row.used_today_date = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    db.commit()
    channel_service.record_sent(db, row, count=1)
    assert channel_service.get_channel(db, channel_id).used_today == 1
    assert channel_service.get_channel(db, channel_id).total_sent == 4
