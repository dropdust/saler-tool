"""AI API：种子扩充 / 翻译（job 化；provider 解析可测试注入）+ 提示词模板（006）。

调用前数据范围可见（FR-031）：请求参数中即为发送给模型的内容（描述 + 节点名等）。
提示词端点（006 契约 §1~§4）：模板的读取/保存/恢复默认；域校验（空/超长阻断、
未知变量/缺失变量/缺槽位警告）经 `core/prompts` 单点实现。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from saler.api.deps import get_session
from saler.api.errors import bad_request, not_found
from saler.api.serializers import iso, llm_call_to_dict
from saler.core.content.ai import run_content_draft, run_content_translate
from saler.core.errors import ValidationFailed
from saler.core.llm_utils import resolve_llm_provider
from saler.core.prompts import registry, store
from saler.core.seeds.ai import run_expansion
from saler.core.seeds.ai_translate import run_translate_seeds, run_translate_terms
from saler.providers.llm import call_log

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/calls")
def list_llm_calls(
    job_id: int | None = None,
    operation: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_session),
) -> dict:
    """LLM 调用明细：逐次尝试的输入/输出/修复链/耗时/用量（新→旧）。"""
    total, rows = call_log.list_calls(
        db,
        job_id=job_id,
        operation=operation,
        limit=max(1, min(limit, 200)),
        offset=max(0, offset),
    )
    return {"total": total, "items": [llm_call_to_dict(row) for row in rows]}


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


# ---------- 提示词模板（006 契约 §1~§4） ----------


def _require_feature(feature: str):
    spec = registry.get_feature(feature)
    if spec is None:
        raise not_found("提示词功能")
    return spec


def _prompt_detail(db: Session, spec) -> dict:
    content, customized = store.get_effective(db, spec.key)
    row = store.get_row(db, spec.key) if customized else None
    reserved = registry.RESERVED_OUTPUT_CONTRACT
    return {
        "feature": spec.key,
        "label": spec.label,
        "content": content,
        "default_content": spec.default_template,
        "customized": customized,
        "updated_at": iso(row.updated_at) if row is not None else None,
        "max_length": registry.MAX_TEMPLATE_LENGTH,
        "variables": [
            {"name": var.name, "label": var.label, "render": var.render} for var in spec.variables
        ],
        "reserved_variables": [
            {"name": reserved.name, "label": reserved.label, "render": reserved.render}
        ],
        "output_contract": spec.output_contract,
    }


@router.get("/prompts")
def list_prompts(db: Session = Depends(get_session)) -> dict:
    items = []
    for key in registry.FEATURES:
        spec = registry.FEATURES[key]
        _, customized = store.get_effective(db, key)
        row = store.get_row(db, key) if customized else None
        items.append(
            {
                "feature": key,
                "label": spec.label,
                "customized": customized,
                "updated_at": iso(row.updated_at) if row is not None else None,
            }
        )
    return {"items": items}


@router.get("/prompts/{feature}")
def get_prompt(feature: str, db: Session = Depends(get_session)) -> dict:
    return _prompt_detail(db, _require_feature(feature))


class PromptSaveRequest(BaseModel):
    content: str


@router.put("/prompts/{feature}")
def save_prompt(feature: str, payload: PromptSaveRequest, db: Session = Depends(get_session)) -> dict:
    """保存模板：空/超长 → 400（contract §3）；未知变量等警告不阻断、随响应返回。"""
    spec = _require_feature(feature)
    try:
        warnings = store.save(db, spec.key, payload.content)
    except ValidationFailed as exc:
        raise bad_request(str(exc)) from exc
    detail = _prompt_detail(db, spec)
    detail["warnings"] = warnings
    return detail


@router.post("/prompts/{feature}/reset")
def reset_prompt(feature: str, db: Session = Depends(get_session)) -> dict:
    spec = _require_feature(feature)
    store.reset(db, spec.key)
    return _prompt_detail(db, spec)
