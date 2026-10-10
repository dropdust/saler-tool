"""内容服务（FR-034/037）：主题/语言版本/版本号/状态机。

关键语义（data-model.md C2/C3）：
- 修改内容 = 生成新版本（version_no 递增）；历史版本可恢复；
- **恢复历史版本 = 以旧内容创建新版本**（保持审计链完整）；
- 已发布内容被改写 → 自动回到 draft（先审后发的防线）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from saler.core.content.render import parse_variables
from saler.core.errors import Duplicate, NotFound, ValidationFailed
from saler.db.models import ContentTheme, ContentVariant, ContentVersion

VARIANT_STATUSES = ("draft", "review", "published", "archived")


# ---------- 主题 ----------


def create_theme(
    db: Session,
    *,
    name: str,
    content_type: str = "email",
    master_lang: str = "zh",
    description: str | None = None,
) -> ContentTheme:
    name = (name or "").strip()
    if not name:
        raise ValidationFailed("主题名称不能为空")
    if content_type not in ("email", "sms", "social_message"):
        raise ValidationFailed(f"非法内容类型：{content_type}")
    if db.query(ContentTheme).filter_by(name=name).first():
        raise Duplicate(f"内容主题已存在：{name}")
    theme = ContentTheme(
        name=name, content_type=content_type, master_lang=master_lang, description=description
    )
    db.add(theme)
    db.commit()
    return theme


def get_theme(db: Session, theme_id: int) -> ContentTheme:
    theme = db.get(ContentTheme, theme_id)
    if theme is None:
        raise NotFound("内容主题")
    return theme


def list_themes(db: Session, *, q: str | None = None, content_type: str | None = None) -> Query:
    query = db.query(ContentTheme)
    if q:
        query = query.filter(ContentTheme.name.contains(q))
    if content_type:
        query = query.filter(ContentTheme.content_type == content_type)
    return query.order_by(ContentTheme.id.desc())


def update_theme(db: Session, theme_id: int, **fields: Any) -> ContentTheme:
    theme = get_theme(db, theme_id)
    for key in ("name", "description"):
        if fields.get(key) is not None:
            setattr(theme, key, fields[key])
    db.commit()
    return theme


def delete_theme(db: Session, theme_id: int) -> None:
    theme = get_theme(db, theme_id)
    for variant in db.query(ContentVariant).filter_by(theme_id=theme.id).all():
        db.query(ContentVersion).filter_by(variant_id=variant.id).delete()
        db.delete(variant)
    db.delete(theme)
    db.commit()


# ---------- 语言版本与版本 ----------


def list_variants(db: Session, theme_id: int) -> list[ContentVariant]:
    return (
        db.query(ContentVariant)
        .filter_by(theme_id=theme_id)
        .order_by(ContentVariant.lang.asc())
        .all()
    )


def get_variant(db: Session, variant_id: int) -> ContentVariant:
    variant = db.get(ContentVariant, variant_id)
    if variant is None:
        raise NotFound("语言版本")
    return variant


def get_current_version(db: Session, variant: ContentVariant) -> ContentVersion | None:
    if variant.current_version_id is None:
        return None
    return db.get(ContentVersion, variant.current_version_id)


def get_version(db: Session, variant_id: int, version_no: int) -> ContentVersion:
    row = (
        db.query(ContentVersion)
        .filter_by(variant_id=variant_id, version_no=version_no)
        .first()
    )
    if row is None:
        raise NotFound(f"版本 v{version_no}")
    return row


def list_versions(db: Session, variant_id: int) -> list[ContentVersion]:
    return (
        db.query(ContentVersion)
        .filter_by(variant_id=variant_id)
        .order_by(ContentVersion.version_no.desc())
        .all()
    )


def _next_version_no(db: Session, variant_id: int) -> int:
    latest = (
        db.query(func.max(ContentVersion.version_no)).filter_by(variant_id=variant_id).scalar()
    )
    return (latest or 0) + 1


def _add_version(
    db: Session,
    variant: ContentVariant,
    *,
    subject: str | None,
    body_md: str,
    change_note: str | None,
    created_by: str = "user",
) -> ContentVersion:
    version = ContentVersion(
        variant_id=variant.id,
        version_no=_next_version_no(db, variant.id),
        subject=subject,
        body_md=body_md or "",
        variables=parse_variables(body_md or ""),
        change_note=change_note,
        created_by=created_by,
    )
    db.add(version)
    db.flush()
    variant.current_version_id = version.id
    db.commit()
    return version


def create_variant(
    db: Session,
    *,
    theme_id: int,
    lang: str,
    subject: str | None = None,
    body_md: str = "",
    source: str = "manual",
    parent_variant_id: int | None = None,
) -> ContentVariant:
    get_theme(db, theme_id)
    lang = (lang or "").strip()
    if not lang:
        raise ValidationFailed("语言不能为空")
    if db.query(ContentVariant).filter_by(theme_id=theme_id, lang=lang).first():
        raise Duplicate(f"该语言版本已存在：{lang}")
    variant = ContentVariant(
        theme_id=theme_id,
        lang=lang,
        source=source,
        parent_variant_id=parent_variant_id,
        status="draft",
    )
    db.add(variant)
    db.commit()
    _add_version(
        db,
        variant,
        subject=subject,
        body_md=body_md,
        change_note="初始版本",
        created_by="llm" if source.startswith("llm") else "user",
    )
    db.refresh(variant)
    return variant


def update_variant_content(
    db: Session,
    variant_id: int,
    *,
    subject: str | None = None,
    body_md: str | None = None,
    change_note: str | None = None,
    created_by: str = "user",
) -> ContentVersion:
    variant = get_variant(db, variant_id)
    current = get_current_version(db, variant)
    new_subject = subject if subject is not None else (current.subject if current else None)
    new_body = body_md if body_md is not None else (current.body_md if current else "")
    version = _add_version(
        db,
        variant,
        subject=new_subject,
        body_md=new_body,
        change_note=change_note or "内容修改",
        created_by=created_by,
    )
    if variant.status == "published":
        variant.status = "draft"  # 已发布被改写 → 回草稿重审
        db.commit()
    return version


def restore_version(db: Session, variant_id: int, version_no: int) -> ContentVersion:
    """恢复 = 以旧版本内容创建新版本（保留审计链）。"""
    old = get_version(db, variant_id, version_no)
    return update_variant_content(
        db,
        variant_id,
        subject=old.subject,
        body_md=old.body_md,
        change_note=f"恢复自 v{version_no}",
    )


def set_status(db: Session, variant_id: int, status: str) -> ContentVariant:
    if status not in VARIANT_STATUSES:
        raise ValidationFailed(f"非法状态：{status}")
    variant = get_variant(db, variant_id)
    if status == "published":
        current = get_current_version(db, variant)
        if current is None or not (
            (current.subject or "").strip() or (current.body_md or "").strip()
        ):
            raise ValidationFailed("内容为空，不能发布")
    variant.status = status
    db.commit()
    return variant


def list_published(db: Session) -> list[ContentVariant]:
    """已发布清单（营销计划只能选这里面的版本，FR-037/046）。"""
    return (
        db.query(ContentVariant)
        .filter_by(status="published")
        .order_by(ContentVariant.theme_id.asc(), ContentVariant.lang.asc())
        .all()
    )
