# Research: 技术选型与决策（Phase 0）

**Feature**: `001-sales-tool` | **Date**: 2026-10-10

本文件汇总 plan 阶段全部关键技术决策（决策 / 理由 / 备选评估）。其中桌面壳、大模型接入、检索渠道三项由三个研究代理经联网调研（2026-10 现状）产出，其余由设计推导。所有 NEEDS CLARIFICATION 均已解决。

---

## 1. 桌面应用形态

**Decision**: **pywebview + 内嵌 FastAPI（uvicorn）+ PyInstaller `--onedir` 打包**。

**Rationale**：
- 单语言工具链（纯 Python 团队零新增成本），Vue 构建产物内嵌，包体约 25–40 MB、首启 2–4s，对本地优先工具完全够用。
- 原生 webview（Windows WebView2 系统自带 / macOS WKWebView / Linux WebKitGTK），配合"本地 API + SSE"通信（见 §3），未来 Web 版可原样复用后端。
- 规避 Electron 的 ~100–150MB 双运行时与双份签名面。

**Alternatives considered**：
- **Electron + Python sidecar**：生态最成熟、渲染最一致，但包体/内存大、签名面大——留作保底选项。
- **Tauri 2 + Python sidecar**：启动 ~0.3s、壳 ~15MB，2026 年已有生产案例；但引入 Rust 工具链与 sidecar 生命周期工程（僵尸进程、代理拦截 loopback、PATH 缺失、端口协商），收益（启动速度）对本地工具非关键——**列为后续迁移目标**（FastAPI 面保持纯 HTTP+SSE 即可平滑迁移）。
- **Wails v3（Go）/ Briefcase / NiceGUI native**：或引入第二语言栈，或与 Web SPA 前端路线不匹配，排除。

**避坑清单（实现与发布必须执行）**：
- Linux：要求 WebKit2GTK ≥2.36，构建/文档区分 4.0（libsoup2）与 4.1（libsoup3）软件包；以 Ubuntu 22.04 为最低验证基线（20.04 过旧）；`GLib.GError: Failed to load web view` 需给出可操作错误提示。
- PyInstaller：用 `--onedir`（避免 onefile 的启动开销与 bootloader-PID 杀死子进程问题）；入口第一时间 `multiprocessing.freeze_support()`；为 uvicorn/fastapi/gi 配 hiddenimports；前端产物 `--add-data` 并以 `sys._MEIPASS` 解析；**冻结包必须冒烟**。
- 生命周期：绑定 `127.0.0.1:0` 由系统分配端口；开窗前轮询 `/health`；关窗即停服务并防孤儿进程。
- 签名公证（发布阶段）：macOS Developer ID + notarytool（inside-out 签名、G2 中间证书、解析 `status: Accepted`、DMG 拖拽安装）；Windows 用 Azure Trusted Signing（~$10/月）或接受 SmartScreen 预热，签名密钥需硬件持有。

## 2. 前端技术栈

**Decision**: **Vue 3 + TypeScript + Vite + Pinia + Vue Router + Element Plus + ECharts + vue-i18n（默认 zh-CN）**。

**Rationale**：Element Plus 是中文业务管理工具事实标准（表格/表单/复杂 CRUD 组件齐备，中文文档）；ECharts `graph` 序列直接支撑种子知识图谱可视化（数千节点、力导布局、按产量着色），与规格 FR-017 一一对应；Vite + TS 满足用户指定栈。

**Alternatives considered**：Naive UI / Ant Design Vue（均可行，生态与中文资料弱于 Element Plus）；图可视化备选 Cytoscape.js（交互更专，但 ECharts 已在同一依赖内覆盖需求）。

## 3. 前后端通信与任务进度

**Decision**: 本地 HTTP（FastAPI）+ **SSE** 推送任务进度；仅绑定回环 + 每次启动随机令牌（普通请求走 `X-App-Token` 头；SSE 因 EventSource 限制用 `?token=` 查询参数）。

**Rationale**：SSE 比 WebSocket 简单、自动重连、天然单向够用；实现范式：后台任务线程/任务 + 队列 + `sse-starlette` 的 `EventSourceResponse`（带节流 ~0.5s/1% 增量、30s keepalive、哨兵关闭；跨线程用 `loop.call_soon_threadsafe`；不要用 `run_in_executor` 包裹阻塞队列读）。契约见 contracts/local-api.md。

**Alternatives considered**：WebSocket（双向不必要）；pywebview 的 JS bridge（无法承载进度流与未来 Web 复用）。

## 4. 数据存储与迁移

**Decision**: **SQLite（WAL）+ SQLAlchemy 2.0 + Alembic**，单文件随数据目录整体迁移；字段类型保持可移植，为未来 Web 版 PostgreSQL 迁移预留。

**Rationale**：单用户本地应用，SQLite 零运维、备份=复制文件；Alembic 支撑"升级不丢数据"（FR-004）；既有行业项目已验证 SQLite 路线。数据形状详见 data-model.md。

**Alternatives considered**：裸 sqlite3（无迁移体系）；DuckDB（分析型，OLTP 不匹配）；内嵌 Postgres（重，无必要）。

## 5. 密钥与凭证安全

**Decision**: 凭证类字段（LLM 密钥、邮箱授权码、短信/检索密钥）**字段级加密（Fernet）+ 主密钥托管于 OS 钥匙串（`keyring`：Windows Credential Manager / macOS Keychain / Linux Secret Service）**；无钥匙串环境（部分 Linux 桌面）回退为"应用口令"（Argon2id 派生密钥）。界面脱敏、日志/导出统一走脱敏序列化（FR-006）。

**Rationale**：桌面端无服务器可保管密钥，OS 钥匙串是标准答案；口令回退保证无 Secret Service 的环境可用；备份默认不含凭据（可选口令再加密导出，见 contracts/data-exchange.md）。

**Alternatives considered**：整库 SQLCipher（密钥分发问题相同且更重）；明文存储（排除）。

## 6. 大模型接入

**Decision**: **自建薄适配层**——以官方 `openai` SDK 作传输（支持任意 `base_url`），统一 `chat/stream/list_models/test_connection`；为 Anthropic 留专用适配器（Messages API 差异大，作为首批之后的增量项）。不引入 LiteLLM（代理与 SDK 捆绑 ~28MB+，桌面端过重且结构化输出曾有多起缺陷）。

**首批 Provider（预置模板，均可自定义）**：

| Provider | Base URL | 备注 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com`（`/v1` 可选） | 标准端结构化输出为 `json_object`（仅保证 JSON 语法）；模型 ID 以 `GET /models` 实测为准，不硬编码 |
| Qwen / DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1`（国内）/ `dashscope-intl…`（国际） | 支持 `json_schema` strict；另有 qwen-mt 翻译接口可选用 |
| Moonshot / Kimi | `https://api.moonshot.ai/v1` 或 `api.moonshot.cn/v1` | `json_schema` 需裁剪为 MFJS 子集（不支持 pattern/oneOf 等）；`max_completion_tokens` 等差异以能力标记处理 |
| 通用 OpenAI 兼容（含 Ollama） | 任意 `base_url + key + model` | 新增服务商=新增一条配置，不改代码；Ollama 云端不强制 schema，按能力标记降级 |

**结构化输出工程实践（写进实现基线）**：
1. 永不信任 provider 的 schema 承诺——一律应用侧 Pydantic 校验（适配器契约见 contracts/provider-adapters.md）。
2. 按能力标记选择请求策略：`json_schema`（可信时）→ `json_object` + 强提示（含"json"字样、格式示例、充足 max_tokens）。
3. 校验失败重试 ≤2–3 次，把校验错误回传模型修复；传输层重试（429/5xx，指数退避）与格式重试分离统计。
4. 解析卫生：去 Markdown 围栏、取最外层 `{...}`/`[...]` 子串再解析。
5. 连接测试优先 `GET /models`，回退 1-token 探测；原样展示服务商错误文本（国内服务商的配额/实名/区域报错需可读）。
6. 遥测：按 provider/model 记录重试率；格式失败可重试、内容失败不重试。

**Alternatives considered**：LiteLLM（见上）；aisuite / llm / any-llm（轻但结构化输出与成熟度不足）；逐家官方 SDK（维护成本乘数）。

## 7. 检索渠道（搜索引擎接入）

**Decision**: 可插拔 SearchProvider 接口（contracts/provider-adapters.md），**首批支持 Brave / Serper.dev / Tavily**，用户配置多个渠道与优先级，按序故障转移。

**关键事实（2026-10 调研）**：
- **Bing Web Search API 已于 2025-08-11 退役**（新客户不可注册；替代品 Grounding 不返回原始 SERP）——不可依赖。
- **Google Programmable Search JSON API 已对新客户关闭，2027-01-01 全面停服**——不可依赖。
- Brave：有免费信用额度档（需绑卡，约 $5/月免费信用、$5/1K 次）；**ToS 对"存储结果/训练"有限制**，需向用户提示（本地线索缓存属于存储行为，建议用户阅读条款）。
- Serper.dev：注册即送 2,500 次、免绑卡，预付 $1/1K 起，接入最简。
- Tavily：每月 1,000 信用自动续、免绑卡；面向 AI 检索优化。
- DuckDuckGo html/lite：非官方端点，403/429/202 软封禁（202 会返回假正常页）——仅作最后兜底，慎用。

**故障转移策略**：按用户配置优先级调用 → 命中限流/封禁时指数退避 + 切换下一渠道 → 全部失败则暂停任务并提示配置新渠道；渠道用量（免费额度消耗）在 `search_provider` 表记录展示。

**Alternatives considered**：自建爬取 Google/Bing HTML（风控不可靠，既有项目经验已证明）；SerpApi 等更贵聚合器（可作 custom 类型接入）。

## 8. 邮件与短信发送

**Decision**：邮件走标准 SMTP（`aiosmtplib`），短信走"HTTP API + 用户自备凭证"的通用适配器（首批内置 1–2 家国内服务商模板 + 自定义端点）。发送层统一负责：suppression/exclusion 检查 → 内容版本渲染 → 通道配额与节奏（默认 20 条/分钟可配、每日上限）→ 写 `send_record`（契约见 provider-adapters.md）。

**Rationale**：用户已有邮箱+授权码工作方式（既有项目 smtp 直发 2000+ 封）；短信服务商按国内生态以模板+自定义覆盖，避免锁定单一厂商。

## 9. 抓取栈与礼貌策略

**Decision**：**httpx（异步、HTTP/2、代理支持）+ selectolax 解析**；联系方式抽取为"正则 + 规范化 + 分类"流水线（邮箱清洗、E.164 号码尝试、WhatsApp/社媒链接识别——借鉴既有项目 fix_email 等经验）；礼貌策略：默认并发 5、单站间隔 ≥1s、可配代理/UA、**robots.txt 默认遵循（可显式关闭，关闭时界面提示合规责任自担）**。

**Alternatives considered**：Scrapy（重、调度模型不适合增量单站任务）；Playwright/Selenium（JS 渲染兜底——v1 不做，控制包体；作为后续可选增强登记）。

## 10. 测试策略

**Decision**：后端 `pytest`（+`pytest-asyncio`、`respx` 模拟 HTTP）；前端 `vitest`；关键契约用**假 Provider 实现**（LLM/Search/Mail/SMS 四类 fake，离线可测）；集成测试以"临时数据目录 + 真实进程"跑任务全链路；发布前每平台**冻结包冒烟**（quickstart S1/S6/S10）。验收场景与规格 SC 的映射见 quickstart.md。

## 11. 打包、CI 与发布

**Decision**：GitHub Actions 三平台矩阵（win/mac/linux）：前端构建 → PyInstaller `--onedir` → 安装器（Inno Setup/NSIS；DMG 签名公证；AppImage/deb）。签名成本点：Windows Azure Trusted Signing ~$10/月（或 SmartScreen 预热）；macOS Developer ID $99/年。自动更新 v1 不做（提供"检查新版本"占位）。

## 12. 未决与后续（明确登记，不阻塞 v1）

- DeepSeek 模型 ID 存在来源冲突 → 实现时以 `GET /models` 实测为准（已写入 §6）。
- Anthropic 专用适配器：首批四个 provider 之后的增量项。
- Tauri 2 迁移：若启动速度/包体成为产品卖点再评估。
- JS 渲染兜底（Playwright）：作为"抓取增强"后续批次。
- robots.txt 默认策略与 Brave ToS 存储条款：发布前请用户复核（合规责任在用户，规格 Assumptions 已声明）。

## 主要来源（三项专题调研）

- 桌面壳与打包：[pywebview Linux 实现](https://deepwiki.com/r0x0r/pywebview/4.4-linux-implementation)、[pywebview 打包基准（pywebview vs Tauri）](https://raw.githubusercontent.com/XucroYuri/NewsSentry/refs/heads/master/docs/benchmark-tauri-vs-pywebview.md)、[Tauri 2 + Python sidecar 模板](https://github.com/dieharders/example-tauri-v2-python-server-sidecar)、[Electron+FastAPI 打包文档](https://gitlab.com/eaternity/firefly/-/blob/main/docs/build/DESKTOP-PACKAGING.md)
- LLM 接入：[DeepSeek API 文档](https://api-docs.deepseek.com/)、[DashScope OpenAI 兼容](https://help.aliyun.com/en/model-studio/compatibility-of-openai-with-dashscope)、[Moonshot/Kimi 平台文档](https://platform.kimi.ai/docs/)、[Thoughtworks Radar: structured output](https://www.thoughtworks.com/es-es/radar/techniques/structured-output-from-llms)
- 检索渠道：[Brave Search API](https://brave.com/search/api/)、[Serper.dev](https://serper.dev)、[Tavily](https://tavily.com)、[Google CSE 概览](https://developers.google.com/custom-search/v1/overview)、[Bing Search API（Microsoft Learn）](https://learn.microsoft.com/en-us/bing/search-apis/bing-web-search/overview)
