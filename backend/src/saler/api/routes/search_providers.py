"""检索渠道 API：CRUD / 连通测试 / 预置模板（FR-019；密钥只写不读回）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from saler.api.deps import get_session
from saler.api.errors import not_found, unprocessable
from saler.api.serializers import search_provider_to_dict
from saler.db.models import SearchProvider
from saler.providers.registry import registry
from saler.providers.search._common import SEARCH_PRESETS

router = APIRouter(prefix="/search", tags=["search"])

SEARCH_KINDS = ("brave", "serper", "tavily", "ddg_html")


class ProviderCreate(BaseModel):
    type_key: str
    name: str
    api_key: str | None = None
    endpoint: str | None = None
    priority: int = 100
    enabled: bool = True
    params: dict = Field(default_factory=dict)


class ProviderUpdate(BaseModel):
    name: str | None = None
    api_key: str | None = None
    endpoint: str | None = None
    priority: int | None = None
    enabled: bool | None = None
    params: dict | None = None


def _get_or_404(db: Session, provider_id: int) -> SearchProvider:
    row = db.get(SearchProvider, provider_id)
    if row is None:
        raise not_found("检索渠道")
    return row


def _build_adapter(row: SearchProvider):
    manifest = registry.get("search", row.type_key)
    if manifest is None or manifest.factory is None:
        return None
    kwargs: dict = {}
    if row.type_key != "ddg_html":
        kwargs["api_key"] = row.secret_encrypted or ""
    if row.endpoint:
        kwargs["base_url"] = row.endpoint
    return manifest.factory(**kwargs)


@router.get("/providers")
def list_providers(db: Session = Depends(get_session)) -> list[dict]:
    rows = db.query(SearchProvider).order_by(SearchProvider.priority.asc(), SearchProvider.id.asc())
    return [search_provider_to_dict(row) for row in rows]


@router.post("/providers", status_code=201)
def create_provider(payload: ProviderCreate, db: Session = Depends(get_session)) -> dict:
    if payload.type_key not in SEARCH_KINDS:
        raise unprocessable(f"暂不支持的检索渠道：{payload.type_key}")
    row = SearchProvider(
        type_key=payload.type_key,
        name=payload.name,
        secret_encrypted=payload.api_key,
        endpoint=payload.endpoint,
        priority=payload.priority,
        enabled=payload.enabled,
        params=payload.params,
    )
    db.add(row)
    db.commit()
    return search_provider_to_dict(row)


@router.put("/providers/{provider_id}")
def update_provider(provider_id: int, payload: ProviderUpdate, db: Session = Depends(get_session)) -> dict:
    row = _get_or_404(db, provider_id)
    fields = payload.model_dump(exclude_unset=True)
    for key, value in fields.items():
        if key == "api_key":
            if value:  # 留空 = 保留原密钥
                row.secret_encrypted = value
        elif value is not None:
            setattr(row, key, value)
    db.commit()
    return search_provider_to_dict(row)


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: int, db: Session = Depends(get_session)) -> dict:
    row = _get_or_404(db, provider_id)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/providers/{provider_id}/test")
def test_provider(provider_id: int, db: Session = Depends(get_session)) -> dict:
    from datetime import UTC, datetime

    row = _get_or_404(db, provider_id)
    adapter = _build_adapter(row)
    if adapter is None:
        raise unprocessable(f"适配器不可用：{row.type_key}")
    result = adapter.test_connection()
    row.health = "healthy" if result.ok else "failing"
    row.last_test_at = datetime.now(UTC)
    row.last_test_result = result.detail[:2000]
    db.commit()
    return {"ok": result.ok, "detail": result.detail}


@router.get("/presets")
def presets() -> dict:
    manifests = {m.type_key: m.config_schema for m in registry.by_kind("search")}
    return {"presets": SEARCH_PRESETS, "config_schemas": manifests}
