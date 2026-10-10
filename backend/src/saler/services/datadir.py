"""数据目录解析与校验（FR-002/033）。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "saler-tool"
MIN_FREE_BYTES = 200 * 1024 * 1024  # 200 MB

_SUBDIRS = ("backups", "exports", "logs", "secrets")


def default_data_dir() -> Path:
    return Path(user_data_dir(APP_NAME))


def resolve_data_dir() -> Path:
    """``SALER_DATA_DIR`` 环境变量优先；否则平台惯例目录。"""
    env = os.environ.get("SALER_DATA_DIR")
    return Path(env) if env else default_data_dir()


def ensure_layout(data_dir: Path | str) -> Path:
    d = Path(data_dir)
    for sub in _SUBDIRS:
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def check_writable(path: Path | str) -> tuple[bool, str]:
    """校验目标目录可写且磁盘空间充足（设置页与迁移前调用）。"""
    p = Path(path)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"无法创建目录：{exc}"
    probe = p / ".saler_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return False, f"目录不可写：{exc}"
    free = shutil.disk_usage(p).free
    if free < MIN_FREE_BYTES:
        return False, f"磁盘空间不足（剩余 {free // 1024 // 1024} MB < 200 MB）"
    return True, ""


def db_path(data_dir: Path | str) -> Path:
    return Path(data_dir) / "saler.db"
