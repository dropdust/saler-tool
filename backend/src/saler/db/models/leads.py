"""线索与挖掘：任务 / 候选域名 / 公司 / 联系方式 / 黑名单 / 排除规则（US2/US6）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from saler.db.base import Base, TimestampMixin, utcnow

DOMAIN_STATUSES = ("pending", "fetching", "done", "no_contact", "failed")
COMPANY_STATUSES = ("new", "contacted", "replied", "won", "lost", "invalid")
CONTACT_TYPES = (
    "email", "phone", "whatsapp", "facebook", "linkedin", "x", "instagram", "wechat", "other",
)
CONTACT_CATEGORIES = ("procurement", "sales", "general", "other")


class CrawlJob(Base, TimestampMixin):
    """挖掘任务（US2 领域明细；通用任务台账见 system.Job）。"""

    __tablename__ = "crawl_job"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200))
    scope: Mapped[dict] = mapped_column(default=dict)   # {seed_ids | filters}
    config: Mapped[dict] = mapped_column(default=dict)  # 检索渠道/并发/频率/代理快照
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    stats: Mapped[dict] = mapped_column(default=dict)
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()


class Domain(Base, TimestampMixin):
    __tablename__ = "domain"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True)
    homepage_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(50))
    first_job_id: Mapped[int | None] = mapped_column(ForeignKey("job.id"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("company.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    fetched_pages: Mapped[int] = mapped_column(default=0)
    country: Mapped[str | None] = mapped_column(String(2))
    country_source: Mapped[str | None] = mapped_column(String(20))  # cctld/query_market/address/phone_prefix/manual
    language: Mapped[str | None] = mapped_column(String(10))
    language_source: Mapped[str | None] = mapped_column(String(20))  # html_lang/detect/manual
    is_excluded: Mapped[bool] = mapped_column(default=False, index=True)
    exclusion_reason: Mapped[str | None] = mapped_column(Text)
    last_crawled_at: Mapped[datetime | None] = mapped_column()


class Company(Base, TimestampMixin):
    __tablename__ = "company"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(300))
    country: Mapped[str | None] = mapped_column(String(2))
    language: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    is_excluded: Mapped[bool] = mapped_column(default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(default=list)
    source: Mapped[str] = mapped_column(String(20), default="crawl")  # crawl/import
    note: Mapped[str | None] = mapped_column(Text)


class Contact(Base, TimestampMixin):
    __tablename__ = "contact"
    __table_args__ = (UniqueConstraint("company_id", "type", "value_normalized"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"), index=True)
    domain_id: Mapped[int | None] = mapped_column(ForeignKey("domain.id"))
    type: Mapped[str] = mapped_column(String(20), index=True)
    value: Mapped[str] = mapped_column(Text)
    value_normalized: Mapped[str] = mapped_column(Text, index=True)
    category: Mapped[str] = mapped_column(String(20), default="general")
    source_url: Mapped[str | None] = mapped_column(Text)
    validity: Mapped[str] = mapped_column(String(20), default="valid")  # valid/suspicious/invalid
    is_primary: Mapped[bool] = mapped_column(default=False)


class Suppression(Base):
    __tablename__ = "suppression"
    __table_args__ = (UniqueConstraint("scope", "target_value"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(20))  # email/phone/contact/company/domain
    target_value: Mapped[str] = mapped_column(Text)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("company.id"))
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contact.id"))
    reason: Mapped[str] = mapped_column(String(20))  # unsubscribed/bounced/manual/complaint/invalid
    source: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ExclusionRule(Base, TimestampMixin):
    __tablename__ = "exclusion_rule"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_type: Mapped[str] = mapped_column(String(20))  # keyword/domain/list
    pattern: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(default=True)
    note: Mapped[str | None] = mapped_column(Text)
