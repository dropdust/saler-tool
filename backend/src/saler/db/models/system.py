"""系统表：LLM/检索配置、应用设置、操作日志、通用任务、备份记录（US3）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from saler.db.base import Base, TimestampMixin, utcnow
from saler.security.fields import EncryptedText


class LlmProvider(Base, TimestampMixin):
    __tablename__ = "llm_provider"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    provider_type: Mapped[str] = mapped_column(String(30), default="openai_compatible")
    base_url: Mapped[str] = mapped_column(Text, default="https://api.openai.com/v1")
    model: Mapped[str] = mapped_column(String(100), default="")
    secret_encrypted: Mapped[str | None] = mapped_column(EncryptedText)  # API Key（只写不读回）
    params: Mapped[dict] = mapped_column(default=dict)
    is_default: Mapped[bool] = mapped_column(default=False)
    health: Mapped[str] = mapped_column(String(20), default="unknown")
    last_test_at: Mapped[datetime | None] = mapped_column()
    last_test_result: Mapped[str | None] = mapped_column(Text)


class SearchProvider(Base, TimestampMixin):
    __tablename__ = "search_provider"

    id: Mapped[int] = mapped_column(primary_key=True)
    type_key: Mapped[str] = mapped_column(String(30))  # brave/serper/tavily/custom_http
    name: Mapped[str] = mapped_column(String(100))
    secret_encrypted: Mapped[str | None] = mapped_column(EncryptedText)  # API Key（只写不读回）
    endpoint: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(default=100)  # 数字小者先调用（failover 顺序）
    enabled: Mapped[bool] = mapped_column(default=True)
    params: Mapped[dict] = mapped_column(default=dict)
    used_today: Mapped[int] = mapped_column(default=0)
    used_today_date: Mapped[str | None] = mapped_column(String(10))
    health: Mapped[str] = mapped_column(String(20), default="unknown")
    last_test_at: Mapped[datetime | None] = mapped_column()
    last_test_result: Mapped[str | None] = mapped_column(Text)
    last_error_kind: Mapped[str | None] = mapped_column(String(20))  # 最近失败类别（ErrorKind.value；004）
    last_error_at: Mapped[datetime | None] = mapped_column()         # 最近失败时间（UTC；004）


class AppSetting(Base):
    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict] = mapped_column(default=dict)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class OperationLog(Base):
    __tablename__ = "operation_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    job_type: Mapped[str] = mapped_column(String(30), index=True)
    ref_type: Mapped[str | None] = mapped_column(String(30))
    ref_id: Mapped[int | None] = mapped_column()
    level: Mapped[str] = mapped_column(String(10), default="info", index=True)
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column()

    __table_args__ = (Index("ix_operation_log_ref", "ref_type", "ref_id", "ts"),)


class Job(Base, TimestampMixin):
    """通用异步任务台账（contracts/local-api.md 的 Job 模式；crawl_job 为挖掘领域明细）。"""

    __tablename__ = "job"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    params: Mapped[dict] = mapped_column(default=dict)
    progress: Mapped[dict] = mapped_column(default=dict)
    result: Mapped[dict | None] = mapped_column()
    error: Mapped[str | None] = mapped_column(Text)
    ref_type: Mapped[str | None] = mapped_column(String(30))
    ref_id: Mapped[int | None] = mapped_column()
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()


class BackupRecord(Base):
    __tablename__ = "backup_record"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(10), default="manual")
    app_version: Mapped[str] = mapped_column(String(20), default="")
    schema_version: Mapped[str | None] = mapped_column(String(20))
    size_bytes: Mapped[int] = mapped_column(default=0)
    checksum: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
