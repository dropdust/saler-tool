"""人群物化（FR-046/050）：筛选条件 → send_record(pending)。

规则：
- 每公司取一个最佳联系方式（首选/采购类优先）；公司无该类型联系方式则不产生记录；
- 硬排除（FR-054）：is_excluded、状态 replied/won/lost/invalid；suppression（email/phone/contact/company 全 scope）；
- 防重（FR-050）：公司在其他计划已有 sent 记录 → skipped/already_contacted（allow_resend 显式放行）；
- 物化幂等：重复执行不产生重复记录（UNIQUE(campaign_id, round_no, contact_id) 兜底）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from saler.core.compliance.suppression import is_suppressed
from saler.db.models import Campaign, CampaignChannel, Channel, Company, Contact, CrawlJob, Domain, SendRecord

EXCLUDED_COMPANY_STATUSES = ("replied", "won", "lost", "invalid")
CONTACT_TYPE_BY_CHANNEL = {"email": "email", "sms": "phone"}
PRIORITY_CATEGORIES = ("procurement", "sales", "general", "other")
KEEP_STATUSES = ("pending", "sent", "failed", "bounced")


def channel_rows(db: Session, campaign_id: int) -> list[CampaignChannel]:
    return (
        db.query(CampaignChannel)
        .filter_by(campaign_id=campaign_id)
        .order_by(CampaignChannel.role.desc(), CampaignChannel.id.asc())  # "primary" > "backup"
        .all()
    )


def required_contact_type(db: Session, campaign: Campaign) -> str:
    rows = channel_rows(db, campaign.id)
    if not rows:
        return "email"
    channel = db.get(Channel, rows[0].channel_id)
    if channel is None:
        return "email"
    return CONTACT_TYPE_BY_CHANNEL.get(channel.channel_type, "email")


def is_company_suppressed(db: Session, company: Company) -> bool:
    return is_suppressed(db, scope="company", value=str(company.id))


def is_contact_suppressed(db: Session, contact: Contact) -> bool:
    if is_suppressed(db, scope="contact", value=str(contact.id)):
        return True
    if contact.type == "email":
        return is_suppressed(db, scope="email", value=contact.value)
    if contact.type == "phone":
        return is_suppressed(db, scope="phone", value=contact.value)
    return False


def filter_companies(db: Session, audience: dict) -> list[Company]:
    """按筛选条件返回候选公司（id 升序，max_count 之前）。"""
    filters = (audience or {}).get("filters") or {}
    query = db.query(Company).filter(Company.is_excluded.is_(False))
    # 进展状态硬排除（FR-054）：已回复/已成交/已拒绝不进任何人群
    query = query.filter(Company.status.notin_(EXCLUDED_COMPANY_STATUSES))
    statuses = filters.get("status")
    if statuses:
        keep = [s for s in statuses if s not in EXCLUDED_COMPANY_STATUSES]
        query = query.filter(Company.status.in_(keep or ["__none__"]))
    if filters.get("country"):
        query = query.filter(Company.country.in_(filters["country"]))
    if filters.get("language"):
        query = query.filter(Company.language.in_(filters["language"]))
    if filters.get("source"):
        query = query.filter(Company.source.in_(filters["source"]))
    companies = query.order_by(Company.id.asc()).all()

    tags = filters.get("tags") or []
    if tags:
        wanted = set(tags)
        companies = [c for c in companies if wanted & set(c.tags or [])]

    seed_ids = set(filters.get("seed_ids") or [])
    if seed_ids:
        job_ids = [
            job.id
            for job in db.query(CrawlJob).all()
            if seed_ids & set((job.scope or {}).get("seed_ids") or [])
        ]
        allowed = {
            row.company_id
            for row in db.query(Domain)
            .filter(Domain.first_job_id.in_(job_ids), Domain.company_id.isnot(None))
            .all()
        }
        companies = [c for c in companies if c.id in allowed]

    exclude_ids = set((audience or {}).get("exclude_company_ids") or [])
    if exclude_ids:
        companies = [c for c in companies if c.id not in exclude_ids]
    return companies


def pick_contact(db: Session, company_id: int, contact_type: str) -> Contact | None:
    """最佳可发联系方式：有效性排除 + 未被抑制。"""
    rows = (
        db.query(Contact)
        .filter_by(company_id=company_id, type=contact_type)
        .filter(Contact.validity != "invalid")
        .all()
    )
    rows.sort(
        key=lambda c: (
            0 if c.is_primary else 1,
            PRIORITY_CATEGORIES.index(c.category) if c.category in PRIORITY_CATEGORIES else 9,
            c.id,
        )
    )
    for contact in rows:
        if not is_contact_suppressed(db, contact):
            return contact
    return None


def any_contact(db: Session, company_id: int, contact_type: str) -> Contact | None:
    return (
        db.query(Contact)
        .filter_by(company_id=company_id, type=contact_type)
        .order_by(Contact.is_primary.desc(), Contact.id.asc())
        .first()
    )


def already_contacted(db: Session, *, company_id: int, exclude_campaign_id: int) -> bool:
    """跨计划防重（FR-050）：公司在其他计划中已有 sent 记录。"""
    return (
        db.query(SendRecord.id)
        .filter(
            SendRecord.company_id == company_id,
            SendRecord.campaign_id != exclude_campaign_id,
            SendRecord.status == "sent",
        )
        .first()
        is not None
    )


def apply_record(
    db: Session,
    *,
    campaign_id: int,
    round_no: int,
    company: Company,
    contact: Contact,
    status: str,
    skip_reason: str | None,
) -> str:
    """幂等写台账：返回 created/updated/kept。"""
    existing = (
        db.query(SendRecord)
        .filter_by(campaign_id=campaign_id, round_no=round_no, company_id=company.id)
        .first()
    )
    if existing is not None:
        if existing.status in KEEP_STATUSES:
            return "kept"
        if existing.status == status and existing.skip_reason == skip_reason:
            return "kept"
        existing.contact_id = contact.id
        existing.contact_value = contact.value
        existing.status = status
        existing.skip_reason = skip_reason
        return "updated"
    db.add(
        SendRecord(
            campaign_id=campaign_id,
            round_no=round_no,
            company_id=company.id,
            contact_id=contact.id,
            contact_value=contact.value,
            status=status,
            skip_reason=skip_reason,
        )
    )
    return "created"


def materialize(db: Session, campaign: Campaign, *, round_no: int = 1) -> dict:
    """把人群定义物化为台账记录（pending / suppressed / skipped）。"""
    audience = campaign.audience or {}
    allow_resend = bool(audience.get("allow_resend"))
    max_count = audience.get("max_count")
    contact_type = required_contact_type(db, campaign)
    companies = filter_companies(db, audience)

    created = updated = 0
    planned_companies = 0
    for company in companies:
        if max_count is not None and planned_companies >= max_count:
            break
        contact = pick_contact(db, company.id, contact_type)
        if contact is None:
            fallback_contact = any_contact(db, company.id, contact_type)
            if fallback_contact is None:
                continue  # 无联系方式：不产生记录（计入预估缺口）
            outcome = apply_record(
                db, campaign_id=campaign.id, round_no=round_no, company=company,
                contact=fallback_contact, status="suppressed", skip_reason="suppressed",
            )
        elif is_company_suppressed(db, company):
            outcome = apply_record(
                db, campaign_id=campaign.id, round_no=round_no, company=company,
                contact=contact, status="suppressed", skip_reason="suppressed",
            )
        elif not allow_resend and already_contacted(
            db, company_id=company.id, exclude_campaign_id=campaign.id
        ):
            outcome = apply_record(
                db, campaign_id=campaign.id, round_no=round_no, company=company,
                contact=contact, status="skipped", skip_reason="already_contacted",
            )
        else:
            outcome = apply_record(
                db, campaign_id=campaign.id, round_no=round_no, company=company,
                contact=contact, status="pending", skip_reason=None,
            )
            planned_companies += 1
        if outcome == "created":
            created += 1
        elif outcome == "updated":
            updated += 1
    db.commit()
    return {**round_report(db, campaign.id, round_no), "created": created, "updated": updated}


def round_report(db: Session, campaign_id: int, round_no: int) -> dict:
    rows = db.query(SendRecord).filter_by(campaign_id=campaign_id, round_no=round_no).all()
    counts = {"planned": 0, "suppressed": 0, "skipped": 0}
    for row in rows:
        if row.status == "pending":
            counts["planned"] += 1
        elif row.status == "suppressed":
            counts["suppressed"] += 1
        elif row.status == "skipped":
            counts["skipped"] += 1
    return counts
