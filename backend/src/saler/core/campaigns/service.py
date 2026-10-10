"""营销计划与轮次服务（FR-046/048/052/053）。

- 计划只能选用「已发布」内容（FR-037 门）；
- 状态机：draft → running ⇄ paused → completed / cancelled；
- 轮次：1 = 首轮（建计划时自动创建），跟进轮次 ≥2 由用户配置（间隔/条件）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Query, Session

from saler.core.content import service as content_service
from saler.core.errors import Duplicate, NotFound, ValidationFailed
from saler.db.models import Campaign, CampaignChannel, CampaignRound, Channel, SendRecord
from saler.services.operation_log import log_op

_STATUSES = ("draft", "running", "paused", "completed", "cancelled")
_ROUND_STATUSES = ("pending", "running", "done", "cancelled")
_CONDITIONS = ("no_reply_or_progress",)


def published_variant_count(db: Session, theme_id: int) -> int:
    return sum(1 for v in content_service.list_published(db) if v.theme_id == theme_id)


def create_campaign(
    db: Session,
    *,
    name: str,
    content_theme_id: int,
    channel_ids: list,
    audience: dict | None = None,
    lang_strategy: str = "auto",
    fixed_lang: str | None = None,
    fallback_lang: str | None = None,
    schedule: dict | None = None,
) -> Campaign:
    name = (name or "").strip()
    if not name:
        raise ValidationFailed("计划名称不能为空")
    if published_variant_count(db, content_theme_id) == 0:
        raise ValidationFailed("内容主题尚未发布任何语言版本：营销计划只能选用已发布内容（FR-037）")
    if lang_strategy not in ("auto", "fixed"):
        raise ValidationFailed(f"非法语言策略：{lang_strategy}")
    if lang_strategy == "fixed" and not fixed_lang:
        raise ValidationFailed("固定语言策略必须指定 fixed_lang")
    if not channel_ids:
        raise ValidationFailed("至少选择一个发送通道")

    roles: list[tuple[int, str]] = []
    for index, item in enumerate(channel_ids):
        if isinstance(item, dict):
            channel_id = int(item.get("channel_id"))
            role = item.get("role") or ("primary" if index == 0 else "backup")
        else:
            channel_id = int(item)
            role = "primary" if index == 0 else "backup"
        if role not in ("primary", "backup"):
            raise ValidationFailed(f"非法通道角色：{role}")
        roles.append((channel_id, role))
    seen: set[int] = set()
    for channel_id, _role in roles:
        if channel_id in seen:
            raise Duplicate("同一通道不能重复选择")
        seen.add(channel_id)
        channel = db.get(Channel, channel_id)
        if channel is None:
            raise NotFound(f"发送通道#{channel_id}")
        if channel.status != "active":
            raise ValidationFailed(f"通道已停用：{channel.name}")

    campaign = Campaign(
        name=name,
        content_theme_id=content_theme_id,
        audience=audience or {},
        lang_strategy=lang_strategy,
        fixed_lang=fixed_lang,
        fallback_lang=fallback_lang,
        schedule=schedule or {},
        status="draft",
    )
    db.add(campaign)
    db.flush()
    for channel_id, role in roles:
        db.add(CampaignChannel(campaign_id=campaign.id, channel_id=channel_id, role=role))
    db.add(CampaignRound(campaign_id=campaign.id, round_no=1, condition="no_reply_or_progress"))
    db.commit()
    return campaign


def get_campaign(db: Session, campaign_id: int) -> Campaign:
    row = db.get(Campaign, campaign_id)
    if row is None:
        raise NotFound("营销计划")
    return row


def list_campaigns(db: Session, *, status: str | None = None) -> Query:
    query = db.query(Campaign)
    if status:
        query = query.filter(Campaign.status == status)
    return query.order_by(Campaign.id.desc())


def update_campaign(db: Session, campaign_id: int, **fields: Any) -> Campaign:
    row = get_campaign(db, campaign_id)
    if row.status not in ("draft", "paused"):
        raise ValidationFailed("仅草稿/暂停中的计划可编辑")
    allowed = {"name", "audience", "lang_strategy", "fixed_lang", "fallback_lang", "schedule", "content_theme_id"}
    for key, value in fields.items():
        if key not in allowed or value is None:
            continue
        if key == "content_theme_id" and published_variant_count(db, int(value)) == 0:
            raise ValidationFailed("内容主题尚未发布任何语言版本")
        if key == "lang_strategy" and value not in ("auto", "fixed"):
            raise ValidationFailed(f"非法语言策略：{value}")
        setattr(row, key, value)
    db.commit()
    return row


def delete_campaign(db: Session, campaign_id: int) -> None:
    row = get_campaign(db, campaign_id)
    if row.status in ("running", "paused"):
        raise ValidationFailed("执行中的计划不可删除：请先中止")
    db.query(SendRecord).filter_by(campaign_id=row.id).delete()
    db.query(CampaignRound).filter_by(campaign_id=row.id).delete()
    db.query(CampaignChannel).filter_by(campaign_id=row.id).delete()
    db.delete(row)
    db.commit()


# ---------- 轮次 ----------


def list_rounds(db: Session, campaign_id: int) -> list[CampaignRound]:
    return (
        db.query(CampaignRound)
        .filter_by(campaign_id=campaign_id)
        .order_by(CampaignRound.round_no.asc())
        .all()
    )


def get_round(db: Session, campaign_id: int, round_no: int) -> CampaignRound:
    row = (
        db.query(CampaignRound)
        .filter_by(campaign_id=campaign_id, round_no=round_no)
        .first()
    )
    if row is None:
        raise NotFound(f"轮次 {round_no}")
    return row


def add_round(
    db: Session,
    campaign_id: int,
    *,
    round_no: int | None = None,
    content_theme_id: int | None = None,
    interval_days: int | None = None,
    condition: str = "no_reply_or_progress",
) -> CampaignRound:
    campaign = get_campaign(db, campaign_id)
    if condition not in _CONDITIONS:
        raise ValidationFailed(f"非法跟进条件：{condition}")
    if content_theme_id is not None and published_variant_count(db, content_theme_id) == 0:
        raise ValidationFailed("该轮次内容主题尚未发布任何语言版本")
    existing = list_rounds(db, campaign_id)
    if round_no is None:
        round_no = (existing[-1].round_no if existing else 0) + 1
    if any(r.round_no == round_no for r in existing):
        raise Duplicate(f"轮次已存在：{round_no}")
    if round_no < 2:
        raise ValidationFailed("轮次 1 为首轮（自动创建）；跟进轮次从 2 开始")
    row = CampaignRound(
        campaign_id=campaign.id,
        round_no=round_no,
        content_theme_id=content_theme_id,
        interval_days=interval_days,
        condition=condition,
    )
    db.add(row)
    db.commit()
    return row


def start_round(db: Session, campaign: Campaign, *, round_no: int = 1) -> CampaignRound:
    """物化人群并置为执行中（发送任务由 API 层随后启动）。"""
    if campaign.status in ("completed", "cancelled"):
        raise ValidationFailed(f"计划已{'完成' if campaign.status == 'completed' else '中止'}，不可再执行")
    round_row = get_round(db, campaign.id, round_no)
    if round_row.status == "done":
        raise ValidationFailed(f"轮次 {round_no} 已完成")
    if round_no > 1:
        from saler.core.campaigns import followup

        followup.materialize_followup(db, campaign, round_no=round_no)
    else:
        from saler.core.campaigns import audience

        audience.materialize(db, campaign, round_no=round_no)
    campaign.status = "running"
    if campaign.started_at is None:
        campaign.started_at = datetime.now(UTC)
    round_row.status = "running"
    round_row.started_at = round_row.started_at or datetime.now(UTC)
    db.commit()
    return round_row


def finish_round(db: Session, campaign: Campaign, round_no: int, stats: dict) -> None:
    round_row = get_round(db, campaign.id, round_no)
    round_row.status = "done"
    round_row.finished_at = datetime.now(UTC)
    round_row.stats = stats
    pending_next = (
        db.query(CampaignRound)
        .filter_by(campaign_id=campaign.id, status="pending")
        .filter(CampaignRound.round_no > round_no)
        .count()
    )
    if pending_next:
        campaign.status = "running"  # 等待下一轮跟进
    else:
        campaign.status = "completed"
        campaign.finished_at = datetime.now(UTC)
    recompute_stats(db, campaign)
    db.commit()


def recompute_stats(db: Session, campaign: Campaign) -> dict:
    rows = db.query(SendRecord).filter_by(campaign_id=campaign.id).all()
    stats = {"planned": len(rows), "sent": 0, "failed": 0, "bounced": 0, "skipped": 0, "suppressed": 0, "pending": 0}
    for row in rows:
        if row.status in stats:
            stats[row.status] += 1
    campaign.stats = stats
    return stats


# ---------- 状态控制 ----------


def pause_campaign(db: Session, campaign: Campaign) -> Campaign:
    if campaign.status != "running":
        raise ValidationFailed("仅执行中的计划可暂停")
    campaign.status = "paused"
    db.commit()
    return campaign


def resume_campaign(db: Session, campaign: Campaign) -> Campaign:
    if campaign.status != "paused":
        raise ValidationFailed("仅暂停中的计划可恢复")
    campaign.status = "running"
    db.commit()
    return campaign


def cancel_campaign(db: Session, campaign: Campaign) -> Campaign:
    if campaign.status in ("completed", "cancelled"):
        raise ValidationFailed("计划已结束")
    campaign.status = "cancelled"
    campaign.finished_at = datetime.now(UTC)
    for round_row in list_rounds(db, campaign.id):
        if round_row.status in ("pending", "running"):
            round_row.status = "cancelled"
            round_row.finished_at = datetime.now(UTC)
    db.commit()
    return campaign


def retry_records(db: Session, campaign_id: int, record_ids: list[int]) -> int:
    """失败/退信记录重置为 pending（唯一键不变；随后经发送任务重跑）。"""
    rows = (
        db.query(SendRecord)
        .filter(SendRecord.campaign_id == campaign_id, SendRecord.id.in_(record_ids))
        .all()
    )
    reset = 0
    for row in rows:
        if row.status in ("failed", "bounced"):
            row.status = "pending"
            row.error_code = None
            row.error_message = None
            reset += 1
    db.commit()
    return reset


def active_job(db: Session, campaign_id: int):
    from saler.db.models import Job

    return (
        db.query(Job)
        .filter(Job.ref_type == "campaign", Job.ref_id == campaign_id)
        .filter(Job.status.notin_(("completed", "failed", "cancelled")))
        .order_by(Job.id.desc())
        .first()
    )


def log_campaign_event(db: Session, campaign: Campaign, message: str, *, level: str = "info") -> None:
    log_op(db, "send", message, ref_type="campaign", ref_id=campaign.id, level=level)
