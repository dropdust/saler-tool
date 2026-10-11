"""T176 单元测试：桌面壳窗口图标解析（chanzi.png）。

- 开发态：解析到仓库 packaging/icon.png 且存在；
- 冻结态：从 sys._MEIPASS/packaging/icon.png 解析；
- 缺失时返回 None（不得阻断启动）。
"""

from __future__ import annotations

import sys
from pathlib import Path


def test_icon_path_dev_mode_points_to_existing_file():
    from saler.desktop.app import _icon_path

    path = _icon_path()
    assert path is not None, "开发态应能解析到仓库内图标"
    assert Path(path).is_file()
    assert Path(path).name == "icon.png"


def test_icon_path_frozen_mode_uses_meipass(tmp_path, monkeypatch):
    from saler.desktop import app as desktop_app

    fake_root = tmp_path / "_MEIPASS"
    (fake_root / "packaging").mkdir(parents=True)
    icon = fake_root / "packaging" / "icon.png"
    icon.write_bytes(b"\x89PNG fake")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_root), raising=False)

    assert desktop_app._icon_path() == str(icon)


def test_icon_path_missing_returns_none(tmp_path, monkeypatch):
    from saler.desktop import app as desktop_app

    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(empty_root), raising=False)

    assert desktop_app._icon_path() is None
