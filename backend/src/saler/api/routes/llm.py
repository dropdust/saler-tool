"""LLM 服务 API：配置 CRUD + 连通测试 + 预置模板（FR-030）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from saler.api.deps import get_session
from saler.api.serializers import llm_provider_to_dict
from saler.core import llm_provider_service
from saler.providers.llm.openai_compatible import LLM_MANIFEST, PROVIDER_PRESETS
from saler.providers.llm.test_connection import run_connection_test

router = APIRouter(prefix="/llm", tags=["llm"])


class ProviderCreate(BaseModel):
    name: str
    provider_type: str = "openai_compatible"
    base_url: str
    model: str = ""
    api_key: str | None = None
    params: dict = Field(default_factory=dict)
    is_default: bool = False


class ProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    params: dict | None = None
    is_default: bool | None = None


@router.get("/providers")
def list_providers(db: Session = Depends(get_session)) -> list[dict]:
    return [llm_provider_to_dict(row) for row in llm_provider_service.list_providers(db)]


@router.post("/providers", status_code=201)
def create_provider(payload: ProviderCreate, db: Session = Depends(get_session)) -> dict:
    row = llm_provider_service.create_provider(db, **payload.model_dump())
    return llm_provider_to_dict(row)


@router.put("/providers/{provider_id}")
def update_provider(
    provider_id: int, payload: ProviderUpdate, db: Session = Depends(get_session)
) -> dict:
    # exclude_unset：只更新显式提供的字段；api_key 省略/null = 保留原密钥
    row = llm_provider_service.update_provider(
        db, provider_id, **payload.model_dump(exclude_unset=True)
    )
    return llm_provider_to_dict(row)


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: int, db: Session = Depends(get_session)) -> dict:
    llm_provider_service.delete_provider(db, provider_id)
    return {"ok": True}


@router.post("/providers/{provider_id}/test")
def test_provider(provider_id: int, db: Session = Depends(get_session)) -> dict:
    """连通性测试：同步执行（threadpool），原样返回服务商错误文本。"""
    row = llm_provider_service.get_provider(db, provider_id)
    result = run_connection_test(row)
    llm_provider_service.record_health(db, provider_id, ok=result.ok, detail=result.detail)
    return {"ok": result.ok, "detail": result.detail, "models": result.models}


@router.get("/presets")
def presets() -> dict:
    return {
        "presets": PROVIDER_PRESETS,
        "config_schema": LLM_MANIFEST.config_schema,
        "secret_fields": list(LLM_MANIFEST.secret_fields),
    }
