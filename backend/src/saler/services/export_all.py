"""全量数据导出（开放格式，未来企业 Web 版迁移预留；contracts/data-exchange.md §6 末段）。

- 每实体一个 ``<table>.jsonl`` + ``manifest.json``，打包为 ``saler-export-<ts>.zip``；
- 凭据类列（``secret_encrypted``）一律不导出（FR-006/宪法第 V 条）。
"""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from saler import __version__
from saler.db.models import (
    AppSetting,
    BackupRecord,
    Campaign,
    CampaignChannel,
    CampaignRound,
    Channel,
    Company,
    Contact,
    ContentTheme,
    ContentVariant,
    ContentVersion,
    CrawlJob,
    Domain,
    DomainSeedHit,
    ExclusionRule,
    GraphEdge,
    GraphNode,
    Job,
    LlmProvider,
    NodeTerm,
    OperationLog,
    SearchProvider,
    Seed,
    SendRecord,
    Suppression,
    ValidationRecord,
)

# 导出顺序即依赖顺序（人读友好）；新增表时在此登记
EXPORT_MODELS = (
    GraphNode,
    NodeTerm,
    GraphEdge,
    Seed,
    ValidationRecord,
    DomainSeedHit,
    CrawlJob,
    Domain,
    Company,
    Contact,
    Suppression,
    ExclusionRule,
    ContentTheme,
    ContentVariant,
    ContentVersion,
    Channel,
    Campaign,
    CampaignChannel,
    CampaignRound,
    SendRecord,
    LlmProvider,
    SearchProvider,
    AppSetting,
    BackupRecord,
    OperationLog,
    Job,
)

REDACTED_COLUMNS = {"secret_encrypted"}


def _row_to_dict(obj) -> dict:
    row: dict = {}
    for column in obj.__table__.columns:
        if column.name in REDACTED_COLUMNS:
            continue  # 凭据零导出
        value = getattr(obj, column.name)
        if isinstance(value, datetime):
            row[column.name] = value.isoformat()
        else:
            row[column.name] = value
    return row


def export_all_data(
    session_factory: sessionmaker[Session],
    data_dir: Path | str,
    *,
    out_dir: Path | str | None = None,
) -> dict:
    data_dir = Path(data_dir)
    out_dir = Path(out_dir) if out_dir is not None else data_dir / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    archive = out_dir / f"saler-export-{stamp}.zip"

    counts: dict[str, int] = {}
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for model in EXPORT_MODELS:
            table = model.__tablename__
            with session_factory() as db:
                rows = [_row_to_dict(obj) for obj in db.query(model).all()]
            counts[table] = len(rows)
            zf.writestr(
                f"{table}.jsonl",
                "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows),
            )
        manifest = {
            "format": "saler-export",
            "version": 1,
            "app_version": __version__,
            "exported_at": datetime.now(UTC).isoformat(),
            "counts": counts,
            "note": "开放格式：每实体一个 JSONL；凭据类字段一律不导出（FR-006）",
        }
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    return {"path": str(archive), "counts": counts, "size_bytes": archive.stat().st_size}
