"""产量归因：以 `domain_seed_hit` 为事实来源重算种子产量（FR-015/016）。"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from saler.db.models import Contact, Domain, DomainSeedHit, Seed


def recompute_seed_yield(db: Session, seed_ids: list[int] | None = None) -> int:
    """重算 n_candidates（命中域名数）与 n_contacts（命中域名下的联系方式数）。"""
    query = db.query(Seed)
    if seed_ids is not None:
        query = query.filter(Seed.id.in_(seed_ids))
    seeds = query.all()
    for seed in seeds:
        seed.n_candidates = (
            db.query(func.count(func.distinct(DomainSeedHit.domain_id)))
            .filter(DomainSeedHit.seed_id == seed.id)
            .scalar()
            or 0
        )
        seed.n_contacts = (
            db.query(func.count(func.distinct(Contact.id)))
            .join(Domain, Contact.domain_id == Domain.id)
            .join(DomainSeedHit, DomainSeedHit.domain_id == Domain.id)
            .filter(DomainSeedHit.seed_id == seed.id)
            .scalar()
            or 0
        )
    db.commit()
    return len(seeds)
