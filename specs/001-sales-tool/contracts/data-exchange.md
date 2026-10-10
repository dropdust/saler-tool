# Contract: 数据交换格式（导入 / 导出 / 回灌 / 备份）

**Feature**: `001-sales-tool` | **Date**: 2026-10-10

覆盖规格中全部"数据进出"场景：种子清单（FR-016/018）、外部收割回灌（FR-016）、线索导出（FR-028）、客户名单导入（FR-029）、内容变量（FR-035）、备份归档（FR-004/033）。所有格式带版本号，向后兼容只做加性演进。

## 1. 种子清单导出（执行用）

**txt（默认，供外部工具/人工执行）**：每行一条查询词，UTF-8 无 BOM；注释行以 `#` 开头（可含批次/优先级说明）。

```text
# batch=v4-graph priority<=2 exported=2026-10-10T06:00:00Z
"Kenya Power" supplier registration
"Kenya Power" contact
power line hardware distributor kenya
```

**csv（含完整元数据，供工具化流水线）**：列固定如下，顺序即契约：

```text
query,lang,priority,batch,product_line,persona,market,status,source,source_entity
```

导入（FR-018）：接受同构 csv；或仅含 `query` 一列的简表（其余留空）。规则：`query` 去重（与存量比较），命中重复整行跳过并在报告中列出；导入行默认 `status=pending`、`review_status=approved`（人工导入视为已审）。

## 2. 外部收割结果回灌（FR-016）

**主格式：JSONL**（每行一条查询的收割结果，键名前缀 `saler.` 便于识别）：

```json
{"saler.schema": "harvest_v1", "seed_query": "\"Kenya Power\" contact", "job_label": "v4-pilot",
 "harvested_at": "2026-10-10T06:00:00Z",
 "results": [{"url": "https://kplc.co.ke/contact", "title": "Contact Us", "snippet": "…"}]}
```

回灌动作（单个 job，事务批量提交）：
1. `seed_query` 未匹配到种子 → 该行进"未匹配清单"（不丢弃、可人工认领）；匹配到多条 → 拒绝并报错（种子 query 唯一）。
2. `results[].url` 提取域名 → 新建/复用 `domain(pending)`；写 `domain_seed_hit` 建立归因。
3. 该种子 `status → done`、`last_run_at` 更新；`n_candidates` 按 `domain_seed_hit` 重算。
4. 回灌报告：`{matched, unmatched_queries, new_domains, dup_domains, errors}`。

**备选格式：csv**：`query,url,title,snippet`，语义同上。

## 3. 线索导出（FR-028）

**csv / xlsx**，列（导出时可选字段，默认全选）：

```text
company_name, domain, country, language, company_status, tags,
contact_type, contact_value, contact_category, contact_validity, source_url,
excluded, note
```

- 一行一条"公司×联系方式"；无联系方式的公司导出公司行（contact 列留空）。
- Excel 版可选附加 Sheet：`被排除(同行/供应商)`、`统计`（按国家/语言/分类分布）——对齐既有工作习惯。
- 导出经 suppression 标注列（`unsubscribed=true`）以便外部工具同样避让。

## 4. 客户名单导入（FR-029）

csv / xlsx，表头允许以下别名（中文/英文均可识别，映射规则内置）：

| 契约字段 | 允许别名示例 |
|---|---|
| email | 邮箱、E-mail、Email |
| phone | 电话、手机、WhatsApp |
| company_name | 公司、企业名称、Company |
| domain | 域名、网站、Website |
| country | 国家、Country |
| language | 语言、使用语言、Language |
| tags | 标签、分类 |
| note | 备注 |

规则：`email` 与 `phone` 至少一列；匹配键**先 domain 后 email**（命中已有公司则仅补联系方式，不新建）；导入前查 suppression，命中则联系方式标 `validity=invalid` 并在报告列明；重复联系方式按 `UNIQUE(company_id, type, value_normalized)` 合并。导入报告：`{new_companies, merged_companies, new_contacts, dup_contacts, suppressed, errors}`。

## 5. 内容变量占位（FR-035）

- 语法：`{{variable_name}}`；解析、渲染、预览共用同一规则。
- 内置变量（后端提供清单，前端提示插入）：
  `{{company_name}}`、`{{contact_name}}`、`{{country}}`、`{{language}}`、`{{sender_name}}`、`{{signature}}`、`{{today}}` 等。
- 渲染规则：未知变量 → 渲染为空并在预览区高亮警告（阻断发布前提示）；已知变量缺值 → 空字符串并在预览警告；`{{signature}}` 来自通道身份配置。
- 版本冻结：`content_version` 保存变量清单快照；`send_record` 引用具体 `content_version_id`（台账可复算"当时发了什么"）。

## 6. 备份归档与恢复（FR-004/033）

**归档**：`saler-backup-YYYYmmdd-HHMMSS.zip`

```text
manifest.json
saler.db               # WAL checkpoint 后的单文件快照
secrets.bin            # 可选：导出凭据（默认不含；含则用用户口令派生密钥再加密）
exports/…              # 可选：随备份携带导出物（默认不含）
```

`manifest.json`：

```json
{
  "format": "saler-backup", "version": 1,
  "app_version": "0.1.0", "schema_version": "0007",
  "created_at": "2026-10-10T06:00:00Z",
  "db_sha256": "…", "db_bytes": 12345678,
  "includes_secrets": false
}
```

**恢复流程**：校验 zip 结构 → 校验 `manifest` 的 format/version/schema 兼容性 → 校验 `db_sha256` → 展示待恢复概览（数据规模/时间/是否含凭据）请用户确认 → 解压到临时目录、启动自检（迁移到当前 schema）→ 原子替换（旧数据目录先整体改名保留，失败自动回滚）。校验失败不触碰现有数据（Edge Cases）。

**数据资产全量导出（未来 Web 版迁移预留，FR-004）**：`export/manifest.json` + 每实体一个 `*.csv`/`*.jsonl`（表名=文件名，含 `schema_version`），字段与 data-model.md 对齐；作为脱离本应用的开放格式出口。

## 7. 兼容性规则

- 所有格式带 `version`/`schema` 标识；读取方遇到未知字段忽略、遇到未知版本明确报错。
- 加性演进优先；删除/改名列时旧名保留至少一个次要版本并在导入映射中继续识别。
- 导出文件在 `exports/` 下生成，文件名含时间戳；导入报告与回灌报告都会写入 `operation_log`（可追溯，FR-026）。
