"""应用设置（app_setting KV + 默认值，开箱即用）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from saler.db.models import AppSetting

DEFAULTS: dict[str, Any] = {
    "ui_lang": "zh-CN",
    "ui_theme": "light",  # 002-frontend-theme：light/dark（未知值读取归一为 light）
    "content_fallback_lang": "en",
    "proxy": "",
    "crawl_defaults": {
        "concurrency": 5,
        "per_host_delay_s": 1.0,
        "max_pages_per_site": 6,
        "respect_robots": True,
        "timeout_s": 20,
    },
    "send_defaults": {"rate_per_minute": 20, "daily_max": 200},
}

# 值域规则（002-frontend-theme，契约 contracts/theme-contract.md §1）：仅约束列出的键
VALUE_RULES: dict[str, tuple[Any, ...]] = {"ui_theme": ("light", "dark")}


def value_error(key: str, value: Any) -> str | None:
    """值域校验：非法返回可读错误消息（None=通过）；由 API 层抛 bad_request。"""
    allowed = VALUE_RULES.get(key)
    if allowed is not None and value not in allowed:
        return f"{key} 仅支持 {'/'.join(str(item) for item in allowed)}"
    return None


def _normalized(key: str, value: Any) -> Any:
    """读取归一：存储侧非法值（手工改库等）退回默认，防脏数据外溢（FR-006）。"""
    if value_error(key, value) is not None:
        return DEFAULTS.get(key)
    return value


def get_all(db: Session) -> dict[str, Any]:
    rows = {row.key: row.value for row in db.query(AppSetting).all()}
    merged = {**DEFAULTS, **rows}
    return {key: _normalized(key, value) for key, value in merged.items()}


def get(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(AppSetting, key)
    value = row.value if row is not None else DEFAULTS.get(key, default)
    return _normalized(key, value)


def set_value(db: Session, key: str, value: Any) -> Any:
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()
    return value


def is_known_key(db: Session, key: str) -> bool:
    return key in DEFAULTS or db.get(AppSetting, key) is not None
