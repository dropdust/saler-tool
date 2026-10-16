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
from saler.api.serializers import llm_call_to_dict
from saler.core.content.ai import run_content_draft, run_content_translate
from saler.core.errors import ValidationFailed
from saler.core.llm_utils import resolve_llm_provider
from saler.core.prompts import registry, store
from saler.core.prompts.assist import run_prompt_assist
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


# ---------- 提示词模板库（006 契约 §1~§4；模板库版） ----------


def _require_feature(feature: str):
    spec = registry.get_feature(feature)
    if spec is None:
        raise not_found("提示词功能")
    return spec


def _prompt_detail(db: Session, spec) -> dict:
    templates, active_id = store.list_templates(db, spec.key)
    active = next((item for item in templates if item["id"] == active_id), None)
    reserved = registry.RESERVED_OUTPUT_CONTRACT
    return {
        "feature": spec.key,
        "label": spec.label,
        "default_content": spec.default_template,
        "active_id": active["id"] if active is not None else None,
        "active_name": active["name"] if active is not None else None,
        "customized": active is not None,
        "max_length": registry.MAX_TEMPLATE_LENGTH,
        "max_name_length": store.NAME_MAX_LENGTH,
        "max_templates": store.MAX_TEMPLATES,
        "templates": [
            {
                "id": item["id"],
                "name": item["name"],
                "content": item["content"],
                "updated_at": item["updated_at"],
            }
            for item in templates
        ],
        "variables": [
            {"name": var.name, "label": var.label, "render": var.render} for var in spec.variables
        ],
        "reserved_variables": [
            {"name": reserved.name, "label": reserved.label, "render": reserved.render}
        ],
        "output_contract": spec.output_contract,
    }


def _detail_with_warnings(db: Session, spec, warnings: list[dict]) -> dict:
    detail = _prompt_detail(db, spec)
    detail["warnings"] = warnings
    return detail


@router.get("/prompts")
def list_prompts(db: Session = Depends(get_session)) -> dict:
    items = []
    for key in registry.FEATURES:
        spec = registry.FEATURES[key]
        templates, active_id = store.list_templates(db, key)
        active = next((item for item in templates if item["id"] == active_id), None)
        items.append(
            {
                "feature": key,
                "label": spec.label,
                "customized": active is not None,
                "active_id": active["id"] if active is not None else None,
                "active_name": active["name"] if active is not None else None,
                "template_count": len(templates),
            }
        )
    return {"items": items}


@router.get("/prompts/{feature}")
def get_prompt(feature: str, db: Session = Depends(get_session)) -> dict:
    return _prompt_detail(db, _require_feature(feature))


class PromptTemplateCreateRequest(BaseModel):
    name: str
    content: str
    activate: bool = True


class PromptTemplateUpdateRequest(BaseModel):
    name: str | None = None
    content: str | None = None


class PromptActivateRequest(BaseModel):
    id: str | None = None


@router.post("/prompts/{feature}/templates", status_code=201)
def create_prompt_template(
    feature: str, payload: PromptTemplateCreateRequest, db: Session = Depends(get_session)
) -> dict:
    """创建/另存为：名称/容量/内容规则违规 → 400；warnings 不阻断、随详情返回（契约 §3a）。"""
    spec = _require_feature(feature)
    try:
        warnings = store.create(
            db, spec.key, name=payload.name, content=payload.content, activate=payload.activate
        )
    except ValidationFailed as exc:
        raise bad_request(str(exc)) from exc
    return _detail_with_warnings(db, spec, warnings)


@router.put("/prompts/{feature}/templates/{template_id}")
def update_prompt_template(
    feature: str,
    template_id: str,
    payload: PromptTemplateUpdateRequest,
    db: Session = Depends(get_session),
) -> dict:
    """更新内容 / 重命名（契约 §3b）；未知 id → 404，规则违规 → 400。"""
    spec = _require_feature(feature)
    if payload.name is None and payload.content is None:
        raise bad_request("至少提供 name 或 content 之一")
    try:
        warnings = store.update(
            db, spec.key, template_id, name=payload.name, content=payload.content
        )
    except ValidationFailed as exc:
        raise bad_request(str(exc)) from exc
    return _detail_with_warnings(db, spec, warnings)


@router.delete("/prompts/{feature}/templates/{template_id}")
def delete_prompt_template(
    feature: str, template_id: str, db: Session = Depends(get_session)
) -> dict:
    """删除模板（契约 §3c）：删除生效模板由服务端自动回退内置默认。"""
    spec = _require_feature(feature)
    store.delete(db, spec.key, template_id)
    return _prompt_detail(db, spec)


@router.put("/prompts/{feature}/active")
def activate_prompt_template(
    feature: str, payload: PromptActivateRequest, db: Session = Depends(get_session)
) -> dict:
    """切换生效 / 恢复默认（契约 §4）：id=None 即切回内置默认（模板库保留）。"""
    spec = _require_feature(feature)
    store.activate(db, spec.key, payload.id)
    return _prompt_detail(db, spec)


class PromptAssistRequest(BaseModel):
    mode: str
    intent: str | None = None
    draft: str | None = None


@router.post("/prompts/{feature}/assist")
def assist_prompt(
    feature: str,
    payload: PromptAssistRequest,
    request: Request,
    db: Session = Depends(get_session),
) -> dict:
    """AI 辅助编写（契约 §5）：同步调用（线程池），建议不入库。

    - 参数违规 → 400 `bad_request`；未配置服务 → 409 `llm_not_configured`（既有门控）；
    - 调用经 `run_prompt_assist` 落 llm_call 明细（operation=prompt_assist、job_id=NULL）。
    """
    spec = _require_feature(feature)
    if payload.mode not in ("generate", "polish"):
        raise bad_request("mode 仅支持 generate / polish")
    if payload.mode == "generate":
        intent = (payload.intent or "").strip()
        if not intent:
            raise bad_request("generate 模式需要提供 intent")
        if len(intent) > 2000:
            raise bad_request("intent 过长（上限 2000 字符）")
        draft = None
    else:
        draft = (payload.draft or "").strip()
        if not draft:
            raise bad_request("polish 模式需要提供 draft")
        if len(draft) > registry.MAX_TEMPLATE_LENGTH:
            raise bad_request(f"draft 过长（上限 {registry.MAX_TEMPLATE_LENGTH} 字符）")
        intent = None
    provider = resolve_llm_provider(db, None)
    return run_prompt_assist(
        request.app.state.session_factory,
        provider,
        feature=spec.key,
        mode=payload.mode,
        intent=intent,
        draft=draft,
    )
