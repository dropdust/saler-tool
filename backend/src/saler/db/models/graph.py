"""种子知识库：图谱节点 / 词表 / 关系（US1）。"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from saler.db.base import Base, TimestampMixin

NODE_TYPES = ("product_line", "persona", "market", "org")
RELATION_TYPES = (
    "product_fit_persona",     # 产品线×客户角色适配
    "product_target_market",   # 产品重点市场
    "org_in_market",           # 机构实体归属市场
    "org_has_persona",         # 机构实体属于某客户角色
)
REVIEW_STATUSES = ("pending", "approved", "rejected")


class GraphNode(Base, TimestampMixin):
    __tablename__ = "graph_node"
    __table_args__ = (UniqueConstraint("node_type", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    node_type: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("graph_node.id"))
    region: Mapped[str | None] = mapped_column(String(50))
    attributes: Mapped[dict] = mapped_column(default=dict)
    confidence: Mapped[float | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(20), default="manual")
    evidence_url: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(20), default="approved", index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")


class NodeTerm(Base):
    __tablename__ = "node_term"
    __table_args__ = (UniqueConstraint("node_id", "lang", "term_type", "term"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("graph_node.id"), index=True)
    lang: Mapped[str] = mapped_column(String(10))
    term: Mapped[str] = mapped_column(String(300))
    term_type: Mapped[str] = mapped_column(String(20), default="name")  # name/alias/synonym/term
    source: Mapped[str] = mapped_column(String(20), default="manual")
    review_status: Mapped[str] = mapped_column(String(20), default="approved")


class GraphEdge(Base, TimestampMixin):
    __tablename__ = "graph_edge"
    __table_args__ = (UniqueConstraint("from_node_id", "to_node_id", "relation_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    from_node_id: Mapped[int] = mapped_column(ForeignKey("graph_node.id"), index=True)
    to_node_id: Mapped[int] = mapped_column(ForeignKey("graph_node.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(20), default="manual")
    review_status: Mapped[str] = mapped_column(String(20), default="approved")
