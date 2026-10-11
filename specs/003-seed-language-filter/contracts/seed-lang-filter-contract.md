# Phase 1 Contract: 种子语言筛选——列表查询、语言取值端点与前端筛选契约

**Feature**: `003-seed-language-filter` | **Date**: 2026-10-11 | 关联：[local-api.md](../../001-sales-tool/contracts/local-api.md)（种子知识库节需同步增补）

本文件定义本特性的三组接口契约。契约 1 为既有本地 API 参数的**正式化与行为锁定**；契约 2 为**新增加性端点**；契约 3 为前端筛选的**交互与纯查询约定**。

---

## 1. 列表查询增量：`GET /api/v1/seeds`（`lang` 参数正式化）

| 项 | 约定 |
|---|---|
| 参数 | `lang`（string，可选）——按存库原值**精确匹配**（`EN` ≠ `en`） |
| 缺省/空值 | 不施加语言限制（返回全部语言） |
| 组合语义 | 与 `q`/`status`/`review_status`/`source`/`batch`/`market_id`/`product_line_id`/`persona_id` **AND 交集**；`total`、分页与 `items` 均为交集口径 |
| 无匹配 | `items: []`、`total: 0`；`200`（非错误） |
| 副作用 | 纯读（FR-009）：不写库、不触发对外调用 |
| 鉴权/错误包 | 与既有完全一致（`X-App-Token`；`{code,message,details}`），无新增机制 |

**说明**：该参数在 001 实现中已存在（`api/routes/seeds.py` + `core/seeds/service.py`）；本契约将其**正式化**（补记于 001 local-api.md），并以契约测试锁定行为（FR-002/003 的可验证载体）。

```jsonc
// GET /api/v1/seeds?lang=ru&review_status=approved&page=1&page_size=50 → 200（节选）
{ "items": [ { "id": 7, "query": "арматура оптом", "lang": "ru", ... } ],
  "total": 128, "page": 1, "page_size": 50 }
```

## 2. 新增端点：`GET /api/v1/seeds/langs`

| 项 | 约定 |
|---|---|
| 响应 | `200`，JSON 字符串数组：库内 `seed.lang` 去重后的**精确取值**，升序；空库 → `[]` |
| 参数 | 无 |
| 副作用 | 纯读 |
| 路由声明位置 | **必须早于** `GET /seeds/{seed_id}`（与 `/seeds/stats`、`/seeds/review-queue` 同约定），否则 `langs` 会被解析为 `seed_id` |
| 鉴权/错误包 | 与既有一致，无新增机制 |

```jsonc
// GET /api/v1/seeds/langs → 200
["EN", "ar", "en", "ru", "zh"]
```

**语义要点**：返回值按存库原值给出（不做大小写折叠/去空白/别名归并），与契约 1 的精确匹配语义配对，共同保证"可见即可筛"（FR-006）。

## 3. 前端筛选契约（种子列表页）

| 项 | 约定 |
|---|---|
| 控件 | 筛选栏内单选 clearable 语言选择器（标签"语言"，与状态/审核/来源/批次同排）；未选择时明确呈现"未按语言筛选"占位 |
| 选项 | 由 `langFilterOptions(present)` 组装：`LANGS` 固定顺序（标签 `中文标签（code）`）＋库内非标准精确取值（原样 code）；标准语言恒在选项内（见 [data-model.md](../data-model.md)） |
| 选项刷新 | 随每次列表刷新（查询/翻页/操作后）同步重新拉取 `/seeds/langs`；选项与库内取值保持同步（新入库语言值立即可选，FR-006） |
| 生效时机 | 改动条件后点击"查询"生效（沿用本页既有交互，不即时自动查询）；搜索词回车同视为查询 |
| 页码 | "查询"动作统一将页码重置为 **第 1 页**；分页器翻页仅翻页、不重置条件（FR-008） |
| 清除 | 一步清除（clearable）："查询"后恢复未按语言过滤的结果，其他筛选条件取值不变（FR-004） |
| 空态 | 结果为空时表格显示明确空态文案（如"没有符合当前筛选条件的种子"）；不回退展示未过滤数据、不报错（FR-007） |
| 纯查询 | 单纯筛选不发起任何写请求（无 POST/PUT/DELETE）、不写本地设置/存储（FR-009） |
| 既有能力兼容 | 排序、翻页、勾选、翻译选中、编辑、失效在筛选结果内行为正常，操作后列表保持语言条件刷新（FR-010） |

## 4. 001 同步要求（宪法"契约变更必须同步"）

| 目标 | 变更 |
|---|---|
| `specs/001-sales-tool/contracts/local-api.md` | 种子知识库表增补 `GET /seeds/langs` 行；`GET/POST /seeds` 行说明补记"列表筛选参数族含 lang 等（003）" |
| `specs/001-sales-tool/quickstart.md` | S4 步骤补"在种子列表按语言筛选（003 增量）" |
