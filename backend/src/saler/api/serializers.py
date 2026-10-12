"""ORM → JSON 序列化。

- datetime 一律 ISO 8601；密钥类字段绝不进入输出（只写不读回，FR-006）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def job_to_dict(job) -> dict[str, Any]:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "name": job.name,
        "status": job.status,
        "progress": job.progress or {},
        "result": job.result,
        "error": job.error,
        "ref_type": job.ref_type,
        "ref_id": job.ref_id,
        "created_at": iso(job.created_at),
        "started_at": iso(job.started_at),
        "finished_at": iso(job.finished_at),
    }


def log_to_dict(entry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "ts": iso(entry.ts),
        "job_type": entry.job_type,
        "ref_type": entry.ref_type,
        "ref_id": entry.ref_id,
        "level": entry.level,
        "message": entry.message,
        "payload": entry.payload,
    }


def node_to_dict(node) -> dict[str, Any]:
    return {
        "id": node.id,
        "node_type": node.node_type,
        "name": node.name,
        "parent_id": node.parent_id,
        "region": node.region,
        "attributes": node.attributes or {},
        "confidence": node.confidence,
        "source": node.source,
        "evidence_url": node.evidence_url,
        "review_status": node.review_status,
        "status": node.status,
    }


def term_to_dict(term) -> dict[str, Any]:
    return {
        "id": term.id,
        "node_id": term.node_id,
        "lang": term.lang,
        "term": term.term,
        "term_type": term.term_type,
        "source": term.source,
        "review_status": term.review_status,
    }


def edge_to_dict(edge) -> dict[str, Any]:
    return {
        "id": edge.id,
        "from_node_id": edge.from_node_id,
        "to_node_id": edge.to_node_id,
        "relation_type": edge.relation_type,
        "source": edge.source,
        "review_status": edge.review_status,
    }


def llm_provider_to_dict(row) -> dict[str, Any]:
    """LLM 服务公开投影：密钥永不出现（只写不读回，FR-006）。"""
    return {
        "id": row.id,
        "name": row.name,
        "provider_type": row.provider_type,
        "base_url": row.base_url,
        "model": row.model,
        "params": row.params or {},
        "is_default": row.is_default,
        "health": row.health,
        "last_test_at": iso(row.last_test_at),
        "last_test_result": row.last_test_result,
    }


def seed_to_dict(seed) -> dict[str, Any]:
    return {
        "id": seed.id,
        "query": seed.query,
        "lang": seed.lang,
        "product_line_id": seed.product_line_id,
        "persona_id": seed.persona_id,
        "market_id": seed.market_id,
        "priority": seed.priority,
        "batch": seed.batch,
        "source_node_id": seed.source_node_id,
        "template": seed.template,
        "status": seed.status,
        "source": seed.source,
        "confidence": seed.confidence,
        "review_status": seed.review_status,
        "n_candidates": seed.n_candidates,
        "n_contacts": seed.n_contacts,
        "note": seed.note,
        "last_run_at": iso(seed.last_run_at),
        "created_at": iso(seed.created_at),
        "updated_at": iso(seed.updated_at),
    }


def crawl_job_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "scope": row.scope or {},
        "config": row.config or {},
        "status": row.status,
        "stats": row.stats or {},
        "started_at": iso(row.started_at),
        "finished_at": iso(row.finished_at),
        "created_at": iso(row.created_at),
    }


def domain_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "domain": row.domain,
        "homepage_url": row.homepage_url,
        "title": row.title,
        "snippet": row.snippet,
        "source": row.source,
        "status": row.status,
        "attempts": row.attempts,
        "last_error": row.last_error,
        "fetched_pages": row.fetched_pages,
        "country": row.country,
        "country_source": row.country_source,
        "language": row.language,
        "language_source": row.language_source,
        "is_excluded": row.is_excluded,
        "exclusion_reason": row.exclusion_reason,
        "company_id": row.company_id,
        "last_crawled_at": iso(row.last_crawled_at),
        "created_at": iso(row.created_at),
    }


def company_to_dict(row, *, domain: str | None = None, contacts_count: int | None = None) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "country": row.country,
        "language": row.language,
        "status": row.status,
        "is_excluded": row.is_excluded,
        "exclusion_reason": row.exclusion_reason,
        "tags": row.tags or [],
        "source": row.source,
        "note": row.note,
        "domain": domain,
        "contacts_count": contacts_count or 0,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def contact_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "domain_id": row.domain_id,
        "type": row.type,
        "value": row.value,
        "value_normalized": row.value_normalized,
        "category": row.category,
        "source_url": row.source_url,
        "validity": row.validity,
        "is_primary": row.is_primary,
        "created_at": iso(row.created_at),
    }


def search_provider_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "type_key": row.type_key,
        "name": row.name,
        "endpoint": row.endpoint,
        "priority": row.priority,
        "enabled": row.enabled,
        "params": row.params or {},
        "used_today": row.used_today,
        "used_today_date": row.used_today_date,
        "health": row.health,
        "last_test_at": iso(row.last_test_at),
        "last_test_result": row.last_test_result,
        "last_error_kind": row.last_error_kind,  # 最近失败类别（004 R9/FR-018）
        "last_error_at": iso(row.last_error_at),
    }


def exclusion_rule_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "rule_type": row.rule_type,
        "pattern": row.pattern,
        "enabled": row.enabled,
        "note": row.note,
        "created_at": iso(row.created_at),
    }


def suppression_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "scope": row.scope,
        "target_value": row.target_value,
        "reason": row.reason,
        "company_id": row.company_id,
        "contact_id": row.contact_id,
        "source": row.source,
        "note": row.note,
        "created_at": iso(row.created_at),
    }


def content_theme_to_dict(row, *, variants_count: int = 0) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "content_type": row.content_type,
        "master_lang": row.master_lang,
        "description": row.description,
        "variants_count": variants_count,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def content_version_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "variant_id": row.variant_id,
        "version_no": row.version_no,
        "subject": row.subject,
        "body_md": row.body_md,
        "variables": row.variables or [],
        "change_note": row.change_note,
        "created_by": row.created_by,
        "created_at": iso(row.created_at),
    }


def content_variant_to_dict(variant, *, current=None) -> dict[str, Any]:
    return {
        "id": variant.id,
        "theme_id": variant.theme_id,
        "lang": variant.lang,
        "status": variant.status,
        "source": variant.source,
        "parent_variant_id": variant.parent_variant_id,
        "current": content_version_to_dict(current) if current is not None else None,
        "created_at": iso(variant.created_at),
        "updated_at": iso(variant.updated_at),
    }


def channel_to_dict(row) -> dict[str, Any]:
    """发送通道（FR-040~044）：密钥只写不读回；config 中疑似密钥键做防御性脱敏。"""
    from saler.security.redact import redact, scrub_text

    return {
        "id": row.id,
        "name": row.name,
        "channel_type": row.channel_type,
        "config": redact(row.config or {}),
        "identity": row.identity or {},
        "daily_limit": row.daily_limit,
        "rate_per_minute": row.rate_per_minute,
        "concurrency": row.concurrency,
        "status": row.status,
        "health": row.health,
        "last_check_at": iso(row.last_check_at),
        "last_check_result": scrub_text(row.last_check_result or "") or None,
        "used_today": row.used_today,
        "used_today_date": row.used_today_date,
        "total_sent": row.total_sent,
        "secret_set": bool(row.secret_encrypted),
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def campaign_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "content_theme_id": row.content_theme_id,
        "audience": row.audience or {},
        "lang_strategy": row.lang_strategy,
        "fixed_lang": row.fixed_lang,
        "fallback_lang": row.fallback_lang,
        "schedule": row.schedule or {},
        "estimate": row.estimate or {},
        "stats": row.stats or {},
        "started_at": iso(row.started_at),
        "finished_at": iso(row.finished_at),
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def campaign_round_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "campaign_id": row.campaign_id,
        "round_no": row.round_no,
        "content_theme_id": row.content_theme_id,
        "interval_days": row.interval_days,
        "condition": row.condition,
        "status": row.status,
        "stats": row.stats or {},
        "started_at": iso(row.started_at),
        "finished_at": iso(row.finished_at),
    }


def send_record_to_dict(row, *, company_name: str | None = None, channel_name: str | None = None) -> dict[str, Any]:
    return {
        "id": row.id,
        "campaign_id": row.campaign_id,
        "round_no": row.round_no,
        "company_id": row.company_id,
        "company_name": company_name,
        "contact_id": row.contact_id,
        "contact_value": row.contact_value,
        "channel_id": row.channel_id,
        "channel_name": channel_name,
        "content_variant_id": row.content_variant_id,
        "content_version_id": row.content_version_id,
        "lang_used": row.lang_used,
        "fallback_used": row.fallback_used,
        "status": row.status,
        "skip_reason": row.skip_reason,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "scheduled_at": iso(row.scheduled_at),
        "sent_at": iso(row.sent_at),
        "created_at": iso(row.created_at),
    }
