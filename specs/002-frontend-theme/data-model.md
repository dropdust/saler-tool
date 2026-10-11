# Phase 1 Data Model: 应用前端主题（浅色 / 深色）

**Feature**: `002-frontend-theme` | **Date**: 2026-10-11 | 上游：[spec.md](spec.md) / [research.md](research.md)

本特性数据面极小：**1 个既有 KV 表的 1 个新增键**，无新表、无 alembic 迁移。

---

## 实体：主题偏好（Theme Preference）

| 项 | 内容 |
|---|---|
| 存储位置 | SQLite `app_setting` KV 表（既有表，001 FR-033 设置域） |
| 键 | `ui_theme`（string；注册进 `settings_service.DEFAULTS` 成为"已知键"） |
| 值 | 枚举 `"light"` \| `"dark"`（JSON 字符串） |
| 默认 | `"light"`（DEFAULTS 提供；无 KV 行时 GET /settings 与 HTML 注入均得 light） |
| 语义 | 单用户、设备级偏好；跨模块全局唯一；不随业务数据变化 |

### 校验与回退规则

| 场景 | 行为 |
|---|---|
| 无记录（全新/清空） | 默认 `light`（FR-006），不创建行 |
| PUT 写入非枚举值（如 `"blue"`、数字、null） | 后端值域校验拒绝 → 400 `bad_request`（`ui_theme 仅支持 light/dark`），不写库 |
| 存储侧非法值（手工改库/历史数据） | **读取侧归一**：非 `"dark"` 一律按 `"light"` 处理（HTML 注入与前端同步共用归一规则），不阻断启动（FR-006 Edge Case） |
| PUT 失败（服务不可用等） | 前端保留会话内已应用主题 + 错误提示；不写库、不回滚（R2） |

### 读写路径

```text
写：前端切换 → PUT /api/v1/settings {values:{ui_theme}} → app_setting UPSERT（首次切换创建行）
读①（持久化事实）：GET /api/v1/settings → 前端启动 syncFromServer / 设置数据面
读②（渲染事实）：后端 GET "/" → settings_service.get(db,"ui_theme","light") → 归一 → 注入 html.dark 类（no-store）
```

### 生命周期

- **创建**：首次切换主题时 upsert 行；此前仅默认值生效。
- **迁移**：随 `saler.db` 整库备份/恢复与数据目录迁移保留（复用 001 US3 备份/迁移能力，零额外实现；FR-012）。
- **删除**：无显式删除；随数据库/数据目录整体处置，清空后回归默认 light。

---

## 运行时状态机（DOM 主题态）

**状态**：`light` ⇄ `dark`。载体：`document.documentElement.classList` 含/不含 `dark`（EP 暗色约定；`theme.css` 同步 `color-scheme`）。

```text
启动：KV 值(归一) ──注入──▶ 首帧 DOM 类 ──syncFromServer(仅dev/异常校正)──▶ DOM 类
用户切换：toggle() ──同帧翻转 DOM 类──▶ PUT /settings ──成功──▶ KV 对齐
                                            └──失败──▶ 会话态保留 + 提示（KV 未变）
恢复/迁移后启动：KV 已含迁移值 ──注入──▶ 首帧即 dark（无中间态）
```

**转换规则**：
1. 启动：生产环境首帧状态 = 服务端注入值（FR-007/SC-005 由构造保证）；前端 `syncFromServer` 仅在 `userTouched === false` 且不一致时校正（dev 模式 / 注入降级场景）。
2. 切换：`toggle()` 同帧生效（FR-003），随后的 PUT 为异步持久化，不阻塞、不刷新、不丢表单状态（FR-004）。
3. 恢复/迁移：KV 即为事实源，无镜像对账逻辑。

**不变量**：
- 除 `ui_theme` KV 行外，主题操作不写任何业务数据、不触发对外调用（FR-013）。
- 任何非法/缺失数据下，系统默认 `light` 且不阻断启动（FR-006）。
- 任何视图不得直接操作 DOM 类（统一经 `stores/theme.ts`，R4）。

---

## 与既有实体关系

- `app_setting`：新增 1 键，无结构变化；与既有 `ui_lang` 等同属"界面偏好"族。
- 无新实体、无关系变更、无 alembic 迁移（`backend/alembic/` 无改动）。
