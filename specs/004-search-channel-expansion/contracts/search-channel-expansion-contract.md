# Phase 1 Contract: 检索渠道扩展——预置元数据、免密钥渠道与运行时记账

**Feature**: `004-search-channel-expansion` | **Date**: 2026-10-12 | 关联：[provider-adapters.md](../../001-sales-tool/contracts/provider-adapters.md) §2（检索适配器）、[local-api.md](../../001-sales-tool/contracts/local-api.md)（检索渠道节）——两份 001 契约按 §6 同步增补。

本文件定义本特性的五组契约增量：预置端点扩展、渠道类型值域、行级记账、错误与链接还原矩阵、前端呈现约定。**全部向后兼容**（既有字段/行为不变，仅新增）。

---

## 1. `GET /api/v1/search/presets` 响应扩展

| 项 | 约定 |
| --- | --- |
| 来源变更 | `presets` 从集中字典改为 **registry 派生**（`registry.by_kind("search")` 的 `manifest.preset`）——新增渠道类型无需改动本端点代码 |
| 既有字段 | `display`、`endpoint`、`needs_key`、`note` 保持存在且语义不变（`needs_key` 改为派生：`secret_fields` 非空） |
| 新增字段 | `apply_url`（string \| null）、`access_mode`（`"official_api"` \| `"html"`）、`market`（string）、`risk`（string） |
| 完整性约束 | 需密钥类型 `apply_url` 必须非空；`html` 类型 `risk` 必须非空（契约测试断言，见 §6） |
| `config_schemas` | 不变（仍是各 manifest 的 JSON Schema） |

```jsonc
// GET /api/v1/search/presets → 200（节选）
{
  "presets": {
    "brave": { "display": "Brave Search", "endpoint": "https://api.search.brave.com/res/v1",
               "needs_key": true, "note": "计量制 $5/千次；每月 $5 免费信用（需绑卡）",
               "apply_url": "https://api-dashboard.search.brave.com/app/keys",
               "access_mode": "official_api", "market": "全球", "risk": "ToS 对结果存储有限制…" },
    "bing_html": { "display": "Bing（网页解析）", "endpoint": "https://www.bing.com/search",
                   "needs_key": false, "note": "免密钥；免费渠道中最宽容",
                   "apply_url": null, "access_mode": "html", "market": "全球",
                   "risk": "非官方接入，受风控影响（验证页/地理重定向），合规责任自担" },
    "wikipedia": { "display": "Wikipedia（官方免费 API）", "endpoint": "https://en.wikipedia.org/w/api.php",
                   "needs_key": false, "note": "官方免密钥检索接口；结果具模糊性，定位为佐证",
                   "apply_url": null, "access_mode": "official_api", "market": "机构资料与佐证",
                   "risk": "命中可能为缩写/母公司等模糊匹配，不得用于自动否定" }
  },
  "config_schemas": { "...": "不变" }
}
```

## 2. 渠道类型值域（`POST /api/v1/search/providers` 校验）

| 项 | 约定 |
| --- | --- |
| 值域 | `registry.by_kind("search")` 全集的 `type_key`（含新增 `baidu_html`/`google_html`/`bing_html`/`mojeek_html`/`wikipedia`；原 `SEARCH_KINDS` 硬编码元组删除） |
| 未知类型 | 422 `unprocessable`（行为不变，报错文案沿用） |
| 免密钥类型 | 请求体携带 `api_key` 时**静默忽略**（不存储）；表单层不呈现密钥字段（见 §5） |
| 工厂装配 | 是否注入 `api_key` 由 `manifest.secret_fields` 空判定（删除 `type_key != "ddg_html"` 特判）；新类型统一接收 `params` 字典 |

## 3. Provider 行响应扩展与运行时记账语义

`GET/POST/PUT /api/v1/search/providers*` 行**新增两个字段**（其余字段不变）：

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `last_error_kind` | string \| null | 最近一次失败尝试的类别（`ErrorKind.value`）；**手动测试与任务运行同口径**；任一成功尝试清空 |
| `last_error_at` | ISO8601 \| null | 上述失败的 UTC 时间；与 `last_error_kind` 同写同清 |

记账语义（`SearchStatsRecorder.record_attempt`）：

- 每次**渠道调用尝试**（一次 `search()` 调用计一次，含失败；引擎内部形态回退/链接还原跟随跳转不重复计数）→ `used_today` +1（按日重置，对齐 sending 渠道 `ensure_used_today` 语义）；手动测试同样计数（一次测试计一次）;
- 成功 → `health="healthy"` 且清空 `last_error_kind/at`；
- 失败 → `health="failing"`，写 `last_error_kind`（`error.kind.value`）与 `last_error_at`；
- `last_test_result` 语义不变（仅手动测试写明细）；
- 装配方式：`resolve_search_chain(db, config, session_factory)` 返回以 `_RecordingAdapter` 包装的链——`SearchFailover` 接口与行为不变；`session_factory` 缺省时记账降级为 no-op（单元测试友好）。

## 4. 错误归类与链接还原矩阵（provider-adapters.md §2 增量）

### 4.1 风控/失败证据 → 归类 → 处置

| 引擎 | 失败证据（按落地页/正文判定，非状态码单判） | 归类 | 处置 |
| --- | --- | --- | --- |
| 百度 | wappass.baidu.com / verify.baidu.com 落地；"百度安全验证"标题；"网络不给力"；HTTP 480 | `blocked` | 退避 + 切换 |
| Google | `/sorry/index`；正文 "unusual traffic"/"not a robot"/中文"异常流量" | `blocked` | 退避 + 切换 |
| Bing | 静默 captcha（200 + `class="captcha"` + 0 结果）；"One last step" 插页；ensearch 重试后仍落 cn.bing.com；RSS 形态空结果经 HTML 复核无果（按 §4.2 判定） | `blocked` | 退避 + 切换 |
| DDG | 202（主页冒充）；403；`anomaly` 页；无结果链接的检测页 | `blocked` | 退避 + 切换 |
| Mojeek | 403 页面 | `blocked` | 退避 + 切换 |
| 全部 HTML | 结果容器**存在**但解析异常/条目结构不可读（页面改版） | `parse` | 立即切换（不重试同页）；容器**整体缺失**归 `blocked`（无法与软封禁区分，保守处理，见 §4.2） |
| Wikipedia | 429（+Retry-After） | `rate_limit` | 遵守 Retry-After |
| 全部 | 连接失败/超时 | `network`/`timeout` | 既有语义 |

### 4.2 空结果纪律（FR-009）

```text
0 条解析结果
 ├─ 命中风控/验证标记 ──▶ blocked（绝不写入数据）
 ├─ 页面结构正常、确无结果 ──▶ 合法空结果（返回 []，任务继续）
 └─ 结构异常（容器缺失等）──▶ blocked（疑似伪装页，宁误判失败）
```

### 4.3 链接还原（FR-004）

| 引擎 | 包装形态 | 还原法 | 失败处置 |
| --- | --- | --- | --- |
| 百度 | `baidu.com/link?url=…` | 结果块 `mu` 属性（备选 `data-landurl`）**离线**提取 | 丢弃该条 |
| Google | 旧式 `/url?q=`（离线解码）；新式 `/goto?url=<签名>` | `/goto` 逐条跟随一次 302（计入节流），读最终 URL | 丢弃该条 |
| Bing | RSS 形态（首选）：链接为直链无需解码；HTML 形态：`ck/a?…&u=a1<base64url>` | 剥 `a1` 前缀 → URL-safe base64 → UTF-8（先反转义 `&amp;`） | 丢弃该条 |
| DDG | `//duckduckgo.com/l/?uddg=` | `unquote(uddg)`（既有） | 丢弃该条 |
| Mojeek | 一般直链，个别包装 | 同法解码/跟随一次 | 丢弃该条 |

**通则**：包装链接 MUST NOT 作为结果 URL 或来源写入任何数据；无法还原 → 丢弃该条并计入解析异常（不改判整页失败）。

## 5. 前端呈现契约（`SearchProviders.vue`）

| 项 | 约定 |
| --- | --- |
| 密钥字段可见性 | `v-if="presets[form.type_key]?.needs_key"`（数据驱动，删除 ddg 特判）；免密钥类型显示"无需密钥"说明 |
| 渠道信息卡 | 添加/编辑对话框在类型选定后渲染：接入方式标签、申请地址按钮（`needs_key` 时；`el-link target="_blank"` 系统浏览器打开）、note、market、risk 全文 |
| 申请地址兜底 | 地址无效时用户仍可见"服务商名称 + 域名"文案自行检索（FR-016）；链接失效不得阻断保存 |
| 列表接入方式标签 | "类型"列以 `presets[type_key].access_mode` 渲染小标签：官方 API / 网页解析 |
| 失败原因呈现 | "健康"列 `failing` 时展示 `last_error_kind` 中文标签：`rate_limit`→限流、`blocked`→风控封禁、`parse`→解析失败、`network`/`timeout`→网络、`auth`→密钥、`quota`→额度；`null` → 仅"异常" |
| 指引文案 | 页面 alert 与 `crawl.py` 409 文案不得出现与 §2 值域矛盾的断言（如"某渠道均不可用"）；须区分"官方 API（稳定/需密钥）"与"免密钥网页渠道（尽力而为/受风控影响/自动兜底）" |

## 6. 契约测试锁定点（TDD 载体）

| 测试 | 断言 |
| --- | --- |
| `tests/contract/test_search_providers.py`（各引擎新类） | 解析（标题/链接/摘要）、链接还原（含 `&amp;`、`uddg`、`mu` 等样本）、风控样本 → 对应 `blocked`、结构异常样本 → `parse`、空结果纪律三分支 |
| `tests/contract/test_search_presets.py`（新增） | 值域 = 10 类型；需密钥 ⇒ `apply_url` 非空；`html` ⇒ `risk` 非空；`needs_key` 与 `secret_fields` 一致 |
| `tests/unit/test_search_stats.py`（新增） | 记账三分支（成功/失败/日切重置）；成功清空最近失败；`session_factory=None` no-op |
| `frontend/tests/search-providers.test.ts`（新增） | 密钥字段按 `needs_key` 显隐；申请地址渲染与缺失兜底；`last_error_kind` 中文映射全表 |

## 7. 001 同步要求（宪法"契约变更必须同步"）

| 目标 | 变更 |
| --- | --- |
| `specs/001-sales-tool/contracts/provider-adapters.md` | §2 检索：新增六 type_key 与接入方式；错误矩阵增 `parse`；`preset` 元数据约定；空结果纪律；链接还原通则 |
| `specs/001-sales-tool/contracts/local-api.md` | 检索渠道节：`/search/presets` 响应扩展字段表；provider 行 +`last_error_kind`/`last_error_at`；运行时记账语义一句 |
| `specs/001-sales-tool/quickstart.md` | S 场景补"免费检索渠道可作补充/兜底（004 增量）"一句 |
