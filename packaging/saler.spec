# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 规格（T138）：--onedir 冻结包（前后端一体：随包前端产物 + 本地 API + 桌面壳）
#
# 构建（Linux 参考流程，见下方注释的 venv 说明）：
#   cd frontend && pnpm build                                  # ① 前端产物
#   cd backend
#   uv venv .venv-frozen --python /usr/bin/python3 --system-site-packages   # ② 系统 Python（可 import gi）+ 系统站点
#   UV_PROJECT_ENVIRONMENT=.venv-frozen uv sync --extra dev
#   UV_PROJECT_ENVIRONMENT=.venv-frozen uv run pyinstaller ../packaging/saler.spec \
#       --noconfirm --distpath dist --workpath build/pyinstaller
# 产出：backend/dist/SalerTool/SalerTool（Linux）/ SalerTool.exe（Windows）
#
# 平台要点：
# - Linux：gi 由构建机系统提供（python3-gi/gir1.2-webkit2-4.1），Typlib 运行期由系统解析
# - Windows：WebView2 系统自带；macOS：WKWebView 系统自带
# - 签名/公证见 packaging/installers/（T140/T141）

import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))  # 仓库根目录
BACKEND = os.path.join(ROOT, "backend")

hiddenimports = [
    # uvicorn 动态导入
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    # 应用运行期
    "aiosqlite",
    "sse_starlette",
    "sse_starlette.sse",
    "openpyxl",
    "sqlalchemy.dialects.sqlite",
    "keyring.backends.SecretService",
    "keyring.backends.macOS",
    "keyring.backends.Windows",
    "jsonschema",
]
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("saler")

import sys  # noqa: E402

if sys.platform.startswith("linux"):
    # gi（WebKitGTK 绑定）：随包收集 gi.so；typelib 由系统 /usr/lib/*/girepository-1.0 解析
    hiddenimports += ["gi", "webview.platforms.gtk"]
elif sys.platform == "darwin":
    hiddenimports += ["webview.platforms.cocoa"]
elif sys.platform in ("win32", "cygwin"):
    hiddenimports += ["webview.platforms.winforms", "webview.platforms.edgechromium"]

a = Analysis(
    [os.path.join(BACKEND, "src", "saler", "desktop", "__main__.py")],
    pathex=[os.path.join(BACKEND, "src")],
    binaries=[],
    datas=[
        # 前端构建产物（先执行 pnpm build）
        (os.path.join(ROOT, "frontend", "dist"), "frontend/dist"),
        # 迁移脚本随包分发（冻结启动时对数据目录执行 alembic upgrade）
        (os.path.join(BACKEND, "alembic"), "alembic"),
        (os.path.join(BACKEND, "alembic.ini"), "."),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SalerTool",
    debug=False,
    strip=False,
    upx=False,          # UPX 在 macOS/部分杀软下误报；体积换安稳
    console=False,      # 桌面 GUI；诊断走日志文件（--server 模式可用日志/数据目录 server_url.txt 取地址）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SalerTool",
)
