"""营销内容：主题 / 语言版本 / 版本（US4）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from saler.db.base import Base, TimestampMixin, utcnow

VARIANT_STATUSES = ("draft", "review", "published", "archived")


class ContentTheme(Base, TimestampMixin):
    __tablename__ = "content_theme"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), unique=True)
    content_type: Mapped[str] = mapped_column(String(20), default="email")  # email/sms/social_message
    master_lang: Mapped[str] = mapped_column(String(10), default="zh")
    description: Mapped[str | None] = mapped_column(Text)


class ContentVariant(Base, TimestampMixin):
    __tablename__ = "content_variant"
    __table_args__ = (UniqueConstraint("theme_id", "lang"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    theme_id: Mapped[int] = mapped_column(ForeignKey("content_theme.id"), index=True)
    lang: Mapped[str] = mapped_column(String(10))
    parent_variant_id: Mapped[int | None] = mapped_column(ForeignKey("content_variant.id"))
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual/llm_assisted/llm_translated
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    # 当前版本指针：不加 FK 约束以避免与 content_version 循环依赖（见 data-model.md C2）
    current_version_id: Mapped[int | None] = mapped_column()


class ContentVersion(Base):
    __tablename__ = "content_version"
    __table_args__ = (UniqueConstraint("variant_id", "version_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("content_variant.id"), index=True)
    version_no: Mapped[int] = mapped_column()
    subject: Mapped[str | None] = mapped_column(Text)
    body_md: Mapped[str] = mapped_column(Text, default="")
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    variables: Mapped[list] = mapped_column(default=list)
    change_note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
