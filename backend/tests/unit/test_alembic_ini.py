"""T266 回归：alembic.ini 必须为纯 ASCII。

Alembic 的 Config 经 configparser 以"系统区域编码"读取 ini（无 encoding 参数可配）；
Windows（cp1252）遇到 UTF-8 多字节序列中的 0x8d 等未定义字节会直接
UnicodeDecodeError——恢复备份与桌面端首启迁移都会崩（2026-10-14 Windows CI 实证：
byte 0x8d at position 12，正是"据"（E6 8D AE）的第二个字节）。
"""

from __future__ import annotations

from pathlib import Path

INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def test_alembic_ini_is_pure_ascii():
    data = INI.read_bytes()
    offenders = [i for i, byte in enumerate(data) if byte > 127]
    assert not offenders, (
        f"alembic.ini 含非 ASCII 字节（偏移 {offenders[:5]}）——"
        "Windows 以 cp1252 读取会 UnicodeDecodeError，请改用英文注释"
    )
