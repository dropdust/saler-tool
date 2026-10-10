"""退订/黑名单 API（FR-051；T122 完整验收在 US6，这里先落 CRUD——导入/发送链路依赖）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from saler.api.deps import get_session
from saler.api.serializers import suppression_to_dict
from saler.core.compliance import suppression

router = APIRouter(prefix="/suppressions", tags=["compliance"])


class SuppressionCreate(BaseModel):
    scope: str
    target_value: str
    reason: str
    company_id: int | None = None
    contact_id: int | None = None
    source: str | None = None
    note: str | None = None


@router.get("")
def list_suppressions(scope: str | None = None, db: Session = Depends(get_session)) -> list[dict]:
    return [suppression_to_dict(row) for row in suppression.list_suppressions(db, scope=scope)]


@router.post("", status_code=201)
def create_suppression(payload: SuppressionCreate, db: Session = Depends(get_session)) -> dict:
    row, created = suppression.add_suppression(db, **payload.model_dump())
    return {"created": created, **suppression_to_dict(row)}


@router.delete("/{suppression_id}")
def delete_suppression(suppression_id: int, db: Session = Depends(get_session)) -> dict:
    suppression.delete_suppression(db, suppression_id)
    return {"ok": True}
