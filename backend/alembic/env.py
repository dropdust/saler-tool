"""Alembic 环境：目标元数据来自 saler.db.models；SQLite 使用 batch 模式。

数据库 URL 解析：``SALER_DB_URL`` 环境变量 > 默认 ``sqlite:///./saler-dev.db``。
应用运行时通过 `saler.services.migrations.run_migrations(data_dir)` 以编程方式调用。
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from saler.db.base import Base
import saler.db.models  # noqa: F401  确保全部模型注册到 metadata

config = context.config
if config.config_file_name is not None and os.path.exists(config.config_file_name):
    try:
        fileConfig(config.config_file_name)
    except Exception:
        pass

target_metadata = Base.metadata


def get_url() -> str:
    return os.environ.get("SALER_DB_URL", "sqlite:///./saler-dev.db")


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url())
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
