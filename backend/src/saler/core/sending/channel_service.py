"""发送通道服务（FR-040~044）：CRUD / 身份与限额 / 健康 / 日用量。

- secret 只写不读回：任何返回值与日志不得含明文（FR-006）；
- used_today 按日期跨日重置（FR-044）；
- 适配器经 Provider Registry 构造（mail/sms），业务层不依赖具体服务商。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Query, Session

from saler.core.errors import Duplicate, NotFound, ValidationFailed
from saler.db.models import Channel
from saler.providers.errors import ProviderError
from saler.providers.mail.base import OutgoingMail
from saler.providers.registry import registry
from saler.security.redact import register_secret_value, scrub_text

CHANNEL_TYPES = ("email", "sms")
STATUSES = ("active", "disabled")


def _kind_of(channel_type: str) -> str:
    return "mail" if channel_type == "email" else "sms"


def _resolve_provider_type(channel_type: str, config: dict) -> str:
    return str((config or {}).get("provider") or ("smtp" if channel_type == "email" else "http_generic"))


def _validate_limits(*, daily_limit: int, rate_per_minute: int, concurrency: int) -> None:
    if daily_limit < 0:
        raise ValidationFailed("每日上限不能为负（0 = 不限制）")
    if rate_per_minute < 1:
        raise ValidationFailed("发送频率至少为 1 条/分钟")
    if concurrency < 1:
        raise ValidationFailed("并发数至少为 1")


# ---------- CRUD ----------


def list_channels(db: Session) -> Query:
    return db.query(Channel).order_by(Channel.id.asc())


def get_channel(db: Session, channel_id: int) -> Channel:
    row = db.get(Channel, channel_id)
    if row is None:
        raise NotFound("发送通道")
    return row


def create_channel(
    db: Session,
    *,
    name: str,
    channel_type: str = "email",
    config: dict | None = None,
    identity: dict | None = None,
    secret: str | None = None,
    daily_limit: int = 200,
    rate_per_minute: int = 20,
    concurrency: int = 1,
    status: str = "active",
) -> Channel:
    name = (name or "").strip()
    if not name:
        raise ValidationFailed("通道名称不能为空")
    if channel_type not in CHANNEL_TYPES:
        raise ValidationFailed(f"v1 仅支持邮件/短信通道（social 为二期预留）：{channel_type}")
    config = dict(config or {})
    if registry.get(_kind_of(channel_type), _resolve_provider_type(channel_type, config)) is None:
        raise ValidationFailed(f"未知的通道提供方：{_resolve_provider_type(channel_type, config)}")
    if status not in STATUSES:
        raise ValidationFailed(f"非法状态：{status}")
    _validate_limits(
        daily_limit=daily_limit, rate_per_minute=rate_per_minute, concurrency=concurrency
    )
    if db.query(Channel).filter_by(name=name).first():
        raise Duplicate(f"通道名称已存在：{name}")
    row = Channel(
        name=name,
        channel_type=channel_type,
        config=config,
        identity=dict(identity or {}),
        secret_encrypted=secret or None,
        daily_limit=daily_limit,
        rate_per_minute=rate_per_minute,
        concurrency=concurrency,
        status=status,
    )
    db.add(row)
    db.commit()
    return row


def update_channel(
    db: Session,
    channel_id: int,
    *,
    name: str | None = None,
    config: dict | None = None,
    identity: dict | None = None,
    secret: str | None = None,  # 显式传入非空才替换（留空 = 保留原密钥）
    daily_limit: int | None = None,
    rate_per_minute: int | None = None,
    concurrency: int | None = None,
    status: str | None = None,
) -> Channel:
    row = get_channel(db, channel_id)
    if name is not None:
        name = name.strip()
        if not name:
            raise ValidationFailed("通道名称不能为空")
        other = db.query(Channel).filter(Channel.name == name, Channel.id != row.id).first()
        if other:
            raise Duplicate(f"通道名称已存在：{name}")
        row.name = name
    if config is not None:
        config = dict(config)
        if registry.get(_kind_of(row.channel_type), _resolve_provider_type(row.channel_type, config)) is None:
            raise ValidationFailed("未知的通道提供方")
        row.config = config
    if identity is not None:
        row.identity = dict(identity)
    if secret:
        row.secret_encrypted = secret
    if status is not None:
        if status not in STATUSES:
            raise ValidationFailed(f"非法状态：{status}")
        row.status = status
    _validate_limits(
        daily_limit=daily_limit if daily_limit is not None else row.daily_limit,
        rate_per_minute=rate_per_minute if rate_per_minute is not None else row.rate_per_minute,
        concurrency=concurrency if concurrency is not None else row.concurrency,
    )
    if daily_limit is not None:
        row.daily_limit = daily_limit
    if rate_per_minute is not None:
        row.rate_per_minute = rate_per_minute
    if concurrency is not None:
        row.concurrency = concurrency
    db.commit()
    return row


def delete_channel(db: Session, channel_id: int) -> None:
    row = get_channel(db, channel_id)
    db.delete(row)
    db.commit()


# ---------- 适配器与健康 ----------


def build_adapter(channel: Channel):
    """由通道配置构造适配器（解密后仅存于内存，不回显）。"""
    kind = _kind_of(channel.channel_type)
    type_key = _resolve_provider_type(channel.channel_type, channel.config or {})
    manifest = registry.get(kind, type_key)
    if manifest is None or manifest.factory is None:
        raise ValidationFailed(f"适配器不可用：{type_key}")
    secret = channel.secret_encrypted
    register_secret_value(secret)
    return manifest.factory(
        config=dict(channel.config or {}),
        secret=secret,
        identity=dict(channel.identity or {}),
    )


def _mark_health(db: Session, channel: Channel, *, ok: bool, detail: str) -> None:
    channel.health = "healthy" if ok else "failing"
    channel.last_check_at = datetime.now(UTC)
    channel.last_check_result = scrub_text(detail or "")[:2000]
    db.commit()


def test_channel(db: Session, channel: Channel) -> dict:
    """连通性测试（FR-041）：调用适配器 verify 并落地健康状态。"""
    adapter = build_adapter(channel)
    result = adapter.verify()
    _mark_health(db, channel, ok=bool(result.ok), detail=result.detail or "")
    return {"ok": bool(result.ok), "detail": scrub_text(result.detail or "")}


# ---------- 用量 ----------


def ensure_used_today(db: Session, channel: Channel) -> None:
    """跨日重置日用量（FR-044）。"""
    today = datetime.now(UTC).date().isoformat()
    if channel.used_today_date != today:
        channel.used_today = 0
        channel.used_today_date = today
        db.commit()


def record_sent(db: Session, channel: Channel, *, count: int = 1) -> None:
    """发送层记账（正式发送消耗日限额；由 US6 发送引擎调用）。"""
    ensure_used_today(db, channel)
    channel.used_today = (channel.used_today or 0) + count
    channel.total_sent = (channel.total_sent or 0) + count
    db.commit()


def usage(db: Session, channel: Channel) -> dict:
    ensure_used_today(db, channel)
    remaining = (
        max(channel.daily_limit - channel.used_today, 0) if channel.daily_limit > 0 else None
    )
    return {
        "used_today": channel.used_today,
        "daily_limit": channel.daily_limit,
        "rate_per_minute": channel.rate_per_minute,
        "concurrency": channel.concurrency,
        "remaining_today": remaining,
        "total_sent": channel.total_sent,
        "health": channel.health,
        "status": channel.status,
        "last_check_at": channel.last_check_at.isoformat() if channel.last_check_at else None,
        "last_check_result": scrub_text(channel.last_check_result or "") or None,
    }


# ---------- 测试发送（FR-039/S9②；不消耗日限额） ----------


def _perform_send(db: Session, channel: Channel, *, send_call) -> dict:
    try:
        result = send_call(build_adapter(channel))
    except ProviderError as err:
        _mark_health(db, channel, ok=False, detail=f"{err.kind.value}: {err}")
        return {"ok": False, "detail": scrub_text(str(err))}
    except Exception as exc:  # noqa: BLE001 —— 测试发送端点须可读失败而非 500
        _mark_health(db, channel, ok=False, detail=f"unknown: {type(exc).__name__}: {exc}")
        return {"ok": False, "detail": f"发送失败：{scrub_text(str(exc))}"}
    _mark_health(db, channel, ok=True, detail=f"测试发送成功（{result.message_id}）")
    channel.total_sent = (channel.total_sent or 0) + 1
    db.commit()
    return {"ok": True, "message_id": result.message_id}


def _identity_mail(channel: Channel, *, to: str, subject: str, body_text: str) -> OutgoingMail:
    identity = channel.identity or {}
    return OutgoingMail(
        from_name=identity.get("from_name") or "",
        from_addr=identity.get("from_addr") or "",
        reply_to=identity.get("reply_to"),
        to=to,
        subject=subject,
        body_text=body_text,
        body_html=f"<p>{body_text}</p>",
    )


def test_send_canned(db: Session, channel: Channel, *, to: str) -> dict:
    """通道级测试发送：内置样例文案（S9②）。"""
    if channel.channel_type == "email":
        message = _identity_mail(
            channel, to=to, subject="【测试】销售获客工具", body_text="这是一封测试邮件：通道配置正确，可以开始发送。"
        )
        return _perform_send(db, channel, send_call=lambda adapter: adapter.send(message=message))
    identity = channel.identity or {}
    return _perform_send(
        db,
        channel,
        send_call=lambda adapter: adapter.send(
            phone_e164=to, text="【测试】销售获客工具：通道配置正确。", signature=identity.get("signature")
        ),
    )


def send_content_test(
    db: Session,
    channel: Channel,
    *,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> dict:
    """内容版本测试发送（FR-039）：渲染后的真实内容，试发与正式发送走同一适配器接口。"""
    if channel.channel_type == "email":
        identity_mail = _identity_mail(channel, to=to, subject=subject or "（无主题）", body_text=body_text)
        if body_html:
            identity_mail.body_html = body_html
        return _perform_send(
            db, channel, send_call=lambda adapter: adapter.send(message=identity_mail)
        )
    identity = channel.identity or {}
    text = f"{subject} {body_text}".strip() if subject else body_text
    return _perform_send(
        db,
        channel,
        send_call=lambda adapter: adapter.send(
            phone_e164=to, text=text, signature=identity.get("signature")
        ),
    )
