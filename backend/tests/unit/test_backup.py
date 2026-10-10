"""T077 单元测试：备份归档生成/校验/损坏拒绝；staged restore 回滚（FR-004/SC-005）。"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

import saler.db.models  # noqa: F401
from saler.core.errors import ValidationFailed
from saler.db.base import Base
from saler.db.models import AppSetting
from saler.db.session import make_engine
from saler.services import backup as backup_service


def _make_data_dir(tmp_path: Path, *, setting_key: str, setting_value: str) -> Path:
    data_dir = tmp_path / f"data-{setting_key}"
    data_dir.mkdir(parents=True)
    engine = make_engine(data_dir / "saler.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(AppSetting(key=setting_key, value=setting_value))
        db.commit()
    engine.dispose()
    return data_dir


def _setting(data_dir: Path, key: str) -> str | None:
    engine = make_engine(data_dir / "saler.db")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        row = db.get(AppSetting, key)
        value = row.value if row else None
    engine.dispose()
    return value  # type: ignore[return-value]


def test_create_backup_manifest_and_checksum(tmp_path):
    data_dir = _make_data_dir(tmp_path, setting_key="marker_a", setting_value="A")
    result = backup_service.create_backup(data_dir)
    archive = Path(result["path"])
    assert archive.exists() and result["size_bytes"] > 0

    manifest = backup_service.read_manifest(archive)
    assert manifest["format"] == "saler-backup"
    assert manifest["version"] == 1
    assert manifest["includes_secrets"] is False
    assert len(manifest["db_sha256"]) == 64
    assert backup_service.validate_backup(archive)["ok"] is True


def test_validate_rejects_corrupt_archive(tmp_path):
    data_dir = _make_data_dir(tmp_path, setting_key="marker_b", setting_value="B")
    archive = Path(backup_service.create_backup(data_dir)["path"])
    archive.write_bytes(b"not a zip at all")
    with pytest.raises(ValidationFailed):
        backup_service.validate_backup(archive)


def test_validate_rejects_tampered_db(tmp_path):
    data_dir = _make_data_dir(tmp_path, setting_key="marker_c", setting_value="C")
    archive = Path(backup_service.create_backup(data_dir)["path"])
    # 重写 zip，替换 db 内容 → 校验和必然不符
    tampered = archive.with_name("tampered.zip")
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(tampered, "w") as target:
        for item in source.namelist():
            data = source.read(item)
            if item == "saler.db":
                data = data + b"\x00" * 16
            target.writestr(item, data)
    with pytest.raises(ValidationFailed):
        backup_service.validate_backup(tampered)


def test_validate_rejects_unknown_format_version(tmp_path):
    data_dir = _make_data_dir(tmp_path, setting_key="marker_d", setting_value="D")
    archive = Path(backup_service.create_backup(data_dir)["path"])
    bad = archive.with_name("bad-version.zip")
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(bad, "w") as target:
        for item in source.namelist():
            data = source.read(item)
            if item == "manifest.json":
                data = data.replace(b'"version": 1', b'"version": 999')
            target.writestr(item, data)
    with pytest.raises(ValidationFailed):
        backup_service.validate_backup(bad)


def test_restore_roundtrip_keeps_old_as_backup(tmp_path):
    source = _make_data_dir(tmp_path, setting_key="from_backup", setting_value="旧数据")
    archive = Path(backup_service.create_backup(source)["path"])

    target = _make_data_dir(tmp_path, setting_key="newer", setting_value="新数据")
    report = backup_service.restore_backup(archive, target)

    assert _setting(target, "from_backup") == "旧数据"     # 已还原到备份时点
    assert _setting(target, "newer") is None               # 新写数据被整体替换
    assert Path(report["previous_db_backup"]).exists()     # 旧库留档可回退


def test_restore_rejects_invalid_archive_without_touching_target(tmp_path):
    target = _make_data_dir(tmp_path, setting_key="keep_me", setting_value="安全")
    bogus = tmp_path / "bogus.zip"
    bogus.write_bytes(b"garbage")
    with pytest.raises(ValidationFailed):
        backup_service.restore_backup(bogus, target)
    assert _setting(target, "keep_me") == "安全"            # 校验失败不触碰现有数据
