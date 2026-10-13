"""AI API：种子扩充 / 翻译（job 化；provider 解析可测试注入）。

调用前数据范围可见（FR-031）：请求参数中即为发送给模型的内容（描述 + 节点名等）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from saler.api.deps import get_session
from saler.core.content.ai import run_content_draft, run_content_translate
from saler.core.llm_utils import resolve_llm_provider
from saler.core.seeds.ai import run_expansion
from saler.core.seeds.ai_translate import run_translate_seeds, run_translate_terms

router = APIRouter(prefix="/ai", tags=["ai"])


class ExpandRequest(BaseModel):
    provider_id: int | None = None
    description: str | None = None
    from_node_ids: list[int] = Field(default_factory=list)
    count: int = 20
    # 目标语言不在此处：扩充一律产出中文母版，审核后经 /ai/seeds/translate 翻译（FR-012②）


class TranslateSeedsRequest(BaseModel):
    provider_id: int | None = None
    seed_ids: list[int] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)


class TranslateTermsRequest(BaseModel):
    provider_id: int | None = None
    node_ids: list[int] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)


@router.post("/seeds/expand", status_code=202)
async def expand(payload: ExpandRequest, request: Request, db: Session = Depends(get_session)) -> dict:
    provider = resolve_llm_provider(db, payload.provider_id)
    manager = request.app.state.job_manager
    params = {**payload.model_dump(), "provider": getattr(provider, "provider_name", "llm")}
    job_id = manager.create("ai_seed_expand", name="AI 扩充种子", params=params)
    manager.start(
        job_id,
        lambda ctx: run_expansion(
            ctx, request.app.state.session_factory, provider, payload=payload.model_dump()
        ),
    )
    return {"job_id": job_id}


@router.post("/seeds/translate", status_code=202)
async def translate_seeds(
    payload: TranslateSeedsRequest, request: Request, db: Session = Depends(get_session)
) -> dict:
    provider = resolve_llm_provider(db, payload.provider_id)
    manager = request.app.state.job_manager
    job_id = manager.create("ai_seed_translate", name="种子翻译", params=payload.model_dump())
    manager.start(
        job_id,
        lambda ctx: run_translate_seeds(
            ctx, request.app.state.session_factory, provider, payload=payload.model_dump()
        ),
    )
    return {"job_id": job_id}


@router.post("/terms/translate", status_code=202)
async def translate_terms(
    payload: TranslateTermsRequest, request: Request, db: Session = Depends(get_session)
) -> dict:
    provider = resolve_llm_provider(db, payload.provider_id)
    manager = request.app.state.job_manager
    job_id = manager.create("ai_term_translate", name="词表翻译", params=payload.model_dump())
    manager.start(
        job_id,
        lambda ctx: run_translate_terms(
            ctx, request.app.state.session_factory, provider, payload=payload.model_dump()
        ),
    )
    return {"job_id": job_id}


class ContentDraftRequest(BaseModel):
    provider_id: int | None = None
    theme_id: int
    brief: str
    tone: str | None = None


class ContentTranslateRequest(BaseModel):
    provider_id: int | None = None
    theme_id: int
    master_variant_id: int | None = None
    targets: list[str] = Field(default_factory=list)


@router.post("/content/draft", status_code=202)
async def content_draft(
    payload: ContentDraftRequest, request: Request, db: Session = Depends(get_session)
) -> dict:
    provider = resolve_llm_provider(db, payload.provider_id)
    manager = request.app.state.job_manager
    job_id = manager.create("ai_content_draft", name="AI 起草母版", params=payload.model_dump())
    manager.start(
        job_id,
        lambda ctx: run_content_draft(
            ctx, request.app.state.session_factory, provider, payload=payload.model_dump()
        ),
    )
    return {"job_id": job_id}


@router.post("/content/translate", status_code=202)
async def content_translate(
    payload: ContentTranslateRequest, request: Request, db: Session = Depends(get_session)
) -> dict:
    provider = resolve_llm_provider(db, payload.provider_id)
    manager = request.app.state.job_manager
    job_id = manager.create(
        "ai_content_translate", name="主题级多语言生成", params=payload.model_dump()
    )
    manager.start(
        job_id,
        lambda ctx: run_content_translate(
            ctx, request.app.state.session_factory, provider, payload=payload.model_dump()
        ),
    )
    return {"job_id": job_id}
