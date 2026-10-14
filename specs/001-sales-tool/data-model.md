# Data Model: 通用销售获客工具（本地桌面版）

**Feature**: `001-sales-tool` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

## 设计约定

- **存储形态**：单机 **SQLite**（开启 WAL 模式），位于用户数据目录内，随数据目录整体备份/迁移（FR-002/004/033）。
- **访问方式**：Python 后端经 ORM（SQLAlchemy 2.0）访问，schema 演进用 Alembic 迁移管理；字段类型保持可移植（TEXT/INTEGER/REAL/BOOLEAN），为未来 Web 版迁移 PostgreSQL 预留（仅此约束，不做多租户设计）。
- **主键**：各表整型自增主键；对外文件（导入/导出）以自然键（域名、查询词、邮箱值等）为准，不依赖内部 ID。
- **时间**：统一以 UTC 存储（ISO 8601 文本），界面按用户本地时区展示。
- **枚举**：以下枚举以字符串常量落库（不用数据库原生 enum），便于演进；新增值必须向后兼容。
- **语言/国家**：语言用 BCP-47/ISO 639-1（`en`、`ru`、`ar`…），国家用 ISO 3166-1 alpha-2（`ke`、`sa`…）。
- **删除策略**：业务对象默认"停用/归档"而非物理删除；仅任务日志与缓存允许清理。

## 实体总览

```text
种子知识库           线索与挖掘                营销内容              通道与计划
┌─────────────┐   ┌──────────────────┐   ┌────────────────┐   ┌────────────────┐
│ graph_node  │   │ crawl_job        │   │ content_theme  │   │ channel        │
│ node_term   │   │ domain ──hit──── │   │ content_variant│   │ campaign       │
│ graph_edge  │   │ company          │   │ content_version│   │ campaign_channel│
│ seed ──hit──│──▶│ contact          │   └────────────────┘   │ campaign_round │
│ validation_ │   │ suppression      │                        │ send_record    │
│  record     │   │ exclusion_rule   │                        └────────────────┘
└─────────────┘   └──────────────────┘
系统：llm_provider / search_provider / app_setting / operation_log / llm_call / backup_record / job
```

---

## A. 种子知识库（US1）

### A1. `graph_node` 图谱节点

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| node_type | TEXT | `product_line` 产品线 / `persona` 客户角色 / `market` 市场地区 / `org` 具名机构实体 |
| name | TEXT | 规范名称（中文或原文） |
| parent_id | INTEGER FK→graph_node, NULL | 层级：市场（大区→国家）、产品（类目→线） |
| region | TEXT NULL | 大区名（仅市场节点，用于筛选/统计，如"南亚"） |
| attributes | JSON | 类型相关属性（如机构实体的组织类型、官网） |
| confidence | REAL NULL | 置信度（0–1，AI/检索来源必填） |
| source | TEXT | `manual` / `llm` / `search` / `import` |
| evidence_url | TEXT NULL | 来源链接（校验佐证） |
| review_status | TEXT | `pending` / `approved` / `rejected`（AI 候选默认 pending，FR-012/014） |
| status | TEXT | `active` / `disabled` |
| created_at / updated_at | TEXT | |

**唯一约束**：`UNIQUE(node_type, name)`（同一类型内不重名）。

### A2. `node_term` 节点词表

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| node_id | INTEGER FK→graph_node | |
| lang | TEXT | 语言 |
| term | TEXT | 词条文本 |
| term_type | TEXT | `name` 规范名 / `alias` 别名 / `synonym` 同义词 / `term` 行业术语 |
| source | TEXT | `manual` / `llm`（中文母版翻译，FR-009）/ `search` / `import` |
| review_status | TEXT | `pending` / `approved` / `rejected` |

**唯一约束**：`UNIQUE(node_id, lang, term_type, term)`。

### A3. `graph_edge` 图谱关系

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| from_node_id / to_node_id | INTEGER FK | |
| relation_type | TEXT | `product_fit_persona` 产品线×客户角色适配（FR-008）/ `product_target_market` 产品重点市场 / `org_in_market` 机构归属市场 / `org_has_persona` 机构属于某客户角色 |
| source / review_status | TEXT | 同节点 |

**唯一约束**：`UNIQUE(from_node_id, to_node_id, relation_type)`。

### A4. `seed` 种子

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| query | TEXT | 搜索词/查询模板实例（**唯一**，FR-010） |
| lang | TEXT | 该搜索词使用的语言 |
| product_line_id / persona_id / market_id | INTEGER FK, NULL | 分类维度（产品线/客户角色/市场） |
| priority | INTEGER | 1 高 / 2 中 / 3 低 |
| batch | TEXT | 批次（如 `manual-1`、`llm-20261010-1`、`search-1`） |
| source_node_id | INTEGER FK→graph_node, NULL | 实体种子：由哪个具名机构实体生成（模板实例化追溯） |
| template | TEXT NULL | 源查询模板（如 `"<名称>" supplier registration`） |
| status | TEXT | `pending` / `running` / `done` / `invalid`（FR-015） |
| source | TEXT | `manual` / `llm` / `search` / `import` |
| confidence | REAL NULL | |
| review_status | TEXT | `pending` / `approved` / `rejected` |
| n_candidates | INTEGER | 产量：命中候选公司数（denormalized 计数，ingest 时重算） |
| n_contacts | INTEGER | 产量：产出联系方式数（同上） |
| note | TEXT NULL | |
| last_run_at | TEXT NULL | |
| created_at / updated_at | TEXT | |

**索引**：`status`、`(batch)`、`(product_line_id, persona_id, market_id)`、`(priority)`。

### A5. `domain_seed_hit` 种子命中（归因）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| domain_id | INTEGER FK→domain | |
| seed_id | INTEGER FK→seed | |
| job_id | INTEGER FK→job NULL | 哪次任务命中（通用任务台账，见 E6） |
| first_seen_at | TEXT | |

**唯一约束**：`UNIQUE(domain_id, seed_id)`。产量计数以此表 `COUNT(DISTINCT)` 校准（FR-015/016）。

### A6. `validation_record` 校验记录

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| target_type | TEXT | `seed` / `graph_node` |
| target_id | INTEGER | |
| provider | TEXT | 佐证来源（如 `wikipedia` / 用户配置的检索渠道） |
| status | TEXT | `found` / `not_found` / `ambiguous` / `error` |
| confidence | REAL NULL | |
| evidence_url | TEXT NULL | |
| checked_at | TEXT | |

追加式（保留历史），不覆盖（FR-014）。

---

## B. 线索与挖掘（US2）

### B1. `crawl_job` 挖掘任务

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT NULL | |
| scope | JSON | 种子范围（seed_ids 或筛选条件） |
| config | JSON | 任务快照：检索渠道、并发、频率、代理、单站页数上限等（FR-025） |
| status | TEXT | `queued` / `running` / `paused` / `completed` / `failed` / `cancelled`（FR-024/048 同款语义） |
| stats | JSON | `{targets, done, no_contact, failed, candidates, contacts}`（FR-026） |
| started_at / finished_at / created_at | TEXT | |

### B2. `domain` 候选域名

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| domain | TEXT | **唯一** |
| homepage_url | TEXT | 首次发现的 URL |
| title / snippet | TEXT | 检索结果摘录 |
| source | TEXT | 发现渠道（检索 provider 名 / 黄页名录 / 手工） |
| first_job_id | INTEGER FK NULL | |
| company_id | INTEGER FK→company, NULL | 归属公司（合并后回填） |
| status | TEXT | 抓取状态：`pending` / `fetching` / `done`（有联系信息）/ `no_contact` / `failed`（FR-024 断点续跑的状态机） |
| attempts | INTEGER | 重试计数 |
| last_error | TEXT NULL | |
| fetched_pages | INTEGER | 已抓页数 |
| country / country_source | TEXT NULL | 国家 + 来源（`cctld` / `query_market` / `address` / `phone_prefix` / `manual`） |
| language / language_source | TEXT NULL | 语言 + 来源（`html_lang` / `detect` / `manual`） |
| is_excluded / exclusion_reason | BOOLEAN / TEXT NULL | 排除规则命中（FR-023，单独存放不删） |
| created_at / updated_at / last_crawled_at | TEXT | |

**索引**：`status`、`is_excluded`、`company_id`、`country`。

### B3. `company` 客户/线索

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT NULL | 公司名（可后补） |
| country / language | TEXT NULL | 汇总自主要域名 |
| status | TEXT | `new` / `contacted` / `replied` / `won` / `lost` / `invalid`（FR-027/054） |
| is_excluded / exclusion_reason | BOOLEAN / TEXT NULL | 同行/供应商等（FR-023） |
| tags | JSON | 标签数组 |
| source | TEXT | `crawl` / `import` |
| note | TEXT NULL | |
| created_at / updated_at | TEXT | |

### B4. `contact` 联系方式

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| company_id | INTEGER FK | 必填 |
| domain_id | INTEGER FK NULL | 来源域名 |
| type | TEXT | `email` / `phone` / `whatsapp` / `facebook` / `linkedin` / `x` / `instagram` / `wechat` / `other`（FR-020，可扩展） |
| value | TEXT | 原值（清洗后展示值） |
| value_normalized | TEXT | 规范化值（邮箱小写、电话 E.164 尽量化、社媒句柄去 URL） |
| category | TEXT | `procurement` 采购 / `sales` 销售 / `general` 通用 / `other`（FR-021） |
| source_url | TEXT NULL | 来源页面（FR-021） |
| validity | TEXT | `valid` / `suspicious`（疑似无效，FR-021）/ `invalid` |
| is_primary | BOOLEAN | 主要联系方式标记 |
| created_at / updated_at | TEXT | |

**唯一约束**：`UNIQUE(company_id, type, value_normalized)` —— 同一公司内去重合并；同一邮箱出现在不同公司则各自保留（与既有实践一致）。

### B5. `suppression` 退订/黑名单

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| scope | TEXT | `email` / `phone` / `contact` / `company` / `domain` |
| target_value | TEXT | 规范化目标值（email 用邮箱值；company 用 id） |
| company_id / contact_id | INTEGER FK NULL | 关联 |
| reason | TEXT | `unsubscribed` / `bounced` / `manual` / `complaint` / `invalid` |
| source / note | TEXT NULL | |
| created_at | TEXT | |

**唯一约束**：`UNIQUE(scope, target_value)`。发送前统一经此表过滤（FR-051），导入时同样检查（FR-029）。

### B6. `exclusion_rule` 排除规则

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| rule_type | TEXT | `keyword` / `domain` / `list` |
| pattern | TEXT | 关键词、域名或值清单（JSON 数组） |
| enabled | BOOLEAN | |
| note | TEXT NULL | |
| created_at / updated_at | TEXT | |

---

## C. 营销内容（US4）

### C1. `content_theme` 内容主题

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT | **唯一** |
| content_type | TEXT | `email` / `sms` / `social_message` |
| master_lang | TEXT | 母版语言，默认 `zh`（澄清结论：中文母版） |
| description | TEXT NULL | 用途备注（如"首轮开发信/第二轮跟进"） |
| created_at / updated_at | TEXT | |

### C2. `content_variant` 语言版本

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| theme_id | INTEGER FK | |
| lang | TEXT | 语言 |
| parent_variant_id | INTEGER FK NULL | 血缘：由哪个母版/版本生成（中文母版为 NULL） |
| source | TEXT | `manual` / `llm_assisted`（辅助编写）/ `llm_translated`（翻译生成） |
| status | TEXT | `draft` / `review` / `published` / `archived`（FR-037；未发布不可被计划选用 FR-046） |
| current_version_id | INTEGER FK→content_version NULL | 当前版本指针 |
| created_at / updated_at | TEXT | |

**唯一约束**：`UNIQUE(theme_id, lang)`。

### C3. `content_version` 内容版本

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| variant_id | INTEGER FK | |
| version_no | INTEGER | 从 1 递增 |
| subject | TEXT NULL | 主题行（邮件适用） |
| body_md | TEXT | 正文（Markdown 源） |
| body_text / body_html | TEXT NULL | 渲染缓存（纯文本/HTML） |
| variables | JSON | 正文使用的变量名列表（如 `["company_name","contact_name"]`） |
| change_note | TEXT NULL | |
| created_by | TEXT | `user` / `llm` |
| created_at | TEXT | |

**唯一约束**：`UNIQUE(variant_id, version_no)`。
**恢复语义**：恢复历史版本 = 以旧版本内容创建新版本（version_no+1），保持审计链完整（FR-037）。

**变量占位规范**（契约见 contracts/data-exchange.md）：`{{company_name}}`、`{{contact_name}}`、`{{signature}}` 等；未识别变量在预览时高亮提示。

---

## D. 通道与营销计划（US5/US6）

### D1. `channel` 发送通道

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT | 唯一展示名（如"主发件箱-Alice"） |
| channel_type | TEXT | `email` / `sms` / `social`（social 为二期预留，v1 不可启用） |
| config | JSON | 非敏感配置：邮件（host/port/username/加密方式）、短信（服务商名/端点模板） |
| secret_encrypted | BLOB | 敏感凭证密文（授权码/短信 Secret），加密方案见 research.md；**任何日志/导出/界面均不解密回显**（FR-006） |
| identity | JSON | 发件人名称、签名、回复地址（邮件）；短信签名（FR-043） |
| daily_limit / rate_per_minute / concurrency | INTEGER | 发送限制（FR-042） |
| status | TEXT | `active` / `disabled` |
| health | TEXT | `unknown` / `healthy` / `failing`；last_check_at / last_check_result（FR-041） |
| used_today / used_today_date | INTEGER / TEXT | 日用量与重置日（FR-044） |
| total_sent | INTEGER | 累计发送 |
| created_at / updated_at | TEXT | |

### D2. `campaign` 营销计划

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT | |
| status | TEXT | `draft` / `running` / `paused` / `completed` / `cancelled`（FR-048） |
| audience | JSON | 人群定义：筛选条件（国家/语言/标签/来源种子/公司状态）+ 显式排除；执行时物化为 send_record（FR-046） |
| content_theme_id | INTEGER FK | 选用主题（须已发布） |
| lang_strategy | TEXT | `auto`（按客户语言匹配）/ `fixed` |
| fixed_lang / fallback_lang | TEXT NULL | 固定语言 / 回退语言（FR-036） |
| schedule | JSON | `{mode: immediate|scheduled, start_at, daily_max, interval_seconds}`（FR-046） |
| estimate | JSON | 创建时的影响范围预估快照（FR-047） |
| stats | JSON | `{planned, sent, failed, skipped, suppressed}` |
| created_at / started_at / finished_at | TEXT | |

### D3. `campaign_channel` 计划×通道

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| campaign_id / channel_id | INTEGER FK | |
| role | TEXT | `primary` / `backup`（失败可换通道，FR-048） |

**唯一约束**：`UNIQUE(campaign_id, channel_id)`。

### D4. `campaign_round` 跟进轮次

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| campaign_id | INTEGER FK | |
| round_no | INTEGER | 1=首轮，递增 |
| content_theme_id | INTEGER FK NULL | 该轮可选独立主题（跟进内容），NULL 则用计划主题 |
| interval_days | INTEGER NULL | 距上一轮完成后的间隔（FR-052） |
| condition | TEXT | `no_reply_or_progress`（默认：未获回复/进展标记者进入下一轮） |
| status | TEXT | `pending` / `running` / `done` / `cancelled` |
| stats | JSON | |
| started_at / finished_at | TEXT | |

**唯一约束**：`UNIQUE(campaign_id, round_no)`。

### D5. `send_record` 发送记录（计划人群 + 台账一体）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| campaign_id | INTEGER FK | |
| round_no | INTEGER | |
| company_id / contact_id | INTEGER FK | 收件对象 |
| contact_value | TEXT | 发送时联系方式快照（邮箱/手机号） |
| channel_id | INTEGER FK NULL | 实际使用通道 |
| content_variant_id / content_version_id | INTEGER FK NULL | 实际发送的内容版本（FR-049） |
| lang_used / fallback_used | TEXT / BOOLEAN | 实际语言与是否回退（FR-036） |
| status | TEXT | `pending` / `sent` / `failed` / `skipped` / `suppressed` / `bounced` |
| skip_reason | TEXT NULL | 如 `already_sent`（防重，FR-050）/ `suppressed` / `no_contact` |
| error_code / error_message | TEXT NULL | 失败原因（FR-048） |
| scheduled_at / sent_at / created_at | TEXT | |

**唯一约束**：`UNIQUE(campaign_id, round_no, contact_id)` —— 从数据层保证"同一客户同一轮次不重复发送"（FR-050）。
**注意**：本表即台账（FR-049），也是断点续发与进度统计（FR-048）的唯一事实来源。

---

## E. 系统表（US3）

### E1. `llm_provider` 大模型配置

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | |
| name | TEXT | 展示名 |
| provider_type | TEXT | `openai_compatible` / `anthropic` / `ollama`（具体支持清单见 research.md） |
| base_url | TEXT | 接入地址 |
| model | TEXT | 默认模型 |
| secret_encrypted | BLOB | API 密钥密文 |
| params | JSON | 温度等 |
| is_default | BOOLEAN | 默认服务 |
| health / last_test_at / last_test_result | TEXT | 连通性测试（FR-030） |
| created_at / updated_at | TEXT | |

### E2. `search_provider` 检索渠道（FR-019）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| type_key | TEXT | `brave` / `serper` / `tavily` / `custom_http`（适配器注册表见 contracts/provider-adapters.md） |
| name | TEXT | 展示名 |
| secret_encrypted | BLOB | API 密钥密文（FR-006） |
| endpoint | TEXT NULL | 自定义端点（custom 类型） |
| priority | INTEGER | 渠道调用顺序（failover，用户可调） |
| enabled | BOOLEAN | |
| params | JSON | 附加参数（结果数、地区/语言偏好） |
| used_today / used_today_date | INTEGER / TEXT | 渠道用量（对照各服务免费/付费额度） |
| health / last_test_at / last_test_result | TEXT | 连通性与限流状态 |
| created_at / updated_at | TEXT | |

### E3. `app_setting` 应用设置（KV）

`key`(PK)：`data_dir`、`proxy`、`ui_lang`、`content_fallback_lang`、`crawl_defaults`（并发/频率/robots 策略）、`send_defaults`、`backup` 等；`value` JSON。

### E4. `operation_log` 操作日志

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| ts | TEXT | |
| job_type | TEXT | `crawl` / `send` / `llm` / `import` / `export` / `backup` / `restore` / `system` |
| ref_type / ref_id | TEXT / INTEGER NULL | 关联对象（crawl_job / campaign / …） |
| level | TEXT | `info` / `warn` / `error` |
| message | TEXT | |
| payload | JSON NULL | 结构化细节（脱敏后） |

**索引**：`(ref_type, ref_id, ts)`、`(level, ts)`；容量策略：滚动保留（默认 30 天 / 50 万条，可配置）。

### E5. `backup_record` 备份记录

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| path | TEXT | 备份文件路径 |
| kind | TEXT | `manual` / `auto` |
| app_version / schema_version | TEXT | |
| size_bytes | INTEGER | |
| checksum | TEXT | |
| created_at | TEXT | |

### E6. `job` 通用任务（异步任务台账）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| job_type | TEXT | `ai_seed_expand` / `ai_seed_translate` / `ingest_harvest` / `seed_validate` / `crawl` / `send` … |
| name | TEXT NULL | 展示名 |
| status | TEXT | `queued` / `running` / `paused` / `completed` / `failed` / `cancelled` |
| params | JSON | 创建参数（请求快照） |
| progress | JSON | 最近一次进度（SSE 快照用） |
| result | JSON NULL | 终态结果 |
| error | TEXT NULL | 失败信息 |
| ref_type / ref_id | TEXT / INTEGER NULL | 关联领域对象（campaign / crawl_job 等） |
| started_at / finished_at | TEXT NULL | |
| created_at / updated_at | TEXT | |

> 说明：所有长任务（AI 扩充/翻译、回灌、校验、挖掘、发送）都在本表登记，
> 支撑 `contracts/local-api.md` 的 Job 模式（详情 / SSE / 暂停 / 恢复 / 取消）。
> `crawl_job` 保留为挖掘领域明细（scope/config/stats），与本表通过 ref 关联。

### E7. `llm_call` LLM 调用明细（逐次尝试的输入/输出/修复链/耗时/用量）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| ts | TEXT | |
| job_id | INTEGER NULL | 归属任务（无 FK；观测表随滚动清理独立于任务台账） |
| call_index | INTEGER | 同一任务内第几次模型调用（多语言循环逐语言一次；attempt=1 时自增） |
| phase | TEXT NULL | 任务层标注的调用上下文（如 `lang:en`） |
| operation | TEXT | `seed_expand` / `seed_translate` / `term_translate` / `content_draft` / `content_translate` |
| provider / model | TEXT | 调用时的服务商与模型 |
| attempt | INTEGER | 该次调用内的第几次尝试（>1 为 schema 修复重试） |
| ok | BOOLEAN | 该次尝试是否通过校验/成功 |
| error_kind / error_detail | TEXT NULL | 失败类别（ErrorKind.value）与细节 |
| request_messages | JSON | 实际发送的消息（system + user + 修复链累积对话） |
| response_text | TEXT NULL | 模型原始输出 |
| latency_ms | INTEGER NULL | 该次尝试耗时 |
| usage | JSON NULL | token 用量（服务商返回时记录） |

**索引**：`ts`、`job_id`、`operation`；容量策略：滚动保留（默认 30 天 / 1 万条，随启动维护清理）。
**用途**：分析 prompt 质量、修复率与多步编排需求（agent / 模板 / DAG 决策的数据基础）；查询见 `GET /ai/calls`。

---

## F. 状态机汇总

```text
seed.review_status:   pending → approved | rejected
seed.status:          pending → running → done | invalid ；invalid → pending（重开）
graph_node.review:    同 seed
domain.status:        pending → fetching → done | no_contact | failed ；failed → pending（重试）
company.status:       new → contacted → replied → won | lost ；任意 → invalid
content_variant:      draft → review → published → archived
                      编辑已发布 → 生成新 draft 版本；恢复历史版本 → 新版本号
campaign.status:      draft → running ⇄ paused → completed | cancelled
campaign_round.status:pending → running → done | cancelled
send_record.status:   pending → sent | failed | skipped | suppressed | bounced
                      failed → pending（重试）
channel.health:       unknown → healthy | failing（每次测试/发送后更新）
```

## G. 关键校验规则（服务层强制）

| # | 规则 | 来源 |
|---|---|---|
| 1 | `seed.query` 全局唯一；重复入库拒绝并提示 | FR-010 |
| 2 | `graph_node` 同类型不重名；合并操作需显式执行 | FR-011 |
| 3 | AI/检索来源的节点、词条、种子默认 `review_status=pending`，未批准不进正式执行队列 | FR-012/014 |
| 4 | `contact` 同公司同类型同值唯一；保存前做规范化（邮箱小写、句柄去 URL） | FR-021 |
| 5 | 发送前必查 `suppression` + `company.is_excluded` + `domain.is_excluded`，命中即 `suppressed`/`skipped` | FR-051/023 |
| 6 | 计划只能引用 `published` 内容版本；执行时把 `content_version_id` 冻结进 send_record | FR-037/046/049 |
| 7 | `send_record` 唯一键（campaign, round, contact）防重复发送 | FR-050 |
| 8 | 渠道日用量在跨日时按 `used_today_date` 重置；超限进入排队 | FR-042/048 |
| 9 | 凭证类字段只写不解密回显；导出与日志统一走脱敏序列化 | FR-006 |
| 10 | 语言匹配：客户语言 → 对应 variant；缺失则 fallback_lang 并标记 `fallback_used` | FR-036 |

## H. 索引与规模

- 目标规模（SC-007）：种子 ≥10,000 / 线索 ≥100,000，普通桌面硬件操作保持可用响应。
- 主要索引：`seed(status)`、`seed(batch)`、`domain(status, is_excluded)`、`domain(company_id)`、`contact(company_id, type)`、`contact(value_normalized)`、`send_record(campaign_id, round_no, status)`、`send_record(contact_id)`、`operation_log(ref_type, ref_id, ts)`。
- 列表搜索：`company.name` / `contact.value` 用普通索引 + LIKE 前缀；如性能不足，启用 SQLite **FTS5** 影子表（可后加，不改主 schema）。
- 批量写入（抓取回写、发送状态更新）走单事务批量提交（每 N 条或每 2 秒），WAL 下避免长事务。

## I. 数据目录布局与备份

```text
<数据目录>/                      # 用户可选（FR-033），默认按平台惯例
├── saler.db                     # SQLite（WAL）
├── secrets/                     # 加密密钥材料（如需口令派生）
├── backups/                     # 备份归档（saler-backup-YYYYmmdd-HHMMSS.zip）
├── exports/                     # 导出产物（线索表、计划报表、种子清单）
├── logs/                        # 应用运行日志（滚动）
└── cache/                       # 可选页面缓存（可随时清理）
```

备份归档格式与恢复校验流程详见 [contracts/data-exchange.md](contracts/data-exchange.md)。
