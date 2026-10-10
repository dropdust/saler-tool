---

description: "Task list for 通用销售获客工具（本地桌面版）"
---

# Tasks: 通用销售获客工具（本地桌面版）

**Input**: Design documents from `/specs/001-sales-tool/`

**Prerequisites**: [plan.md](plan.md)（required）, [spec.md](spec.md)（required）, [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md), `.specify/memory/constitution.md`

**Tests**: 必含——项目宪法第 I 条（测试驱动开发，不可协商）要求每个用户故事先写可失败的测试再实现；契约测试一律使用 `backend/tests/fixtures/fakes/` 的假 Provider（离线可跑）。

**Organization**: 任务按用户故事分组，每个故事可独立实现、独立测试、独立交付。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无未完成依赖）
- **[Story]**: 所属用户故事（US1–US6）
- 每个任务都包含确切文件路径

## Path Conventions

- 后端：`backend/src/saler/`、后端测试：`backend/tests/`
- 前端：`frontend/src/`、前端测试：`frontend/tests/`
- 打包与发布：`packaging/`；CI：`.github/workflows/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 仓库与项目骨架初始化

- [x] T001 初始化 git 仓库与根 `.gitignore`（排除密钥与数据：`*.db`、`secrets/`、`backups/`、`exports/`、`.env*`、`dist/`、`node_modules/`；宪法第 V 条）
- [x] T002 [P] 后端项目骨架：`backend/pyproject.toml`（uv；依赖清单见 plan.md Technical Context；dev 依赖 pytest/pytest-asyncio/respx/ruff）与 `backend/src/saler/__init__.py`
- [x] T003 [P] 前端项目骨架：`frontend/package.json`（Vue3/TS/Vite/Pinia/Vue Router/Element Plus/ECharts/vue-i18n/vitest）、`frontend/vite.config.ts`、`frontend/tsconfig.json`
- [x] T004 [P] 测试骨架：`backend/tests/conftest.py`（临时数据目录 fixture、ASGI 测试客户端、假 Provider 注入）、`frontend/tests/` vitest 配置
- [x] T005 [P] 打包与 CI 骨架：`packaging/saler.spec`（占位）、`packaging/installers/README.md`、`.github/workflows/ci.yml`（三平台矩阵：ruff + pytest + vitest）
- [x] T006 [P] 开发文档：`backend/README.md`、`frontend/README.md`（运行/测试命令，对应 quickstart.md §2）

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 所有用户故事的共同地基（API/DB/任务引擎/安全/Provider 基座/前端壳）

**⚠️ CRITICAL**: 本阶段完成前，任何用户故事不得开始

- [x] T007 数据库层：`backend/src/saler/db/base.py`（DeclarativeBase + 命名约定）、`backend/src/saler/db/session.py`（SQLite WAL、`foreign_keys=ON`、会话工厂）
- [x] T008 全量数据模型（严格按 data-model.md，含全部唯一约束/枚举/索引）：`backend/src/saler/db/models/graph.py`、`seeds.py`、`leads.py`、`content.py`、`channels_campaigns.py`、`system.py`
- [x] T009 Alembic 初始化与基线迁移（`backend/alembic.ini`、`backend/alembic/`；迁移含全部表与索引；`alembic upgrade head` 可从零建库）
- [x] T010 [P] 安全基座：`backend/src/saler/security/keyring_store.py`（OS 钥匙串主密钥 + 口令回退 Argon2id）、`backend/src/saler/security/fields.py`（Fernet 加密列类型）、`backend/src/saler/security/token.py`（每次启动随机令牌）
- [x] T011 [P] 安全基座：`backend/src/saler/security/redact.py`（脱敏序列化 + 日志过滤器；任何密钥不得进入日志/导出，FR-006）、`backend/src/saler/logging_config.py`（loguru 滚动文件日志至数据目录）
- [x] T012 安全测试（先失败后实现）：keyring 回退、加解密往返、脱敏不泄露断言 `backend/tests/unit/test_security.py`
- [x] T013 [P] 设置与数据目录：`backend/src/saler/services/settings_service.py`（app_setting KV + 默认值）、`backend/src/saler/services/datadir.py`（platformdirs 解析、可写/空间校验）
- [x] T014 [P] 操作日志：`backend/src/saler/services/operation_log.py`（写入/查询/容量滚动清理；契约见 data-model.md E4）
- [x] T015 Provider 适配器基座：`backend/src/saler/providers/errors.py`（ProviderError 错误分类，按 contracts/provider-adapters.md 表）、`backend/src/saler/providers/registry.py`（type_key/config_schema/secret_fields/factory）
- [x] T016 LLM 适配器实现：`backend/src/saler/providers/llm/base.py`（Protocol）、`openai_compatible.py`（chat/stream/list_models/test_connection；能力标记 json_schema/json_object；解析卫生 + Pydantic 校验修复循环 ≤3 次）、`schemas.py`（seed_expansion_v1 / seed_translation_v1 / content_draft_v1 / content_translation_v1）、注册 manifest
- [x] T017 任务引擎：`backend/src/saler/jobs/engine.py`（asyncio worker、任务状态持久化（queued/running/paused/completed/failed/cancelled）、协作式暂停/取消/恢复）、`backend/src/saler/jobs/events.py`（每任务事件队列）
- [x] T018 SSE 与任务 API：`backend/src/saler/api/sse.py`（sse-starlette：节流 ~0.5s、30s keepalive、哨兵关闭）、`backend/src/saler/api/routes/jobs.py`（列表/详情/events/暂停恢复取消；SSE 用 `?token=`）
- [x] T019 API 基座：`backend/src/saler/api/main.py`（app factory、X-App-Token 中间件、统一错误包 `{code,message,details}`、分页助手、`/health`）、`backend/src/saler/api/deps.py`
- [x] T020 桌面壳：`backend/src/saler/desktop/app.py`（pywebview 窗口；uvicorn 于线程绑定 `127.0.0.1:0`；开窗前轮询 `/health`；关窗停机防孤儿）、`backend/src/saler/desktop/__main__.py`
- [x] T021 基座测试（先失败后实现）：任务状态机/暂停恢复 `backend/tests/unit/test_jobs_engine.py`、SSE 事件流 `backend/tests/integration/test_sse_flow.py`
- [x] T022 假 Provider 夹具：`backend/tests/fixtures/fakes/llm_fake.py`（含"非法 JSON→修复"脚本化场景）、`search_fake.py`、`mail_fake.py`、`sms_fake.py`（离线契约测试共用）
- [x] T023 前端外壳：`frontend/src/main.ts`、`App.vue`、`router/index.ts`（7 模块路由占位）、`layouts/MainLayout.vue`（侧边导航 + 模块入口）
- [x] T024 前端 API 客户端：`frontend/src/api/client.ts`（注入 X-App-Token、统一错误提示）、`api/types.ts`、`composables/useJobEvents.ts`（SSE 订阅 hook）、`stores/app.ts`
- [x] T025 前端基线与 i18n：`frontend/src/i18n/zh-CN.ts`、通用组件（表格/表单容器/确认对话框/空态）`frontend/src/components/common/`

**Checkpoint**: 地基就绪——`uv run python -m saler.desktop` 可打开空壳应用并通过 `/health`；用户故事可并行开始

---

## Phase 3: User Story 1 - 目标画像与种子知识库 (Priority: P1) 🎯 MVP

**Goal**: 图谱+词表建模；手工/大模型知识图谱扩充/检索三来源种子；AI 中文→外文翻译；审核门；产量归因；可视化；导出与回灌

**Independent Test**: 全新行业从零完成"建模 → 手工种子 → AI 扩充+翻译 → 审核 → 可视化 → 导出 → 回灌"（quickstart S3/S4/S5；AI 用假 Provider 亦可通过契约测试）

### Tests for User Story 1 ⚠️（先写，确认失败）

- [x] T026 [P] [US1] 契约测试：图谱/种子 API（`UNIQUE(node_type,name)`、`seed.query` 唯一、审核流转、批量导入）`backend/tests/contract/test_seeds_api.py`
- [x] T027 [P] [US1] 单元测试：产量统计口径（按 `domain_seed_hit` 的 COUNT DISTINCT 归因；不跨种子求和）`backend/tests/unit/test_yield_stats.py`
- [x] T028 [P] [US1] 单元测试：AI 扩充/翻译落库（全部 `review_status=pending`、query 去重、失败重试与错误上报）`backend/tests/unit/test_seed_ai.py`
- [x] T029 [P] [US1] 集成测试：S3/S5 流程（建模→扩充→审核→翻译→导出→回灌报告）`backend/tests/integration/test_us1_seed_flow.py`

### Implementation for User Story 1

- [x] T030 [P] [US1] 图谱服务：节点/词表/关系 CRUD、合并、停用、审核操作 `backend/src/saler/core/graph/service.py`（FR-007~011）
- [x] T031 [P] [US1] 种子服务：CRUD/批量/唯一校验/状态机（pending/running/done/invalid）/审核 `backend/src/saler/core/seeds/service.py`（FR-010/015）
- [x] T032 [US1] 产量归因与统计：`backend/src/saler/core/seeds/yield_stats.py`（回灌后重算 n_candidates/n_contacts；按产品线/角色/市场/批次分组；注：模块名不用保留字 yield）
- [x] T033 [P] [US1] 域名共享服务：`backend/src/saler/core/leads/domain_service.py`（create-or-get `domain` 唯一、排除标记；供 US2 复用）
- [x] T034 [US1] 回灌服务：`backend/src/saler/services/ingest_harvest.py`（harvest_v1 JSONL/csv 解析、seed_query 匹配、domain+命中写入、报告 matched/unmatched/new_domains；contracts/data-exchange.md §2）
- [x] T035 [US1] 种子导出：`backend/src/saler/services/export_seeds.py`（txt/csv 两格式，列序与契约 §1 一致）
- [x] T036 [US1] AI 扩充服务：`backend/src/saler/core/seeds/ai.py`（行业描述/节点→prompt→`generate_structured(seed_expansion_v1)`→候选节点/边/种子 pending 落库、去重；扩充数量与语言由用户指定；FR-012）
- [x] T037 [US1] AI 翻译服务：`backend/src/saler/core/seeds/ai_translate.py`（中文种子/词表→目标语言，词表术语表参与；FR-009/012）
- [x] T038 [US1] 校验服务：`backend/src/saler/core/seeds/verifiers.py`（Wikipedia 默认校验器 + validation_record 记录/置信度；低置信度不进正式队列；FR-014）
- [x] T039 [US1] API：`backend/src/saler/api/routes/graph.py`（nodes/terms/edges/overview 含覆盖率与产量着色数据；FR-017）
- [x] T040 [US1] API：`backend/src/saler/api/routes/seeds.py`（CRUD/bulk/stats/export/ingest/review/validate；FR-015/016/018）
- [x] T041 [US1] API：`backend/src/saler/api/routes/ai.py`（`/ai/seeds/expand`、`/ai/seeds/translate`，job 化；调用前数据范围可见 FR-031）
- [x] T042 [P] [US1] 前端：种子列表 + 待审核队列 `frontend/src/views/seeds/SeedList.vue`、`ReviewQueue.vue`
- [x] T043 [P] [US1] 前端：图谱管理（节点/词表/关系编辑、合并、停用）`frontend/src/views/seeds/GraphManage.vue`
- [x] T044 [P] [US1] 前端：AI 扩充/翻译对话框（描述输入、数量与语言选择、数据发送范围提示）`frontend/src/views/seeds/AiExpandDialog.vue`
- [x] T045 [US1] 前端：知识图谱可视化（ECharts graph：结构视图/实体视图、市场批次筛选、覆盖率与产量着色）`frontend/src/views/seeds/GraphView.vue`、`frontend/src/components/graph/ForceGraph.vue`（FR-017）
- [x] T046 [US1] 前端：产量统计面板 + 导出/回灌界面 `frontend/src/views/seeds/StatsPanel.vue`、`frontend/src/views/seeds/ImportExport.vue`
- [ ] T047 [US1] 对照 quickstart S3/S4/S5 手工验证并在 `specs/001-sales-tool/quickstart.md` 勾注结论

**Checkpoint**: US1 可独立演示——新行业目标画像与种子库完整可用

---

## Phase 4: User Story 2 - 客户线索挖掘与联系方式提取 (Priority: P2)

**Goal**: 基于种子经检索渠道发现公司 → 抓取公开页面 → 抽取邮箱/电话/WhatsApp/Facebook → 去重分类、国家语言富化、排除规则、导入导出、断点续跑

**Independent Test**: 手工种子（或 US1 导出种子）→ 挖掘任务 → 去重后的公司与联系方式列表 → 导出（quickstart S6/S7；断网中断恢复不重抓）

### Tests for User Story 2 ⚠️（先写，确认失败）

- [x] T048 [P] [US2] 单元测试：联系方式抽取（图片邮箱/JS 拼接/防爬噪点/多 @/空格变体，HTML fixtures）`backend/tests/unit/test_extractor.py` + `backend/tests/fixtures/html/`
- [x] T049 [P] [US2] 契约测试：检索适配器（respx；限流→切渠道；DDG 202 软封禁识别为失败）`backend/tests/contract/test_search_providers.py`
- [x] T050 [P] [US2] 单元测试：挖掘引擎（断点续跑、同目标不重抓、暂停/恢复、失败重试）`backend/tests/unit/test_crawl_engine.py`
- [x] T051 [P] [US2] 集成测试：S6/S7（挖掘→去重→排除→人工修订→导出）`backend/tests/integration/test_us2_crawl_flow.py`

### Implementation for User Story 2

- [x] T052 [P] [US2] 检索适配器：Brave `backend/src/saler/providers/search/brave.py`
- [x] T053 [P] [US2] 检索适配器：Serper `backend/src/saler/providers/search/serper.py`
- [x] T054 [P] [US2] 检索适配器：Tavily `backend/src/saler/providers/search/tavily.py`
- [x] T055 [P] [US2] 检索适配器：DuckDuckGo 兜底（403/429/202 一律视为失败）`backend/src/saler/providers/search/ddg_fallback.py`
- [x] T056 [US2] 检索故障转移与注册：`backend/src/saler/providers/search/failover.py`（按 priority 调用、指数退避、quota/blocked 切渠道；用量计入 `search_provider.used_today`）
- [x] T057 [US2] 抓取层：`backend/src/saler/core/leads/fetcher.py`（httpx 异步、代理、单站 ≥1s 间隔、并发上限、robots 策略开关、重试、页大小上限；FR-025）
- [x] T058 [US2] 页面解析与联系页发现：`backend/src/saler/core/leads/parser.py`（selectolax；contact/about 链接候选）
- [x] T059 [US2] 联系方式抽取：`backend/src/saler/core/leads/extractor.py`（邮箱/电话/WhatsApp/Facebook/LinkedIn/X/Instagram/WeChat；规范化、用途分类、疑似无效标注；FR-020/021）
- [x] T060 [US2] 国家语言富化：`backend/src/saler/core/leads/enrich.py`（来源优先级 ccTLD > 查询市场 > 地址/电话区号；html lang + 检测；记录 country_source/language_source）
- [x] T061 [US2] 公司/联系方式服务：`backend/src/saler/core/leads/company_service.py`（合并多域名公司、状态、标签、`UNIQUE(company_id,type,value_normalized)` 执行；FR-022/027）
- [x] T062 [US2] 排除规则服务与应用任务：`backend/src/saler/core/compliance/exclusion.py`（关键词/域名/名单；命中对象单独存放；FR-023）
- [x] T063 [US2] 挖掘引擎：`backend/src/saler/core/leads/crawl_engine.py`（种子→检索→域名（pending）→抓取→抽取→落库；进度统计与日志；暂停/恢复/重试状态机；FR-019/024/026）
- [x] T064 [US2] 客户导入：`backend/src/saler/services/import_customers.py`（列名映射、先 domain 后 email 匹配、黑名单检查、导入报告；contracts/data-exchange.md §4）
- [x] T065 [US2] 线索导出：`backend/src/saler/services/export_leads.py`（字段与契约 §3 一致；被排除 Sheet + 统计 Sheet）
- [x] T066 [US2] API：`backend/src/saler/api/routes/crawl.py`（任务创建/控制）、`backend/src/saler/api/routes/domains.py`（列表/修订）
- [x] T067 [US2] API：`backend/src/saler/api/routes/companies.py`（列表/修订/合并/contacts/import/export；FR-027~029）
- [x] T068 [US2] API：`backend/src/saler/api/routes/search_providers.py`（CRUD/测试；密钥只写不读回）
- [x] T069 [US2] API：`backend/src/saler/api/routes/exclusion_rules.py`（CRUD + 对存量重跑 apply）
- [x] T070 [P] [US2] 前端：挖掘任务页（创建向导、SSE 进度、日志、暂停恢复）`frontend/src/views/leads/CrawlJobs.vue`
- [x] T071 [P] [US2] 前端：候选域名列表（状态筛选、人工排除/恢复）`frontend/src/views/leads/DomainList.vue`
- [x] T072 [P] [US2] 前端：公司列表与详情（联系方式、纠错补录、合并、状态标记）`frontend/src/views/leads/CompanyList.vue`、`frontend/src/views/leads/CompanyDetail.vue`
- [x] T073 [P] [US2] 前端：检索渠道配置页（按 config_schema 动态表单、测试、优先级排序）`frontend/src/views/settings/SearchProviders.vue`
- [x] T074 [US2] 前端：导入导出与排除规则界面 `frontend/src/views/leads/ImportExport.vue`、`frontend/src/views/leads/ExclusionRules.vue`
- [ ] T075 [US2] 对照 quickstart S6/S7 手工验证，并在 `specs/001-sales-tool/quickstart.md` 勾注结论

**Checkpoint**: US2 可独立演示——从种子到可导出的联系方式列表

---

## Phase 5: User Story 3 - 大模型接入与应用数据管理 (Priority: P2)

**Goal**: 多 LLM 服务配置与连通测试（密钥加密脱敏）；数据目录选择/迁移；备份/恢复/全量导出

**Independent Test**: 全新安装：选目录 → 配置密钥并测试 → AI 功能解锁；备份在新环境恢复一致（quickstart S1/S2/S11）

### Tests for User Story 3 ⚠️（先写，确认失败）

- [x] T076 [P] [US3] 契约测试：LLM providers CRUD + 测试端点（响应永不含密钥明文）`backend/tests/contract/test_llm_providers_api.py`
- [x] T077 [P] [US3] 单元测试：备份归档生成/校验/损坏或版本不符的拒绝；staged restore 回滚 `backend/tests/unit/test_backup.py`
- [x] T078 [P] [US3] 集成测试：S11 备份→异机恢复一致性 + S2 配置流程 `backend/tests/integration/test_us3_backup_restore.py`

### Implementation for User Story 3

- [x] T079 [US3] LLM Provider 服务：`backend/src/saler/core/llm_provider_service.py`（CRUD、secret 只写、is_default、参数与模型字段；FR-030）
- [x] T080 [US3] 连通测试流程：`backend/src/saler/providers/llm/test_connection.py`（GET /models 优先、1-token ping 回退、原样展示服务商错误）
- [x] T081 [US3] API：`backend/src/saler/api/routes/llm.py`（providers CRUD + `/test`）
- [x] T082 [US3] 数据目录迁移：`backend/src/saler/services/datadir.py` 增补（校验→复制→核对→原子切换；FR-033）
- [x] T083 [US3] 备份/恢复服务：`backend/src/saler/services/backup.py`（zip + manifest + checksum；恢复先校验再原子替换，失败回滚；contracts/data-exchange.md §6）
- [x] T084 [US3] API：`backend/src/saler/api/routes/backup.py` 与 `backend/src/saler/api/routes/settings.py`（含 data-dir 校验/迁移）
- [x] T085 [US3] 全量数据导出（开放格式，未来 Web 迁移预留）：`backend/src/saler/services/export_all.py`（§6 末段）
- [x] T086 [P] [US3] 前端：大模型配置页（多服务、脱敏展示、测试按钮、默认标记）`frontend/src/views/settings/LlmProviders.vue`
- [x] T087 [P] [US3] 前端：通用设置页（数据目录、网络代理、界面语言、内容回退语言）`frontend/src/views/settings/General.vue`
- [x] T088 [P] [US3] 前端：备份管理页（创建/校验/恢复确认/历史）`frontend/src/views/settings/Backup.vue`
- [x] T089 [US3] 前端：离线降级门（未配置 LLM 时禁用 AI 入口并提示；FR-032）`frontend/src/composables/useAiGate.ts`
- [ ] T090 [US3] 对照 quickstart S1/S2/S11 手工验证，并在 `specs/001-sales-tool/quickstart.md` 勾注结论

**Checkpoint**: US3 可独立演示——密钥管理、数据主权与迁移完整可用

---

## Phase 6: User Story 4 - 营销内容管理 (Priority: P3)

**Goal**: 内容主题与多语言版本（中文母版血缘）；AI 辅助编写母版 + 主题级多语言生成；变量渲染预览；版本管理与发布门

**Independent Test**: 建主题 → AI 起草母版 → 生成 ≥3 语言版本 → 预览 → 版本回溯 → 发布；全程不连通道（quickstart S8）

### Tests for User Story 4 ⚠️（先写，确认失败）

- [x] T091 [P] [US4] 单元测试：变量渲染（未知/缺失变量告警、签名注入）与语言匹配回退（fallback_used）`backend/tests/unit/test_content_render.py`
- [x] T092 [P] [US4] 契约测试：版本/发布/归档/恢复=新版本；未发布内容在计划 API 被拒 `backend/tests/contract/test_content_api.py`
- [x] T093 [P] [US4] 集成测试：S8 全流程 `backend/tests/integration/test_us4_content_flow.py`

### Implementation for User Story 4

- [x] T094 [US4] 内容服务：`backend/src/saler/core/content/service.py`（主题/语言版本/版本号/状态机；恢复历史=生成新版本；FR-037）
- [x] T095 [US4] 渲染器：`backend/src/saler/core/content/render.py`（`{{var}}` 解析/渲染/告警；变量清单入 content_version.variables；contracts/data-exchange.md §5）
- [x] T096 [US4] 语言匹配：`backend/src/saler/core/content/match.py`（auto/fixed/fallback 策略与 fallback 标注；FR-036）
- [x] T097 [US4] AI 内容服务：`backend/src/saler/core/content/ai.py`（content_draft_v1 母版起草/润色；content_translation_v1 主题级多语言生成，复用图谱词表术语；结果一律进 draft/review；FR-038）
- [x] T098 [US4] API：`backend/src/saler/api/routes/content.py`（themes/variants/versions/publish/archive/restore/preview）
- [x] T099 [P] [US4] 前端：内容主题列表与状态总览 `frontend/src/views/content/ThemeList.vue`
- [x] T100 [US4] 前端：版本编辑器（Markdown、变量插入、实时预览与告警）`frontend/src/views/content/VariantEditor.vue`
- [x] T101 [US4] 前端：AI 起草/翻译对话框与多语言对照视图 `frontend/src/views/content/AiContentDialog.vue`
- [x] T102 [US4] 前端：版本历史与恢复 `frontend/src/views/content/VersionHistory.vue`
- [ ] T103 [US4] 对照 quickstart S8 手工验证，并在 `specs/001-sales-tool/quickstart.md` 勾注结论

**Checkpoint**: US4 可独立演示——多语言营销内容生产就绪

---

## Phase 7: User Story 5 - 营销通道管理 (Priority: P4)

**Goal**: 邮件（P0）与短信通道的配置、连通测试、身份与限额、用量统计、健康状态；内容测试发送

**Independent Test**: 配置邮箱通道 → 测试连接 → 发测试邮件给自己 → 配限额与第二发件人（quickstart S9）

### Tests for User Story 5 ⚠️（先写，确认失败）

- [x] T104 [P] [US5] 契约测试：通道 CRUD（secret 不读回）、健康、限额结构 `backend/tests/contract/test_channels_api.py`
- [x] T105 [P] [US5] 单元测试：SMTP 适配器（本地假 SMTP/respx；auth/recipient_rejected 等错误映射）`backend/tests/unit/test_mail_adapter.py`
- [x] T106 [P] [US5] 集成测试：S9 配置→测试发送（假 MailSender）`backend/tests/integration/test_us5_channel_flow.py`

### Implementation for User Story 5

- [x] T107 [US5] 邮件适配器：`backend/src/saler/providers/mail/smtp.py`（aiosmtplib；verify/send/send_limit_hint；错误映射按 contracts/provider-adapters.md §3）
- [x] T108 [US5] 短信适配器：`backend/src/saler/providers/sms/http_generic.py`（HTTP API + 用户凭证；附 1–2 家服务商配置模板）
- [x] T109 [US5] 通道服务：`backend/src/saler/core/sending/channel_service.py`（CRUD、identity、daily_limit/rate/concurrency、used_today 跨日重置、health；FR-042/044）
- [x] T110 [US5] API：`backend/src/saler/api/routes/channels.py`（CRUD/test/usage；FR-040/041）
- [x] T111 [US5] 内容测试发送（US4×US5）：`backend/src/saler/api/routes/content.py` 增补 `test-send`（FR-039）
- [x] T112 [P] [US5] 前端：通道管理页（动态表单、脱敏展示、测试按钮、健康与用量）`frontend/src/views/channels/ChannelList.vue`、`ChannelForm.vue`
- [ ] T113 [US5] 对照 quickstart S9 手工验证，并在 `specs/001-sales-tool/quickstart.md` 勾注结论

**Checkpoint**: US5 可独立演示——邮件/短信通道可配置可验证

---

## Phase 8: User Story 6 - 营销计划与批量触达 (Priority: P5)

**Goal**: 人群×内容×通道×数量的计划编排；预估；执行/暂停/恢复；发送台账防重复打扰；退订黑名单；多轮跟进；报表导出

**Independent Test**: 测试客户走通"圈人群→选内容→选通道→试发→发送→台账→二次计划默认跳过→退订排除"（quickstart S10）

### Tests for User Story 6 ⚠️（先写，确认失败）

- [x] T114 [P] [US6] 单元测试：人群圈选与预估（数量、语言/通道分布、ETA 按限额推算）`backend/tests/unit/test_audience_estimate.py`
- [x] T115 [P] [US6] 单元测试：防重唯一键 `UNIQUE(campaign_id, round_no, contact_id)`、退订/排除命中即 skipped/suppressed、失败重试不改唯一键 `backend/tests/unit/test_send_guard.py`
- [x] T116 [P] [US6] 集成测试：S10 全链路 + 多轮跟进（未回复者进入下一轮，已标记回复者排除）`backend/tests/integration/test_us6_campaign_flow.py`

### Implementation for User Story 6

- [x] T117 [US6] 人群解析：`backend/src/saler/core/campaigns/audience.py`（筛选条件→send_record(pending) 物化；排除 suppression/exclusion/已有触达；FR-046/050）
- [x] T118 [US6] 预估服务：`backend/src/saler/core/campaigns/estimate.py`（客户数/条数/语言通道分布/时长；FR-047）
- [x] T119 [US6] 计划与轮次服务：`backend/src/saler/core/campaigns/service.py`（状态机 draft→running⇄paused→completed/cancelled；轮次配置；仅可选已发布内容；FR-046/052/053）
- [x] T120 [US6] 发送引擎：`backend/src/saler/core/sending/engine.py`（按通道配额与节奏节流；渲染并冻结 content_version；经 MailSender/SMSSender 发送；写台账；失败重试；primary→backup 换通道；暂停/恢复；FR-048/049）
- [x] T121 [US6] 多轮跟进调度：`backend/src/saler/core/campaigns/followup.py`（间隔触发、no_reply_or_progress 条件、轮次内容选择）
- [x] T122 [US6] 退订/黑名单：`backend/src/saler/core/compliance/suppression.py` + `backend/src/saler/api/routes/suppressions.py`（CRUD；命中对象所有后续计划自动排除；FR-051）
- [x] T123 [US6] 客户状态联动：`backend/src/saler/core/leads/company_service.py` 增补（已回复/已成交/拒绝 → 跟进与排除逻辑即时生效；FR-054）
- [x] T124 [US6] API：`backend/src/saler/api/routes/campaigns.py`（CRUD/estimate/rounds/start|pause|resume|cancel/records/retry/report/test-send）
- [x] T125 [US6] 报表与导出：`backend/src/saler/services/campaign_report.py`（按通道/语言/轮次统计；导出）
- [x] T126 [P] [US6] 前端：计划创建向导（人群→内容→通道→数量节奏 + 预估确认）`frontend/src/views/campaigns/CampaignWizard.vue`
- [x] T127 [P] [US6] 前端：执行监控（SSE 进度、暂停/恢复/中止、失败原因）`frontend/src/views/campaigns/CampaignMonitor.vue`
- [x] T128 [US6] 前端：台账查询与失败重试 `frontend/src/views/campaigns/RecordTable.vue`
- [x] T129 [US6] 前端：报表与导出 `frontend/src/views/campaigns/Report.vue`
- [x] T130 [US6] 前端：退订/黑名单管理页 `frontend/src/views/settings/Suppressions.vue`
- [ ] T131 [US6] 对照 quickstart S10 手工验证，并在 `specs/001-sales-tool/quickstart.md` 勾注结论

**Checkpoint**: 全部用户故事就绪——从种子到批量触达的完整闭环

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: 横切质量、性能、打包与发布（依赖全部目标故事完成）

- [x] T132 [P] 性能：FTS5 影子表（company/contact 搜索；仅在索引不足时启用）`backend/src/saler/db/fts.py`
- [x] T133 [P] 大列表虚拟滚动组件（10 万级线索列表）`frontend/src/components/tables/VirtualTable.vue`
- [x] T134 Linux WebKitGTK 启动诊断与可操作错误提示 `backend/src/saler/desktop/diagnostics.py`
- [x] T135 代理兼容：回环地址绕过系统代理（`no_proxy`）`backend/src/saler/services/proxy.py`
- [x] T136 维护任务：operation_log 滚动清理 + 备份提醒 `backend/src/saler/jobs/maintenance.py`
- [x] T137 AI 遥测：各 provider/model 重试率记录入 operation_log `backend/src/saler/providers/llm/telemetry.py`
- [x] T138 PyInstaller spec 完稿（`--onedir`、hiddenimports（uvicorn/fastapi/gi）、`--add-data` 前端产物、`multiprocessing.freeze_support()`）`packaging/saler.spec`
- [x] T139 三平台构建矩阵完善（前端构建→PyInstaller→产物上传）`.github/workflows/build.yml`
- [x] T140 安装器脚本：`packaging/installers/windows/inno.iss`、`packaging/installers/linux/appimage.yml`、`packaging/installers/macos/dmg-notes.md`
- [x] T141 签名与公证（发布阶段）：`packaging/installers/macos/notarize.sh`（inside-out 签名、G2 中间证书、`status: Accepted` 解析）、`packaging/installers/windows/sign.md`（Azure Trusted Signing）
- [ ] T142 冻结包冒烟：三平台安装产物跑 quickstart S1/S6/S10 并记录
- [ ] T143 quickstart 全场景 S1–S12 走查记录（含 S12 无大模型兜底与三平台一致性）
- [x] T144 用户文档初稿：`docs/user-guide.md`（安装、首次配置、密钥与合规说明、常见问题）
- [x] T145 刷新 `specs/001-sales-tool/plan.md` 的 Constitution Check 为对 v1.0.0 的对照结论
- [x] T146 运行 `/speckit-analyze` 做跨工件一致性检查并处置发现项

---

## Phase 10: 补充任务（/speckit-analyze 修复项 C1/C2）

**来源**: `/speckit-analyze` 覆盖度分析（2026-10-10），经用户确认按建议增补（编号续接，不重排既有任务）。

**C1（FR-013 检索扩充图谱）——归 US1，建议在 T041 之后执行**

- [x] T147 [P] [US1] 单元测试：检索扩充图谱服务（从检索结果/目录提炼候选实体与种子→`source=search`→`review_status=pending`；`seed.query` 去重；evidence 来源记录）`backend/tests/unit/test_seed_discover.py`
- [x] T148 [US1] 检索扩充服务：`backend/src/saler/core/seeds/discover.py`（复用 T015 检索接口与 T036 落库/审核管线；真实渠道故障转移随 T056 接入，测试用假 SearchProvider）+ API 增补 `/seeds/discover`（job 化）于 `backend/src/saler/api/routes/seeds.py`（FR-013）
- [x] T149 [US1] 前端：检索扩充入口（选择检索渠道→输入关键词/目录→提炼结果→进入待审核）`frontend/src/views/seeds/ImportExport.vue`

**C2（SC-011 首用引导）——归 US6，建议随 T126 一并执行**

- [x] T150 [US6] 前端：首用引导与上下文提示（计划向导内联说明、字段帮助、首次流程检查清单；确保"无需外部文档"路径可用）`frontend/src/views/campaigns/CampaignWizard.vue`、`frontend/src/components/common/OnboardingHint.vue`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖，可立即开始
- **Foundational (Phase 2)**: 依赖 Setup 完成；**阻塞所有用户故事**
- **User Stories (Phase 3+)**: 均依赖 Foundational 完成
- **Polish (Phase 9)**: 依赖所需用户故事完成
- **补充任务 (Phase 10)**: 随所属故事执行——T147–T149 属 US1（T041 之后）、T150 属 US6（随 T126），不构成独立阶段

### User Story Dependencies

- **US1 (P1)**: Foundational 后可开始；无其他故事依赖 —— MVP
- **US2 (P2)**: Foundational 后可开始；以 US1 种子库为输入（也可用手工种子独立验证）；复用 T033 域名服务
- **US3 (P2)**: Foundational 后可开始；无故事依赖（US1/US4 的 AI 现场使用需要其配置，但测试用假 Provider 独立进行）
- **US4 (P3)**: Foundational 后可开始；无故事依赖
- **US5 (P4)**: Foundational 后可开始；无故事依赖
- **US6 (P5)**: 依赖 US2（线索）+ US4（已发布内容）+ US5（通道）三者完成
- **补充任务**: T147–T149 归 US1（测试用假 SearchProvider 独立验证；真实检索渠道接入见 US2 T052–T056）；T150 归 US6

### Within Each User Story

- 测试（T0xx 测试组）必须先写并确认失败，才能进入实现任务（宪法第 I 条）
- 服务/模型先于 API；API 先于前端整合；核心实现先于集成
- 按优先级顺序完成故事（P1 → P5）

### Parallel Opportunities

- Setup 中 T002–T006 并行；Foundational 中带 [P] 任务并行
- Foundational 完成后，US1/US3/US4/US5 可并行开工（不同开发线）；US2 建议紧随 US1
- 各故事内：测试组 [P] 并行 → 实现中的 [P] 服务并行 → 前端视图 [P] 并行

---

## Parallel Example: User Story 1

```bash
# 1) 并行启动 US1 测试组（先写并确认失败）：
Task: "契约测试：图谱/种子 API in backend/tests/contract/test_seeds_api.py"
Task: "单元测试：产量统计口径 in backend/tests/unit/test_yield_stats.py"
Task: "单元测试：AI 扩充/翻译落库 in backend/tests/unit/test_seed_ai.py"
Task: "集成测试：S3/S5 流程 in backend/tests/integration/test_us1_seed_flow.py"

# 2) 并行实现互不相交的服务：
Task: "图谱服务 in backend/src/saler/core/graph/service.py"
Task: "种子服务 in backend/src/saler/core/seeds/service.py"
Task: "域名共享服务 in backend/src/saler/core/leads/domain_service.py"

# 3) 并行实现前端视图：
Task: "种子列表+审核队列 in frontend/src/views/seeds/SeedList.vue"
Task: "图谱管理 in frontend/src/views/seeds/GraphManage.vue"
Task: "AI 扩充对话框 in frontend/src/views/seeds/AiExpandDialog.vue"
```

## Parallel Example: User Story 6

```bash
# 并行启动三个检索器/引擎测试（先写并确认失败）：
Task: "人群与预估测试 in backend/tests/unit/test_audience_estimate.py"
Task: "发送守卫测试 in backend/tests/unit/test_send_guard.py"
Task: "S10 集成测试 in backend/tests/integration/test_us6_campaign_flow.py"

# 并行实现：
Task: "人群解析 in backend/src/saler/core/campaigns/audience.py"
Task: "预估服务 in backend/src/saler/core/campaigns/estimate.py"
Task: "退订黑名单服务 in backend/src/saler/core/compliance/suppression.py"
```

---

## Implementation Strategy

### MVP First（US1）

1. 完成 Phase 1: Setup
2. 完成 Phase 2: Foundational（关键——阻塞一切）
3. 完成 Phase 3: US1
4. **停下验证**：跑 quickstart S3/S4/S5，独立验收种子知识库
5. 可演示可继续

### Incremental Delivery

1. Setup + Foundational → 地基就绪
2. US1 → 验证 → MVP（种子知识库）
3. US3 → 验证（LLM 配置+数据主权就绪，解锁 AI 现场能力）
4. US2 → 验证（获客闭环：种子→线索）
5. US4 → US5 → 验证（内容与通道就绪）
6. US6 → 验证（触达闭环）
7. Polish → 打包发布（冻结包冒烟 + S1–S12 全场景）

### Parallel Team Strategy

多人协作时：Setup+Foundational 共同完成；此后 A 线 US1→US2、B 线 US3、C 线 US4→US5，最后合流 US6。

---

## Notes

- `[P]` = 不同文件、无未完成依赖，可并行
- `[USx]` 标签用于追溯；Setup/Foundational/Polish 不带故事标签
- 每个故事可独立完成与验收；完成后可在 Checkpoint 停止演示
- 测试一律先失败再实现（宪法第 I 条）；假 Provider 保证离线可测
- 每个任务完成即提交（仓库尚未 git init，T001 首先处理）
- 避免：模糊任务、同文件冲突、破坏故事独立性的跨故事依赖
