"""通道与营销计划：通道 / 计划 / 轮次 / 发送台账（US5/US6）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from saler.db.base import Base, TimestampMixin, utcnow
from saler.security.fields import EncryptedText

CHANNEL_TYPES = ("email", "sms", "social")  # social 为二期预留，v1 不可启用
CAMPAIGN_STATUSES = ("draft", "running", "paused", "completed", "cancelled")
SEND_STATUSES = ("pending", "sent", "failed", "skipped", "suppressed", "bounced")


class Channel(Base, TimestampMixin):
    __tablename__ = "channel"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    channel_type: Mapped[str] = mapped_column(String(20), default="email")
    config: Mapped[dict] = mapped_column(default=dict)          # 非敏感配置（host/port/username…）
    secret_encrypted: Mapped[str | None] = mapped_column(EncryptedText)  # 授权码/Secret（只写不读回）
    identity: Mapped[dict] = mapped_column(default=dict)        # 发件人名称/签名/回复地址
    daily_limit: Mapped[int] = mapped_column(default=200)
    rate_per_minute: Mapped[int] = mapped_column(default=20)
    concurrency: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(20), default="active")
    health: Mapped[str] = mapped_column(String(20), default="unknown")  # unknown/healthy/failing
    last_check_at: Mapped[datetime | None] = mapped_column()
    last_check_result: Mapped[str | None] = mapped_column(Text)
    used_today: Mapped[int] = mapped_column(default=0)
    used_today_date: Mapped[str | None] = mapped_column(String(10))
    total_sent: Mapped[int] = mapped_column(default=0)


class Campaign(Base, TimestampMixin):
    __tablename__ = "campaign"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    audience: Mapped[dict] = mapped_column(default=dict)
    content_theme_id: Mapped[int | None] = mapped_column(ForeignKey("content_theme.id"))
    lang_strategy: Mapped[str] = mapped_column(String(10), default="auto")  # auto/fixed
    fixed_lang: Mapped[str | None] = mapped_column(String(10))
    fallback_lang: Mapped[str | None] = mapped_column(String(10))
    schedule: Mapped[dict] = mapped_column(default=dict)
    estimate: Mapped[dict] = mapped_column(default=dict)
    stats: Mapped[dict] = mapped_column(default=dict)
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()


class CampaignChannel(Base):
    __tablename__ = "campaign_channel"
    __table_args__ = (UniqueConstraint("campaign_id", "channel_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaign.id"), index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channel.id"))
    role: Mapped[str] = mapped_column(String(10), default="primary")  # primary/backup


class CampaignRound(Base):
    __tablename__ = "campaign_round"
    __table_args__ = (UniqueConstraint("campaign_id", "round_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaign.id"), index=True)
    round_no: Mapped[int] = mapped_column()
    content_theme_id: Mapped[int | None] = mapped_column(ForeignKey("content_theme.id"))
    interval_days: Mapped[int | None] = mapped_column()
    condition: Mapped[str] = mapped_column(String(30), default="no_reply_or_progress")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    stats: Mapped[dict] = mapped_column(default=dict)
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()


class SendRecord(Base):
    """发送台账：同时是"计划人群物化 + 防重复唯一键 + 断点续发"的唯一事实来源。"""

    __tablename__ = "send_record"
    __table_args__ = (UniqueConstraint("campaign_id", "round_no", "contact_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaign.id"), index=True)
    round_no: Mapped[int] = mapped_column()
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"))
    contact_id: Mapped[int] = mapped_column(ForeignKey("contact.id"))
    contact_value: Mapped[str] = mapped_column(Text)  # 发送时联系方式快照
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channel.id"))
    content_variant_id: Mapped[int | None] = mapped_column(ForeignKey("content_variant.id"))
    content_version_id: Mapped[int | None] = mapped_column(ForeignKey("content_version.id"))
    lang_used: Mapped[str | None] = mapped_column(String(10))
    fallback_used: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    skip_reason: Mapped[str | None] = mapped_column(String(30))
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime | None] = mapped_column()
    sent_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
