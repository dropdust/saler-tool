"""T082 单元测试：数据目录迁移（复制→核对→原子指针切换，FR-033）。"""

from __future__ import annotations

import sqlite3

import pytest

from saler.core.errors import ValidationFailed
from saler.services import datadir


@pytest.fixture()
def fake_default(tmp_path, monkeypatch):
    """把“平台默认目录”重定向到临时路径，并隔离环境变量。"""
    monkeypatch.delenv("SALER_DATA_DIR", raising=False)
    default = tmp_path / "default"
    monkeypatch.setattr(datadir, "default_data_dir", lambda: default)
    return default


def _seed_data_dir(path, *, marker: str) -> None:
    datadir.ensure_layout(path)
    (path / "exports" / "sample.txt").write_text(marker, encoding="utf-8")
    with sqlite3.connect(path / "saler.db") as con:
        con.execute("CREATE TABLE marker (value TEXT)")
        con.execute("INSERT INTO marker VALUES (?)", (marker,))


def test_move_copies_verifies_and_switches_pointer(tmp_path, fake_default):
    old = fake_default
    _seed_data_dir(old, marker="原始数据")

    new = tmp_path / "moved"
    report = datadir.move_data_dir(old, new)

    assert report["restart_required"] is True
    assert (new / "saler.db").exists()
    assert (new / "exports" / "sample.txt").read_text(encoding="utf-8") == "原始数据"
    with sqlite3.connect(new / "saler.db") as con:
        assert con.execute("SELECT value FROM marker").fetchone()[0] == "原始数据"
    # 指针生效：解析出的数据目录指向新位置
    assert datadir.resolve_data_dir() == new
    # 旧数据保留（未删除）
    assert (old / "saler.db").exists()


def test_move_twice_updates_pointer(tmp_path, fake_default):
    old = fake_default
    _seed_data_dir(old, marker="A")
    second = tmp_path / "second"
    datadir.move_data_dir(old, second)
    assert datadir.resolve_data_dir() == second

    third = tmp_path / "third"
    datadir.move_data_dir(second, third)
    assert datadir.resolve_data_dir() == third
    assert (third / "saler.db").exists()


def test_move_back_to_default_clears_pointer(tmp_path, fake_default):
    # 默认目录 → 新位置 → 迁回另一个“默认”场景：迁回默认等价目录时清除指针
    relocated = tmp_path / "relocated"
    _seed_data_dir(relocated, marker="B")
    back = fake_default
    datadir.move_data_dir(relocated, back)
    assert not (fake_default / "relocation.json").exists()
    assert datadir.resolve_data_dir() == fake_default


def test_move_rejects_nonempty_target(tmp_path, fake_default):
    _seed_data_dir(fake_default, marker="C")
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "junk.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValidationFailed):
        datadir.move_data_dir(fake_default, target)


def test_move_rejects_source_without_db(tmp_path, fake_default):
    empty_source = tmp_path / "no-db"
    empty_source.mkdir()
    with pytest.raises(ValidationFailed):
        datadir.move_data_dir(empty_source, tmp_path / "target")
