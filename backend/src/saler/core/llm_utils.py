"""LLM Provider 解析：从 `llm_provider` 表构造适配器实例。

（US1 的 AI 扩充/翻译使用；US3 提供完整的配置管理面。）
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from saler.core.errors import LLMNotConfigured, ValidationFailed
from saler.db.models import LlmProvider
from saler.providers.llm.openai_compatible import OpenAICompatibleProvider


def resolve_llm_provider(db: Session, provider_id: int | None = None):
    row: LlmProvider | None
    if provider_id is not None:
        row = db.get(LlmProvider, provider_id)
        if row is None:
            raise ValidationFailed(f"大模型服务不存在：{provider_id}")
    else:
        row = (
            db.query(LlmProvider).filter_by(is_default=True).first()
            or db.query(LlmProvider).order_by(LlmProvider.id.asc()).first()
        )
    if row is None:
        raise LLMNotConfigured("尚未配置大模型服务：请先在「设置 → 大模型」中添加并测试")
    return OpenAICompatibleProvider(
        base_url=row.base_url,
        api_key=row.secret_encrypted or "",  # EncryptedText 读路径自动解密
        model=row.model,
        supports_json_schema=bool((row.params or {}).get("supports_json_schema")),
        provider_name=row.name,
    )
