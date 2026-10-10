"""计划报表与导出（FR-048/053）：按通道/语言/轮次统计 + XLSX 台账导出。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy.orm import Session

from saler.core.campaigns import service as campaign_service
from saler.db.models import Channel, Company, SendRecord

STATUSES = ("pending", "sent", "failed", "bounced", "skipped", "suppressed")


def _empty_bucket() -> dict:
    return {status: 0 for status in STATUSES}


def report(db: Session, campaign_id: int) -> dict:
    campaign = campaign_service.get_campaign(db, campaign_id)
    records = (
        db.query(SendRecord)
        .filter_by(campaign_id=campaign_id)
        .order_by(SendRecord.round_no.asc(), SendRecord.id.asc())
        .all()
    )
    channel_names = {row.id: row.name for row in db.query(Channel).all()}

    totals = _empty_bucket()
    by_channel: dict[str, dict] = {}
    by_lang: dict[str, dict] = {}
    by_round: dict[str, dict] = {}
    for row in records:
        totals[row.status] = totals.get(row.status, 0) + 1
        channel_key = channel_names.get(row.channel_id, "未发送")
        by_channel.setdefault(channel_key, _empty_bucket())[row.status] += 1
        lang_key = row.lang_used or "（未发送）"
        by_lang.setdefault(lang_key, _empty_bucket())[row.status] += 1
        round_key = str(row.round_no)
        by_round.setdefault(round_key, _empty_bucket())[row.status] += 1

    return {
        "campaign": {
            "id": campaign.id,
            "name": campaign.name,
            "status": campaign.status,
            "started_at": campaign.started_at.isoformat() if campaign.started_at else None,
            "finished_at": campaign.finished_at.isoformat() if campaign.finished_at else None,
        },
        "totals": totals,
        "by_channel": by_channel,
        "by_lang": by_lang,
        "by_round": by_round,
    }


def export_xlsx(db: Session, campaign_id: int, *, out_dir: Path) -> Path:
    """导出为 XLSX：统计 Sheet（按通道/语言/轮次）+ 台账 Sheet（逐条记录）。"""
    data = report(db, campaign_id)
    campaign = campaign_service.get_campaign(db, campaign_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"campaign_{campaign_id}_report_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.xlsx"

    company_names = {row.id: (row.name or f"#{row.id}") for row in db.query(Company).all()}
    channel_names = {row.id: row.name for row in db.query(Channel).all()}

    wb = Workbook()
    stats_sheet = wb.active
    stats_sheet.title = "统计"
    stats_sheet.append(["计划", campaign.name, "状态", campaign.status])
    stats_sheet.append([])
    stats_sheet.append(["总计", *STATUSES])
    stats_sheet.append(["", *[data["totals"].get(s, 0) for s in STATUSES]])
    for group_name, group in (("按通道", data["by_channel"]), ("按语言", data["by_lang"]), ("按轮次", data["by_round"])):
        stats_sheet.append([])
        stats_sheet.append([group_name, *STATUSES])
        for key, bucket in group.items():
            stats_sheet.append([key, *[bucket.get(s, 0) for s in STATUSES]])

    ledger = wb.create_sheet("台账")
    ledger.append(
        ["轮次", "公司", "联系方式", "通道", "语言", "回退", "状态", "跳过原因",
         "错误码", "错误信息", "发送时间", "内容版本"]
    )
    for row in (
        db.query(SendRecord)
        .filter_by(campaign_id=campaign_id)
        .order_by(SendRecord.round_no.asc(), SendRecord.id.asc())
        .all()
    ):
        ledger.append(
            [
                row.round_no,
                company_names.get(row.company_id, ""),
                row.contact_value,
                channel_names.get(row.channel_id, ""),
                row.lang_used or "",
                "是" if row.fallback_used else "",
                row.status,
                row.skip_reason or "",
                row.error_code or "",
                row.error_message or "",
                row.sent_at.isoformat() if row.sent_at else "",
                row.content_version_id or "",
            ]
        )
    wb.save(path)
    return path
