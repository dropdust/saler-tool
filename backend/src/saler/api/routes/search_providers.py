"""检索渠道 API：CRUD / 连通测试 / 预置模板（FR-019；密钥只写不读回）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import saler.providers.search  # noqa: F401  # 导入包即注册全部 manifest（约定）
from saler.api.deps import get_session
from saler.api.errors import not_found, unprocessable
from saler.api.serializers import search_provider_to_dict
from saler.core.leads.search_stats import apply_attempt
from saler.db.models import SearchProvider
from saler.providers.registry import registry

router = APIRouter(prefix="/search", tags=["search"])


def _search_kinds() -> set[str]:
    """类型值域 = registry 全量——新增渠道零改动被发现（004 R8）。"""
    return {m.type_key for m in registry.by_kind("search")}


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
    kwargs: dict = {"params": row.params or {}}
    if manifest.secret_fields:  # 需密钥类型才注入（免密钥渠道由 manifest 驱动，免特判）
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
    if payload.type_key not in _search_kinds():
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
    row.last_test_at = datetime.now(UTC)
    row.last_test_result = result.detail[:2000]
    apply_attempt(row, ok=result.ok, error_kind=result.kind)  # 与任务执行同口径（R9）
    db.commit()
    return {"ok": result.ok, "detail": result.detail}


@router.get("/presets")
def presets() -> dict:
    """预置元数据由 registry 派生（单一数据源 = 各 manifest.preset；004 R8）。

    既有键 display/endpoint/needs_key/note 语义不变（向后兼容）；新增
    apply_url/access_mode/market/risk；needs_key 为派生值（secret_fields 非空）。
    """
    out: dict[str, dict] = {}
    schemas: dict[str, dict] = {}
    for m in registry.by_kind("search"):
        p = m.preset or {}
        out[m.type_key] = {
            "display": m.display_name,
            "endpoint": p.get("endpoint", ""),
            "needs_key": bool(m.secret_fields),
            "note": p.get("note", ""),
            "apply_url": p.get("apply_url"),
            "access_mode": p.get("access_mode", "official_api"),
            "market": p.get("market", ""),
            "risk": p.get("risk", ""),
        }
        schemas[m.type_key] = m.config_schema
    return {"presets": out, "config_schemas": schemas}
