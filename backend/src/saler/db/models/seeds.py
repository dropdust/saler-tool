"""种子 / 命中归因 / 校验记录（US1）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from saler.db.base import Base, TimestampMixin, utcnow

SEED_STATUSES = ("pending", "running", "done", "invalid")


class Seed(Base, TimestampMixin):
    __tablename__ = "seed"

    id: Mapped[int] = mapped_column(primary_key=True)
    query: Mapped[str] = mapped_column(String(500), unique=True)
    lang: Mapped[str] = mapped_column(String(10), default="en")
    product_line_id: Mapped[int | None] = mapped_column(ForeignKey("graph_node.id"))
    persona_id: Mapped[int | None] = mapped_column(ForeignKey("graph_node.id"))
    market_id: Mapped[int | None] = mapped_column(ForeignKey("graph_node.id"))
    priority: Mapped[int] = mapped_column(default=2)  # 1 高 / 2 中 / 3 低
    batch: Mapped[str | None] = mapped_column(String(50), index=True)
    source_node_id: Mapped[int | None] = mapped_column(ForeignKey("graph_node.id"))
    template: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual/llm/search/import
    confidence: Mapped[float | None] = mapped_column()
    review_status: Mapped[str] = mapped_column(String(20), default="approved", index=True)
    n_candidates: Mapped[int] = mapped_column(default=0)
    n_contacts: Mapped[int] = mapped_column(default=0)
    note: Mapped[str | None] = mapped_column(Text)
    last_run_at: Mapped[datetime | None] = mapped_column()


class DomainSeedHit(Base):
    """种子→域名命中归因（产量以本表 COUNT(DISTINCT) 校准）。"""

    __tablename__ = "domain_seed_hit"
    __table_args__ = (UniqueConstraint("domain_id", "seed_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domain.id"), index=True)
    seed_id: Mapped[int] = mapped_column(ForeignKey("seed.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("job.id"))
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)


class ValidationRecord(Base):
    """种子/实体的真实性校验历史（追加式，FR-014）。"""

    __tablename__ = "validation_record"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str] = mapped_column(String(20))  # seed / graph_node
    target_id: Mapped[int] = mapped_column(index=True)
    provider: Mapped[str] = mapped_column(String(50))  # wikipedia / search / manual
    status: Mapped[str] = mapped_column(String(20))  # found / not_found / ambiguous / error
    confidence: Mapped[float | None] = mapped_column()
    evidence_url: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(default=utcnow)
