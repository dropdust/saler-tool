# Phase 1 Contract: 前端主题（ui_theme）——设置键、HTML 入口注入与前端主题契约

**Feature**: `002-frontend-theme` | **Date**: 2026-10-11 | 关联：[local-api.md](../../001-sales-tool/contracts/local-api.md)（settings 节需同步增补）

本文件定义本特性的三组接口契约。契约 1 为既有本地 API 的**加性增量**；契约 2 为桌面壳/浏览器加载入口的**服务行为**；契约 3 为前端内部的**主题落地约定**。

---

## 1. 设置 API 增量（GET/PUT `/api/v1/settings`）

| 项 | 约定 |
|---|---|
| 键名 | `ui_theme` |
| 类型/值域 | string，枚举 `"light"` \| `"dark"` |
| 默认值 | `"light"`（`settings_service.DEFAULTS` 提供；无 KV 行时 GET 也返回） |
| PUT 校验 | 值不在值域内 → `400`，错误包 `{code:"bad_request", message:"ui_theme 仅支持 light/dark", details:null}`；不写库 |
| 读取归一 | 存储侧任何异常值（手工改库等）→ 对外一律呈现 `"light"` |
| 鉴权/错误包 | 与既有一致（`X-App-Token`；`{code,message,details}`），无新增机制 |

**示例**：
```jsonc
// GET /api/v1/settings → 200（节选）
{ "ui_lang": "zh-CN", "ui_theme": "dark", "proxy": "", ... }

// PUT /api/v1/settings  {"values": {"ui_theme": "light"}} → 200（返回全量设置）
// PUT /api/v1/settings  {"values": {"ui_theme": "blue"}}  → 400 bad_request
```

**001 同步要求**：实现时在 `specs/001-sales-tool/contracts/local-api.md` 的 settings 行补记 `ui_theme` 键与值域（宪法"契约变更必须同步"）。

## 2. HTML 入口服务行为（`GET /`，仅当存在前端产物时注册）

| 项 | 约定 |
|---|---|
| 路由 | 显式 `GET /`，注册于 StaticFiles("/") 挂载**之前**；仅当 `frontend_dist` 存在时注册（否则保持现状 404） |
| 响应体 | `frontend/dist/index.html` 内容；当 `ui_theme == "dark"` 时在 `<html …>` 起始标签注入 `class="dark"`（与既有 class 合并）；`light` 时原样返回 |
| 读取失败（DB 异常/KV 非法） | 归一/回退 `"light"` 原样返回，**不阻断**（FR-006）；非法值同样按 light |
| 注入未匹配（HTML 结构变化） | 原样返回 + warning 日志（降级：由前端 `syncFromServer` 校正） |
| 响应头 | `Cache-Control: no-store`（防止旧主题被缓存；每次窗口加载取当前值） |
| 鉴权 | 无（非 `/api/` 路径，与既有一致） |
| 静态资源 | `/assets/*` 等由 StaticFiles 原样服务，不受注入影响 |
| 边界（记录不处理） | 直接访问 `/index.html` 由 StaticFiles 原样返回（无注入）；客户端唯一入口为 `/`（hash 路由），无 SPA 深链 |

## 3. 前端主题契约（DOM 与样式约定）

| 项 | 约定 |
|---|---|
| 主题载体 | `<html class="dark">`；`styles/theme.css` 设置 `html{color-scheme:light}`、`html.dark{color-scheme:dark}` 与 `html,body` 基底（`--el-bg-color` / `--el-text-color-primary`） |
| 样式来源 | 组件样式只用 `--el-*` 变量；**禁止硬编码颜色**；新增自定义变量（图表边线、预览保真基底）统一在 `theme.css` 定义亮/暗双套 |
| 状态接口 | `stores/theme.ts`：`current`、`toggle()`、`syncFromServer()`；**唯一** DOM 类操作者；视图仅消费 |
| 图表（ECharts） | 颜色经 `theme/palette.ts` 读取 computed CSS 变量；主题变更时整图重渲（GraphView `watch`） |
| 内容保真（FR-010） | 营销内容预览容器（`VariantEditor` 预览区等）为**主题无关区**：固定"收件人视角"浅色基底（白底深字、固定边框），不随 `html.dark` 变化；用户图片素材不做任何反色/滤镜（FR-011） |
| 切换控件 | MainLayout 页头，全局一步可达，当前态可辨识（图标 + 无障碍标签），中文文案 |
