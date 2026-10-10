"""数据目录解析与校验（FR-002/033）。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "saler-tool"
MIN_FREE_BYTES = 200 * 1024 * 1024  # 200 MB

_SUBDIRS = ("backups", "exports", "logs", "secrets")


def default_data_dir() -> Path:
    return Path(user_data_dir(APP_NAME))


def _read_pointer() -> Path | None:
    """平台默认目录下的迁移指针（relocation.json，原子写入）。"""
    pointer = default_data_dir() / "relocation.json"
    try:
        if pointer.exists():
            data = json.loads(pointer.read_text(encoding="utf-8"))
            target = Path(str(data.get("data_dir", "")))
            if target and target.exists():
                return target
    except Exception:  # 指针损坏则回退默认目录
        pass
    return None


def resolve_data_dir() -> Path:
    """解析顺序：``SALER_DATA_DIR`` 环境变量 > 迁移指针 > 平台惯例目录。"""
    env = os.environ.get("SALER_DATA_DIR")
    if env:
        return Path(env)
    return _read_pointer() or default_data_dir()


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


def move_data_dir(old: Path | str, new: Path | str) -> dict:
    """复制 → 核对 → 原子指针切换（FR-033）。

    旧数据保留在原有位置（由用户确认后自行删除）；运行时热切换不做，
    写入迁移指针后需重启应用生效。
    """
    from saler.core.errors import ValidationFailed

    old, new = Path(old), Path(new)
    if not (old / "saler.db").exists():
        raise ValidationFailed("源目录缺少 saler.db，无法迁移")
    if old.resolve() == new.resolve():
        raise ValidationFailed("目标目录与当前数据目录相同")
    ok, message = check_writable(new)
    if not ok:
        raise ValidationFailed(message)
    if any(new.iterdir()):
        raise ValidationFailed("目标目录非空：请选择空目录或新目录")

    # 1) 落盘 WAL（单用户桌面，短暂独占可接受）
    with sqlite3.connect(old / "saler.db") as con:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # 2) 复制全量数据
    shutil.copytree(old, new, dirs_exist_ok=True)

    # 3) 核对：文件清单（忽略 WAL 临时文件）与主库 sha256
    def _manifest(root: Path) -> dict[str, int]:
        return {
            str(path.relative_to(root)): path.stat().st_size
            for path in sorted(root.rglob("*"))
            if path.is_file() and not path.name.endswith(("-wal", "-shm"))
        }

    source_files, target_files = _manifest(old), _manifest(new)
    missing = sorted(set(source_files) - set(target_files))
    if missing:
        raise ValidationFailed(f"复制不完整，缺少 {len(missing)} 个文件（如 {missing[:3]}）")

    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    source_sha, target_sha = _sha256(old / "saler.db"), _sha256(new / "saler.db")
    if source_sha != target_sha:
        raise ValidationFailed("主库校验不一致（数据目录可能正在写入）：请稍后重试迁移")

    # 4) 原子指针切换：指针位于平台默认目录；迁回默认目录时清除指针
    pointer = default_data_dir() / "relocation.json"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    if new.resolve() == default_data_dir().resolve():
        pointer.unlink(missing_ok=True)
    else:
        tmp = pointer.with_name("relocation.json.tmp")
        tmp.write_text(
            json.dumps(
                {
                    "data_dir": str(new),
                    "moved_from": str(old),
                    "moved_at": datetime.now(UTC).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(tmp, pointer)

    return {
        "new_data_dir": str(new),
        "files_copied": len(target_files),
        "db_sha256": target_sha,
        "restart_required": True,
        "note": "旧数据已保留在原有位置；确认无误后可自行删除。重启应用后生效。",
    }
