# Saler Tool · 销售获客工具（本地桌面版）

把"行业专用的获客工具链"通用化为面向任意行业的**销售工作台**：
种子知识库 → 客户线索挖掘 → 联系方式提取 → 营销内容 → 自有通道 → 批量触达。
全链路跑在用户本机，**数据资产留在用户侧**。

- **本地优先**：pywebview 桌面壳 + 回环 FastAPI + SQLite；离线可查看与管理全部数据；外部调用（大模型 / 检索 / 抓取 / 发送）一律由用户主动触发且对其可见。
- **密钥零入库**：所有凭证加密存储（OS 钥匙串 + 字段级加密），界面、日志、导出全程脱敏。
- **无 AI 亦可用**：未配置大模型时，手工建模、规则抓取、发送全链路完整可用；AI 入口明确提示"需配置模型"。
- **三平台一致**：Windows 10/11、macOS 12+、Ubuntu 22.04+（WebKitGTK ≥ 2.36）。

## 五步闭环

| 模块 | 做什么 |
|---|---|
| 种子知识库 | 图谱化目标画像（产品线 / 客户角色 / 市场）+ 多语言词表；手工 / AI / 检索扩充种子，先审后用 |
| 客户线索 | 按种子检索公开网页 → 候选域名 → 抽取邮箱 / 电话 / WhatsApp / Facebook → 去重、排除规则、导出 |
| 营销内容 | 中文母版为源，AI 辅助起草与主题级多语言生成；草稿 → 待审 → 发布的版本化管理 |
| 营销通道 | 登记自有发信邮箱 / 短信网关：连通测试、限额与用量、试发（邮件为 P0 通道） |
| 营销计划 | 圈人群 × 选内容 × 选通道 → 影响预估 → 试发 → 启动；实时进度、发送台账、退订黑名单 |

## 技术栈

- **后端**：Python ≥ 3.12，FastAPI + uvicorn（仅绑定 127.0.0.1）、SQLAlchemy 2.0 + Alembic（SQLite WAL）、pywebview（桌面壳）、PyInstaller `--onedir`（打包）
- **前端**：Vue 3 + TypeScript + Vite + Pinia + Element Plus + ECharts + vue-i18n（zh-CN 优先）
- **外部能力**：LLM / 检索 / 邮件 / 短信全部走 `providers/` 适配器（Protocol + Registry，零配置发现）

## 本地开发

前置：Python ≥ 3.12 + [uv](https://docs.astral.sh/uv/)；Node ≥ 20 + pnpm。

```bash
# 1) 后端（本地 API + 任务引擎；开发入口自动建数据目录、初始化密钥并跑迁移）
cd backend
uv sync --extra dev
uv run uvicorn saler.api.dev:app --reload --port 8620

# 2) 前端（Vite dev server，/api 代理到 127.0.0.1:8620）
cd frontend
pnpm install
pnpm dev            # http://localhost:5173

# 3) 桌面壳（原生窗口；需先 pnpm build，或设置 SALER_DEV_URL 指向 Vite）
cd backend
uv run python -m saler.desktop
```

Ubuntu 桌面壳运行库：`sudo apt install python3-gi gir1.2-webkit2-4.1`。

### 开发用环境变量

| 变量 | 用途 |
|---|---|
| `SALER_DATA_DIR` | 覆盖数据目录（默认平台惯例目录，如 Linux `~/.local/share/saler-tool`） |
| `SALER_TOKEN` | 开发模式本地 API 令牌（默认 `dev-token`） |
| `SALER_DEV_URL` | 桌面壳改为加载 Vite 开发服务器（如 `http://localhost:5173`） |
| `SALER_MASTER_PASSPHRASE` | 无钥匙串环境 / 自动化下的主口令（Argon2id 派生加密密钥） |
| `SALER_DB_URL` | Alembic 单独执行迁移时的数据库 URL（应用运行时数据库恒为数据目录内 SQLite） |

本地 API 契约（路由、Job/SSE 模式、鉴权）见 [specs/001-sales-tool/contracts/local-api.md](specs/001-sales-tool/contracts/local-api.md)。

## 测试与静态检查

```bash
cd backend  && uv run pytest -q && uv run ruff check src tests   # 当前基线：320 passed
cd frontend && pnpm test && pnpm lint                            # 当前基线：57 passed
```

测试分层：领域逻辑单元测试、假 Provider 契约测试（四类假适配器，全离线）、临时数据目录集成测试；前端 vitest。
新增功能遵循"红 → 绿 → 重构"（宪法第 I 条），禁止为过 CI 弱化测试。

## 构建与打包

```bash
bash packaging/build-local.sh            # Linux 一键：①前端产物 → ②冻结 venv → ③PyInstaller → ④冒烟
bash packaging/build-local.sh --install  # 构建 + 冒烟 + 安装到应用菜单
```

- 冻结产物：`backend/dist/SalerTool/`（后端 + 本地 API + 内嵌前端 SPA + 桌面壳，用户点开即用）。
- 三平台安装器（Inno Setup / DMG / AppImage）见 [packaging/installers/README.md](packaging/installers/README.md)；Windows/macOS 由 [.github/workflows/build.yml](.github/workflows/build.yml) 在对应 runner 构建。
- 无窗服务模式（诊断 / 无 GUI 环境）：`SalerTool --server --port 8877`，访问地址写入数据目录 `server_url.txt`。

## 仓库结构

```text
backend/    Python 包 saler：
              api/       回环 HTTP 路由（对齐 contracts/local-api.md）
              core/      领域逻辑（不依赖 FastAPI / 桌面壳）
              providers/ LLM / 检索 / 邮件 / 短信适配器
              jobs/      异步任务引擎（SSE 进度事件）
              db/        模型与 Alembic 迁移
              security/  加密列、钥匙串、脱敏
              services/  数据目录、备份、导入导出
              desktop/   pywebview 入口与服务器生命周期
frontend/   Vue 3 SPA：views（五模块界面 + 设置）/ api（契约客户端）/ stores / components
packaging/  PyInstaller spec、Linux 一键构建脚本、三平台安装器
specs/      规格驱动工件（spec / plan / 契约 / quickstart 验收场景）
docs/       面向使用者的用户手册
```

## 文档索引

| 想了解 | 读 |
|---|---|
| 产品范围、用户故事与验收场景 | [specs/001-sales-tool/spec.md](specs/001-sales-tool/spec.md) |
| 技术选型与决策依据 | [specs/001-sales-tool/plan.md](specs/001-sales-tool/plan.md)、[research.md](specs/001-sales-tool/research.md) |
| 数据模型与状态机 | [specs/001-sales-tool/data-model.md](specs/001-sales-tool/data-model.md) |
| 接口契约（本地 API / 适配器 / 数据交换） | [specs/001-sales-tool/contracts/](specs/001-sales-tool/contracts/) |
| 运行与逐场景验收（S1–S12） | [specs/001-sales-tool/quickstart.md](specs/001-sales-tool/quickstart.md) |
| 面向使用者的操作手册 | [docs/user-guide.md](docs/user-guide.md) |
| 开发宪法与质量门 | [.specify/memory/constitution.md](.specify/memory/constitution.md) |
| 当前进度（唯一事实源） | [specs/001-sales-tool/tasks.md](specs/001-sales-tool/tasks.md) 及 `specs/00x-*/tasks.md` 勾选状态 |

## 开发约定（摘自宪法，完整条款见上表）

- **规格驱动**：新功能走 Spec Kit 流程（`/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`，技能在 `.claude/skills/`）；`tasks.md` 勾选状态是进度的唯一事实。
- **逐任务提交**：每完成一个任务立即提交一次，提交信息含任务 ID 并说明"为什么"。
- **契约同步**：接口与行为变更必须同步更新 `contracts/`；工件冲突以 `spec.md` 为准。
- **密钥零入库**：任何密钥不得出现在源码、示例、测试夹具、日志、导出物与提交历史中；测试一律使用假 Provider 与占位值。
