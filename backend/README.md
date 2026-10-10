# Saler 后端 / 桌面壳

Python ≥ 3.12 + uv。命令均在 `backend/` 目录下执行。

## 安装与测试

```bash
uv sync --extra dev          # 安装依赖（含开发依赖）
uv run pytest -q             # 运行全部测试
uv run ruff check src tests  # 静态检查
```

## 本地开发运行

```bash
# 仅后端（前端用 pnpm dev 单独跑，浏览器访问 Vite 开发地址）
# 开发入口会初始化数据目录/密钥并运行迁移；令牌默认 dev-token
uv run uvicorn saler.api.dev:app --reload --port 8620

# 桌面壳（pywebview 原生窗口；开发期可加载 Vite dev server）
uv run python -m saler.desktop
```

## 结构

- `src/saler/api/` — 本地 HTTP API（仅在 127.0.0.1 提供，X-App-Token 鉴权；契约见 `specs/001-sales-tool/contracts/local-api.md`）
- `src/saler/core/` — 领域逻辑（不依赖 FastAPI/桌面壳）
- `src/saler/providers/` — LLM / 检索 / 邮件 / 短信适配器（契约见 `contracts/provider-adapters.md`）
- `src/saler/jobs/` — 异步任务引擎（SSE 进度事件）
- `src/saler/db/` — SQLAlchemy 模型与迁移
- `src/saler/security/` — 密钥库、加密列、脱敏
- `src/saler/services/` — 设置、数据目录、备份、导入导出
- `src/saler/desktop/` — pywebview 入口与服务器生命周期

## 约定

- 测试先行（宪法第 I 条）：新增功能先写失败测试。
- 密钥零入库（宪法第 V 条）：所有凭证经 `security/` 加密存储，日志/导出走脱敏。
