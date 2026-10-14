"""候选域名 API：列表筛选、检索溯源（命中 query 词）与人工修订（排除/恢复/国家语言纠偏）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from saler.api.deps import get_session, paginate, pagination
from saler.api.serializers import domain_to_dict, seed_hit_to_dict
from saler.core.leads import domain_service

router = APIRouter(prefix="/domains", tags=["domains"])


class DomainUpdate(BaseModel):
    country: str | None = None
    country_source: str | None = None
    language: str | None = None
    language_source: str | None = None
    is_excluded: bool | None = None
    exclusion_reason: str | None = None


@router.get("")
def list_domains(
    status: str | None = None,
    excluded: bool | None = Query(default=None),
    country: str | None = None,
    q: str | None = None,
    page_params: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_session),
) -> dict:
    page, page_size = page_params
    result = paginate(
        domain_service.list_domains(db, status=status, excluded=excluded, country=country, q=q),
        page,
        page_size,
    )
    counts = domain_service.seed_hit_counts(db, [row.id for row in result["items"]])
    result["items"] = [
        domain_to_dict(row, seed_hits_count=counts.get(row.id, 0)) for row in result["items"]
    ]
    return result


@router.get("/{domain_id}")
def get_domain(domain_id: int, db: Session = Depends(get_session)) -> dict:
    """详情：含命中明细（query 词/任务/首次命中时间），供异常域名溯源。"""
    row = domain_service.get_domain(db, domain_id)
    hits = domain_service.list_seed_hits(db, domain_id)
    data = domain_to_dict(row, seed_hits_count=len(hits))
    data["seed_hits"] = [seed_hit_to_dict(seed, hit) for seed, hit in hits]
    return data


@router.put("/{domain_id}")
def update_domain(domain_id: int, payload: DomainUpdate, db: Session = Depends(get_session)) -> dict:
    fields = payload.model_dump(exclude_unset=True)
    row = domain_service.update_domain(db, domain_id, **fields)
    counts = domain_service.seed_hit_counts(db, [row.id])
    return domain_to_dict(row, seed_hits_count=counts.get(row.id, 0))
