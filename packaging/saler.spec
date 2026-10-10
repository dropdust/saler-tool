# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 规格（T138）：--onedir 三平台冻结包
#
# 用法（仓库根目录）：
#   cd frontend && pnpm build            # ① 前端产物
#   cd ../backend && uv run pyinstaller ../packaging/saler.spec   # ② 冻结
# 产出：backend/dist/SalerTool/（onedir；不用 onefile：冷启动与更新友好）
#
# 平台要点：
# - Linux：系统需安装 WebKitGTK（python3-gi + gir1.2-webkit2-4.1）；gi 不进包，运行期取系统绑定
# - Windows：WebView2 系统自带（Win10/11）；macOS：WKWebView 系统自带
# - 签名/公证见 packaging/installers/（T140/T141）

import sys

from PyInstaller.utils.hooks import collect_submodules

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

if sys.platform.startswith("linux"):
    # gi（WebKitGTK 绑定）留在系统提供：把已安装的冻结依赖排除在包外，避免与发行版冲突
    hiddenimports += ["gi", "gi.repository"]
elif sys.platform == "darwin":
    hiddenimports += ["webview.platforms.cocoa"]
elif sys.platform in ("win32", "cygwin"):
    hiddenimports += ["webview.platforms.winforms", "webview.platforms.edgechromium"]

a = Analysis(
    ["../backend/src/saler/desktop/__main__.py"],
    pathex=["../backend/src"],
    binaries=[],
    datas=[
        # 前端构建产物（先执行 pnpm build）
        ("../frontend/dist", "frontend/dist"),
        # 迁移脚本随包分发（桌面包启动时对数据目录执行 alembic）
        ("../backend/alembic", "alembic"),
        ("../backend/alembic.ini", "."),
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
    console=False,      # 桌面 GUI；诊断走日志文件
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
