"""影响范围预估（FR-047）：客户数 / 条数 / 语言与通道分布 / 预计时长。

预估不改库：按当前人群与内容/通道配置干跑一遍（与物化同一套筛选规则）。
"""

from __future__ import annotations

import math

from sqlalchemy.orm import Session

from saler.core.campaigns import audience as audience_service
from saler.core.content import service as content_service
from saler.core.content.match import choose_variant
from saler.db.models import Campaign, Channel


def published_variants(db: Session, theme_id: int) -> dict[str, object]:
    """已发布语言版本（FR-037：未发布内容不可被计划选用）。"""
    out: dict[str, object] = {}
    for variant in content_service.list_published(db):
        if variant.theme_id == theme_id:
            out[variant.lang] = variant
    return out


def estimate(db: Session, campaign: Campaign) -> dict:
    audience = campaign.audience or {}
    allow_resend = bool(audience.get("allow_resend"))
    contact_type = audience_service.required_contact_type(db, campaign)
    companies = audience_service.filter_companies(db, audience)

    variants = published_variants(db, campaign.content_theme_id) if campaign.content_theme_id else {}

    audience_count = 0
    by_lang: dict[str, int] = {}
    fallback_count = 0
    suppressed = 0
    skipped = 0
    by_channel: dict[str, int] = {}
    rate_total = 0
    capacity_total = 0
    capacity_limited = False

    primary_type: str | None = None
    for campaign_channel in audience_service.channel_rows(db, campaign.id):
        channel = db.get(Channel, campaign_channel.channel_id)
        if channel is None:
            continue
        if primary_type is None:
            primary_type = channel.channel_type  # 顺序即优先级：首条为主通道
        rate_total += max(channel.rate_per_minute, 1)
        if channel.daily_limit > 0:
            capacity_total += max(channel.daily_limit - channel.used_today, 0)
            capacity_limited = True

    for company in companies:
        if audience.get("max_count") is not None and audience_count >= audience["max_count"]:
            break
        contact = audience_service.pick_contact(db, company.id, contact_type)
        if contact is None:
            if audience_service.any_contact(db, company.id, contact_type) is not None:
                suppressed += 1
            continue
        if audience_service.is_company_suppressed(db, company):
            suppressed += 1
            continue
        if not allow_resend and audience_service.already_contacted(
            db, company_id=company.id, exclude_campaign_id=campaign.id
        ):
            skipped += 1
            continue
        audience_count += 1
        key = primary_type or "email"
        by_channel[key] = by_channel.get(key, 0) + 1

        variant, _lang, fallback = choose_variant(
            variants,
            customer_lang=company.language,
            strategy=campaign.lang_strategy or "auto",
            fixed_lang=campaign.fixed_lang,
            fallback_lang=campaign.fallback_lang or "en",
        )
        lang = getattr(variant, "lang", None) or campaign.fixed_lang or "en"
        by_lang[lang] = by_lang.get(lang, 0) + 1
        if fallback:
            fallback_count += 1

    eta_minutes = _eta_minutes(audience_count, rate_total, capacity_total, capacity_limited)
    result = {
        "audience_count": audience_count,
        "message_count": audience_count,
        "by_lang": by_lang,
        "by_channel": by_channel,
        "fallback_count": fallback_count,
        "suppressed": suppressed,
        "skipped": skipped,
        "eta_minutes": eta_minutes,
        "daily_capacity": capacity_total if capacity_limited else None,
    }
    campaign.estimate = result
    db.commit()
    return result


def _eta_minutes(count: int, rate_total: int, capacity_total: int, capacity_limited: bool) -> int:
    if count <= 0:
        return 0
    within_today = not capacity_limited or count <= capacity_total
    if within_today:
        return max(1, math.ceil(count / max(rate_total, 1)))
    days = math.ceil(count / max(capacity_total, 1))
    return days * 24 * 60  # 按每日容量估算（跨日续发）
