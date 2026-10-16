"""模板库存取服务（006 模板库版）：app_setting KV 上的读取 / 创建 / 更新 / 删除 / 生效切换。

- 键 `prompt_templates_{feature}`；值 `{"active_id": str|null, "items": [{id,name,content,updated_at}]}`；
- **内置默认模板永不落库**：行缺失或 `active_id=null`（或悬空）→ 生效注册表默认（data-model §1）；
- 内容经 `registry.validate_template`：errors 阻断（ValidationFailed），warnings 随返回
  交由调用方（API 层）呈现——规则只有一份（research R6）；
- 名称规则：strip 后必填、≤ NAME_MAX_LENGTH、同功能内唯一；库容 ≤ MAX_TEMPLATES；
- 删除生效模板自动回退默认；`get_effective` 签名 `(content, customized)` 与单模板版一致
  （运行管线零改动）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from saler.core.errors import NotFound, ValidationFailed
from saler.core.prompts import registry
from saler.services import settings_service

KEY_PREFIX = "prompt_templates_"

#: 模板名称上限（契约 §2 max_name_length）
NAME_MAX_LENGTH = 60
#: 每功能模板数量上限（契约 §2 max_templates）
MAX_TEMPLATES = 50


def key_for(feature_key: str) -> str:
    return f"{KEY_PREFIX}{feature_key}"


def _now_iso() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat()


def _empty() -> dict:
    return {"active_id": None, "items": []}


def _load(db: Session, feature_key: str) -> dict:
    """读取归一（防脏数据外溢）：非法形状/条目一律丢弃；active_id 悬空视为默认。"""
    row = settings_service.get(db, key_for(feature_key), None)
    if not isinstance(row, dict):
        return _empty()
    items: list[dict] = []
    for raw in row.get("items") or []:
        if not isinstance(raw, dict):
            continue
        tid, name, content = raw.get("id"), raw.get("name"), raw.get("content")
        if not (isinstance(tid, str) and tid and isinstance(name, str) and name and isinstance(content, str)):
            continue
        items.append(
            {"id": tid, "name": name, "content": content, "updated_at": raw.get("updated_at")}
        )
    active = row.get("active_id")
    if not any(item["id"] == active for item in items):
        active = None
    return {"active_id": active, "items": items}


def _save(db: Session, feature_key: str, data: dict) -> None:
    settings_service.set_value(db, key_for(feature_key), data)


def _validate_name(data: dict, name: str | None, *, exclude_id: str | None = None) -> str:
    clean = (name or "").strip()
    if not clean:
        raise ValidationFailed("模板名称不能为空")
    if len(clean) > NAME_MAX_LENGTH:
        raise ValidationFailed(f"模板名称过长（{len(clean)}/{NAME_MAX_LENGTH} 字符）")
    if any(item["name"] == clean and item["id"] != exclude_id for item in data["items"]):
        raise ValidationFailed(f"模板名称已存在：{clean}（同功能内不得重名）")
    return clean


def _validate_content(feature_key: str, content: str) -> list[dict]:
    result = registry.validate_template(feature_key, content)
    if result["errors"]:
        raise ValidationFailed(result["errors"][0])
    return result["warnings"]


def _find(data: dict, template_id: str) -> dict:
    item = next((it for it in data["items"] if it["id"] == template_id), None)
    if item is None:
        raise NotFound("提示词模板")
    return item


def list_templates(db: Session, feature_key: str) -> tuple[list[dict], str | None]:
    """返回 (库内模板列表, 生效模板 id)；active_id 为 None 表示生效内置默认。"""
    data = _load(db, feature_key)
    return data["items"], data["active_id"]


def get_active(db: Session, feature_key: str) -> dict | None:
    """当前生效的具名模板（未自定义返回 None；徽标/详情呈现用）。"""
    items, active_id = list_templates(db, feature_key)
    return next((it for it in items if it["id"] == active_id), None)


def get_effective(db: Session, feature_key: str) -> tuple[str, bool]:
    """返回 (生效模板内容, 是否自定义)；未知功能键 KeyError（调用方先行校验）。"""
    feature = registry.FEATURES[feature_key]
    active = get_active(db, feature_key)
    if active is None:
        return feature.default_template, False
    return active["content"], True


def create(
    db: Session, feature_key: str, *, name: str, content: str, activate: bool = True
) -> list[dict]:
    """创建/另存为：名称与容量规则 + 内容校验；激活与否由 activate 决定。返回 warnings。"""
    data = _load(db, feature_key)
    if len(data["items"]) >= MAX_TEMPLATES:
        raise ValidationFailed(f"模板数量已达上限（{MAX_TEMPLATES}），请先删除不再使用的模板")
    clean = _validate_name(data, name)
    warnings = _validate_content(feature_key, content)
    template_id = f"t_{uuid4().hex[:8]}"
    while any(item["id"] == template_id for item in data["items"]):
        template_id = f"t_{uuid4().hex[:8]}"
    data["items"].append(
        {"id": template_id, "name": clean, "content": content, "updated_at": _now_iso()}
    )
    if activate:
        data["active_id"] = template_id
    _save(db, feature_key, data)
    return warnings


def update(
    db: Session, feature_key: str, template_id: str, *, name: str | None = None, content: str | None = None
) -> list[dict]:
    """更新内容 / 重命名（至少一项）；校验先于持久化（失败不改动既有数据）。返回 warnings。"""
    data = _load(db, feature_key)
    item = _find(data, template_id)
    if name is not None:
        item["name"] = _validate_name(data, name, exclude_id=template_id)
    warnings: list[dict] = []
    if content is not None:
        warnings = _validate_content(feature_key, content)
        item["content"] = content
    item["updated_at"] = _now_iso()
    _save(db, feature_key, data)
    return warnings


def delete(db: Session, feature_key: str, template_id: str) -> None:
    """删除模板；删除生效模板自动回退内置默认（服务端行为，契约 §3c）。"""
    data = _load(db, feature_key)
    remaining = [item for item in data["items"] if item["id"] != template_id]
    if len(remaining) == len(data["items"]):
        raise NotFound("提示词模板")
    data["items"] = remaining
    if data["active_id"] == template_id:
        data["active_id"] = None
    _save(db, feature_key, data)


def activate(db: Session, feature_key: str, template_id: str | None) -> None:
    """切换生效；None = 切回内置默认（模板库保留）；幂等。"""
    data = _load(db, feature_key)
    if template_id is not None and not any(item["id"] == template_id for item in data["items"]):
        raise NotFound("提示词模板")
    data["active_id"] = template_id
    _save(db, feature_key, data)
