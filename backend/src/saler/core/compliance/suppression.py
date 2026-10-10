"""退订/黑名单（FR-051/029）：检查与登记。

发送与导入两条链路都先经 `is_suppressed` 过滤（合规工具必备，宪法附加约束）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from saler.core.errors import NotFound, ValidationFailed
from saler.db.models import Suppression

SCOPES = ("email", "phone", "contact", "company", "domain")
REASONS = ("unsubscribed", "bounced", "manual", "complaint", "invalid")


def normalized_target(scope: str, value: str) -> str:
    value = (value or "").strip()
    return value.lower() if scope in ("email", "domain") else value


def is_suppressed(db: Session, *, scope: str, value: str) -> bool:
    return (
        db.query(Suppression)
        .filter_by(scope=scope, target_value=normalized_target(scope, value))
        .first()
        is not None
    )


def add_suppression(
    db: Session,
    *,
    scope: str,
    target_value: str,
    reason: str,
    company_id: int | None = None,
    contact_id: int | None = None,
    source: str | None = None,
    note: str | None = None,
) -> tuple[Suppression, bool]:
    if scope not in SCOPES:
        raise ValidationFailed(f"非法范围：{scope}")
    if reason not in REASONS:
        raise ValidationFailed(f"非法原因：{reason}")
    normalized = normalized_target(scope, target_value)
    if not normalized:
        raise ValidationFailed("目标值不能为空")
    existing = db.query(Suppression).filter_by(scope=scope, target_value=normalized).first()
    if existing is not None:
        return existing, False
    row = Suppression(
        scope=scope,
        target_value=normalized,
        reason=reason,
        company_id=company_id,
        contact_id=contact_id,
        source=source,
        note=note,
    )
    db.add(row)
    db.commit()
    return row, True


def list_suppressions(db: Session, *, scope: str | None = None) -> list[Suppression]:
    query = db.query(Suppression)
    if scope:
        query = query.filter_by(scope=scope)
    return query.order_by(Suppression.id.desc()).all()


def get_suppression(db: Session, suppression_id: int) -> Suppression:
    row = db.get(Suppression, suppression_id)
    if row is None:
        raise NotFound("黑名单条目")
    return row


def delete_suppression(db: Session, suppression_id: int) -> None:
    db.delete(get_suppression(db, suppression_id))
    db.commit()
