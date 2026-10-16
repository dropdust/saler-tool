# Contract: 本地 API（前端 ↔ 后端）

**Feature**: `001-sales-tool` | **Date**: 2026-10-10

前端（Vue 3 SPA，本地 webview 或浏览器承载）与 Python 后端之间的唯一接口，由后端在本机回环地址提供。
未来企业 Web 版沿用同一 API 语义（换传输与鉴权即可），因此本契约也承担"桌面版与 Web 版功能面一致"的职责。

## 通用约定

- **Base URL**：`http://127.0.0.1:<随机端口>/api/v1`（仅绑定回环地址，不监听外网）。
- **鉴权**：应用启动时后端生成一次性随机令牌，注入 webview 引导页；普通请求带 `X-App-Token` 头，校验失败返回 `401`；SSE（`/jobs/{id}/events`）因浏览器 EventSource 无法设置请求头，改以查询参数 `?token=` 传递（仅回环地址可访问，令牌每次启动轮换）。
- **格式**：请求/响应 `application/json; charset=utf-8`；时间一律 ISO 8601 UTC（`2026-10-10T06:00:00Z`）。
- **错误**：`{ "code": "<稳定错误码>", "message": "人类可读中文说明", "details": {...} }`；HTTP 状态语义化（400 参数、401 鉴权、404 不存在、409 冲突/重复、422 业务校验、500 内部）。
- **分页**：`?page=1&page_size=50` → `{ "items": [...], "total": 123, "page": 1, "page_size": 50 }`。
- **文件进出**：导入用 `POST`（multipart 或本地路径引用）；导出生成文件到 `exports/` 并返回 `{ "path": "..." }`。

## 长任务（Job）模式

爬取、发送、AI 批量生成、导入、备份等一律异步任务化（规格 FR-024/026/048/053）：

1. `POST /<operation>` → `202 { "job_id": 42 }`
2. `GET /jobs/{id}` → `{ "id": 42, "type": "crawl", "status": "running|queued|paused|completed|failed|cancelled|interrupted", "progress": {...}, "stats": {...}, "started_at": "...", "finished_at": null, "can_pause": true, "rerunnable": false }`
   - `interrupted`：进程退出遗留的非终态任务，**仅由启动对账写入**（区别于 failed=运行出错、cancelled=用户操作；005 增补）；
   - `can_pause`/`rerunnable`：任务类型能力（目录派生，前端据此渲染暂停/重跑按钮；005 增补）；
   - `params` **不进**响应负载（可能含整份名单内容）。
3. `GET /jobs/{id}/events` → **SSE** 流，事件：
   - `event: progress` — `{ "done": 120, "total": 500, "message": "抓取 example.com 联系页" }`；已终态任务订阅先发快照 `progress`，随即按状态分派终态事件后即断
   - `event: log` — `{ "level": "info|warn|error", "message": "..." }`
   - `event: done` — 仅 `completed`；其余终态 `event: error` — `{ "code": "job_failed|cancelled|interrupted", "message": "..." }`
4. `POST /jobs/{id}/pause|resume|cancel`（终态一律 409）
5. `POST /jobs/{id}/rerun` → `202 { "job_id": 57, ...starter 附加项 }`（005 增补）：
   仅对"已失败/已取消/已中断"的**可重跑类型**（`crawl`/`ingest_harvest`/`company_import`）；
   守卫三态 409——`not_rerunnable`（无 starter，附指引文案）/`not_terminal`/`already_completed`；
   重跑属用户主动操作（服务端绝不自动重放）；新任务不复制 `progress/result/error`

## 端点清单（按模块）

### 系统与设置（US3）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/PUT | `/settings` | 应用设置（数据目录、代理、界面语言、**界面主题 `ui_theme`（枚举 light/dark，默认 light，非法值 400；002 增补）**、回退语言、抓取/发送默认值） |
| POST | `/settings/data-dir/validate` | 校验目标目录可写、空间充足（FR-033） |
| POST | `/settings/data-dir/move` | 迁移数据目录 → job |
| POST | `/backups` | 生成备份归档 → job；GET `/backups` 列表 |
| POST | `/backups/validate` | 校验备份文件 | 
| POST | `/restore` | 恢复（先校验、再确认覆盖） → job |
| GET | `/logs?ref_type=&ref_id=&level=` | 查询操作日志（FR-026） |

### 大模型（US3）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/llm/providers`；PUT/DELETE `/llm/providers/{id}` | 通道管理式 CRUD；密钥只写不读回 |
| POST | `/llm/providers/{id}/test` | 连通性测试 → `{ok, detail}`（FR-030） |
| POST | `/ai/seeds/expand` | 知识图谱扩充种子：`{provider_id?, description?, from_node_ids?, count}` → job；产出一律**中文母版**（lang=zh）待审核，审核后经 `/ai/seeds/translate` 翻译为目标语言（FR-012①→②） |
| POST | `/ai/seeds/translate` | 中文种子/词表翻译：`{seed_ids|texts, targets:[lang]}` → job（FR-012/009） |
| POST | `/ai/content/draft` | 中文母版辅助编写：`{theme_id, brief, tone, length?}` → job，产出 draft 版本（FR-038） |
| POST | `/ai/content/translate` | 母版 → 目标语言版本：`{theme_id, master_variant_id, targets:[lang]}` → job（FR-038） |
| GET | `/ai/calls?job_id=&operation=&limit=&offset=` | LLM 调用明细（逐次尝试的输入/输出/修复链/耗时/用量；新→旧）→ `{total, items[]}`；`ok` 三态（`null` = 进行中：请求已发出、尚未返回）；`operation` 含 `prompt_assist`（006 辅助调用，`job_id` 为 null） |
| GET | `/ai/prompts` | 提示词模板库状态列表（006）：两功能 `{feature,label,customized,active_id,active_name,template_count}` 固定顺序 |
| GET | `/ai/prompts/{feature}` | 模板详情（006）：生效状态 + `templates[]` 全文 + 变量目录/保留槽位/固定段 + 上限；未知 feature → 404 |
| POST | `/ai/prompts/{feature}/templates` | 创建/另存为（006）：`{name, content, activate?}` → 201 详情 + `warnings[]`；名称/容量/内容规则 → 400（warnings 不阻断） |
| PUT | `/ai/prompts/{feature}/templates/{id}` | 更新内容/重命名（006）：`{name?, content?}`；未知 id → 404 |
| DELETE | `/ai/prompts/{feature}/templates/{id}` | 删除模板（006）：删除生效模板自动回退内置默认（模板库保留其余） |
| PUT | `/ai/prompts/{feature}/active` | 切换生效/恢复默认（006）：`{id \| null}`；null=切回内置默认；未知 id → 404 |
| POST | `/ai/prompts/{feature}/assist` | AI 辅助编写（006）：`{mode: generate\|polish, intent?, draft?}` → `{suggestion, notes}`；同步短调用（60s 时限），建议不入库，逐次尝试落 llm_call（`operation=prompt_assist`、`job_id=NULL`）；参数 400 / 未配置 409 `llm_not_configured` |
| — | 提示词语义 | 模板变量 `{name}` 精确替换、`{{...}}`（内容占位符）豁免；`{output_contract}` = 机器解析依赖的固定段槽位（不可编辑，缺失运行期自动补尾）；运行期在任务开始时定格生效模板；运行与辅助的完整提示词均可见于 `/ai/calls`（006 契约 §6/§7） |

### 种子知识库（US1）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/graph/nodes`；GET/PUT/DELETE `/graph/nodes/{id}` | 节点 CRUD；DELETE 为停用语义 |
| POST | `/graph/nodes/merge` | 合并重复节点 `{target_id, source_ids[]}` |
| GET/POST | `/graph/nodes/{id}/terms`；PUT/DELETE `/graph/terms/{id}` | 词表管理（FR-009） |
| GET/POST | `/graph/edges`；DELETE `/graph/edges/{id}` | 关系管理（FR-008） |
| GET | `/graph/overview?batch=&market=` | 可视化数据：节点/边 + 覆盖率与产量着色数据（FR-017） |
| GET/POST | `/seeds`（列表筛选含 `lang` 等组合条件；精确匹配，003）；PUT/DELETE(`停用`) `/seeds/{id}`；POST `/seeds/bulk` | 种子 CRUD 与批量（FR-010/011） |
| GET | `/seeds/stats?group_by=product_line|persona|market|batch` | 产量统计与排序（FR-015） |
| GET | `/seeds/langs` | 库内语言取值（语言筛选选项数据源，003；去重精确值、不折叠大小写） |
| POST | `/seeds/export` | `{filters, format: txt|csv}` → 导出执行清单（FR-016） |
| POST | `/seeds/ingest` | 回灌外部执行结果（格式见 data-exchange.md） → job（FR-016） |
| POST | `/seeds/validate` | 真实性/相关性校验 `{seed_ids|node_ids[]}` → job（FR-014） |
| GET | `/seeds/review-queue`；POST `/seeds/review` | 待审核队列与批量采纳/拒绝（FR-012） |

### 挖掘与线索（US2）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/crawl/jobs` | 启动挖掘：`{scope:{seed_ids\|filters}, config:{search_providers[], concurrency, rate, proxy, max_pages_per_site}}` → `{job_id, crawl_job_id}` |
| GET | `/crawl/jobs`；GET `/crawl/jobs/{id}` | 挖掘明细（领域台账）：`crawl_job.status` 与任务台账**全周期一致**（queued → running → completed/failed/cancelled；进程退出遗留由启动对账置 `interrupted`），`started_at/finished_at` 与状态同刻写入（005 增补，FR-019） |
| GET | `/domains?status=&country=&excluded=&q=` | 候选域名列表 |
| PUT | `/domains/{id}` | 人工修订（排除/恢复/改国家语言） |
| GET | `/companies?filters...`；PUT `/companies/{id}` | 线索列表与修订（状态/标签/名称，FR-027） |
| POST | `/companies/merge` | 同公司多域名合并 |
| GET | `/companies/{id}/contacts`；POST/PUT `/contacts[...]` | 联系方式管理与人工补录（FR-027） |
| POST | `/companies/import` | 导入名单（CSV/Excel 或本地路径） → job（FR-029） |
| POST | `/companies/export` | `{filters, fields[], format: csv|xlsx}` → 文件（FR-028） |
| GET/POST/PUT/DELETE | `/exclusion-rules[...]` | 排除规则；POST `/exclusion-rules/apply` 对存量线索重跑 → job（FR-023） |
| GET/POST/DELETE | `/suppressions[...]` | 退订/黑名单（FR-051） |

### 营销内容（US4）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/content/themes`；PUT/DELETE `/content/themes/{id}` | 内容主题 |
| GET/POST | `/content/themes/{id}/variants`；PUT `/content/variants/{id}` | 语言版本（FR-034/036） |
| GET/POST | `/content/variants/{id}/versions` | 版本列表/新版本（FR-037） |
| POST | `/content/variants/{id}/publish｜archive｜restore` | 状态流转；`restore {version_no}` 生成新版本 |
| POST | `/content/variants/{id}/preview` | 变量渲染预览 `{vars?|contact_id?}`（FR-039） |
| POST | `/content/variants/{id}/test-send` | `{channel_id, to}` 测试发送（FR-039） |

### 营销通道（US5）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/channels`；PUT/DELETE `/channels/{id}` | 通道 CRUD；`secret` 只写不读回（FR-006/040） |
| POST | `/channels/{id}/test` | 连通性测试 → `{ok, detail}`（FR-041） |
| GET | `/channels/{id}/usage` | 当日用量/额度/健康状态（FR-042/044） |
| GET | `/search/providers`；POST/PUT `/search/providers[...]`；POST `/search/providers/{id}/test` | 检索渠道配置与测试（FR-019）；行含 `last_error_kind/at`（最近失败；测试与任务同口径记账 `used_today`，004） |
| GET | `/search/presets` | 渠道预置元数据 `{presets, config_schemas}`——presets 字段：display/endpoint/needs_key（派生）/note/apply_url/access_mode/market/risk，由注册表派生（004） |

### 营销计划（US6）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/campaigns`；PUT/DELETE `/campaigns/{id}` | 计划 CRUD（FR-046） |
| POST | `/campaigns/{id}/estimate` | 影响范围预估 `{audience, content, channels}` → `{audience_count, message_count, by_lang, by_channel, eta}`（FR-047） |
| POST/GET | `/campaigns/{id}/rounds` | 跟进轮次配置（FR-052） |
| POST | `/campaigns/{id}/start｜pause｜resume｜cancel` | 执行控制（FR-048/053） |
| GET | `/campaigns/{id}/records?status=&round=` | 发送台账查询（FR-049） |
| POST | `/campaigns/{id}/records/retry` | 失败项重试 `{record_ids[]}` |
| POST | `/campaigns/{id}/test-send` | 试发：`{n, to_self:true}`（FR-053） |
| GET | `/campaigns/{id}/report`；POST `/campaigns/{id}/report/export` | 统计与导出（按通道/语言/轮次） |

### 任务与日志

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/jobs?type=&status=` | 任务列表；`status` 支持**逗号多值**（如 `running,paused,queued`），未知值 422（005 增补） |
| GET | `/jobs/{id}`；GET `/jobs/{id}/events`（SSE）；POST `/jobs/{id}/pause｜resume｜cancel` | 任务状态、事件流与控制（见「长任务（Job）模式」） |
| POST | `/jobs/{id}/rerun` | 重新运行失败/取消/中断的可重跑任务（005 增补，见「长任务（Job）模式」§5） |

## 兼容性约束

- API 一律模块化命名（`/campaigns`、`/seeds`…），供未来 Web 版直接复用；桌面特有端点（数据目录、备份、本地文件路径）单独命名空间，Web 版裁剪即可。
- 所有"路径"类参数在桌面版允许本机绝对路径；响应中回传的路径必须经过数据目录白名单校验。
- 契约变更采用加性演进：新增字段向后兼容；破坏性变更需提升 `/api/v2` 并同步前端。
