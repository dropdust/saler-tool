"""应用设置 API（KV；未知键拒绝）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from saler.api.deps import get_session
from saler.api.errors import bad_request
from saler.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings(db: Session = Depends(get_session)) -> dict:
    return settings_service.get_all(db)


class SettingsUpdate(BaseModel):
    values: dict


@router.put("")
def put_settings(payload: SettingsUpdate, db: Session = Depends(get_session)) -> dict:
    for key, value in payload.values.items():
        if not settings_service.is_known_key(db, key):
            raise bad_request(f"未知设置项：{key}")
        settings_service.set_value(db, key, value)
    return settings_service.get_all(db)
