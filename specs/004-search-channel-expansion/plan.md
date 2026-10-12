# Implementation Plan: 检索渠道扩展——密钥申请指引与免密钥搜索引擎

**Branch**: `004-search-channel-expansion` | **Date**: 2026-10-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-search-channel-expansion/spec.md`

## Summary

在既有可插拔检索渠道框架（001 FR-019 已交付）上完成两组能力：

1. **预置渠道元数据扩张**：每个渠道类型补充**官方密钥申请地址**、接入方式（官方 API / 网页解析）、适用市场与风险要点；前端"添加/编辑渠道"界面一屏呈现（FR-013~016）。
2. **六个免密钥渠道类型**：百度、Google、Bing、Mojeek（HTML 网页解析）与 Wikipedia（MediaWiki 官方免密钥接口，接入方式=官方 API）；既有 DuckDuckGo 兜底渠道纳入统一呈现并加固（FR-001~012）。全部沿用既有优先级故障转移链；落实"安全失败"纪律（风控页识别为失败、绝不写入数据）、新增 `parse` 错误类别、按尝试的运行时记账（用量/健康/最近失败原因，FR-006/018）与前端风险透明呈现（FR-017~020）。

**技术路线**：延续 httpx + selectolax（**不新增任何第三方依赖**）；`providers/search/` 增加 HTML 渠道共基类与各引擎适配器；预置元数据随 registry manifest 共置注册，`/search/presets` 由注册表派生——消灭路由 `SEARCH_KINDS` 硬编码与 `ddg_html` 特判（宪法"约定大于配置"）。决策依据与各引擎机制见 [research.md](research.md)。

## Technical Context

**Language/Version**: Python ≥ 3.12（后端）；TypeScript 5.x + Vue 3（前端）

**Primary Dependencies**: 既有栈——FastAPI、SQLAlchemy + Alembic、httpx、selectolax（lexbor）、pywebview、Element Plus。本特性**零新增依赖**（Wikipedia 走标准 HTTP JSON API；不引入 curl_cffi 等 TLS 指纹库，见 research.md R12）。

**Storage**: SQLite；Alembic 迁移：`search_provider` 表新增 `last_error_kind`、`last_error_at` 两列（nullable，支撑 FR-018）

**Testing**: pytest + respx（各引擎离线契约测试，页面样本固化为 fixture）；vitest（前端组件/逻辑）；集成测试延续"临时数据目录 + 假 Provider"模式；无真实网络依赖的 CI 可跑全集

**Target Platform**: Windows / macOS / Linux 桌面（pywebview 壳 + 本地 FastAPI + SPA）

**Project Type**: desktop-app（三段式单仓：backend / frontend / packaging）

**Performance Goals**: 渠道连通测试沿用 15s 超时；引擎级保守节流（默认 ≥2s 间隔 + 抖动，见 R12）；不劣化既有 10k 规模验收（本特性不触碰种子/线索查询路径）

**Constraints**: 礼貌抓取（间隔/并发沿用既有约束并加引擎级节流）；密钥零入库（免费渠道无密钥）；对外调用由用户主动触发且可见可控；合规提示前置于界面

**Scale/Scope**: 渠道类型 4 → 10（3 需密钥 + 7 免密钥）；单用户桌面、人工触发的小批量检索（每任务数十次引擎请求）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 要求摘要 | 本特性对照 | 结论 |
| --- | --- | --- | --- |
| I. 测试驱动开发 | 红→绿→重构；测试分层齐备 | 每个新引擎先行落失败契约测试（respx：解析/链接还原/风控样本→blocked/结构异常→parse/空结果纪律三分支）；预置完整性、记账单元、前端呈现各自先行测试；DDG 加固用例锁定既有行为 | PASS（按计划） |
| II. 对象与封装 | 领域对象建模；providers 不依赖外部框架与 DB | 新适配器实现 `SearchProvider` Protocol 并注册 manifest；`html_base` 共基类收敛共性；运行时记账经 `core/leads` 的 `_RecordingAdapter` 注入——`providers/` 零 DB 依赖、`SearchFailover` 零改动；前端只依赖本地 API 契约 | PASS（按计划） |
| III. 约定大于配置 | 契约同步；零配置发现；默认开箱即用 | 预置元数据随 manifest 共置于适配器模块；新增渠道=实现接口+注册 manifest，前端自动可见；`/search/presets` 与类型校验由 registry 派生；顺带清除 `SEARCH_KINDS` 硬编码与 `ddg_html` 特判；契约增量入本特性 contracts/ 并同步 001 两份契约 | PASS（按计划） |
| IV. 技术栈限定 | Python/TS+Vue 既定栈；依赖审查 | 零新增第三方依赖（Wikipedia 走标准 HTTP JSON；curl_cffi/Playwright 明确否决并登记再评估） | PASS（按计划） |
| V. 密钥零入库 | 凭证只运行时提供、加密存储、脱敏 | 免费渠道无密钥；`apply_url` 为公开信息非凭证；测试用假 Provider 与占位值；既有加密与脱敏机制不变 | PASS（按计划） |

**Phase 1 设计后复核**：research.md / data-model.md / contracts 未引入新违反项——关键复核点：① 两个新列仅存**错误类别与时间**（非凭证、无敏感载荷）；② 记账代理收在 `core/leads`，`providers/` 保持零 DB 依赖；③ 零新依赖决议贯穿各引擎方案；④ 测试锁定点矩阵（contract §6）覆盖全部 FR。**复核结论：PASS**。

## Complexity Tracking

> 无违宪项。本节不适用（若实现期出现必须的例外，按宪法 Governance 记录于此）。

## Project Structure

### Documentation (this feature)

```text
specs/004-search-channel-expansion/
├── plan.md              # 本文件（/speckit-plan 输出）
├── research.md          # Phase 0 输出：引擎机制、路线决策与依据
├── data-model.md        # Phase 1 输出：预置元数据、行级记账与状态机
├── quickstart.md        # Phase 1 输出：验证指南（V1~V6）
├── contracts/
│   └── search-channel-expansion-contract.md   # 本特性契约增量（预置端点/渠道清单/错误矩阵）
└── tasks.md             # Phase 2 输出（/speckit-tasks 生成，不在本阶段）
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/
│   └── xxxx_search_provider_error_columns.py   # +last_error_kind / +last_error_at
├── src/saler/
│   ├── providers/
│   │   ├── errors.py                  # +ErrorKind.PARSE（网页端解析失败）
│   │   ├── registry.py                # ProviderManifest +可选 preset 元数据字段
│   │   └── search/
│   │       ├── _common.py             # −SEARCH_PRESETS（迁至各 manifest）；+浏览器 UA 池
│   │       ├── html_base.py           # 新增：HTML 渠道共基类（节流/UA/hooks/安全失败编排）
│   │       ├── baidu.py               # 新增：baidu_html（mu 属性离线还原真实链接）
│   │       ├── google.py              # 新增：google_html（/url?q= 还原、sorry 检测）
│   │       ├── bing.py                # 新增：bing_html（ck/a base64url 还原、cn.bing.com 检测）
│   │       ├── mojeek.py              # 新增：mojeek_html（results-standard 解析、403 检测）
│   │       ├── wikipedia.py           # 新增：wikipedia（MediaWiki API、语言版本可配）
│   │       └── ddg_fallback.py        # 加固：浏览器 UA + Referer、纳入统一 preset 元数据
│   ├── core/leads/
│   │   ├── search_setup.py            # registry 驱动 kwargs（secret_fields 判定）；装配记账代理
│   │   └── search_stats.py            # 新增：按尝试记账（used_today 日期重置/health/最近失败）
│   ├── api/
│   │   ├── routes/search_providers.py # SEARCH_KINDS→registry；/search/presets 由 manifest 派生
│   │   ├── routes/crawl.py            # 409 文案更新（FR-019）
│   │   └── serializers.py             # +last_error_kind / +last_error_at
│   └── db/models/system.py            # SearchProvider +2 列
└── tests/
    ├── contract/
    │   ├── test_search_providers.py   # +各引擎类（解析/还原/风控/parse）；DDG 加固用例
    │   └── test_search_presets.py     # 新增：预置元数据完整性（申请地址/接入方式/必有字段）
    └── unit/
        ├── test_search_stats.py       # 新增：记账与日期重置
        └── fixtures/search_pages/     # 各引擎页面样本（合成/脱敏，固化形状）

frontend/
├── src/
│   ├── api/types.ts                   # Preset 与 SearchProviderRow 扩展
│   └── views/settings/SearchProviders.vue  # 信息卡/申请地址/接入方式标签/失败原因/指引更新
└── tests/
    └── search-providers.test.ts       # 新增：needs_key 判定、申请地址渲染、失败原因映射
```

**Structure Decision**: 沿用 001 三段式布局，纯增量与局部重构：适配器全部落在 `providers/search/`（新增共基类 `html_base.py` 收敛四个 HTML 引擎的节流/UA/风控识别重复逻辑）；DB 记账归属 `core/leads/`（providers 层保持无 DB 依赖）；预置元数据共置于各适配器 manifest 内，`/search/presets`、类型校验、前端表单全部由其派生。

## Phase 0 / Phase 1 关键决策摘要

（完整决策与依据见 [research.md](research.md)；数据形状见 [data-model.md](data-model.md)；接口增量见 [contracts/search-channel-expansion-contract.md](contracts/search-channel-expansion-contract.md)）

- **接入方式总表**：百度/Google/Bing/Mojeek/DuckDuckGo = 网页解析（非官方）；Wikipedia = 官方免密钥 API。Bing 官方 API 已退役、Google PSE 已对新客户关闭（001 research §7），网页途径是零成本访问的唯一方式——诚实定位为"尽力而为、安全失败"。
- **链接还原以离线解码为优先**：百度 `mu`/`data-landurl` 属性、Google 旧式 `/url?q=`、Bing `ck/a` 的 `u=a1<base64url>`、DDG `uddg=` 均离线还原；例外——Google 新式 `/goto?url=<签名>` 无法离线解析，仅在必要时逐条跟随一次 302（计入引擎节流），仍不可还原则丢弃该条（FR-004，宁缺毋污染）。
- **风控识别按页面证据（非状态码单判）**：百度安全验证/wappass、Google sorry 与 unusual traffic、Bing 验证页与 cn.bing.com 重定向、DDG 202 主页/403/anomaly 页、Mojeek 403；识别即失败（blocked），绝不写入数据；合法零结果与拦截空结果尽力区分、无法区分按失败。
- **运行时记账**：`SearchFailover` 不改——在 `core/leads` 以"记账代理"包装各渠道适配器（providers 层零侵入），每次实际调用记 `used_today`（含日期重置）、成功置健康、失败置异常并记录 `last_error_kind/at` 与原因明细；测试按钮与任务执行同口径。
- **节流与 UA**：HTML 渠道使用桌面浏览器 UA 池（轮换）+ `Accept-Language`，引擎实例级最小间隔（默认 2s + 随机抖动）；百度要求 UA 与 cookie（BAIDUID）配对；Wikipedia 使用描述性 UA（Wikimedia 政策）与 ≤1 req/s 礼貌节流。共享出口 IP 被风控是已知现实（runte 前身项目量产教训），界面明示风险、失败自动切换。
- **申请地址（官方）**：Brave = `https://api-dashboard.search.brave.com/app/keys`（旧 api.search.brave.com/app/keys 已 403）；Serper = `https://serper.dev/dashboard`（注册即见）；Tavily = `https://app.tavily.com`；含各档免费额度要点与"Brave 免费额度需绑卡"等提示（数据入 research.md R11）。
