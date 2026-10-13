"""T197 单元测试：冻结包 GTK/Pango 定位变量修正（中文输入修复）。

背景：PyInstaller 的 pyi_rth_gtk 钩子把 GTK_EXE_PREFIX/GTK_DATA_PREFIX/GTK_PATH/
PANGO_LIBDIR/PANGO_SYSCONFDIR 指向包内 sys._MEIPASS（_internal/）。Ubuntu 的 GTK3
依据 GTK_EXE_PREFIX 推导模块目录（<prefix>/lib/gtk-3.0/3.0.0/immodules），而冻结包
并不携带 GTK 模块——输入法模块（im-wayland.so）只在系统目录，导致 GTK 找不到任何
输入法模块、中文无法输入（连带 canberra 等模块加载失败）。

drop_bundle_gtk_env 只移除「取值指向包内目录」的变量；用户/环境自行设置的其它
取值一律保留（不误伤）。
"""

from __future__ import annotations

import os
import sys

import pytest

BUNDLE = "/tmp/fake-bundle/_internal"
BUNDLE_VARS = (
    "GTK_EXE_PREFIX",
    "GTK_DATA_PREFIX",
    "GTK_PATH",
    "PANGO_LIBDIR",
    "PANGO_SYSCONFDIR",
)


@pytest.fixture()
def frozen_env(monkeypatch):
    """模拟冻结进程：sys._MEIPASS 指向包内目录。"""
    monkeypatch.setattr(sys, "_MEIPASS", BUNDLE, raising=False)
    return monkeypatch


def test_removes_self_referential_vars(frozen_env):
    from saler.desktop.app import drop_bundle_gtk_env

    for var in BUNDLE_VARS:
        frozen_env.setenv(var, BUNDLE)

    removed = drop_bundle_gtk_env()

    assert set(removed) == set(BUNDLE_VARS)
    for var in BUNDLE_VARS:
        assert var not in os.environ


def test_keeps_foreign_values(frozen_env):
    """用户自定义取值（不指向包内）不受影响；指向包内的照常移除。"""
    from saler.desktop.app import drop_bundle_gtk_env

    frozen_env.setenv("GTK_PATH", "/opt/custom/gtk")
    frozen_env.setenv("GTK_EXE_PREFIX", BUNDLE)

    removed = drop_bundle_gtk_env()

    assert removed == ["GTK_EXE_PREFIX"]
    assert os.environ["GTK_PATH"] == "/opt/custom/gtk"


def test_mixed_list_removed_as_whole(frozen_env):
    """取值是路径列表（os.pathsep 分隔）时：只要任一项落在包内，整条移除。"""
    from saler.desktop.app import drop_bundle_gtk_env

    frozen_env.setenv("GTK_PATH", f"/opt/a{os.pathsep}{BUNDLE}/lib")

    removed = drop_bundle_gtk_env()

    assert removed == ["GTK_PATH"]
    assert "GTK_PATH" not in os.environ


def test_noop_without_frozen_marker(monkeypatch):
    """非冻结运行（无 _MEIPASS）：不动环境（不误删真实用户的取值）。"""
    from saler.desktop.app import drop_bundle_gtk_env

    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setenv("GTK_PATH", "/opt/keep/gtk")

    assert drop_bundle_gtk_env() == []
    assert os.environ["GTK_PATH"] == "/opt/keep/gtk"
