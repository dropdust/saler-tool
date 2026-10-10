#!/usr/bin/env bash
# 冻结包冒烟（T142 的 Linux 部分）：以隔离数据目录启动冻结产物的 --server 模式，
# 验证 ① 首启建库与迁移 ② /health ③ SPA 首页 ④ 数据目录结构 ⑤ 优雅退出。
# 用法：packaging/smoke.sh [dist/SalerTool/SalerTool]
set -euo pipefail

BIN="${1:-backend/dist/SalerTool/SalerTool}"
PORT="${PORT:-8877}"
WORK="$(mktemp -d /tmp/saler-smoke.XXXXXX)"
DATA_DIR="$WORK/data"
LOG="$WORK/app.log"

[ -x "$BIN" ] || { echo "缺少冻结产物：$BIN"; exit 1; }

cleanup() {
  [ -n "${PID:-}" ] && kill "$PID" 2>/dev/null || true
  wait "$PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "== ① 启动冻结包（数据目录：$DATA_DIR）=="
SALER_DATA_DIR="$DATA_DIR" "$BIN" --server --port "$PORT" > "$LOG" 2>&1 &
PID=$!

for _ in $(seq 1 100); do
  if curl -sf "http://127.0.0.1:$PORT/api/v1/health" > /dev/null 2>&1; then break; fi
  kill -0 "$PID" 2>/dev/null || { echo "进程提前退出："; cat "$LOG"; exit 2; }
  sleep 0.2
done

echo "== ② 健康检查 =="
HEALTH="$(curl -sf "http://127.0.0.1:$PORT/api/v1/health")"
echo "$HEALTH" | grep -q '"ok":true' || { echo "health 异常：$HEALTH"; exit 3; }

echo "== ③ SPA 首页 =="
INDEX="$(curl -sf "http://127.0.0.1:$PORT/")"
echo "$INDEX" | grep -qi "<div id=\"app\"" || echo "$INDEX" | grep -qi "<html" \
  || { echo "未返回 SPA 页面"; exit 4; }

echo "== ④ 数据目录结构（首启已建库/迁移/写地址）=="
for f in saler.db server_url.txt logs/saler.log; do
  [ -e "$DATA_DIR/$f" ] || { echo "缺少 $DATA_DIR/$f"; ls -R "$DATA_DIR"; exit 5; }
done
sqlite3 "$DATA_DIR/saler.db" "select count(*) from alembic_version" >/dev/null 2>&1 \
  || python3 -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); assert c.execute('select count(*) from alembic_version').fetchone()[0]==1" "$DATA_DIR/saler.db"

echo "== ⑤ 日志无异常关键字 =="
grep -E "Traceback|ERROR" "$LOG" && { echo "日志存在异常"; exit 6; } || true

echo "== ✅ 冒烟通过（health: $HEALTH）=="
