"""内容 API：主题 / 语言版本 / 版本 / 发布流转 / 预览（FR-034~039）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from saler.api.deps import get_session
from saler.api.serializers import (
    content_theme_to_dict,
    content_variant_to_dict,
    content_version_to_dict,
)
from saler.core.content import service as content_service
from saler.core.content.render import render
from saler.core.errors import ValidationFailed
from saler.core.leads import company_service
from saler.core.sending import channel_service

router = APIRouter(prefix="/content", tags=["content"])


class ThemeCreate(BaseModel):
    name: str
    content_type: str = "email"
    master_lang: str = "zh"
    description: str | None = None


class ThemeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class VariantCreate(BaseModel):
    lang: str
    subject: str | None = None
    body_md: str = ""


class VariantUpdate(BaseModel):
    subject: str | None = None
    body_md: str | None = None
    change_note: str | None = None


class RestoreRequest(BaseModel):
    version_no: int


class PreviewRequest(BaseModel):
    vars: dict[str, str] = Field(default_factory=dict)
    company_id: int | None = None


def _variant_view(db: Session, variant) -> dict:
    return content_variant_to_dict(
        variant, current=content_service.get_current_version(db, variant)
    )


# ---------- 主题 ----------


@router.get("/themes")
def list_themes(
    q: str | None = None,
    content_type: str | None = None,
    db: Session = Depends(get_session),
) -> list[dict]:
    rows = content_service.list_themes(db, q=q, content_type=content_type).all()
    return [
        content_theme_to_dict(
            row, variants_count=len(content_service.list_variants(db, row.id))
        )
        for row in rows
    ]


@router.post("/themes", status_code=201)
def create_theme(payload: ThemeCreate, db: Session = Depends(get_session)) -> dict:
    theme = content_service.create_theme(db, **payload.model_dump())
    return content_theme_to_dict(theme)


@router.get("/themes/{theme_id}")
def get_theme(theme_id: int, db: Session = Depends(get_session)) -> dict:
    theme = content_service.get_theme(db, theme_id)
    view = content_theme_to_dict(theme, variants_count=len(content_service.list_variants(db, theme_id)))
    view["variants"] = [
        _variant_view(db, variant) for variant in content_service.list_variants(db, theme_id)
    ]
    return view


@router.put("/themes/{theme_id}")
def update_theme(theme_id: int, payload: ThemeUpdate, db: Session = Depends(get_session)) -> dict:
    theme = content_service.update_theme(db, theme_id, **payload.model_dump(exclude_none=True))
    return content_theme_to_dict(theme)


@router.delete("/themes/{theme_id}")
def delete_theme(theme_id: int, db: Session = Depends(get_session)) -> dict:
    content_service.delete_theme(db, theme_id)
    return {"ok": True}


# ---------- 语言版本 ----------


@router.get("/themes/{theme_id}/variants")
def list_variants(theme_id: int, db: Session = Depends(get_session)) -> list[dict]:
    content_service.get_theme(db, theme_id)
    return [
        _variant_view(db, variant) for variant in content_service.list_variants(db, theme_id)
    ]


@router.post("/themes/{theme_id}/variants", status_code=201)
def create_variant(theme_id: int, payload: VariantCreate, db: Session = Depends(get_session)) -> dict:
    variant = content_service.create_variant(db, theme_id=theme_id, **payload.model_dump())
    return _variant_view(db, variant)


@router.get("/variants/{variant_id}")
def get_variant(variant_id: int, db: Session = Depends(get_session)) -> dict:
    return _variant_view(db, content_service.get_variant(db, variant_id))


@router.put("/variants/{variant_id}")
def update_variant(variant_id: int, payload: VariantUpdate, db: Session = Depends(get_session)) -> dict:
    content_service.update_variant_content(
        db, variant_id, **payload.model_dump(exclude_unset=True)
    )
    return _variant_view(db, content_service.get_variant(db, variant_id))


@router.post("/variants/{variant_id}/publish")
def publish_variant(variant_id: int, db: Session = Depends(get_session)) -> dict:
    variant = content_service.set_status(db, variant_id, "published")
    return _variant_view(db, variant)


@router.post("/variants/{variant_id}/archive")
def archive_variant(variant_id: int, db: Session = Depends(get_session)) -> dict:
    variant = content_service.set_status(db, variant_id, "archived")
    return _variant_view(db, variant)


@router.post("/variants/{variant_id}/back-to-draft")
def back_to_draft(variant_id: int, db: Session = Depends(get_session)) -> dict:
    variant = content_service.set_status(db, variant_id, "draft")
    return _variant_view(db, variant)


@router.post("/variants/{variant_id}/restore")
def restore_variant(variant_id: int, payload: RestoreRequest, db: Session = Depends(get_session)) -> dict:
    version = content_service.restore_version(db, variant_id, payload.version_no)
    return content_version_to_dict(version)


@router.get("/variants/{variant_id}/versions")
def list_versions(variant_id: int, db: Session = Depends(get_session)) -> list[dict]:
    content_service.get_variant(db, variant_id)
    return [
        content_version_to_dict(row) for row in content_service.list_versions(db, variant_id)
    ]


@router.get("/published")
def list_published(db: Session = Depends(get_session)) -> list[dict]:
    """已发布清单（营销计划选用门，FR-037/046）。"""
    from saler.db.models import ContentTheme

    theme_names = {theme.id: theme.name for theme in db.query(ContentTheme).all()}
    rows = []
    for variant in content_service.list_published(db):
        current = content_service.get_current_version(db, variant)
        rows.append(
            {
                "id": variant.id,
                "theme_id": variant.theme_id,
                "theme_name": theme_names.get(variant.theme_id, ""),
                "lang": variant.lang,
                "subject": current.subject if current else None,
            }
        )
    return rows


def _render_version(db: Session, current, payload_vars: dict, company_id: int | None) -> tuple[str, str, list[str]]:
    variables: dict[str, str] = {key: str(value) for key, value in payload_vars.items()}
    if company_id is not None:
        company = company_service.get_company(db, company_id)
        variables.setdefault("company_name", company.name or "")
        variables.setdefault("country", company.country or "")
        variables.setdefault("language", company.language or "")
    subject, warn_subject = render(current.subject or "", variables)
    body, warn_body = render(current.body_md, variables)
    return subject, body, warn_subject + warn_body


@router.post("/variants/{variant_id}/preview")
def preview_variant(
    variant_id: int, payload: PreviewRequest, db: Session = Depends(get_session)
) -> dict:
    variant = content_service.get_variant(db, variant_id)
    current = content_service.get_current_version(db, variant)
    if current is None:
        return {"subject": "", "body": "", "warnings": ["尚未有内容版本"]}
    subject, body, warnings = _render_version(db, current, payload.vars, payload.company_id)
    return {"subject": subject, "body": body, "warnings": warnings}


class TestSendRequest(BaseModel):
    channel_id: int
    to: str
    vars: dict[str, str] = Field(default_factory=dict)
    company_id: int | None = None


@router.post("/variants/{variant_id}/test-send")
def test_send_variant(
    variant_id: int, payload: TestSendRequest, db: Session = Depends(get_session)
) -> dict:
    """内容版本测试发送（FR-039）：变量渲染后经所选通道发给自己（试发与正式同一接口）。"""
    variant = content_service.get_variant(db, variant_id)
    current = content_service.get_current_version(db, variant)
    if current is None:
        raise ValidationFailed("尚未有内容版本，无法测试发送")
    channel = channel_service.get_channel(db, payload.channel_id)
    subject, body, _warnings = _render_version(db, current, payload.vars, payload.company_id)
    return channel_service.send_content_test(
        db, channel, to=payload.to, subject=subject, body_text=body
    )
