"""LLM Provider 配置服务（FR-030）：CRUD / 默认互斥 / 密钥只写 / 健康标记。

密钥字段（secret_encrypted）经 EncryptedText 加密落库；本服务只负责写入与
"留空则保留"，任何读路径都不回传明文（api/serializers.llm_provider_to_dict）。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from saler.core.errors import NotFound, ValidationFailed
from saler.db.models import LlmProvider

ALLOWED_TYPES = ("openai_compatible",)


def list_providers(db: Session) -> list[LlmProvider]:
    return db.query(LlmProvider).order_by(LlmProvider.id.asc()).all()


def get_provider(db: Session, provider_id: int) -> LlmProvider:
    row = db.get(LlmProvider, provider_id)
    if row is None:
        raise NotFound("大模型服务")
    return row


def _clear_defaults(db: Session, *, except_id: int | None = None) -> None:
    query = db.query(LlmProvider).filter(LlmProvider.is_default.is_(True))
    if except_id is not None:
        query = query.filter(LlmProvider.id != except_id)
    for row in query.all():
        row.is_default = False


def create_provider(
    db: Session,
    *,
    name: str,
    provider_type: str = "openai_compatible",
    base_url: str,
    model: str = "",
    api_key: str | None = None,
    params: dict | None = None,
    is_default: bool = False,
) -> LlmProvider:
    name = (name or "").strip()
    base_url = (base_url or "").strip()
    if not name or not base_url:
        raise ValidationFailed("名称与接入地址不能为空")
    if provider_type not in ALLOWED_TYPES:
        raise ValidationFailed(f"暂不支持的 provider_type：{provider_type}")
    first = db.query(LlmProvider).count() == 0
    if is_default or first:
        _clear_defaults(db)
    row = LlmProvider(
        name=name,
        provider_type=provider_type,
        base_url=base_url,
        model=model or "",
        secret_encrypted=api_key,  # None/空 不写入
        params=params or {},
        is_default=is_default or first,
    )
    db.add(row)
    db.commit()
    return row


def update_provider(
    db: Session,
    provider_id: int,
    *,
    name: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    params: dict | None = None,
    is_default: bool | None = None,
) -> LlmProvider:
    row = get_provider(db, provider_id)
    if name is not None:
        if not name.strip():
            raise ValidationFailed("名称不能为空")
        row.name = name.strip()
    if base_url is not None:
        if not base_url.strip():
            raise ValidationFailed("接入地址不能为空")
        row.base_url = base_url.strip()
    if model is not None:
        row.model = model
    if params is not None:
        row.params = params
    if api_key:  # 空字符串/None = 保留原密钥（只写不读回的配套语义）
        row.secret_encrypted = api_key
    if is_default is True:
        _clear_defaults(db, except_id=row.id)
        row.is_default = True
    elif is_default is False:
        row.is_default = False
    db.commit()
    return row


def delete_provider(db: Session, provider_id: int) -> None:
    row = get_provider(db, provider_id)
    db.delete(row)
    db.commit()


def record_health(db: Session, provider_id: int, *, ok: bool, detail: str) -> LlmProvider:
    row = get_provider(db, provider_id)
    row.health = "healthy" if ok else "failing"
    row.last_test_at = datetime.now(UTC)
    row.last_test_result = detail[:2000]
    db.commit()
    return row
