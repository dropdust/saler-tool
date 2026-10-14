"""候选域名共享服务（US1 回灌与本工具挖掘共用；domain 唯一）。

含检索溯源出口：命中计数（列表批量）与命中明细（详情，query 词/任务/首次命中时间）。
"""

from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from saler.core.errors import NotFound, ValidationFailed
from saler.db.models import Domain, DomainSeedHit, Seed


def normalize_domain(raw: str) -> str | None:
    """从 URL/裸域名提取规范域名（小写、去 www、去端口）。

    返回 None 表示不是可用的 http(s) 域名。
    """
    value = (raw or "").strip()
    if not value:
        return None
    if "://" not in value:
        value = "http://" + value
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    if "." not in host or " " in host:
        return None
    return host or None


def get_or_create_domain(
    db: Session,
    *,
    domain: str,
    homepage_url: str | None = None,
    title: str | None = None,
    snippet: str | None = None,
    source: str | None = None,
    job_id: int | None = None,
) -> tuple[Domain, bool]:
    """按唯一域名取用或创建（pending）。返回 (domain, created)。"""
    normalized = normalize_domain(domain)
    if normalized is None:
        raise ValidationFailed(f"非法域名：{domain}")
    row = db.query(Domain).filter_by(domain=normalized).first()
    if row is not None:
        return row, False
    row = Domain(
        domain=normalized,
        homepage_url=homepage_url,
        title=title,
        snippet=snippet,
        source=source,
        first_job_id=job_id,
        status="pending",
    )
    db.add(row)
    db.commit()
    return row, True


def get_domain(db: Session, domain_id: int) -> Domain:
    row = db.get(Domain, domain_id)
    if row is None:
        raise NotFound("候选域名")
    return row


def list_domains(
    db: Session,
    *,
    status: str | None = None,
    excluded: bool | None = None,
    country: str | None = None,
    q: str | None = None,
) -> Query:
    query = db.query(Domain)
    if status:
        query = query.filter(Domain.status == status)
    if excluded is not None:
        query = query.filter(Domain.is_excluded.is_(excluded))
    if country:
        query = query.filter(Domain.country == country)
    if q:
        query = query.filter(Domain.domain.contains(q))
    return query.order_by(Domain.id.desc())


def seed_hit_counts(db: Session, domain_ids: list[int]) -> dict[int, int]:
    """批量取域名→命中种子数（列表页用；无命中的域名不在返回中）。"""
    if not domain_ids:
        return {}
    rows = (
        db.query(DomainSeedHit.domain_id, func.count(DomainSeedHit.id))
        .filter(DomainSeedHit.domain_id.in_(domain_ids))
        .group_by(DomainSeedHit.domain_id)
        .all()
    )
    return {domain_id: count for domain_id, count in rows}


def list_seed_hits(db: Session, domain_id: int) -> list[tuple[Seed, DomainSeedHit]]:
    """域名命中明细（query 词 + 任务 + 首次命中时间），新→旧；无命中返回空列表。"""
    return (
        db.query(Seed, DomainSeedHit)
        .join(DomainSeedHit, DomainSeedHit.seed_id == Seed.id)
        .filter(DomainSeedHit.domain_id == domain_id)
        .order_by(DomainSeedHit.first_seen_at.desc(), DomainSeedHit.id.desc())
        .all()
    )


def update_domain(db: Session, domain_id: int, **fields) -> Domain:
    row = get_domain(db, domain_id)
    allowed = {"country", "country_source", "language", "language_source", "is_excluded", "exclusion_reason"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValidationFailed(f"不允许修改字段：{sorted(unknown)}")
    for key, value in fields.items():
        if value is not None:
            setattr(row, key, value)
    db.commit()
    return row
