"""AI 内容服务（FR-038）：中文母版辅助编写 + 主题级多语言生成/翻译。

- 以中文母版为源；翻译复用图谱词表术语保持多语言一致；
- 产出一律 draft（带 source=llm_assisted / llm_translated），人工审核后才发布。
"""

from __future__ import annotations

import asyncio

from sqlalchemy.orm import Session, sessionmaker

from saler.core.content import service as content_service
from saler.core.errors import ValidationFailed
from saler.db.models import ContentVariant, GraphNode, NodeTerm
from saler.jobs.engine import JobContext
from saler.providers.llm.schemas import CONTENT_DRAFT_V1_SCHEMA, CONTENT_TRANSLATION_V1_SCHEMA
from saler.services.operation_log import log_op


def _master_variant(db: Session, theme_id: int, master_lang: str) -> ContentVariant | None:
    return (
        db.query(ContentVariant)
        .filter_by(theme_id=theme_id, lang=master_lang)
        .first()
    )


def _glossary(db: Session, targets: list[str]) -> dict[str, dict[str, str]]:
    rows = (
        db.query(NodeTerm)
        .filter(NodeTerm.lang.in_(targets), NodeTerm.review_status != "rejected")
        .all()
    )
    node_names = {node.id: node.name for node in db.query(GraphNode).all()}
    out: dict[str, dict[str, str]] = {}
    for term in rows:
        source = node_names.get(term.node_id)
        if source:
            out.setdefault(term.lang, {})[source] = term.term
    return out


def _build_draft_prompt(
    *, content_type: str, brief: str, tone: str | None, language: str
) -> str:
    return (
        f"你是资深外贸销售文案专家。请为下列业务撰写一条{content_type}（语言：{language}）文案。\n"
        f"业务要点：{brief}\n"
        f"语气：{tone or '专业、克制、以价值为先'}。\n"
        "输出 JSON：{\"subject\": \"主题行（如适用）\", \"body_md\": \"Markdown 正文\"}。\n"
        "要求：正文可使用 {{company_name}} 之类的变量占位符（收件人维度个性化）；"
        "不要编造具体价格与交期；落款处使用 {{signature}} 占位。"
    )


def _build_translate_prompt(
    *,
    target_lang: str,
    subject: str | None,
    body_md: str,
    glossary: dict[str, str] | None,
) -> str:
    glossary_text = ""
    if glossary:
        pairs = "\n".join(f"- {k} => {v}" for k, v in list(glossary.items())[:100])
        glossary_text = f"\n术语表（必须采用指定译法）：\n{pairs}"
    return (
        f"将下列营销文案翻译为 {target_lang}，保持营销语气与段落结构；"
        "**必须原样保留 {{变量}} 占位符**；不要添加原文不存在的内容。\n"
        f'输出 JSON：{{"subject": "译后主题", "body_md": "译后正文"}}。{glossary_text}\n\n'
        f"主题：{subject or '（无）'}\n正文：\n{body_md}"
    )


async def run_content_draft(
    ctx: JobContext,
    session_factory: sessionmaker[Session],
    provider,
    *,
    payload: dict,
) -> dict:
    theme_id = payload.get("theme_id")
    brief = (payload.get("brief") or "").strip()
    if not theme_id or not brief:
        raise ValidationFailed("需要提供 theme_id 与 brief")
    with session_factory() as db:
        theme = content_service.get_theme(db, theme_id)
        master_lang = theme.master_lang
        content_type = theme.content_type
    prompt = _build_draft_prompt(
        content_type=content_type, brief=brief, tone=payload.get("tone"), language=master_lang
    )
    ctx.progress(phase="calling_llm")
    ctx.log("大模型正在起草中文母版…")
    data = await asyncio.to_thread(
        provider.generate_structured, prompt=prompt, schema=CONTENT_DRAFT_V1_SCHEMA
    )
    await ctx.checkpoint()
    with session_factory() as db:
        theme = content_service.get_theme(db, theme_id)
        master = _master_variant(db, theme_id, theme.master_lang)
        if master is None:
            variant = content_service.create_variant(
                db,
                theme_id=theme_id,
                lang=theme.master_lang,
                subject=data.get("subject"),
                body_md=data.get("body_md") or "",
                source="llm_assisted",
            )
        else:
            version = content_service.update_variant_content(
                db,
                master.id,
                subject=data.get("subject"),
                body_md=data.get("body_md") or "",
                change_note="AI 起草/润色",
                created_by="llm",
            )
            master.source = "llm_assisted"
            db.commit()
            variant = master
        current = content_service.get_current_version(db, variant)
        log_op(
            db,
            "llm",
            f"AI 起草母版：{theme.name} → v{current.version_no if current else '?'}（待审核）",
            ref_type="job",
            ref_id=ctx.job_id,
            payload={"theme_id": theme_id, "variant_id": variant.id},
        )
    ctx.progress(phase="done")
    return {"variant_id": variant.id, "lang": variant.lang}


async def run_content_translate(
    ctx: JobContext,
    session_factory: sessionmaker[Session],
    provider,
    *,
    payload: dict,
) -> dict:
    theme_id = payload.get("theme_id")
    targets = [t.strip() for t in (payload.get("targets") or []) if t and t.strip()]
    master_variant_id = payload.get("master_variant_id")
    if not theme_id or not targets:
        raise ValidationFailed("需要提供 theme_id 与 targets")

    with session_factory() as db:
        theme = content_service.get_theme(db, theme_id)
        if master_variant_id:
            master = content_service.get_variant(db, master_variant_id)
        else:
            master = _master_variant(db, theme_id, theme.master_lang)
        if master is None:
            raise ValidationFailed("未找到中文母版：请先用 AI 起草或手工创建母版语言版本")
        master_version = content_service.get_current_version(db, master)
        base_subject = master_version.subject if master_version else None
        base_body = master_version.body_md if master_version else ""
        glossary = _glossary(db, targets)

    report: dict = {"created": [], "updated": []}
    for lang in targets:
        await ctx.checkpoint()
        ctx.progress(phase=f"translating:{lang}")
        prompt = _build_translate_prompt(
            target_lang=lang,
            subject=base_subject,
            body_md=base_body,
            glossary=glossary.get(lang),
        )
        data = await asyncio.to_thread(
            provider.generate_structured, prompt=prompt, schema=CONTENT_TRANSLATION_V1_SCHEMA
        )
        with session_factory() as db:
            existing = (
                db.query(ContentVariant)
                .filter_by(theme_id=theme_id, lang=lang)
                .first()
            )
            if existing is not None:
                content_service.update_variant_content(
                    db,
                    existing.id,
                    subject=data.get("subject"),
                    body_md=data.get("body_md") or "",
                    change_note="AI 翻译更新",
                    created_by="llm",
                )
                existing.source = "llm_translated"
                existing.parent_variant_id = master.id
                db.commit()
                report["updated"].append(lang)
            else:
                content_service.create_variant(
                    db,
                    theme_id=theme_id,
                    lang=lang,
                    subject=data.get("subject"),
                    body_md=data.get("body_md") or "",
                    source="llm_translated",
                    parent_variant_id=master.id,
                )
                report["created"].append(lang)
            log_op(
                db,
                "llm",
                f"主题级多语言生成：{lang}（待审核）",
                ref_type="job",
                ref_id=ctx.job_id,
                payload={"theme_id": theme_id, "lang": lang},
            )
    ctx.progress(phase="done", created=len(report["created"]), updated=len(report["updated"]))
    return report
