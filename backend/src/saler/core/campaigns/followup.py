"""多轮跟进调度（FR-052）：未获回复/进展的客户按间隔进入下一轮。

条件 ``no_reply_or_progress``（默认）：上一轮已发送、且公司状态不是 已回复/已成交/已拒绝/无效
（即未被标记进展）的客户进入本轮；标记进展者即时排除（FR-054）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from saler.core.campaigns import audience as audience_service
from saler.db.models import Campaign, CampaignRound, Company, SendRecord


def materialize_followup(db: Session, campaign: Campaign, *, round_no: int) -> dict:
    """跟进轮次物化：上一轮 sent 的客户中，未获进展者生成 pending 记录。"""
    if round_no <= 1:
        raise ValueError("跟进轮次从 2 开始")
    previous = round_no - 1
    sent_rows = (
        db.query(SendRecord)
        .filter_by(campaign_id=campaign.id, round_no=previous, status="sent")
        .order_by(SendRecord.id.asc())
        .all()
    )
    contact_type = audience_service.required_contact_type(db, campaign)
    created = 0
    for row in sent_rows:
        company = db.get(Company, row.company_id)
        if company is None:
            continue
        if company.status in audience_service.EXCLUDED_COMPANY_STATUSES:
            continue  # 已获进展/无效 → 不进下一轮（FR-052/054）
        if audience_service.is_company_suppressed(db, company):
            continue
        contact = audience_service.pick_contact(db, company.id, contact_type)
        if contact is None:
            continue
        outcome = audience_service.apply_record(
            db,
            campaign_id=campaign.id,
            round_no=round_no,
            company=company,
            contact=contact,
            status="pending",
            skip_reason=None,
        )
        if outcome == "created":
            created += 1
    db.commit()
    return {**audience_service.round_report(db, campaign.id, round_no), "created": created}


def due_rounds(db: Session, *, now: datetime | None = None) -> list[tuple[Campaign, CampaignRound]]:
    """到期应执行的跟进轮次（供调度器/维护任务轮询；interval_days=None 表示手动触发）。"""
    now = now or datetime.now(UTC)
    out: list[tuple[Campaign, CampaignRound]] = []
    for round_row in (
        db.query(CampaignRound)
        .filter(CampaignRound.round_no > 1, CampaignRound.status == "pending")
        .order_by(CampaignRound.id.asc())
        .all()
    ):
        campaign = db.get(Campaign, round_row.campaign_id)
        if campaign is None or campaign.status not in ("running", "paused"):
            continue
        if round_row.interval_days is None:
            continue
        previous = (
            db.query(CampaignRound)
            .filter_by(campaign_id=campaign.id, round_no=round_row.round_no - 1)
            .first()
        )
        if previous is None or previous.status != "done" or previous.finished_at is None:
            continue
        due_at = previous.finished_at + timedelta(days=round_row.interval_days)
        if due_at <= now:
            out.append((campaign, round_row))
    return out
