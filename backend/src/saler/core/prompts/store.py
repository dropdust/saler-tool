"""模板存取服务（006）：app_setting KV 上的"有效模板"读取 / 保存 / 恢复默认。

- 键 `prompt_template_{feature}`；**行存在 = 已自定义**（data-model.md §1）；
- 无行（或脏数据行无 content）→ 注册表默认，customized=False；
- 保存经 `registry.validate_template`：errors 阻断（ValidationFailed），warnings 随返回
  交由调用方（API 层）呈现——规则只有一份，前后端同源（research R6）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from saler.core.errors import ValidationFailed
from saler.core.prompts import registry
from saler.services import settings_service

KEY_PREFIX = "prompt_template_"


def key_for(feature_key: str) -> str:
    return f"{KEY_PREFIX}{feature_key}"


def get_effective(db: Session, feature_key: str) -> tuple[str, bool]:
    """返回 (有效模板文本, 是否已自定义)；未知功能键 KeyError（调用方先行校验）。"""
    feature = registry.FEATURES[feature_key]
    row = settings_service.get(db, key_for(feature_key), None)
    content = str((row or {}).get("content") or "") if isinstance(row, dict) else ""
    if not content:  # 无行或脏数据（缺 content）→ 一律回落默认（防脏数据外溢）
        return feature.default_template, False
    return content, True


def save(db: Session, feature_key: str, content: str) -> list[dict]:
    """校验通过后写入；返回 warnings（不阻断保存）。errors 非空抛 ValidationFailed。"""
    result = registry.validate_template(feature_key, content)
    if result["errors"]:
        raise ValidationFailed(result["errors"][0])
    settings_service.set_value(db, key_for(feature_key), {"content": content})
    return result["warnings"]


def reset(db: Session, feature_key: str) -> None:
    """恢复默认 = 删行；对未自定义功能幂等无副作用。"""
    settings_service.delete_value(db, key_for(feature_key))
