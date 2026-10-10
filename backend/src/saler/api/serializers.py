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
