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


def _config(db_url: str):
    from alembic.config import Config

    ini_path, script_dir = _find_paths()
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(script_dir))
    # env.py 从环境变量读取 URL（兼容 Config 选项被忽略的情形）
    os.environ["SALER_DB_URL"] = db_url
    return cfg


def run_migrations(db_url: str) -> None:
    from alembic import command

    command.upgrade(_config(db_url), "head")


def ensure_schema(db_url: str) -> None:
    """把目标库准备到当前 schema：

    - 空库 → ``upgrade head``；
    - 已有业务表但无 alembic 版本戳（如 create_all 生成的库）→ ``stamp head``；
    - 已有版本戳 → 常规 ``upgrade``（跨版本备份恢复场景）。
    """
    import sqlite3

    path = db_url.removeprefix("sqlite:///")
    tables: set[str] = set()
    try:
        probe = sqlite3.connect(path)
        try:
            tables = {
                row[0]
                for row in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            probe.close()
    except sqlite3.Error:
        pass
    if {"seed", "job", "app_setting"} & tables and "alembic_version" not in tables:
        from alembic import command

        command.stamp(_config(db_url), "head")
        return
    run_migrations(db_url)
