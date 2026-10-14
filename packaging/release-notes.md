## 销售获客工具 {VERSION}

本地优先的 B2B 销售获客工作台：知识图谱与多语言种子 → 检索挖掘线索 → 内容生成 → 邮件/短信触达 → 退订与排除合规。数据全部保存在本机，无需服务器。

### 下载与安装

| 平台 | 文件 | 说明 |
|---|---|---|
| Windows 10/11 (x64) | `SalerTool-Setup-{VERSION}.exe` | 双击安装；卸载默认保留用户数据 |
| macOS（Apple 芯片） | `SalerTool-{VERSION}-macos-arm64.zip` | 解压后运行 `SalerTool`；未签名版本首次运行需「右键 → 打开」，或执行 `xattr -dr com.apple.quarantine SalerTool` |
| Linux (x86_64) | `SalerTool-{VERSION}-x86_64.AppImage` | `chmod +x` 后直接运行；需系统 WebKitGTK（Ubuntu 24.04+：`sudo apt install python3-gi gir1.2-webkit2-4.1`） |

完整性校验：同页 `SHA256SUMS`。

首次启动自动建库（数据目录：Windows `%LOCALAPPDATA%\saler-tool`；macOS `~/Library/Application Support/saler-tool`；Linux `~/.local/share/saler-tool`）。

> 说明：macOS 签名/公证与 Windows 代码签名将在证书就绪后启用（见 `packaging/installers/`）。
