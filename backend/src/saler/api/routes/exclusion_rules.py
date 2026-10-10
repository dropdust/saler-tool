"""排除规则 API：CRUD + 对存量重跑（FR-023）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from saler.api.deps import get_session
from saler.api.serializers import exclusion_rule_to_dict
from saler.core.compliance import exclusion

router = APIRouter(prefix="/exclusion-rules", tags=["exclusion"])


class RuleCreate(BaseModel):
    rule_type: str
    pattern: str
    note: str | None = None
    enabled: bool = True


class RuleUpdate(BaseModel):
    pattern: str | None = None
    note: str | None = None
    enabled: bool | None = None


@router.get("")
def list_rules(db: Session = Depends(get_session)) -> list[dict]:
    return [exclusion_rule_to_dict(row) for row in exclusion.list_rules(db)]


@router.post("", status_code=201)
def create_rule(payload: RuleCreate, db: Session = Depends(get_session)) -> dict:
    row = exclusion.create_rule(
        db,
        rule_type=payload.rule_type,
        pattern=payload.pattern,
        note=payload.note,
        enabled=payload.enabled,
    )
    return exclusion_rule_to_dict(row)


@router.put("/{rule_id}")
def update_rule(rule_id: int, payload: RuleUpdate, db: Session = Depends(get_session)) -> dict:
    row = exclusion.update_rule(db, rule_id, **payload.model_dump(exclude_none=True))
    return exclusion_rule_to_dict(row)


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_session)) -> dict:
    exclusion.delete_rule(db, rule_id)
    return {"ok": True}


@router.post("/apply")
def apply_rules(db: Session = Depends(get_session)) -> dict:
    return exclusion.apply_to_domains(db)
