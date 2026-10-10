# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 规格骨架（完整化见 tasks.md T138）
# 用法（仓库根目录）：
#   cd frontend && pnpm build
#   pyinstaller packaging/saler.spec
# 产出：dist/SalerTool/（--onedir；约定不用 onefile）

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "aiosqlite",
]
hiddenimports += collect_submodules("uvicorn")

a = Analysis(
    ["../backend/src/saler/desktop/__main__.py"],
    pathex=["../backend/src"],
    binaries=[],
    datas=[
        # 前端构建产物（先执行 pnpm build）
        ("../frontend/dist", "frontend/dist"),
        # 迁移脚本随包分发
        ("../backend/alembic", "alembic"),
        ("../backend/alembic.ini", "."),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
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
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SalerTool",
)
