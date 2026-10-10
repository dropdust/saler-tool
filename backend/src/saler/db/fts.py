"""FTS5 影子表（T132）：company/contact 大表搜索加速；不可用时自动回退 LIKE。

- 影子表为 external-content FTS5（content='company' / 'contact'），触发器增量同步；
- 启用条件：`search_fts` 设置显式开启，或表规模超过阈值（默认 2 万行，"仅索引不足时启用"）；
- 查询按词前缀匹配（term*），特殊字符经引号转义，避免 FTS 语法注入。
"""

from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

FTS_MIN_ROWS = 20_000
_TOKEN_RE = re.compile(r"[0-9A-Za-z_@.\-]+")

_COMPANY_DDL = [
    "CREATE VIRTUAL TABLE IF NOT EXISTS company_fts USING fts5("
    "name, content='company', content_rowid='id', tokenize='unicode61')",
    "CREATE TRIGGER IF NOT EXISTS company_fts_ai AFTER INSERT ON company BEGIN "
    "INSERT INTO company_fts(rowid, name) VALUES (new.id, new.name); END",
    "CREATE TRIGGER IF NOT EXISTS company_fts_ad AFTER DELETE ON company BEGIN "
    "INSERT INTO company_fts(company_fts, rowid, name) VALUES ('delete', old.id, old.name); END",
    "CREATE TRIGGER IF NOT EXISTS company_fts_au AFTER UPDATE ON company BEGIN "
    "INSERT INTO company_fts(company_fts, rowid, name) VALUES ('delete', old.id, old.name); "
    "INSERT INTO company_fts(rowid, name) VALUES (new.id, new.name); END",
]
_CONTACT_DDL = [
    "CREATE VIRTUAL TABLE IF NOT EXISTS contact_fts USING fts5("
    "value, value_normalized, content='contact', content_rowid='id', tokenize='unicode61')",
    "CREATE TRIGGER IF NOT EXISTS contact_fts_ai AFTER INSERT ON contact BEGIN "
    "INSERT INTO contact_fts(rowid, value, value_normalized) "
    "VALUES (new.id, new.value, new.value_normalized); END",
    "CREATE TRIGGER IF NOT EXISTS contact_fts_ad AFTER DELETE ON contact BEGIN "
    "INSERT INTO contact_fts(contact_fts, rowid, value, value_normalized) "
    "VALUES ('delete', old.id, old.value, old.value_normalized); END",
    "CREATE TRIGGER IF NOT EXISTS contact_fts_au AFTER UPDATE ON contact BEGIN "
    "INSERT INTO contact_fts(contact_fts, rowid, value, value_normalized) "
    "VALUES ('delete', old.id, old.value, old.value_normalized); "
    "INSERT INTO contact_fts(rowid, value, value_normalized) "
    "VALUES (new.id, new.value, new.value_normalized); END",
]


def fts5_supported(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS __fts_probe USING fts5(x)"))
            conn.execute(text("DROP TABLE IF EXISTS __fts_probe"))
            conn.commit()
        return True
    except Exception:  # noqa: BLE001 —— 编译不含 FTS5 时回退 LIKE
        return False


def should_use_fts(db: Session, *, min_rows: int = FTS_MIN_ROWS) -> bool:
    """显式设置优先；未设置时仅当规模超过阈值才启用。"""
    from saler.db.models import Company
    from saler.services import settings_service

    setting = settings_service.get(db, "search_fts")
    if setting is not None:
        return bool(setting)
    return db.query(Company.id).count() >= min_rows


def ensure_shadow(engine: Engine) -> bool:
    """建影子表与同步触发器（幂等）。返回是否可用。"""
    if not fts5_supported(engine):
        return False
    with engine.connect() as conn:
        for statement in (*_COMPANY_DDL, *_CONTACT_DDL):
            conn.execute(text(statement))
        conn.commit()
    return True


def rebuild(engine: Engine) -> None:
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO company_fts(company_fts) VALUES('rebuild')"))
        conn.execute(text("INSERT INTO contact_fts(contact_fts) VALUES('rebuild')"))
        conn.commit()


def _match_expression(query: str) -> str:
    tokens = _TOKEN_RE.findall(query or "")
    return " AND ".join(f'"{token}"*' for token in tokens)


def search_company_ids(engine: Engine, query: str, *, limit: int = 2000) -> list[int]:
    expr = _match_expression(query)
    if not expr:
        return []
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT rowid FROM company_fts WHERE company_fts MATCH :expr LIMIT :limit"),
            {"expr": expr, "limit": limit},
        ).all()
    return [row[0] for row in rows]


def search_contact_ids(engine: Engine, query: str, *, limit: int = 2000) -> list[int]:
    expr = _match_expression(query)
    if not expr:
        return []
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT rowid FROM contact_fts WHERE contact_fts MATCH :expr LIMIT :limit"),
            {"expr": expr, "limit": limit},
        ).all()
    return [row[0] for row in rows]
