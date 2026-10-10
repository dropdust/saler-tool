"""候选域名共享服务（US1 回灌与本工具挖掘共用；domain 唯一）。"""

from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy.orm import Query, Session

from saler.core.errors import NotFound, ValidationFailed
from saler.db.models import Domain


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
