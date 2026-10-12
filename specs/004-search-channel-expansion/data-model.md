# Phase 1 Data Model: 检索渠道扩展——密钥申请指引与免密钥搜索引擎

**Feature**: `004-search-channel-expansion` | **Date**: 2026-10-12 | 上游：[spec.md](spec.md) / [research.md](research.md)

本特性**不新增实体**：渠道类型预置从代码内更新为"随 manifest 注册的结构化元数据（不落库）"；`search_provider` 表为**加列迁移**（2 列，可空，无回填）；`SearchItem` 契约不变。

---

## 1. 渠道类型预置（Preset 元数据，随 manifest 注册，不落库）

来源：各适配器模块的 `ProviderManifest.preset`（约定：与适配器共置，见 research R8）。

| 字段 | 类型 | 含义 | 约束 |
| --- | --- | --- | --- |
| `display` | string | 界面显示名 | 取自 `manifest.display_name`（单一来源） |
| `endpoint` | string | 默认端点（界面展示/留空回退） | 非空 |
| `needs_key` | bool | 是否需要密钥 | **派生值**：`len(secret_fields) > 0`，不手写 |
| `note` | string | 额度/计费要点 | 需密钥类型必填 |
| `apply_url` | string \| null | 官方申请/密钥页 | **需密钥类型必须非空**（契约测试断言，支撑 FR-013/SC-005）；免密钥为 null |
| `access_mode` | `"official_api"` \| `"html"` | 接入方式 | 必填（FR-017 数据源） |
| `market` | string | 适用市场与定位 | 必填（FR-014；如"中文市场"/"独立索引"/"机构资料与佐证"） |
| `risk` | string | 条款/风控/合规提示 | **`html` 类型必填**（FR-020）；`official_api` 有条款限制时亦填 |

### 九个渠道类型的预置数据（定稿清单：3 需密钥 + 6 免密钥）

| type_key | display | access_mode | needs_key | apply_url | market（摘要） |
| --- | --- | --- | --- | --- | --- |
| `brave` | Brave Search | official_api | ✔ | `https://api-dashboard.search.brave.com/app/keys` | 全球；免费信用需绑卡、存储条款提示 |
| `serper` | Serper.dev（Google SERP） | official_api | ✔ | `https://serper.dev/dashboard` | 全球；注册赠 2,500 次（一次性） |
| `tavily` | Tavily（AI 检索） | official_api | ✔ | `https://app.tavily.com` | 全球；1,000 信用/月自动续 |
| `baidu_html` | 百度（网页解析） | html | ✖ | null | 中文市场；验证码频繁，合规责任自担 |
| `google_html` | Google（网页解析） | html | ✖ | null | 全球；**高风险**（JS 渲染门槛），尽力而为 |
| `bing_html` | Bing（网页解析） | html | ✖ | null | 全球；免费渠道首选（最宽容） |
| `mojeek_html` | Mojeek（网页解析） | html | ✖ | null | 英国独立索引/欧美补充 |
| `ddg_html` | DuckDuckGo（非官方兜底） | html | ✖ | null | 隐私场景/最后兜底（既有渠道，统一纳入） |
| `wikipedia` | Wikipedia（官方免费 API） | official_api | ✖ | null | 机构资料检索与佐证；命中具模糊性（note 内说明） |

> `official_api` 且 `needs_key=false` 即 Wikipedia（官方接口、免密钥）；前端"官方 API"标签不蕴含"需密钥"。

## 2. `search_provider` 行（既有表，+2 列）

| 列 | 类型 | 说明 |
| --- | --- | --- |
| （既有）`id/type_key/name/secret_encrypted/endpoint/priority/enabled/params/used_today/used_today_date/health/last_test_at/last_test_result` | — | 语义全部不变；`last_test_result` 仅承载**手动测试**明细 |
| `last_error_kind` **（新）** | String(20) \| null | 最近一次**失败尝试**的类别（`ErrorKind.value`）；测试与任务运行**同口径**写入；任一成功尝试清空 |
| `last_error_at` **（新）** | datetime \| null | 上述失败的 UTC 时间；随 `last_error_kind` 同写同清 |

**迁移**：单条 Alembic revision（`ALTER TABLE ADD COLUMN` ×2，可空、无回填、无反向依赖）。

### 健康状态机（health ∈ unknown / healthy / failing）

```text
unknown ──测试成功 或 任一成功尝试──▶ healthy
unknown ──测试失败 或 任一失败尝试──▶ failing   （写 last_error_kind/at）
healthy ──任一失败尝试──────────────▶ failing   （写 last_error_kind/at）
failing ──任一成功尝试──────────────▶ healthy   （清空 last_error_kind/at）
```

- 界面呈现："正常 / 异常 / 未测"沿用；`failing` 时附带最近失败原因标签（`last_error_kind` → 中文映射，见契约 §4）。
- `used_today` 记账：每次**实际发起的外呼**（含失败与链接还原跳转）+1；跨日重置（复用 sending 渠道语义）。渠道"测试"按钮同样计数。

## 3. `ErrorKind` 扩展（`providers/errors.py`）

| 值 | 含义 | 可重试 | 界面标签 |
| --- | --- | --- | --- |
| `PARSE` **（新）** | 页面结构变化/解析失败（网页端特有） | ✖（立即切换） | 解析失败 |
| `blocked`（既有） | 风控/验证页/软封禁 | ✖ | 风控封禁 |
| `rate_limit`（既有） | 限流（含 Retry-After） | ✔ | 限流 |
| `network` / `timeout`（既有） | 网络不可达/超时 | ✔ | 网络 |
| `auth`（既有） | 密钥无效（需密钥渠道） | ✖ | 密钥 |
| `quota`（既有） | 额度耗尽 | ✖ | 额度 |
| `server`（既有） | 对端 5xx | ✔ | 服务端 |

`RETRYABLE_KINDS` 变更：仅加入无新项（`PARSE` 不入；维持 `{RATE_LIMIT, TIMEOUT, NETWORK, SERVER}`）。

## 4. 搜索请求参数模型（`search()` 签名不变）

- 免密钥渠道遵循既有 `search(*, query, count, lang, country, timeout_s)`；
- `lang`：Wikipedia 映射语言子域（调用方提供时覆盖渠道 `params.lang`，默认 `en`）；百度忽略（中文默认）；Google/Bing/Mojeek 映射 `hl`/`setlang` 等（引擎支持时生效，不支持时忽略不报错——FR-011）；
- 渠道级 `params`（既有 JSON 列）：`interval_s`（节流覆盖，默认 2.0）、Wikipedia `lang`；新增类型工厂统一接收 `params` 字典。

## 5. 流量与数据流（无状态持久化以外的变更）

```text
任务/测试 ──▶ resolve_search_chain(db, config, session_factory)
                │ 为每行装配 _RecordingAdapter(inner=adapter, row_id, recorder)
                ▼
           SearchFailover（零改动）──▶ 逐渠道 search()
                │ 成功/失败
                ▼
           SearchStatsRecorder.record_attempt(row_id, ok, error)
                │ 短事务
                ▼
           search_provider 行：used_today / health / last_error_kind / last_error_at
```

- **不外泄**：`SearchItem`（title/url/snippet）仍是唯一对外结果形状；日志与报错按既有脱敏口径（密钥不入日志——免费渠道本就无密钥）。
