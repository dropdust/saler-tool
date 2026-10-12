---
description: "Task list for 检索渠道扩展——密钥申请指引与免密钥搜索引擎"
---

# Tasks: 检索渠道扩展——密钥申请指引与免密钥搜索引擎

**Input**: Design documents from `/specs/004-search-channel-expansion/`

**Prerequisites**: [plan.md](plan.md)（required）, [spec.md](spec.md)（required）, [research.md](research.md), [data-model.md](data-model.md), [contracts/search-channel-expansion-contract.md](contracts/search-channel-expansion-contract.md), [quickstart.md](quickstart.md), `.specify/memory/constitution.md`

**Tests**: 必含——项目宪法第 I 条（测试驱动开发，不可协商）要求先写可失败的测试再实现；本特性测试全部离线可跑（pytest + respx + vitest；引擎页面样本固化为合成 fixture，不依赖真实外网）。标注"红→绿"的任务严格先失败后实现；行为锁定类（既有能力回归）注明"书写即绿"或"保持既有用例绿"。

**Organization**: 任务按用户故事分组（US1 免密钥六渠道 / US2 申请地址与决策要点 / US3 运行时风险透明），每个故事可独立实现、独立测试、独立交付。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无未完成依赖）
- **[Story]**: 所属用户故事（US1–US3）；Setup/Foundational/Polish 不带标签
- 每个任务都包含确切文件路径
- 任务编号自 **T198** 起（延续 003 的 T196 提交与在途的 T197 GTK 修正，避免提交信息任务 ID 冲突）

## Path Conventions

- 后端：`backend/src/saler/`、后端测试：`backend/tests/`
- 前端：`frontend/src/`、前端测试：`frontend/tests/`
- 本特性**零新增依赖、无打包面变化**（沿用 001 冻结包冒烟流程，无安装器/打包脚本改动）

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 基线核对，建立 TDD 红→绿对照基线

- [X] T198 基线绿灯核对：在途他线改动（seeds-AI / GraphView / GTK 修复等）采取**隔离策略**——全部保留不触碰，本特性各任务仅暂存自身触碰文件（绝不 `git add -A`）；基线 `uv run pytest -q` **231 passed**、`pnpm test` **48 passed** + `pnpm lint` clean——基线绿，进入 Phase 2；同期搭载 004 规格工件入库

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 全部用户故事共同依赖的基座——错误类别、manifest 元数据通道、数据库列、注册表驱动装配

**⚠️ CRITICAL**: 本阶段完成前，任何用户故事不得开始

- [X] T199 [P] 错误类别扩展（红→绿）：`backend/src/saler/providers/errors.py` 增 `PARSE = "parse"`（注释：页面结构变化/解析失败，网页端检索特有；**不可重试**）；新建 `backend/tests/unit/test_provider_errors.py`——PARSE 枚举值正确、`RETRYABLE_KINDS` 不含 PARSE、`ProviderError(kind="parse")` 可构造且 `retryable=False`（data-model.md §3 / contract §4.1）→ 3 项确认失败 → **转绿（3 passed）**
- [X] T200 [P] manifest 元数据通道（红→绿）：`backend/src/saler/providers/registry.py` `ProviderManifest` 增可选字段 `preset: dict[str, Any] | None = None`（frozen dataclass 默认值，既有四类注册零改动）；新建 `backend/tests/unit/test_provider_registry.py`——默认 None、带 preset 注册后可读、`by_kind("search")` 返回顺序稳定（research R8）→ 2 项红 → **转绿（3 passed）**
- [X] T201 数据库迁移（红→绿）：`backend/src/saler/db/models/system.py` `SearchProvider` 增 `last_error_kind: Mapped[str | None] = mapped_column(String(20))` 与 `last_error_at: Mapped[datetime | None] = mapped_column()`（均可空、无回填）；新建 `backend/alembic/versions/c4a7e91b2d3f_search_provider_error_columns.py`（`down_revision=80e843b63e22`）；验证：`alembic upgrade head` → PRAGMA 确认两列在 → `downgrade -1` → 再 `upgrade head` 往返通过（head=c4a7e91b2d3f）；全量 **237 passed**（contract §3 / data-model.md §2）
- [X] T202 注册表驱动装配重构（行为锁定——书写即绿/既有用例保持绿）：先在 `backend/tests/contract/test_search_providers_api.py`（新建）补路由级回归测试——POST 未知 `type_key` → 422、POST `ddg_html` 免密钥可保存、GET `/search/presets` 返回 `presets`+`config_schemas` 形状；随后重构：`backend/src/saler/api/routes/search_providers.py` 删除 `SEARCH_KINDS` 元组改用 `registry.by_kind("search")` 值域、`_build_adapter` 的 `type_key != "ddg_html"` 特判改为 `manifest.secret_fields` 空判定；`backend/src/saler/core/leads/search_setup.py` 同步同一判定——重构后全量既有测试绿（FR-001 单独立即可用性不回归；research R8）→ 基线 **6 项书写即绿**；包级 `__init__` 单一注册点；工厂统一接收渠道级 `params` 注入；ruff 全过、全量 **243 passed**

**Checkpoint**: 基座就绪——错误类别、preset 通道、行级列、装配去硬编码全部完成，用户故事可开始

---

## Phase 3: User Story 1 - 免密钥免费搜索引擎渠道，零成本可用 (Priority: P1) 🎯 MVP

**Goal**: 百度 / Google / Bing / Mojeek / Wikipedia 五个新免密钥渠道 + DuckDuckGo 既有渠道加固；全部纳入优先级故障转移，遵守安全失败纪律（风控页绝不写入数据、链接全部还原为目标地址），并从任务运行到界面全程记账

**Independent Test**: 逐一添加六个免密钥渠道（无需密钥）完成连通测试；混合链中令首选渠道失败（respx 回放）→ 任务不中断、按序切换、渠道列表用量与失败原因同步；风控样本回放 0 脏数据（quickstart V2/V3/V4/V5）

### Tests for User Story 1 ⚠️（先写，确认失败）

- [X] T203 [US1] HTML 渠道共基类（红→绿）：新建 `backend/src/saler/providers/search/html_base.py`——`HTMLSearchEngine` 抽象基类：client 复用 `build_client`（`follow_redirects=True`）、浏览器 UA 池（Chrome/Win、Safari/Mac、Chrome/Linux 轮换 + `Accept-Language`，可被子类锁定）、引擎实例级节流（`params.interval_s` 默认 2.0s + 0~1.5s 抖动）、`search()` 编排（请求 → `_check_blocked` hook → 解析 hook → 空结果纪律三分支）、`test_connection()`、目标链接还原 hook；新建 `backend/tests/unit/test_html_base.py`（fake engine）——节流生效（两次请求间隔 ≥ 设定值）、UA 在池内轮换、blocked 标记 → `ProviderError(BLOCKED)`、无标记且结构正常 → `[]`、结果容器整体缺失 → `BLOCKED`（疑似伪装/软封禁，保守）、容器存在但解析异常 → `PARSE`（contract §4.2 / research R10/R12）→ **13 项红→绿**（节流用假时钟确定性断言；含 cookie jar 会话保活、状态映射 429/403/503、test_connection 明细带类别前缀）
- [X] T204 [P] [US1] Bing 适配器（红→绿）：新建 `backend/src/saler/providers/search/bing.py` + `backend/tests/contract/test_search_bing_html.py` + `backend/tests/fixtures/search_pages/bing/{rss.xml,results,captcha,cn_redirect}.html`（合成样本）——**RSS 形态优先**：`?q=&format=rss&mkt=en-US&setlang=en`，解析 `<item>`（title/link/description，链接为直链）；**RSS 空结果 → HTML 形态复核**（不得直接判合法空）；**HTML 形态**：`?q=&count=&first=&mkt=en-US&cc=US&ensearch=1` + cookie `ENSEARCH=BENVER=1`，解析 `li.b_algo`（标题链接 `h2 a`、摘要 `.b_caption p`）；`/ck/a?...&u=a1<base64url>` 离线解码（剥 `a1` 前缀 → URL-safe base64 → UTF-8，解析前反转义 `&amp;`；样例 `a1aHR0cHM6Ly9ydXN0LWxhbmcub3JnLw` → `https://rust-lang.org/`）；静默 captcha（HTTP 200 + `class="captcha"` + 0 结果）→ `BLOCKED`；cn.bing.com 落地带 ensearch 重试**一次** → 仍重定向则 `BLOCKED`；MANIFEST：`type_key="bing_html"` + preset（`access_mode="html"`、`market`、`risk`、`apply_url=None`）（contract §4.1/§4.3 / research R4）→ **9 项红→绿**（cn 重定向经 www4 重试一次、空 RSS 转 HTML 复核、静默 captcha/空白页归 blocked）；html_base 节流补丁（interval_s≤0 显式关闭，抖动不再作用于测试）；全量 **265 passed**
- [X] T205 [P] [US1] 百度适配器（红→绿）：新建 `backend/src/saler/providers/search/baidu.py` + `backend/tests/contract/test_search_baidu_html.py` + `backend/tests/fixtures/search_pages/baidu/{results,verify,http480}.html`——请求 `wd/pn/rn/ie=utf-8&oe=utf-8` + 桌面 UA + `Accept-Language: zh-CN`；**首次请求 GET 首页种 cookie（BAIDUID）并与 UA 锁定配对（不轮换）**；解析 `#content_left` 下 `.result`/`.c-container`（含 `.result-op`），标题 `h3 a`，摘要 `.c-abstract`（属性/语义选择器优先，哈希后缀类名只作 fallback），过滤广告（`data-tuiguang`、`data-cs='ad'`、"广告"）；**链接还原：结果块 `mu` 属性（备选 `data-landurl`）离线提取，绝不跟随 `link?url=`**；blocked：落地 wappass.baidu.com / verify.baidu.com、标题含"百度安全验证"、"网络不给力"、HTTP 480；MANIFEST+preset（`market="中文市场"`）（contract §4.1/§4.3 / research R2）→ **8 项红→绿**（mu/data-landurl 离线还原、广告过滤、BAIDUID 单次种入 + 实例内 UA 固定配对、wappass 落地/安全验证标题/HTTP 480 三路判 blocked）；陷阱修复：selectolax 逗号选择器对双类名块重复返回（3 块×2）→ 并集 + (title,url) 去重；全量 **273 passed**
- [ ] T206 [P] [US1] Mojeek 适配器（红→绿）：新建 `backend/src/saler/providers/search/mojeek.py` + `backend/tests/contract/test_search_mojeek_html.py` + `backend/tests/fixtures/search_pages/mojeek/{results,forbidden}.html`——解析 `ul.results-standard > li`（标题 `a.title`、链接 `a.ob` 的 href、摘要 `p.s`）；403 页 → `BLOCKED`；MANIFEST+preset（`market="英国独立索引/欧美补充"`；note 注明官方 API 为付费计量仅试用）（contract §4 / research R6）
- [ ] T207 [P] [US1] Wikipedia 适配器（红→绿）：新建 `backend/src/saler/providers/search/wikipedia.py` + `backend/tests/contract/test_search_wikipedia.py` + `backend/tests/fixtures/search_pages/wikipedia/search.json`——请求 `{lang}.wikipedia.org/w/api.php`（`action=query&list=search&srsearch=&srlimit=`（clamp ≤50）`&srprop=snippet&format=json&formatversion=2`）；语言子域由 `params.lang`（默认 `en`）决定、`search(lang=...)` 调用方提供时覆盖；结果 `query.search[]` → `SearchItem`（URL 直接构造 `https://{lang}.wikipedia.org/wiki/{title}`，snippet HTML 标签清洗）；**UA 为描述性 `SalerTool/<版本> (+项目主页)`（Wikimedia 政策，主页取自包元数据/README）——契约测试断言 UA 含 "SalerTool" 与联系信息形态**；429 → `RATE_LIMIT`（尊重 Retry-After）；MANIFEST：`type_key="wikipedia"`、`access_mode="official_api"`、`needs_key=False`（preset 注明命中模糊性：缩写/母公司误配，不得用于自动否定）（contract §4.1 / research R7）
- [ ] T208 [P] [US1] Google 适配器（红→绿）：新建 `backend/src/saler/providers/search/google.py` + `backend/tests/contract/test_search_google_html.py` + `backend/tests/fixtures/search_pages/google/{results,sorry}.html`——请求 `q/hl/gl/start/pws=0` + consent cookie（`CONSENT=PENDING+987`、`SOCS=CAESHAgBEhIaAB`），**不使用已失效的 `num`**；解析 `#rso` / `div[data-hveid]`（标题 `a > h3`、摘要 `.VwiC3b`/`.st`），多启发式过滤广告（`[data-text-ad]`、`#tads/#tadsb`、"Sponsored/赞助商链接"、`aclk` 链接）；链接还原：旧式 `/url?q=` 离线解码，新式 `/goto?url=<签名>` **逐条跟随一次 302**（计入节流），仍不可还原 → **丢弃该条**（不写包装链接）；blocked：`/sorry/index` 落地、HTTP 200 正文嗅探（"unusual traffic" / "not a robot" / 中文"异常流量"）、429 → `RATE_LIMIT`；MANIFEST+preset（`risk` 明示"高风险、尽力而为"）（contract §4.1/§4.3 / research R3）

### Implementation for User Story 1

- [ ] T209 [US1] DuckDuckGo 加固（红→绿 + 既有用例保持绿）：`backend/src/saler/providers/search/ddg_fallback.py`——请求头浏览器 UA + `Referer: https://duckduckgo.com/`；0 结果纪律收紧（anomaly/检测页 → `BLOCKED`；确无结果且结构正常 → `[]`）；html 形态失败判定软封禁时以 `lite.duckduckgo.com/lite/` 形态**回退一次**；MANIFEST 补 preset（`access_mode="html"`、`apply_url=None`、风险文案）；扩展 `backend/tests/contract/test_search_providers.py` 既有 DDG 测试类（既有 202/403/anomaly 用例保持绿）（research R5）
- [ ] T210 [US1] 运行时记账（红→绿）：新建 `backend/src/saler/core/leads/search_stats.py`——`SearchStatsRecorder(session_factory)`：`record_attempt(row_id, ok, error)`（`used_today` 按日重置累加，对齐 `core/sending/channel_service.ensure_used_today` 语义；成功 → `health="healthy"` 且清空 `last_error_kind/at`；失败 → `health="failing"` 写 `last_error_kind`（`error.kind.value`）与 `last_error_at`；`session_factory=None` → no-op）；`backend/src/saler/core/leads/search_setup.py` 增 `_RecordingAdapter`（实现 `SearchProvider` Protocol，转发并记录，**不触碰 `SearchFailover`**）与 `resolve_search_chain(db, config=None, session_factory=None)` 装配（调用点 `backend/src/saler/api/routes/seeds.py` 与 `backend/src/saler/api/routes/crawl.py` 传入 `request.app.state.session_factory`）；新建 `backend/tests/unit/test_search_stats.py`——成功/失败/跨日重置/成功清空最近失败/None→no-op 五分支（data-model.md §2 状态机 / contract §3）
- [ ] T211 [US1] 测试端点同口径（红→绿）：`backend/src/saler/providers/llm/base.py` `TestResult` 增可选 `kind: str | None = None`（默认 None，LLM/邮件/短信既有用法零影响）；各 search 适配器 `test_connection()` 失败时填 `kind=exc.kind.value`（含既有 brave/serper/tavily/ddg 与新引擎）；`backend/src/saler/api/routes/search_providers.py` 测试路由：成功 → `health="healthy"` 清空 `last_error_*`；失败 → `health="failing"` + 写 `last_error_kind/at`（`last_test_result` 语义不变）；扩展 `backend/tests/contract/test_search_providers_api.py`——测试成功/失败后行字段断言（contract §3）
- [ ] T212 [US1] 前端：密钥字段数据驱动（红→绿）：`frontend/src/views/settings/SearchProviders.vue` 密钥输入框 `v-if` 由硬编码 `form.type_key !== 'ddg_html'` 改为 `presets[form.type_key]?.needs_key`（免密钥类型显示"无需密钥"且不渲染输入框，保存 payload 不含 `api_key`）；新建 `frontend/tests/search-providers.test.ts`——mock `/search/presets` 含 needs_key true/false 两类型：类型切换断言字段显隐与提交 payload（FR-002）
- [ ] T213 [US1] 集成：故障转移 + 记账闭环（红→绿）：新建 `backend/tests/integration/test_search_failover_stats.py`（临时数据目录 + 真实 `SearchFailover` + `_RecordingAdapter` + respx）——链 [渠道A(429) → 渠道B(200 解析成功)]：任务调用不中断返回结果；A 行 `used_today` +1、`health="failing"`、`last_error_kind="rate_limit"`；B 行 `used_today` +1、`health="healthy"`（FR-005/006 / SC-004）
- [ ] T214 [US1] 验收（quickstart V2/V3/V4/V5）：按 [quickstart.md](quickstart.md) 执行——V2 逐渠道添加+测试计时（≤1 分钟）；V3 小批量真实检索：核对来源记录口径与付费渠道一致、抽检链接还原（≥95%，网络可达性如实记录）；V4 风控样本回放确认 0 脏数据；V5 混合链失败 0 中断与列表记账呈现；结论勾注 quickstart 对应小节（SC-001/002/003/004/006）

**Checkpoint**: US1 完成——六个免密钥渠道可用、安全失败、记账闭环，构成 MVP

---

## Phase 4: User Story 2 - 服务商密钥申请地址与决策要点一屏直达 (Priority: P2)

**Goal**: 需密钥渠道展示官方申请地址（一键开系统浏览器）与决策要点（额度/市场/风险）；免密钥渠道标注"无需密钥"；`/search/presets` 全面由 registry 派生

**Independent Test**: 添加/编辑渠道对话框中逐类型核对信息卡（申请地址可点击直达、额度/市场/风险完整、免密钥无密钥字段），quickstart V1

### Tests for User Story 2 ⚠️（先写，确认失败）

- [ ] T215 [P] [US2] 预置完整性契约测试（红）：新建 `backend/tests/contract/test_search_presets.py`——**动态遍历 `registry.by_kind("search")`**（对当时已注册类型断言，US1 完成与否均可独立运行）：每类型 `preset` 非 None 且含 display/endpoint/note/access_mode/market/risk；`needs_key == bool(secret_fields)`；需密钥 ⇒ `apply_url` 非空；`access_mode=="html"` ⇒ `risk` 非空——当前三个付费类型未补齐 → 确认失败（contract §1/§6）

### Implementation for User Story 2

- [ ] T216 [P] [US2] 付费渠道预置数据补齐（转绿 T215）：`backend/src/saler/providers/search/brave.py`、`serper.py`、`tavily.py` 的 MANIFEST 增 preset——`apply_url`：Brave=`https://api-dashboard.search.brave.com/app/keys`（旧址 api.search.brave.com/app/keys 已 403，不得使用）、Serper=`https://serper.dev/dashboard`、Tavily=`https://app.tavily.com`；note 更新：Serper 赠 2,500 次为**一次性**、Brave 每月 $5 信用**需绑卡**、Tavily 1,000 信用/月；`market` 与 `risk`（Brave ToS 存储条款等）（research R11）
- [ ] T217 [US2] 预置端点 registry 派生（红→绿）：`backend/src/saler/api/routes/search_providers.py` `GET /search/presets` 改由 registry 组装（`display=display_name`、`needs_key` 派生、其余字段取自 `preset`）；删除 `backend/src/saler/providers/search/_common.py` 的 `SEARCH_PRESETS` 字典（唯一数据源=各 manifest）；扩展 `backend/tests/contract/test_search_providers_api.py`——presets 覆盖全部注册类型、字段完整、`config_schemas` 形状不变（向后兼容，既有键 display/endpoint/needs_key/note 保留）
- [ ] T218 [US2] 前端信息卡（红→绿）：`frontend/src/api/types.ts` `Preset` 扩展（`apply_url/access_mode/market/risk`）；`frontend/src/views/settings/SearchProviders.vue` 添加/编辑对话框在类型选定后渲染信息卡——接入方式标签、申请地址按钮（`el-link` + `target="_blank"` 系统浏览器打开，仅 needs_key 时）、note/market/risk 全文、免密钥显示"无需密钥"；申请地址缺失时呈现"服务商名 + 域名"可读兜底（FR-016）；扩展 `frontend/tests/search-providers.test.ts`——各字段渲染、needs_key=false 无申请按钮、失效兜底文案（FR-013~015）
- [ ] T219 [US2] 验收（quickstart V1）：真实运行（CDP 自动驱动）——逐类型打开添加对话框核对信息卡；点击 Brave/Serper/Tavily 申请地址确认在**系统浏览器**打开对应官方页面；免密钥 7 类型无密钥字段；编辑既有渠道同样可见信息卡；结论勾注 quickstart（SC-005 / FR-013~016）

**Checkpoint**: US2 完成——开通指引一屏直达，`/search/presets` 单一数据源

---

## Phase 5: User Story 3 - 免费渠道的运行时风险透明 (Priority: P3)

**Goal**: 渠道列表可辨识接入方式与失败原因；页面指引与文案不再出现过时结论；免费渠道"非官方接入"性质明示

**Independent Test**: 列表逐行见接入方式标签；制造/回放网络失败 → 提示归网络类不误示密钥问题；指引文案与当前渠道集合一致，quickstart V6

### Tests for User Story 3 ⚠️（先写，确认失败）

- [ ] T220 [P] [US3] 行响应字段扩展（红→绿）：`backend/src/saler/api/serializers.py` `search_provider_to_dict` 增 `last_error_kind`、`last_error_at`（ISO 或 null）；扩展 `backend/tests/contract/test_search_providers_api.py`——列表/详情响应含两字段、成功清空后为 null（contract §3）
- [ ] T221 [US3] 前端呈现（红→绿）：`frontend/src/views/settings/SearchProviders.vue`——"类型"列附接入方式小标签（`access_mode` → 官方 API / 网页解析）；"健康"列 `failing` 时展示最近失败原因中文标签（映射全表：`rate_limit`→限流、`blocked`→风控封禁、`parse`→解析失败、`network`/`timeout`→网络、`auth`→密钥、`quota`→额度、null→仅"异常"）；扩展 `frontend/tests/search-providers.test.ts`——映射全表断言、标签渲染（FR-017/018）
- [ ] T222 [US3] 指引与文案更新（红→绿）：`frontend/src/views/settings/SearchProviders.vue` 页面 alert 重写——删除"Bing 已退役、Google PSE 已对新客户关闭，均不可用"式**过时断言**，改为两段式：官方 API 渠道（稳定、需密钥）与免密钥网页渠道（尽力而为、受风控影响、自动兜底、合规责任自担）；`backend/src/saler/api/routes/crawl.py` 409 文案去除写死的渠道枚举（Brave / Serper / Tavily / DDG）；前端测试断言 alert 文案不含"均不可用"类措辞并含网页渠道定位说明（FR-019/020）
- [ ] T223 [US3] 验收（quickstart V6）：真实运行核对——渠道列表逐行"接入方式"标签全覆盖；构造网络类失败（渠道端点改为不可达主机）测试 → 提示归网络类、不误示为密钥问题；页面指引与 crawl 409 文案无过时结论、免密钥渠道"非官方接入、合规责任自担"提示可见；结论勾注 quickstart（SC-007 / FR-017~020）

**Checkpoint**: US3 完成——风险透明，三故事独立闭环

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 契约同步、全量回归与一致性审查

- [ ] T224 [P] 契约与文档同步（宪法"契约变更必须同步"；contract §7）：`specs/001-sales-tool/contracts/provider-adapters.md`（§2 检索：六个新 type_key 与接入方式、错误矩阵增 `parse`、`preset` 元数据约定、空结果纪律、链接还原通则）；`specs/001-sales-tool/contracts/local-api.md`（检索渠道节：`/search/presets` 响应扩展字段表、provider 行 +`last_error_kind`/`last_error_at`、运行时记账语义）；`specs/001-sales-tool/quickstart.md`（S 场景补"免费检索渠道可作补充/兜底（004 增量）"一句）
- [ ] T225 回归与一致性：全量测试绿（后端 pytest 全量 / 前端 vitest + lint + build）；`/speckit-analyze` 一致性审查（FR-001~020 与 SC-001~007 覆盖核对，0 CRITICAL）；quickstart 全场景结论齐全（T214/T219/T223 已勾注）；`checklists/requirements.md` 收尾无未决项

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖，可立即开始（先处置 T197 在途改动）
- **Foundational (Phase 2)**: 依赖 Setup——**阻塞**全部用户故事（T199/T200 并行；T201/T202 依赖 T200 的字段存在）
- **User Stories (Phase 3+)**: 依赖 Foundational；按 US1 → US2 → US3 顺序推进（单人）
- **Polish**: 依赖全部故事完成

### User Story Dependencies

- **US1（P1）**: 依赖 Foundational；**不依赖 US2/US3**——引擎各自注册 MANIFEST 含 preset 数据，但预置端点仍是旧字典（新类型暂以 type_key 兜底显示），功能不受影响
- **US2（P2）**: 依赖 Foundational；契约测试动态遍历注册表，**US1 未完成亦可独立交付**（覆盖当时已注册类型）；信息卡对 US1 新类型自动生效（数据已在）
- **US3（P3）**: 依赖 Foundational（列与序列化）；呈现逻辑独立实现；**验收 V6 的真实失败展示依赖 US1 记账（T210）**——建议在 US1 后执行
- **跨故事共享触碰**（顺序执行，勿并行）：`backend/tests/contract/test_search_providers_api.py` 由 T202→T211→T217→T220 顺序扩展；`frontend/tests/search-providers.test.ts` 由 T212→T218→T221 顺序扩展；`SearchProviders.vue` 由 T212→T218→T221→T222 顺序触碰；`search_setup.py` 由 T202→T210→（各引擎任务的导入行）途经

### Within Each User Story

- 测试任务先写并确认**失败**（标注"红→绿"）；行为锁定测试（T202）书写即绿、失败则先修复上游
- `html_base`（T203）先行，T204–T208 各引擎依赖其基类；T209（DDG）独立于基类（保留既有独立实现，仅加固）
- 每完成一个任务立即提交一次（任务与其测试同提交；提交信息含任务 ID 并说明"为什么"——宪法工作流质量门）

### Parallel Opportunities

- Foundational：T199/T200 并行（不同文件）
- US1：T204–T208 可并行（各引擎=独立模块 + 独立契约测试文件 + 独立 fixtures 子目录；唯一共享触碰是 `search_setup.py` 各加一行导入——单行级，冲突可忽略）
- US2：T215/T216 并行（测试文件与三个适配器文件分离）
- US3：T220 与 T221–T222 后端/前端可分线
- Polish：T224 文档同步可与其他收尾并行

---

## Parallel Example: User Story 1 引擎族

```bash
# T203 完成后（同一消息并行发起，各自独立文件）：
Task: "Bing 适配器 + 契约测试 in backend/src/saler/providers/search/bing.py + backend/tests/contract/test_search_bing_html.py"      # T204
Task: "百度适配器 + 契约测试 in backend/src/saler/providers/search/baidu.py + backend/tests/contract/test_search_baidu_html.py"    # T205
Task: "Mojeek 适配器 + 契约测试 in backend/src/saler/providers/search/mojeek.py + backend/tests/contract/test_search_mojeek_html.py" # T206
Task: "Wikipedia 适配器 + 契约测试 in backend/src/saler/providers/search/wikipedia.py + backend/tests/contract/test_search_wikipedia.py" # T207
Task: "Google 适配器 + 契约测试 in backend/src/saler/providers/search/google.py + backend/tests/contract/test_search_google_html.py" # T208
```

---

## Implementation Strategy

### MVP First（US1）

1. Phase 1 Setup（T198）→ Phase 2 Foundational（T199–T202，关键——阻塞一切）
2. Phase 3 US1（T203–T214）
3. **停下验证**：quickstart V2/V3/V4/V5 独立验收
4. 可演示：零密钥用户直接获得六个免费检索渠道

### Incremental Delivery

1. Setup + Foundational → 基座就绪
2. US1 → 验证 → **MVP**（免费渠道可用）
3. US2 → 验证（开通指引一屏直达——付费用户转化路径）
4. US3 → 验证（风险透明——"放心用"形态）
5. Polish → 契约同步 + 全量回归 + `/speckit-analyze`

### Parallel Team Strategy

单人线性 T198→T225 即可；如需并行：A 线后端（T199→T201→T203→T204-Bing/205-百度）、B 线前端（T212→T218 预备）+ 契约测试并行（T215）；T213/T214 与 T219/T223 合流验收。

---

## Notes

- `[P]` = 不同文件、无未完成依赖，可并行；`[USx]` 标签用于追溯（Setup/Foundational/Polish 不带标签）
- 测试一律先失败再实现（宪法第 I 条）；行为锁定任务（T202）标注"书写即绿"，失败即表明上游回归
- 每个任务完成即提交（提交信息含任务 ID；如 `T204: Bing 网页解析渠道——ck/a 离线还原与静默 captcha 识别（为什么：最宽容免费引擎，先落地）`）
- 任务编号自 T198 起（T197 为在途 GTK 修正；提交前先处置 T198 前置）
- 已知共享文件顺序触碰（勿并行）：`test_search_providers_api.py`（T202/211/217/220）、`search-providers.test.ts`（T212/218/221）、`SearchProviders.vue`（T212/218/221/222）、`search_setup.py` 导入表（各引擎任务各加一行）
- 契约变更台账：本特性 contracts/search-channel-expansion-contract.md §7 要求同步 001 两份契约与 quickstart（T224）
- 研发须知（引擎纪律，全部落于契约 §4）：风控页/伪装页绝不写入数据；链接包装必须还原否则丢弃；合法空结果与拦截空结果分不清时按 `blocked` 保守处理；节流默认 2s+抖动（`params.interval_s` 可调）
- 网络现实声明：共享/数据中心出口被风控是已知现实（runte 教训），真实网络单引擎失败属预期呈现，不作为验收阻塞项；防脏数据与切换纪律由离线契约测试（T203–T209/T213）保证
- 避免：模糊任务、同文件并行冲突、破坏故事独立性的跨故事依赖（US2 的契约测试必须动态遍历注册表，不得写死 10 类型清单）
