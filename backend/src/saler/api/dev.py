"""开发模式入口：``uvicorn saler.api.dev:app --reload --port 8620``。

使用 ``SALER_DATA_DIR``（默认平台数据目录），自动建目录、初始化密钥、跑迁移。
令牌取自 ``SALER_TOKEN``（默认 ``dev-token``）。
"""

from __future__ import annotations

import os

from saler.api.main import create_app
from saler.db.session import make_engine
from saler.logging_config import setup_logging
from saler.security.crypto import resolve_secret_box
from saler.services.datadir import db_path, ensure_layout, resolve_data_dir
from saler.services.migrations import run_migrations

_data_dir = ensure_layout(resolve_data_dir())
setup_logging(_data_dir)
resolve_secret_box(_data_dir)
run_migrations(f"sqlite:///{db_path(_data_dir)}")

_engine = make_engine(db_path(_data_dir))

app = create_app(
    engine=_engine, token=os.environ.get("SALER_TOKEN", "dev-token"), data_dir=_data_dir
)
