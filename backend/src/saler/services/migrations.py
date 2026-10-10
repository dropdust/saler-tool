"""以编程方式运行 Alembic 迁移（桌面端启动时调用；升级不丢数据，FR-004）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _find_paths() -> tuple[Path, Path]:
    """定位 alembic.ini 与脚本目录（开发态 src 布局 / 冻结包 _MEIPASS）。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
        return base / "alembic.ini", base / "alembic"
    backend_root = Path(__file__).resolve().parents[3]  # backend/src/saler/services/x.py -> backend/
    return backend_root / "alembic.ini", backend_root / "alembic"


def run_migrations(db_url: str) -> None:
    from alembic.config import Config

    from alembic import command

    ini_path, script_dir = _find_paths()
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(script_dir))
    # env.py 从环境变量读取 URL（兼容 Config 选项被忽略的情形）
    os.environ["SALER_DB_URL"] = db_url
    command.upgrade(cfg, "head")
