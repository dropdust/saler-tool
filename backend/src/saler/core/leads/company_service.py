"""公司/联系方式服务（FR-022/027）：域名归并、去重落库、合并与修订。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from saler.core.errors import NotFound, ValidationFailed
from saler.db.models import Company, Contact, Domain, SendRecord
from saler.db.models.leads import COMPANY_STATUSES

COMPANY_FIELDS = {"name", "country", "language", "status", "tags", "note", "is_excluded", "exclusion_reason"}

#: 获进展/无效状态：状态变更即时作用于跟进与排除逻辑（FR-054）
PROGRESS_EXCLUDED_STATUSES = ("replied", "won", "lost", "invalid")


def mark_status(db: Session, company_id: int, status: str) -> Company:
    """客户状态推进（FR-054）：标记已回复/已成交/已拒绝/无效时立即终止其待发记录。

    待发（pending）记录就地置为 skipped（台账留痕，重试不误发）；
    后续跟进轮次与新计划的人群圈选同样即时排除。
    """
    if status not in COMPANY_STATUSES:
        raise ValidationFailed(f"非法客户状态：{status}")
    company = get_company(db, company_id)
    company.status = status
    if status in PROGRESS_EXCLUDED_STATUSES:
        pending = (
            db.query(SendRecord)
            .filter_by(company_id=company_id, status="pending")
            .all()
        )
        for record in pending:
            record.status = "skipped"
            record.skip_reason = f"company_{status}"
    db.commit()
    return company


def get_or_create_company_for_domain(
    db: Session, *, domain_row: Domain, name: str | None = None
) -> tuple[Company, bool]:
    """按域名归并公司：已有归属则复用（补名称），否则新建并回填 domain.company_id。"""
    if domain_row.company_id:
        company = db.get(Company, domain_row.company_id)
        if company is not None:
            if name and not company.name:
                company.name = name
                db.commit()
            return company, False
    company = Company(
        name=(name or domain_row.domain),
        country=domain_row.country,
        language=domain_row.language,
        source="crawl",
    )
    db.add(company)
    db.commit()
    domain_row.company_id = company.id
    db.commit()
    return company, True


def upsert_contact(
    db: Session,
    *,
    company_id: int,
    domain_id: int | None = None,
    type_: str,
    value: str,
    value_normalized: str,
    category: str = "general",
    source_url: str | None = None,
    validity: str = "valid",
) -> tuple[Contact, bool]:
    """同公司同类型同值唯一（Unique(company_id,type,value_normalized)）。"""
    existing = (
        db.query(Contact)
        .filter_by(company_id=company_id, type=type_, value_normalized=value_normalized)
        .first()
    )
    if existing is not None:
        return existing, False
    contact = Contact(
        company_id=company_id,
        domain_id=domain_id,
        type=type_,
        value=value,
        value_normalized=value_normalized,
        category=category,
        source_url=source_url,
        validity=validity,
    )
    db.add(contact)
    db.commit()
    return contact, True


def create_company_standalone(
    db: Session,
    *,
    name: str | None = None,
    country: str | None = None,
    language: str | None = None,
    source: str = "import",
) -> Company:
    company = Company(name=name, country=country, language=language, source=source)
    db.add(company)
    db.commit()
    return company


def find_company_by_domain(db: Session, domain: str) -> Company | None:
    row = db.query(Domain).filter_by(domain=domain).first()
    if row is None or row.company_id is None:
        return None
    return db.get(Company, row.company_id)


def find_company_by_email(db: Session, email_normalized: str) -> Company | None:
    contact = (
        db.query(Contact)
        .filter_by(type="email", value_normalized=email_normalized)
        .first()
    )
    if contact is None:
        return None
    return db.get(Company, contact.company_id)


def get_company(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise NotFound("客户公司")
    return company


def primary_domain(db: Session, company_id: int) -> Domain | None:
    return (
        db.query(Domain)
        .filter_by(company_id=company_id)
        .order_by(Domain.id.asc())
        .first()
    )


def update_company(db: Session, company_id: int, **fields: Any) -> Company:
    company = get_company(db, company_id)
    unknown = set(fields) - COMPANY_FIELDS
    if unknown:
        raise ValidationFailed(f"不允许修改字段：{sorted(unknown)}")
    for key, value in fields.items():
        if value is not None:
            setattr(company, key, value)
    db.commit()
    return company


def list_companies(
    db: Session,
    *,
    q: str | None = None,
    country: str | None = None,
    language: str | None = None,
    status: str | None = None,
    excluded: bool | None = None,
) -> Query:
    query = db.query(Company)
    if q:
        query = query.outerjoin(Domain, Domain.company_id == Company.id).filter(
            or_(Company.name.contains(q), Domain.domain.contains(q))
        ).distinct()
    if country:
        query = query.filter(Company.country == country)
    if language:
        query = query.filter(Company.language == language)
    if status:
        query = query.filter(Company.status == status)
    if excluded is not None:
        query = query.filter(Company.is_excluded.is_(excluded))
    return query.order_by(Company.id.desc())


def merge_companies(db: Session, *, target_id: int, source_ids: list[int]) -> dict:
    """把 source 公司并入 target：域名与联系方式转移（去重）后删除 source。"""
    target = get_company(db, target_id)
    moved_domains = moved_contacts = 0
    for source_id in source_ids:
        if source_id == target_id:
            continue
        source = get_company(db, source_id)
        for domain_row in db.query(Domain).filter_by(company_id=source.id).all():
            domain_row.company_id = target.id
            moved_domains += 1
        for contact in db.query(Contact).filter_by(company_id=source.id).all():
            duplicate = (
                db.query(Contact)
                .filter_by(
                    company_id=target.id,
                    type=contact.type,
                    value_normalized=contact.value_normalized,
                )
                .first()
            )
            if duplicate is not None:
                db.delete(contact)
            else:
                contact.company_id = target.id
                moved_contacts += 1
        # 黑名单关联同步到目标公司
        from saler.db.models import Suppression

        db.query(Suppression).filter_by(company_id=source.id).update(
            {Suppression.company_id: target.id}, synchronize_session=False
        )
        db.delete(source)
    db.commit()
    return {"domains_moved": moved_domains, "contacts_moved": moved_contacts}
