# Implementation Plan: 通用销售获客工具（本地桌面版）

**Branch**: `001-sales-tool` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-sales-tool/spec.md`

## Summary

把电力金具行业获客工具链通用化为**跨行业、跨平台（Windows/macOS/Linux）的本地优先销售工作台**，核心链路：种子知识库（大模型知识图谱扩充 + 中文种子翻译）→ 客户线索挖掘与联系方式提取（邮箱/电话/WhatsApp/Facebook）→ 营销内容（中文母版 AI 辅助编写 + 主题级多语言生成、人工审校）→ 自有通道（邮件 P0、短信）→ 营销计划批量触达与发送台账。数据资产保留在用户本机，未来企业 Web 版复用同一 API 面。

技术路线（决策依据见 [research.md](research.md)）：**pywebview 桌面壳 + 内嵌 FastAPI（仅回环 + SSE）+ Vue 3/TypeScript/Element Plus/ECharts 前端 + SQLite(SQLAlchemy/Alembic)**；大模型走**自建薄适配层**（首批 DeepSeek / Qwen-DashScope / Moonshot-Kimi / 通用 OpenAI 兼容）；检索渠道走**可插拔 Provider**（首批 Brave / Serper / Tavily，优先级故障转移）；PyInstaller `--onedir` 三平台打包。

## Technical Context

**Language/Version**: Python ≥ 3.12（建议 3.13）；TypeScript 5.x（Node ≥ 20）

**Primary Dependencies**:
- 后端：FastAPI + uvicorn（本地 API）、pywebview（桌面壳）、SQLAlchemy 2.0 + Alembic、httpx + selectolax（抓取）、sse-starlette（进度流）、openai SDK（LLM 传输层；anthropic 适配器为增量项）、cryptography + keyring（凭证加密）、loguru（日志）、PyInstaller（打包）
- 前端：Vue 3、Vite、Pinia、Vue Router、Element Plus、ECharts（图谱可视化）、vue-i18n（默认 zh-CN）
- 测试：pytest（+ pytest-asyncio、respx）、vitest、四类假 Provider（离线契约测试）

**Storage**: SQLite（WAL 模式），位于用户数据目录内，随目录整体备份/迁移；备份为 zip 归档（格式见 [contracts/data-exchange.md](contracts/data-exchange.md)）

**Testing**: pytest（后端单元/集成/契约）、vitest（前端）；集成测试以临时数据目录跑任务全链路；发布前每平台**冻结包冒烟**（[quickstart.md](quickstart.md) S1/S6/S10）

**Target Platform**: Windows 10/11（WebView2 系统自带）、macOS 12+（WKWebView）、Ubuntu 22.04+（WebKitGTK ≥ 2.36）；三平台功能一致（FR-001/SC-006）

**Project Type**: desktop-app（本地优先；后端 API 面为可复用的 Web 服务形态，为未来企业版预留）

**Performance Goals**: 打包后冷启动 ≤ 4s（onedir）；1 万种子 / 10 万线索规模下列表/筛选保持可交互（分页 + 索引，必要时启用 FTS5）；挖掘默认并发 5、单站间隔 ≥ 1s；发送按通道限额节流（默认 20 条/分钟、每日上限可配）

**Constraints**: 离线可查看与管理数据（外部能力均用户主动触发，FR-003）；本地 API 仅绑定回环 + 每次启动随机令牌；凭证加密存储、日志与导出脱敏（FR-006）；界面中文（FR-005）；单用户 v1；UI 依赖除 Element Plus/ECharts 外不再扩张

**Scale/Scope**: 单用户；覆盖 5 大模块 + 设置/数据管理，约 10–12 个主界面；数据规模目标 1 万种子 / 10 万线索（SC-007）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**现状说明**：`.specify/memory/constitution.md` 仍是**未批准的模板占位**（无实际原则条目），无法按宪制门检查。**建议在实现前运行 `/speckit-constitution` 固化项目原则**（可参考下方"规格级门"作为初始原则素材）。

**规格级门（替代检查，全部通过）**：

| 门 | 依据 | 结论 |
|---|---|---|
| 本地优先 / 数据主权：方案不得引入强制服务端依赖 | FR-002/003/033、Assumptions | PASS（全栈本地组件，无云依赖） |
| 无强制云账号：离线可用，外部能力按需触发 | FR-003/032、SC-010 | PASS（AI/检索/发送均为用户主动+可配置凭据） |
| 凭证安全：加密存储、脱敏展示、不出现在日志/导出 | FR-006 | PASS（§5 字段级加密 + OS 钥匙串 + 脱敏序列化） |
| 跨平台一致：一套代码与产线覆盖三平台 | FR-001、SC-006 | PASS（差异集中在 WebView 基线与打包脚本） |
| 可验证性：核心流程离线可测、验收场景明确 | quickstart.md、SC-001~011 | PASS（四类假 Provider + 12 个端到端场景） |

**Phase 1 设计复核**：data-model.md / contracts/ / quickstart.md 与上述门逐条对照，无违反项。Complexity Tracking 为空。

## Project Structure

### Documentation (this feature)

```text
specs/001-sales-tool/
├── plan.md              # 本文件（/speckit-plan 输出）
├── research.md          # Phase 0 输出：技术决策与选型依据
├── data-model.md        # Phase 1 输出：数据模型与状态机
├── quickstart.md        # Phase 1 输出：运行与验证指南
├── contracts/           # Phase 1 输出：接口契约
│   ├── local-api.md         # 前端 ↔ 后端本地 API（含 Job/SSE 模式）
│   ├── provider-adapters.md # LLM / 检索 / 邮件 / 短信适配器接口
│   └── data-exchange.md     # 导入 / 导出 / 回灌 / 备份格式
└── tasks.md             # Phase 2 输出（/speckit-tasks 生成，不在本阶段）
```

### Source Code (repository root)

```text
backend/
├── pyproject.toml                     # uv 管理
├── src/saler/
│   ├── api/                           # FastAPI 路由（对齐 contracts/local-api.md）
│   │   ├── main.py / deps.py / sse.py
│   │   └── routes/                    # settings, llm, search, graph, seeds, crawl,
│   │                                  # companies, content, channels, campaigns, jobs
│   ├── core/                          # 领域逻辑（与桌面壳解耦，Web 版复用）
│   │   ├── graph/                     # 图谱节点/词表/关系
│   │   ├── seeds/                     # 种子生命周期、产量归因、校验
│   │   ├── leads/                     # 挖掘调度、抽取管线、去重、画像
│   │   ├── content/                   # 主题/语言版本/版本管理、渲染
│   │   ├── campaigns/                 # 计划/轮次/人群物化/预估
│   │   ├── sending/                   # 发送编排、配额节奏、台账
│   │   └── compliance/                # suppression / exclusion / 礼貌抓取策略
│   ├── providers/                     # 适配器（对齐 provider-adapters.md）
│   │   ├── llm/                       # base, openai_compatible, anthropic_adapter, registry, schemas
│   │   ├── search/                    # base, brave, serper, tavily, ddg_fallback, registry
│   │   ├── mail/                      # base, smtp
│   │   └── sms/                       # base, http_generic
│   ├── jobs/                          # 任务引擎：队列 / worker / 进度事件 / 暂停恢复
│   ├── db/                            # SQLAlchemy models、Alembic 迁移、repositories
│   ├── security/                      # 密钥库（keyring + 口令回退）、启动令牌、加密字段
│   ├── services/                      # 备份恢复、导入导出、数据目录、报表
│   └── desktop/                       # pywebview 入口、uvicorn 生命周期、端口协商
└── tests/                             # unit / integration / contract / fixtures（假 Provider）

frontend/
├── package.json / vite.config.ts / index.html
├── src/
│   ├── main.ts / App.vue / router/ / stores/ / api/ / i18n/
│   ├── views/                         # dashboard, seeds-graph, leads, content, channels, campaigns, settings
│   └── components/                    # common/ graph/ tables/ editor/
└── tests/                             # vitest

packaging/
├── saler.spec                         # PyInstaller（--onedir）
└── installers/                        # windows/inno.iss、windows/nsis.nsi、macos/（签名公证说明）、linux/appimage.yml

.github/workflows/                     # 三平台构建矩阵（frontend → PyInstaller → 安装器）
```

**Structure Decision**: 采用"**桌面壳 + 本地 Web 后端 + SPA 前端**"的三段式单仓布局。`backend/src/saler/api/`（接口层）与 `core/`（领域层）严格分离：API 面即未来企业 Web 版的接口面（壳可换、服务可上云，仅换 `desktop/` 与部署形态）；`frontend/` 只依赖 `contracts/local-api.md`；`packaging/` 独立承载三平台打包与签名。该布局同时满足规格"数据在用户侧 + 后续提供 Web 服务"的双阶段路线，并使 pywebview → Tauri 的潜在迁移成本为零。

## Complexity Tracking

无宪制（规格级门）违规项，无需豁免。
