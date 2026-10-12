#!/usr/bin/env bash
# 本机安装（Linux，无需 root）：把冻结产物装进当前用户的桌面环境——
# 应用菜单可搜索「销售获客工具」、文件管理器可双击图标启动。
#
# 用法：
#   bash packaging/installers/linux/install-local.sh            # 默认取 backend/dist/SalerTool
#   bash packaging/installers/linux/install-local.sh <产物目录>
# 卸载：
#   rm -rf ~/.local/opt/saler-tool ~/.local/share/applications/saler-tool.desktop
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SRC="${1:-$ROOT/backend/dist/SalerTool}"
DEST="$HOME/.local/opt/saler-tool"
APPS="$HOME/.local/share/applications"

[ -d "$SRC" ] || { echo "缺少冻结产物：$SRC（先执行 pyinstaller packaging/saler.spec，见 packaging/installers/README.md）"; exit 1; }
[ -x "$SRC/SalerTool" ] || { echo "产物缺少可执行文件：$SRC/SalerTool"; exit 1; }

mkdir -p "$DEST" "$APPS"
rm -rf "$DEST/SalerTool"
cp -r "$SRC" "$DEST/SalerTool"

# 图标（如仓库提供 packaging/installers/linux/saler.png）
ICON_LINE=""
if [ -f "$ROOT/packaging/installers/linux/saler.png" ]; then
  ICONS="$HOME/.local/share/icons/hicolor/256x256/apps"
  mkdir -p "$ICONS"
  cp "$ROOT/packaging/installers/linux/saler.png" "$ICONS/saler-tool.png"
  ICON_LINE="Icon=saler-tool"
fi

cat > "$APPS/saler-tool.desktop" << EOF
[Desktop Entry]
Type=Application
Name=销售获客工具
Comment=本地销售获客工作台（数据保存在本机）
Exec=$DEST/SalerTool/SalerTool
$ICON_LINE
Terminal=false
Categories=Office;Finance;
StartupWMClass=SalerTool
EOF

command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
# 图标缓存刷新（-t：用户 hicolor 无 index.theme 也兼容；帮助各桌面环境重读新建图标）
if [ -n "$ICON_LINE" ] && command -v gtk-update-icon-cache >/dev/null; then
  gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo "✅ 已安装到应用菜单：搜索「销售获客工具」即可点开"
echo "   可执行文件：$DEST/SalerTool/SalerTool（也可直接双击）"
echo "   数据目录：~/.local/share/saler-tool（设置的「通用设置」可迁移）"
echo "   卸载：rm -rf $DEST $APPS/saler-tool.desktop"
