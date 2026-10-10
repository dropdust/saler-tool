"""备份与恢复（contracts/data-exchange.md §6；FR-004/SC-005）。

- 归档：``saler-backup-<ts>.zip`` = ``manifest.json`` + ``saler.db``（sqlite backup API 一致性快照）；
- 校验：格式/版本/主库 SHA-256 三重检查，失败绝不触碰现有数据；
- 恢复：staged —— 解包 → 迁移到当前 schema → 旧库改名留档 → 原子替换；异常自动回滚。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from saler import __version__
from saler.core.errors import ValidationFailed

ARCHIVE_FORMAT = "saler-backup"
ARCHIVE_VERSION = 1
MANIFEST_NAME = "manifest.json"
DB_NAME = "saler.db"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_version(db_file: Path) -> str | None:
    try:
        handle = sqlite3.connect(db_file)
        try:
            row = handle.execute("SELECT version_num FROM alembic_version").fetchone()
        finally:
            handle.close()
        return row[0] if row else None
    except sqlite3.Error:
        return None


def create_backup(
    data_dir: Path | str,
    *,
    include_secrets: bool = False,
    out_dir: Path | str | None = None,
) -> dict:
    data_dir = Path(data_dir)
    db_file = data_dir / DB_NAME
    if not db_file.exists():
        raise ValidationFailed("数据目录缺少 saler.db，无法备份")
    if include_secrets:
        raise ValidationFailed("暂不支持随备份导出凭据（凭据始终留在本机钥匙串）")
    out_dir = Path(out_dir) if out_dir is not None else data_dir / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    archive = out_dir / f"saler-backup-{stamp}.zip"

    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / DB_NAME
        source = sqlite3.connect(db_file)
        target = sqlite3.connect(snapshot)
        with target:
            source.backup(target)  # 含 WAL 内容的一致性快照
        source.close()
        target.close()

        manifest = {
            "format": ARCHIVE_FORMAT,
            "version": ARCHIVE_VERSION,
            "app_version": __version__,
            "schema_version": _schema_version(snapshot),
            "created_at": datetime.now(UTC).isoformat(),
            "db_sha256": _sha256_file(snapshot),
            "db_bytes": snapshot.stat().st_size,
            "includes_secrets": False,
        }
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(snapshot, DB_NAME)
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))

    return {
        "path": str(archive),
        "size_bytes": archive.stat().st_size,
        "manifest": manifest,
    }


def read_manifest(archive_path: Path | str) -> dict:
    archive_path = Path(archive_path)
    if not archive_path.exists():
        raise ValidationFailed(f"备份文件不存在：{archive_path}")
    try:
        with zipfile.ZipFile(archive_path) as zf:
            raw = zf.read(MANIFEST_NAME)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValidationFailed(f"备份文件校验失败：不是有效的备份归档（{exc}）") from exc
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationFailed("备份文件校验失败：manifest.json 无法解析") from exc
    if manifest.get("format") != ARCHIVE_FORMAT:
        raise ValidationFailed("备份文件校验失败：格式标识不符")
    if manifest.get("version") != ARCHIVE_VERSION:
        raise ValidationFailed(
            f"备份文件校验失败：版本 {manifest.get('version')} 不受支持（当前 {ARCHIVE_VERSION}）"
        )
    return manifest


def validate_backup(archive_path: Path | str) -> dict:
    """完整校验：归档结构 + 主库 SHA-256。"""
    manifest = read_manifest(archive_path)
    with zipfile.ZipFile(archive_path) as zf:
        if DB_NAME not in zf.namelist():
            raise ValidationFailed("备份文件校验失败：缺少 saler.db")
        digest = hashlib.sha256()
        with zf.open(DB_NAME) as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    if digest.hexdigest() != manifest.get("db_sha256"):
        raise ValidationFailed("备份文件校验失败：数据校验和不一致（文件已损坏或被修改）")
    return {"ok": True, "manifest": manifest}


def restore_backup(archive_path: Path | str, data_dir: Path | str) -> dict:
    """staged restore：校验 → 解包 → 迁移到当前 schema → 原子替换（失败回滚）。"""
    manifest = validate_backup(archive_path)["manifest"]
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    db_file = data_dir / DB_NAME

    staged_root = Path(tempfile.mkdtemp(prefix="saler-restore-", dir=str(data_dir.parent)))
    previous_db: Path | None = None
    try:
        with zipfile.ZipFile(archive_path) as zf:
            zf.extract(DB_NAME, staged_root)  # 仅解出主库（不展开任意路径）
        staged_db = staged_root / DB_NAME

        # 升级到当前 schema（跨版本备份可恢复；失败则中止，不触碰现网数据）
        from saler.services.migrations import ensure_schema

        ensure_schema(f"sqlite:///{staged_db}")

        # 归并为"单文件"形态：checkpoint 后切回 DELETE 日志，
        # 否则 stamp/迁移写入的内容可能仍在 -wal 中，原子搬移会丢页
        handle = sqlite3.connect(staged_db)
        try:
            handle.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            handle.execute("PRAGMA journal_mode=DELETE")
            handle.execute("SELECT 1")
        finally:
            handle.close()

        # 原子替换：旧库改名留档 → 新库就位 → 清理旧 WAL/SHM
        if db_file.exists():
            previous_db = db_file.with_name(
                f"saler.db.pre-restore-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
            )
            os.replace(db_file, previous_db)
        os.replace(staged_db, db_file)
        for suffix in ("-wal", "-shm"):
            (data_dir / f"{DB_NAME}{suffix}").unlink(missing_ok=True)

        return {
            "restored_from": str(archive_path),
            "db_sha256": manifest["db_sha256"],
            "previous_db_backup": str(previous_db) if previous_db else None,
            "restart_required": True,
        }
    except Exception:
        # 回滚：新库尚未就位时，把旧库改回原名
        if previous_db is not None and previous_db.exists() and not db_file.exists():
            os.replace(previous_db, db_file)
        raise
    finally:
        shutil.rmtree(staged_root, ignore_errors=True)
