"""桌面壳启动诊断（T134）：Linux WebKitGTK 缺失等环境问题给出可操作提示。"""

from __future__ import annotations

import importlib.util
import platform
from dataclasses import dataclass

LINUX_HINT = (
    "安装 WebView 运行库后重试：Ubuntu/Debian 执行 "
    "`sudo apt install python3-gi gir1.2-webkit2-4.1`（或 4.0）；"
    "确认发行版 ≥ Ubuntu 22.04；无 GUI 环境请使用命令行版。"
)


@dataclass
class Diagnosis:
    ok: bool
    detail: str
    hint: str = ""


def check_desktop_environment() -> Diagnosis:
    """检查 pywebview 与（Linux 上）WebKitGTK 绑定是否可用。"""
    if importlib.util.find_spec("webview") is None:
        return Diagnosis(False, "缺少 pywebview 依赖", "重新安装应用或执行 `uv sync` 安装依赖。")
    if platform.system() != "Linux":
        return Diagnosis(True, f"桌面环境自检通过（{platform.system()}）")
    for version in ("4.1", "4.0"):
        try:
            import gi  # noqa: PLC0415

            gi.require_version("WebKit2", version)
            from gi.repository import WebKit2  # noqa: F401, PLC0415

            return Diagnosis(True, f"WebKitGTK {version} 可用")
        except Exception:  # noqa: BLE001 —— 继续尝试下一版本
            continue
    return Diagnosis(False, "未找到 WebKitGTK（gir1.2-webkit2-4.1/4.0）", LINUX_HINT)


def friendly_startup_error(exc: Exception) -> str:
    """把启动期异常翻译为用户可操作的信息（GLib/WebView 缺失场景）。"""
    text = f"{type(exc).__name__}: {exc}"
    lowered = text.lower()
    if "web view" in lowered or "webkit" in lowered or "glib" in lowered:
        return f"桌面窗口加载失败：{text}\n\n{LINUX_HINT}"
    return f"桌面窗口启动失败：{text}"
