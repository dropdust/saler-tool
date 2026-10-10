"""排除规则（FR-023）：关键词/域名/名单，命中后"移出买家列表、单独存放"（不删除）。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from saler.core.errors import NotFound, ValidationFailed
from saler.db.models import Company, Domain, ExclusionRule

RULE_TYPES = ("keyword", "domain", "list")


def _patterns(rule: ExclusionRule) -> list[str]:
    if rule.rule_type == "list":
        return [line for line in rule.pattern.splitlines() if line.strip()]
    return [rule.pattern]


def rule_matches(rule: ExclusionRule, *, domain: str, title: str | None, snippet: str | None) -> str | None:
    domain_l = domain.lower()
    for pattern in _patterns(rule):
        p = pattern.strip().lower()
        if not p:
            continue
        if rule.rule_type == "domain":
            if domain_l == p or domain_l.endswith("." + p):
                return f"domain:{p}"
        else:
            haystack = " ".join(filter(None, [title or "", snippet or "", domain_l])).lower()
            if p in haystack:
                return f"{rule.rule_type}:{p}"
    return None


def create_rule(
    db: Session, *, rule_type: str, pattern: str, note: str | None = None, enabled: bool = True
) -> ExclusionRule:
    if rule_type not in RULE_TYPES:
        raise ValidationFailed(f"非法规则类型：{rule_type}")
    if not (pattern or "").strip():
        raise ValidationFailed("规则内容不能为空")
    rule = ExclusionRule(rule_type=rule_type, pattern=pattern.strip(), note=note, enabled=enabled)
    db.add(rule)
    db.commit()
    return rule


def get_rule(db: Session, rule_id: int) -> ExclusionRule:
    rule = db.get(ExclusionRule, rule_id)
    if rule is None:
        raise NotFound("排除规则")
    return rule


def list_rules(db: Session) -> list[ExclusionRule]:
    return db.query(ExclusionRule).order_by(ExclusionRule.id.asc()).all()


def update_rule(db: Session, rule_id: int, **fields) -> ExclusionRule:
    rule = get_rule(db, rule_id)
    for key in ("pattern", "note", "enabled"):
        if key in fields and fields[key] is not None:
            setattr(rule, key, fields[key])
    db.commit()
    return rule


def delete_rule(db: Session, rule_id: int) -> None:
    db.delete(get_rule(db, rule_id))
    db.commit()


def apply_to_domains(db: Session) -> dict:
    """对存量域名重跑全部启用规则；命中者（及其公司）标记排除并注明原因。"""
    rules = [rule for rule in db.query(ExclusionRule).filter_by(enabled=True).all()]
    excluded = 0
    candidates = db.query(Domain).filter(Domain.is_excluded.is_(False)).all()
    for domain_row in candidates:
        for rule in rules:
            reason = rule_matches(
                rule,
                domain=domain_row.domain,
                title=domain_row.title,
                snippet=domain_row.snippet,
            )
            if reason is None:
                continue
            domain_row.is_excluded = True
            domain_row.exclusion_reason = reason
            excluded += 1
            if domain_row.company_id:
                company = db.get(Company, domain_row.company_id)
                if company is not None:
                    company.is_excluded = True
                    company.exclusion_reason = reason
            break
    db.commit()
    return {"evaluated": len(candidates), "excluded": excluded}
