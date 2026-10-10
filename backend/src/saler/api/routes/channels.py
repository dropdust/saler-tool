"""发送通道 API：CRUD / 连通测试 / 用量 / 测试发送（FR-040~045；secret 只写不读回）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from saler.api.deps import get_session
from saler.api.serializers import channel_to_dict
from saler.core.sending import channel_service

# 触发 mail/sms 适配器注册（新增提供方无需改本文件）
from saler.providers.mail import smtp as _smtp  # noqa: F401
from saler.providers.registry import registry
from saler.providers.sms import http_generic as _sms  # noqa: F401

router = APIRouter(prefix="/channels", tags=["channels"])


class ChannelCreate(BaseModel):
    name: str
    channel_type: str = "email"
    config: dict = Field(default_factory=dict)
    identity: dict = Field(default_factory=dict)
    secret: str | None = None
    daily_limit: int = 200
    rate_per_minute: int = 20
    concurrency: int = 1
    status: str = "active"


class ChannelUpdate(BaseModel):
    name: str | None = None
    config: dict | None = None
    identity: dict | None = None
    secret: str | None = None
    daily_limit: int | None = None
    rate_per_minute: int | None = None
    concurrency: int | None = None
    status: str | None = None


class TestSendRequest(BaseModel):
    to: str


@router.get("/providers")
def list_provider_manifests() -> list[dict]:
    """通道适配器清单（前端按 config_schema 动态渲染表单；§5 注册表约定）。"""
    out: list[dict] = []
    for kind in ("mail", "sms"):
        for manifest in registry.by_kind(kind):
            out.append(
                {
                    "kind": manifest.kind,
                    "type_key": manifest.type_key,
                    "display_name": manifest.display_name,
                    "config_schema": manifest.config_schema,
                    "secret_fields": list(manifest.secret_fields),
                    "presets": _sms.SMS_PRESETS if kind == "sms" else {},
                }
            )
    return out


@router.get("")
def list_channels(db: Session = Depends(get_session)) -> list[dict]:
    return [channel_to_dict(row) for row in channel_service.list_channels(db)]


@router.post("", status_code=201)
def create_channel(payload: ChannelCreate, db: Session = Depends(get_session)) -> dict:
    row = channel_service.create_channel(db, **payload.model_dump())
    return channel_to_dict(row)


@router.get("/{channel_id}")
def get_channel(channel_id: int, db: Session = Depends(get_session)) -> dict:
    return channel_to_dict(channel_service.get_channel(db, channel_id))


@router.put("/{channel_id}")
def update_channel(
    channel_id: int, payload: ChannelUpdate, db: Session = Depends(get_session)
) -> dict:
    row = channel_service.update_channel(db, channel_id, **payload.model_dump(exclude_unset=True))
    return channel_to_dict(row)


@router.delete("/{channel_id}")
def delete_channel(channel_id: int, db: Session = Depends(get_session)) -> dict:
    channel_service.delete_channel(db, channel_id)
    return {"ok": True}


@router.post("/{channel_id}/test")
def test_channel(channel_id: int, db: Session = Depends(get_session)) -> dict:
    """连通性测试/凭证校验（FR-041）→ {ok, detail}；同时刷新健康状态。"""
    channel = channel_service.get_channel(db, channel_id)
    return channel_service.test_channel(db, channel)


@router.get("/{channel_id}/usage")
def channel_usage(channel_id: int, db: Session = Depends(get_session)) -> dict:
    """当日用量/额度/健康（FR-042/044）。"""
    channel = channel_service.get_channel(db, channel_id)
    return channel_service.usage(db, channel)


@router.post("/{channel_id}/test-send")
def test_send(channel_id: int, payload: TestSendRequest, db: Session = Depends(get_session)) -> dict:
    """通道级测试发送（S9②）：内置样例文案，不消耗日限额。"""
    channel = channel_service.get_channel(db, channel_id)
    return channel_service.test_send_canned(db, channel, to=payload.to)
