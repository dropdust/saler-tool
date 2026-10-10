# 安装器与发布产物

约定：PyInstaller `--onedir` 产物（`dist/SalerTool/`）作为各平台安装器的输入。
脚本与详细流程见 tasks.md T139–T141（Polish 阶段）。

| 平台 | 安装器 | 说明 |
|---|---|---|
| Windows | Inno Setup（`windows/inno.iss`）或 NSIS | 签名采用 Azure Trusted Signing（约 $10/月），或接受 SmartScreen 预热 |
| macOS | .app → 签名 + 公证 → DMG | Developer ID（$99/年）必需；inside-out 签名、G2 中间证书、`status: Accepted` 解析、DMG 拖拽安装 |
| Linux | AppImage 或 .deb | 最低验证基线 Ubuntu 22.04（WebKitGTK ≥ 2.36 / 4.1，libsoup3） |

发布前检查单（每平台）：
1. `pnpm build` 前端产物已更新；
2. `pyinstaller packaging/saler.spec` 冻结包通过"冒烟"：运行 quickstart S1 / S6 / S10；
3. 版本号同步（`pyproject.toml` / `package.json`）；
4. 附件记录：构建日志、冒烟记录（写入 quickstart 勾注）。
