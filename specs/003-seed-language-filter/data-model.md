# Phase 1 Data Model: 种子列表语言筛选

**Feature**: `003-seed-language-filter` | **Date**: 2026-10-11 | 上游：[spec.md](spec.md) / [research.md](research.md)

本特性**零数据面变更**：无新表、无新列、无 alembic 迁移、无数据规范化；仅对既有 `seed.lang` 列增加"读取侧"的筛选与枚举语义。

---

## 既有实体：种子（Seed）

| 项 | 内容 |
|---|---|
| 相关列 | `seed.lang`（既有列：`String(10)`、NOT NULL、创建默认 `"en"`，见 `backend/src/saler/db/models/seeds.py`） |
| 取值来源 | 标准语言（前端统一语言表 `LANGS` 的 17 个代码）；批量导入/回灌可带入其他字符串（含大小写/空白差异） |
| 本特性作用 | 作为筛选维度**读取**；不写入、不修改、不迁移 |

## 派生结构：语言选项集合（Language Option Set，不落库）

筛选控件候选项 = `LANGS`（固定顺序，标签 `中文标签（code）`，如"俄语（ru）"）⊕ 后端 `GET /seeds/langs` 返回的、不在 `LANGS` 中的精确取值（标签 = 原值 code，按后端升序追加、去重）。

| 规则 | 约定 |
|---|---|
| 覆盖性 | 覆盖 `LANGS` 全部语言 + 库内全部实际取值 → "可见即可筛"（FR-001/006） |
| 匹配 | 选项值 = 存库原值；筛选为精确匹配（`EN` 与 `en` 为两个独立选项，互不混淆） |
| 标签 | `LANGS` 取值 → 统一中文标签（与建种/翻译处一致）；其他取值 → 原样 code |
| 空库 | `distinct(seed.lang)` 为空 → 选项 = `LANGS`（选择任一语言，结果为空态） |

## 筛选条件语义（列表查询参数组合）

- 语言条件与其他条件（`q`/`status`/`review_status`/`source`/`batch`/`market_id` 等）为 **AND 交集**；`total`、分页与 `items` 均为交集口径（FR-003）。
- 缺省/清除（空值）→ 不施加语言限制（FR-002/004）。
- 纯读：不产生任何 INSERT/UPDATE/DELETE，不触发对外调用（FR-009）。

## 不变量

1. `seed.lang` 的任何取值不被改写（无规范化迁移）。
2. 选项集合中"库内取值"部分与 `distinct(seed.lang)` 在加载时点始终一致（挂载时刷新；翻译完成后防御性刷新）。
3. 每次筛选的结果集 = 全库中满足全部已选条件的种子（无缓存偏差）；清除语言条件后恢复为与筛选前一致的完整结果。

## 与既有实体关系

- `seed` 表无结构变化；`domain_seed_hit`、`validation_record` 等关联表不受影响。
- 语言取值与图谱词表（`graph_node_term.lang`）、线索语言（`domain`/`company` 语言）无约束耦合，本特性不建立跨表语言一致性规则。
