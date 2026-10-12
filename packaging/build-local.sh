#!/usr/bin/env bash
# 本机构建（Linux，已验证流程 T174 固化）：一键 ①前端产物 → ②冻结 venv → ③PyInstaller 冻结 → ④冒烟。
# 产物：backend/dist/SalerTool/；步骤⑤本机安装用 --install 或另跑 packaging/installers/linux/install-local.sh。
#
# 用法：
#   bash packaging/build-local.sh                  # 完整构建 + 冒烟
#   bash packaging/build-local.sh --skip-frontend  # 复用现有 frontend/dist（纯后端改动省时）
#   bash packaging/build-local.sh --no-smoke       # 跳过冒烟（发布前必须补跑，不推荐）
#   bash packaging/build-local.sh --install        # 构建后继续执行本机安装（步骤⑤）
#   bash packaging/build-local.sh -h               # 查看用法
#
# 前置（Ubuntu 22.04+）：sudo apt install python3-gi gir1.2-webkit2-4.1 python3-venv
# 需 pnpm、uv 在 PATH；冻结 venv 必须用「能看到系统 gi 的 Python」（默认 /usr/bin/python3，
# 可用环境变量 SALER_FROZEN_PYTHON 覆盖）。流程说明见 packaging/installers/README.md。
set -euo pipefail

usage() {
  sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
}

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${SALER_FROZEN_PYTHON:-/usr/bin/python3}"
DO_FRONTEND=1
DO_SMOKE=1
DO_INSTALL=0

for arg in "$@"; do
  case "$arg" in
    --skip-frontend) DO_FRONTEND=0 ;;
    --no-smoke) DO_SMOKE=0 ;;
    --install) DO_INSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数：$arg（-h 查看用法）" >&2; exit 2 ;;
  esac
done

echo "== 前置检查 =="
command -v pnpm >/dev/null || { echo "缺少 pnpm（前端构建需要）"; exit 1; }
command -v uv >/dev/null || { echo "缺少 uv（后端依赖管理，https://docs.astral.sh/uv/）"; exit 1; }
[ -x "$PYTHON_BIN" ] || { echo "缺少冻结用 Python：$PYTHON_BIN（可用 SALER_FROZEN_PYTHON 覆盖）"; exit 1; }
"$PYTHON_BIN" -c 'import gi' 2>/dev/null \
  || { echo "$PYTHON_BIN 看不到系统 gi —— 先执行：sudo apt install python3-gi gir1.2-webkit2-4.1 python3-venv"; exit 1; }

if [ "$DO_FRONTEND" = 1 ]; then
  echo "== ① 前端产物（frontend/dist）=="
  (cd "$ROOT/frontend" && pnpm install && pnpm build)
else
  echo "== ① 前端产物（跳过：复用现有 frontend/dist）=="
  [ -f "$ROOT/frontend/dist/index.html" ] || { echo "--skip-frontend 但 frontend/dist 不存在，先完整构建一次"; exit 1; }
fi

echo "== ② 冻结 venv（backend/.venv-frozen，system-site-packages）=="
cd "$ROOT/backend"
if [ ! -x .venv-frozen/bin/python ]; then
  uv venv .venv-frozen --python "$PYTHON_BIN" --system-site-packages
fi
UV_PROJECT_ENVIRONMENT=.venv-frozen uv sync --extra dev

echo "== ③ 冻结（packaging/saler.spec → backend/dist/SalerTool/）=="
UV_PROJECT_ENVIRONMENT=.venv-frozen uv run --no-sync pyinstaller "$ROOT/packaging/saler.spec" \
  --noconfirm --distpath dist --workpath build/pyinstaller

if [ "$DO_SMOKE" = 1 ]; then
  echo "== ④ 冒烟（隔离数据目录）=="
  bash "$ROOT/packaging/smoke.sh" "$ROOT/backend/dist/SalerTool/SalerTool"
else
  echo "== ④ 冒烟（跳过：--no-smoke；发布前必须补跑）=="
fi

if [ "$DO_INSTALL" = 1 ]; then
  echo "== ⑤ 本机安装（应用菜单）=="
  bash "$ROOT/packaging/installers/linux/install-local.sh"
fi

echo "== ✅ 构建完成：$ROOT/backend/dist/SalerTool/ =="
echo "   安装到应用菜单：bash packaging/installers/linux/install-local.sh"
