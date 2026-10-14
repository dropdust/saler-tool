# 打包与安装器（前后端一体）

冻结产物 = Python 后端 + 本地 API + 前端 SPA（`frontend/dist` 随包）+ 桌面壳，
用户侧安装后**点开即用**，无需任何开发环境。

约定：PyInstaller `--onedir` 产物（`backend/dist/SalerTool/`）作为各平台安装器的输入。

| 平台 | 安装器 | 说明 |
|---|---|---|
| Windows | Inno Setup（`windows/inno.iss`） | 签名采用 Azure Trusted Signing（`windows/sign.md`） |
| macOS | .app → 签名 + 公证 → DMG | 见 `macos/dmg-notes.md`；脚本 `macos/notarize.sh`；签名就绪前发布未签名 zip |
| Linux | 本机安装脚本（`linux/install-local.sh`）或 AppImage（`linux/appimage.yml`） | CI 产物构建于 Ubuntu 24.04（运行基线 24.04+）；需 `python3-gi` + `gir1.2-webkit2-4.1` |

## 发布流程（GitHub Release）

推 `v*` 标签即触发 `.github/workflows/build.yml`：三平台构建 → 打包安装器
（Windows Inno Setup / macOS zip / Linux AppImage）→ 自动创建 GitHub Release，
附各安装器与 `SHA256SUMS`。发布说明模板：`packaging/release-notes.md`（`{VERSION}` 占位，按标签替换）。

AppImage 由 CI 在 ubuntu-24.04 构建（glibc 2.39），运行基线 Ubuntu 24.04+；
如需兼容更老的发行版，请在目标基线的容器/本机执行 `linux/appimage.yml` 后手动附加到 Release。

## Linux 构建（已验证流程）

系统需先装运行库与构建依赖：`sudo apt install python3-gi gir1.2-webkit2-4.1 python3-venv`

**一键构建（推荐）**——等价于下方 ①–④（含前置检查与冒烟；`--install` 连带 ⑤）：

```bash
bash packaging/build-local.sh            # ①前端 → ②冻结 venv → ③PyInstaller → ④冒烟
bash packaging/build-local.sh --install  # 构建 + 冒烟 + 安装到应用菜单
# 其他开关：--skip-frontend（复用 frontend/dist）｜--no-smoke（发布前必须补跑）｜-h
```

**等价手动步骤**（CI 与本脚本共用同一流程）：

```bash
# ① 前端产物
cd frontend && pnpm install && pnpm build

# ② 冻结 venv：必须用「能看到系统 gi 的 Python」——venv 开 system-site-packages
cd ../backend
uv venv .venv-frozen --python /usr/bin/python3 --system-site-packages
UV_PROJECT_ENVIRONMENT=.venv-frozen uv sync --extra dev

# ③ 冻结（产出 backend/dist/SalerTool/）
UV_PROJECT_ENVIRONMENT=.venv-frozen uv run --no-sync pyinstaller ../packaging/saler.spec \
    --noconfirm --distpath dist --workpath build/pyinstaller

# ④ 冒烟（隔离数据目录：首启建库迁移 → /health → SPA 首页 → 优雅退出）
bash ../packaging/smoke.sh backend/dist/SalerTool/SalerTool

# ⑤ 本机安装（应用菜单可点开；也可直接双击 dist/SalerTool/SalerTool）
bash packaging/installers/linux/install-local.sh
```

Windows / macOS 由 `.github/workflows/build.yml` 在对应 runner 上执行 ①②③（无需 system-site-packages），
再经 `windows/inno.iss` / `macos/notarize.sh` 出安装器。

## 无窗服务模式（诊断/无 GUI 环境）

```bash
SalerTool --server --port 8877     # 地址写入 <数据目录>/server_url.txt
```

## 发布前检查单（每平台）

1. `pnpm build` 前端产物已更新；
2. 冻结包通过冒烟（`packaging/smoke.sh`；三平台另需 quickstart S1 / S6 / S10 实机走查）；
3. 版本号同步（`pyproject.toml` / `package.json`）；
4. 附件记录：构建日志、冒烟记录（写入 quickstart 勾注）。

## 体积说明

当前 Linux 冻结包约 350 MB（含 Python 运行时与全部依赖）。如需瘦身：在 spec 的
`excludes` 中按需裁掉可选依赖（如 PIL），并用 `--strip` 剥离符号；对最终用户体验无影响。
