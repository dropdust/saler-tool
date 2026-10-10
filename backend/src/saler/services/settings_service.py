"""应用设置（app_setting KV + 默认值，开箱即用）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from saler.db.models import AppSetting

DEFAULTS: dict[str, Any] = {
    "ui_lang": "zh-CN",
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


def get_all(db: Session) -> dict[str, Any]:
    rows = {row.key: row.value for row in db.query(AppSetting).all()}
    return {**DEFAULTS, **rows}


def get(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(AppSetting, key)
    if row is not None:
        return row.value
    return DEFAULTS.get(key, default)


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
