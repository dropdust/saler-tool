# Phase 0 Research: 检索渠道扩展——密钥申请指引与免密钥搜索引擎

**Feature**: `004-search-channel-expansion` | **Date**: 2026-10-12 | 上游：[spec.md](spec.md) / [plan.md](plan.md)

技术上下文的未知项均在编写本文件前解析完毕（**无遗留 NEEDS CLARIFICATION**）。调研渠道：① SERP 抓取机制联网调研（百度 / Google+Bing 两路）；② 服务商申请地址与免费接口联网核实（Brave/Serper/Tavily/Mojeek/Wikipedia/DDG）；③ 前身项目 runte 代码侦察（可移植经验与量产教训）。**声明**：各引擎页面结构与风控策略具有强时效性（本调研截至 2026-10-12），实现时以固化 fixture 观测为准，运行期以"安全失败"纪律兜底。

---

## R1 总体路线：六引擎接入方式总表

| 引擎 | type_key | 接入方式 | 端点/请求要点 | 链接还原 | 风控识别（判失败） | 市场定位 |
| --- | --- | --- | --- | --- | --- | --- |
| 百度 | `baidu_html` | 网页解析 | `www.baidu.com/s?wd=&pn=&rn=&ie=utf-8`；桌面 Chrome UA 实际必需 | `mu="..."`（备选 `data-landurl`）属性**离线**还原，不跟随 `link?url=` | 落地 wappass.baidu.com / verify.baidu.com、"百度安全验证"标题、"网络不给力"、HTTP 480 | 中文市场 |
| Google | `google_html` | 网页解析 | `www.google.com/search?q=&hl=&gl=&start=&pws=0`；`num=` 自约 2025-09 失效（固定 10 条/页）；consent 用 `CONSENT`/`SOCS` cookie | 旧式 `/url?q=` **离线**解码；新式 `/goto?url=<签名>` 无法离线解析 → 必要时逐条跟随 302（计入节流），不可还原即丢弃 | `/sorry/index` 跳转；HTTP 200 验证页（正文含 "unusual traffic"/中文"异常流量"）——按正文嗅探，不靠状态码；429 | 全球（高风险：2025 起纯 HTML 成功率不稳） |
| Bing | `bing_html` | 网页解析 | **RSS 形态首选**：`www.bing.com/search?q=&format=rss&mkt=en-US&setlang=en`（免反爬标记、链接直链；约 10 条上限、无分页）；**HTML 形态回退**：`?q=&count=&first=&mkt=en-US&cc=US&ensearch=1`（+cookie `ENSEARCH=BENVER=1`） | RSS 直链；HTML 形态 `ck/a` 的 `u=a1<base64url>` **离线**解码（先反转义 `&amp;`） | 静默 captcha（HTTP 200、`class="captcha"`、0 结果）、"One last step" 插页、cn.bing.com 地理重定向 | 全球（三大引擎中最宽容，免费渠道首选） |
| DuckDuckGo | `ddg_html` | 网页解析（既有） | `html.duckduckgo.com/html/`（既有实现） | `uddg=` 解码（既有） | 202（主页冒充成功）、403、`anomaly` 页、无结果链接的检测页（既有实现已覆盖前两类） | 隐私场景 / 最后兜底 |
| Mojeek | `mojeek_html` | 网页解析 | `www.mojeek.com/search?q=` | `a.ob` 直链；个别包装跳转按同法还原 | 403 Forbidden（title 判定） | 英国独立索引、欧美补充 |
| Wikipedia | `wikipedia` | **官方免密钥 API** | `{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch=&srlimit=&srprop=snippet&format=json&formatversion=2` | 不适用（`/wiki/{title}` 直接构造） | 429 + Retry-After（礼貌节流下罕见） | 机构资料检索与佐证（条目粒度） |

---

## R2 百度：`mu` 属性离线还原 + cookie/UA 配对 + 安全验证识别

**Decision**: 网页解析接入。请求带桌面 Chrome UA 与 `Accept-Language: zh-CN`；**首次 GET 首页种 cookie（BAIDUID）并持久化于渠道实例的 cookie jar**（`ab` cookie 由 UA 派生，UA 与 cookie 必须配对、不可轮换）；结果解析 `#content_left` 下 `.result`/`.c-container`（含 `.result-op`），标题 `h3 a`，摘要优先 `.c-abstract`（哈希后缀类名轮换，属性/语义选择器优先），跳过广告（`data-tuiguang`、`data-cs='ad'`、`"广告"` 文本）。**链接还原用结果块 `mu` 属性（备选 `data-landurl`）离线完成**，绝不逐条跟随 `link?url=`（请求放大 ×N、链接有时效）。风控识别：最终落地域名 wappass.baidu.com / verify.baidu.com、页面标题含"百度安全验证"、"网络不给力"文案、HTTP 480——**按落地页与正文判定，不按状态码单独判定**。识别即 `blocked` 失败。

**Rationale**: 百度无面向公众的免费搜索 API（官方开发接口需中国大陆手机号等门槛）；`mu` 属性是当前抓取社区的通行离线还原法，彻底规避每结果一次跳转请求。BAIDUID/UA 配对是低成本的风控规避（非规避检测本身，而是满足其会话一致性预期）。

**Alternatives considered**:
- 逐条跟随 `link?url=` 302——每结果 +1 请求、放大封禁面、链接过期——否决；
- `curl_cffi`（TLS/JA3 指纹模拟）——新增重依赖，宪法 IV 纪律下否决；登记为"若百度风控长期高频再评估"；
- 无 cookie 裸请求——检测触发率高——否决（保留一次首页 GET 的成本可接受）。

**边界声明**: 百度对抓取持否定条款立场（服务条款）；预设 risk 文案明示合规责任在用户（对齐既有口径）。数据中心 IP 与非中国大陆出口被质询的概率显著更高。

## R3 Google：双形态链接 + 正文嗅探风控 + 诚实定位

**Decision**: 网页解析接入（尽力而为）。请求 `q/hl/gl/start/pws=0`（不再使用失效的 `num`）；携带 `CONSENT=PENDING+987`、`SOCS=CAESHAgBEhIaAB` cookie 避开 EEA 同意插页。链接还原：旧式 `/url?q=<urlencoded>` 离线解码；出现新式 `/goto?url=<签名 token>` 时**仅在必要时逐条跟随一次 302**（受引擎节流与条数约束），仍不可还原则丢弃该条。风控识别：跳转 `/sorry/index`；页面对 HTTP 200 也按**正文嗅探**（"unusual traffic"、"not a robot"、中文"我们的系统检测到您的计算机网络中存在异常流量"）判 `blocked`；429 判 `rate_limit`。DOM：`#rso` / `div[data-hveid]`（比旧 `div.g` 耐久）取块，`a > h3` 取标题，`.VwiC3b`/`.st` 取摘要；广告多启发式过滤（`[data-text-ad]`、`#tads/#tadsb`、可见"Sponsored/赞助商链接"、`aclk` 链接）。

**Rationale**: Google 官方免密钥途径（PSE）已对新客户关闭（001 research §7），网页途径是唯一零成本方式；但 2025 年起 JS 渲染门槛提高、数据中心 IP 被重点标记——**纯 HTML 成功率的客观上限存在**，因此在预设文案与风险标签中明示"高风险、尽力而为"，并以自动切换兜底。不引入 Playwright 渲染（001 research §12 已登记为后续批次，避免包体与控制复杂度）。

**Alternatives considered**:
- 对本特性引入 JS 渲染——违反依赖纪律与包体约束——否决（后续独立评估）;
- 忽略 `/goto` 签名链接、原样保留转发 URL——会污染域名归属与去重（线索管线按目标域名聚合）——否决，宁丢弃该条（FR-004 边界情形）；
- 跟随 consent 插页——用 cookie 直达更省请求——否决跟随方案。

## R4 Bing：RSS 形态优先 + `ck/a` 离线解码 + 静默 captcha 检测 + cn 重定向处理

**Decision**: 网页解析接入，定位为**免费渠道首选**（三大引擎中最宽容）。**请求形态两级**：① **RSS 形态优先**——`?q=&format=rss&mkt=en-US&setlang=en`，免反爬标记、链接为直链（约 10 条上限、无分页、偶发空 XML）；② **HTML 形态回退**——`?q=&count=&first=&mkt=en-US&cc=US&ensearch=1` + cookie `ENSEARCH=BENVER=1`（`count=50` + `first=` 以低频次换深度）。**RSS 空结果不直接判合法空，转 HTML 形态复核后按空结果纪律判定**。链接还原：RSS 直链无需解码；HTML 形态 `/ck/a?...&u=a1<base64url>` 离线解码（剥 `a1` 前缀 → URL-safe base64 → UTF-8；解析前先反转义 `&amp;`）。风控识别：**先查 captcha 标记再判定空结果**——HTTP 200 且 0 个 `li.b_algo` 时，若页面含 `class="captcha"` 等验证痕迹 → `blocked`（静默 captcha 是实证失败模式）；"One last step" 插页同判；落地 cn.bing.com 时代 `ensearch` 重试一次，仍被地理重定向 → `blocked` 并提示检查代理出口。DOM：`li.b_algo` 块、`h2 a` 标题链接、`.b_caption p` 摘要（`.b_lineclamp` 不作首选）。

**Rationale**: Bing 官方 API 已于 2025-08 退役，网页是唯一免费途径；解码链路已由社区印证（含回归样例），离线可行性高。cn 重定向是中文网络环境的常态失败点，必须显式处理与提示（runte 的 `www4.bing.com` 重试仅"有时"有效——本实现保留一次重试但以失败提示为主路径）。**RSS 形态依据**：独立核实现行有效（2025–2026 多源在用——Rust `daedra` 的 Bing RSS 后端、多个无密钥检索技能；searx 的 bing 引擎历史同源）：同一索引、无挑战页、直链；其限制（≤10 条、无分页、偶发空 XML、引号查询易失效）由 HTML 回退覆盖（来源：webless 源码实测 + Bing RSS 多源核实，2026-10）。

**Alternatives considered**: 保留转发链接不作还原——污染域名归属——否决；依赖 `www4.bing.com` 硬切换——仅缓解——否决为唯一手段。

## R5 DuckDuckGo：既有渠道加固（统一纳入）

**Decision**: 保留既有 `ddg_html` 实现（GET html 端点 + 202/403/anomaly 三类软封禁检测），本特性做三项加固：① 请求头补桌面浏览器 UA + `Referer: https://duckduckgo.com/`（应对无结果链接的"检测页"形态）；② 0 结果时严格区分"anomaly 页/检测页"（`blocked`）与合法空结果（返回 `[]`，仅当页面结构正常且确无结果容器异常时）；③ `lite.duckduckgo.com/lite/` 作为同渠道内一次性回退形态（html 失败且判定为软封禁时不再重试，直接切换下一渠道——lite 仅作为解析形态选择，不追加重试风暴）。同时纳入统一 preset 元数据（access_mode=html、无需密钥、风险文案）。

**Rationale**: 2025/2026 生态资料显示 html 端点仍可用但对 UA/Referer 敏感（无浏览器头会得到约 14KB 检测页）；`lite` 端点被普遍认为更宽容。既有实现已覆盖最关键的防脏数据纪律（202 主页冒充），保持并小幅补齐即可。数据中心 IP 段存在整体软封禁风险（生态报告），`blocked` 归类与切换即正确处置。

**Alternatives considered**: 引入 `ddgs` 第三方库（其内部端点更易变、新依赖）——否决；新增独立 `ddg_lite` 渠道类型——渠道类型膨胀，同一引擎多形态收敛在一个适配器内更符合"用户心智=引擎"——否决。

## R6 Mojeek：HTML 路线（官方 API 无永久免费档）

**Decision**: 网页解析接入 `www.mojeek.com/search?q=`。解析 `ul.results-standard > li`；标题 `a.title`；链接 `a.ob` 的 `href`（直链为主，个别包装跳转按离线解码/必要时跟随一次）；摘要 `p.s`。风控识别：403 页面（title 判定）。预设 risk 注明：Mojeek 官方 Web Search API 为付费计量（Personal 档 £1/千次、1 q/s，**仅有试用额度**），如需高稳定性用户可自行申请——本渠道不绑定密钥。

**Rationale**: 官方 API 无永久免费档，不满足"免密钥"目标；网页端点结构稳定（社区选择器多年沿用），且 Mojeek 作为独立索引（非 Google/Bing 转售）对结果多样性有独到价值。

**Alternatives considered**: 官方 API 接入（需付费 → 变相成为第四个"需密钥"渠道，超出用户"免费搜索服务"的诉求）——否决，登记为可选后续。

## R7 Wikipedia：官方 API + 描述性 UA + 语言版本 + "旁证"定位

**Decision**: 走 MediaWiki 官方免密钥 JSON API：`action=query&list=search&srsearch=<q>&srlimit=<count,≤50>&srprop=snippet&format=json&formatversion=2`。**UA 使用描述性字符串 `SalerTool/<版本> (+项目主页)`**——Wikimedia UA 政策强制要求可识别 UA（匿名/伪造 UA 可能 403），项目主页地址实现时取自 README/包元数据。礼貌节流 ≤1 req/s（远低于匿名+UA 档 200 req/min 上限）。**语言版本为渠道配置项**（`params.lang`，默认 `en`，可 `zh` 等；`search()` 调用方给 `lang` 时覆盖）。结果 URL 直接构造 `https://{lang}.wikipedia.org/wiki/{title}`；`snippet` 为含标签 HTML 的片段 → 清洗为纯文本。429 尊重 `Retry-After`。

**Rationale**: Wikipedia 是六个目标中唯一具备官方免密钥接口的服务（性质=官方 API，稳定性预期最高）；条目粒度的结果适配"机构资料检索与佐证"场景（001 FR-014 校验流的外部公开来源）。

**关键警示（runte 实测教训）**: Wikipedia 搜索命中有**模糊性**——可能命中缩写、母公司、名称相近的无关条目（runte 实证："Murphy Group"→"Johnston & Murphy"）；「查不到 ≠ 机构为假」。渠道定位为佐证来源，**不得用于自动否定**；预设文案与实现注释均须携带此口径。

**Alternatives considered**: 网页版 Wikipedia 抓取——官方 API 完全免费且稳定，无抓取必要——否决；`lang` 固定单值——多市场用法需要，配置化成本极低——否决固定。

## R8 预置元数据并入 registry manifest（消灭三处硬编码）

**Decision**: `ProviderManifest` 增可选字段 `preset: dict | None`；search 渠道在各自适配器模块内共置填充：`endpoint`（默认端点展示值）、`note`（额度/计费要点）、`apply_url`（官方申请地址，免密钥为 `None`）、`access_mode`（`official_api` / `html`）、`market`（适用市场与定位）、`risk`（条款/风控/合规提示）；`needs_key` 由 `secret_fields` 派生（不再手写）。**删除 `_common.SEARCH_PRESETS`**；`GET /search/presets` 由 `registry.by_kind("search")` 派生；`POST /search/providers` 的 `type_key` 校验改为注册表值域（删除 `SEARCH_KINDS` 元组）；`search_setup.resolve_search_chain` 与路由 `_build_adapter` 的 `type_key != "ddg_html"` 特判改为 `secret_fields` 空判定。

**Rationale**: 宪法 III——"新增 Provider 只需实现接口并注册 manifest，不需要修改前端或其他模块"。现状存在三处硬编码（路由类型表、装配特判 ×2）与一处集中预置表，正是本特性要新增 6 个渠道类型时的爆炸点；共置后元数据与适配器永不漂移，前端零改动自动可见新类型。

**Alternatives considered**: 保留集中式 `SEARCH_PRESETS` 并继续双数据源——漂移风险与"改两处"成本——否决；独立 UI 元数据 YAML——离适配器更远且引新格式——否决。

## R9 运行时记账：代理包装 + 行级列（FR-006/018 的落地）

**Decision**: ① 迁移新增两列 `search_provider.last_error_kind: String(20) | None`、`last_error_at: datetime | None`；② 新增 `core/leads/search_stats.py`：`SearchStatsRecorder(session_factory)`，方法 `record_attempt(row_id, ok, error)`——`used_today` 按日重置累加（对齐 `sending/channel_service.ensure_used_today` 既有语义）、成功 → `health="healthy"` 且清空最近失败、失败 → `health="failing"` 并写 `last_error_kind/at`；③ 装配：`resolve_search_chain(db, config, session_factory)` 以 `_RecordingAdapter`（实现同一 Protocol）包装每个适配器，`SearchFailover` **零改动**、`providers/` 层**零 DB 依赖**；④ 测试按钮端点同口径（写 health/last_error_*，`last_test_result` 语义不变=测试明细）。

**Rationale**: FR-018 验收场景要求"某渠道连续被限流时列表可见最近失败原因"——必须覆盖任务运行时（不仅手动测试）。代理收在 `core/leads`，依赖倒置（providers 不知道 DB 的存在）；`SearchFailover` 保持纯编排，回归面最小。

**Alternatives considered**: `SearchFailover` 内嵌回调直连 DB session——providers 层侵入 DB、分层破坏——否决；任务结束批量回写——任务中途不可见且队列表实现更绕——否决。

## R10 错误分类扩展与"空结果"纪律

**Decision**: `ErrorKind` 新增 `PARSE = "parse"`（页面结构变化/解析失败；**不可重试**，立即切换下一渠道）。"0 结果"判定纪律（FR-009 落地）：**先查风控/验证标记**（依 R1~R6 各引擎证据）→ 有标记判 `blocked`；无标记且页面结构正常 → 合法空结果（返回 `[]`）；页面结构异常（结果容器缺失/整页不可解析）→ 判 `blocked`（疑似伪装页，沿用 DDG 防脏数据口径）。风控类（`blocked`）与限流类（`rate_limit`）的既有映射不变；`RETRYABLE_KINDS` 不含 `PARSE`/`BLOCKED`。

**Rationale**: 直接落实 FR-007/008/009；Bing"静默 captcha 返回 200 + 0 结果"是实证案例，证明"0 结果 ≠ 无结果"。宁可误判失败（切下一渠道），不得让验证页/伪装页以空结果形态蒙混过关。

**Alternatives considered**: 统一"0 结果即失败"——合法空结果被误报、用户体验与健康统计失真——否决；忽略 0 结果争议直接返回空——脏数据/静默失败风险——否决。

## R11 申请地址与免费档事实（2026-10-12 核实）

| 服务商 | apply_url（申请/密钥页） | 免费档要点 | 注意 |
| --- | --- | --- | --- |
| Brave | `https://api-dashboard.search.brave.com/app/keys` | 计量制约 $5/千次；**每月 $5 免费信用**；免费信用也需绑卡 | 旧地址 `api.search.brave.com/app/keys` 已 403（应用新址）；头 `X-Subscription-Token`（既有适配器已实现） |
| Serper.dev | `https://serper.dev/dashboard`（未登录引导登录/注册；注册无绑卡） | 注册赠 2,500 次（**一次性**，非每月） | 头 `X-API-KEY`（既有）；接入最简 |
| Tavily | `https://app.tavily.com`（登录后 API Keys 页） | 1,000 信用/月自动续、免绑卡 | 密钥 `tvly-` 前缀（既有）；另有 keyless 模式（见下） |
| 百度 / Google / Bing / Mojeek / DuckDuckGo / Wikipedia | 无需密钥（apply_url = null） | 免费网页/官方接口 | 预设显示"无需密钥"；Wikipedia 附官方 API 说明（note 内） |

**备注**: Tavily 于 2025+ 提供 keyless 免密钥模式（`X-Tavily-Access-Mode: keyless`，限流）——登记为**后续可选渠道候选**（不在本期六渠道范围内，避免范围蔓延）；`apply_url` 可能随服务商调整失效，界面以"服务商名+域名"兜底可读（FR-016）。

**主要来源**（联网核实）: Brave API Dashboard（n8n/CrewAI/ByteChef 文档多方互证）、serper.dev 多篇接入指南（CSDN/NPM/Qwen-Agent）、docs.tavily.com（Credits & Pricing / Keyless）、mojeek.com/services/search/web-search-api 及社区帖（free trial 与定价档）、Wikimedia UA Policy 与 Rate limits（foundation.wikimedia.org / mediawiki.org）、DDG 生态资料（rust_scrapling `is_duckduckgo_blocked`、agent-search-mcp learnings）。

## R12 节流、UA 与出口风险（含 runte 前身项目教训）

**Decision**: 新增 `providers/search/html_base.py` 共基类，收敛四个 HTML 引擎（百度/Google/Bing/Mojeek，DDG 选择性复用）的共性：① **引擎实例级最小请求间隔**——默认 2.0s + 0~1.5s 随机抖动，经渠道 `params.interval_s` 可调；链接还原的跟随请求同池计数；② **桌面浏览器 UA 池轮换**（Chrome/Win、Safari/Mac、Chrome/Linux，对齐 runte 经验），`Accept-Language` 按引擎（百度 `zh-CN`，其余 `en-US`）；③ **例外**——百度 UA 与 cookie 配对后**不再轮换**（R2）；Wikipedia 用描述性 UA（R7）；④ 代理沿用全局 `config.proxy`（既有配置与 `trust_env=False` 纪律不变）；⑤ `follow_redirects=True` 与超时沿用既有 `build_client` 约定。

**Rationale 与风险声明**: runte 量产教训——**共享代理（机场）出口下 Google/Bing/DDG 本地抓取全部被风控，最终量产改走服务端搜索**（runte README 原文记载）。这证明：本特性免费渠道的价值成立但**成功率受出口 IP 强烈约束**；产品必须（且规格已）承诺"尽力而为 + 安全失败 + 自动切换 + 可诊断"，而不是稳定可用。界面与预设 risk 文案如实呈现。默认间隔 2s 为桌面交互场景折中（runte 量产用 6–12s；渠道 `params` 可加大）。

**Alternatives considered**: 引入 `curl_cffi` TLS 指纹（百度/Google 风控对抗）——重依赖、宪法 IV 纪律——否决（登记再评估）；引入 Playwright JS 渲染——包体与控制复杂度——否决（001 §12 后续批次）；统一 6–12s 大间隔——桌面测试/小批量交互体验过差——否决为默认（可配置放大）。

## R13 前端呈现与指引更新（FR-013~020 的界面落地）

**Decision**: ① 添加/编辑对话框在渠道类型选定后渲染"渠道信息卡"：接入方式标签（官方 API / 网页解析）、需要密钥与否（`needs_key=false` → **隐藏密钥输入框**，删除 `form.type_key !== 'ddg_html'` 特判）、申请地址按钮（`el-link` + `target="_blank"`，沿用既有外链模式）、额度要点（note）、适用市场（market）、风险提示（risk）；编辑态同样可见（FR-015）。② 渠道列表"类型"列附接入方式小标签（FR-017）；"健康"列在 `failing` 时展示最近失败原因中文标签（映射：`rate_limit`→限流、`blocked`→风控封禁、`parse`→解析失败、`network`/`timeout`→网络、`auth`→密钥、`quota`→额度；数据源=新列 `last_error_kind`）（FR-018）。③ 页面指引 alert 重写：删除"Bing 已退役、Google PSE 已对新客户关闭，均不可用"的过时断言，改为两段式——官方 API 渠道（稳定、需密钥）与免密钥网页渠道（尽力而为、受风控影响、自动兜底）的定位说明（FR-019）；`crawl.py` 的 409 提示文案同步（不再枚举写死的渠道名）。④ 免密钥网页渠道显示"非官方接入、合规责任自担"提示（FR-020，沿用既有 DDG 口径）。

**Rationale**: FR-013~020 全部为界面/呈现层需求，逐条在此落位；删除的过时文案正是本特性要修正的"已过时结论"。

**Alternatives considered**: 信息卡放入单独"渠道百科"页面——多一跳、与"添加时就能看到"的诉求背离——否决；失败原因只存文本明细由前端解析——字符串协议脆弱——否决（新列结构化存储）。

## R14 001 契约同步清单（宪法"契约变更必须同步"）

| 目标 | 变更 |
| --- | --- |
| `specs/001-sales-tool/contracts/provider-adapters.md` | §2 检索——新增六个 type_key 与接入方式；错误矩阵增 `parse`；manifest `preset` 元数据约定；"空结果纪律" |
| `specs/001-sales-tool/contracts/local-api.md` | 检索渠道节——`GET /search/presets` 响应扩展字段；`GET /search/providers` 行 +`last_error_kind`/`last_error_at`；运行时记账语义 |
| `specs/001-sales-tool/quickstart.md` | S 场景（线索挖掘前置）补一句"免费渠道可选作补充/兜底（004 增量）" |
| `backend/src/saler/api/routes/crawl.py` | 409 文案更新（FR-019，随实现同步） |

## R15 webless（PyPI 0.1.0）评估——用户问询（2026-10-13）

**背景**: 用户问询"webless（Python 库）适合这个需求么？"。已直接检视 PyPI 包（下载 sdist 阅读全部 1,860 行源码 + PyPI JSON 元数据 + GitHub 仓库 API），结论如下。

**事实**: `webless` 0.1.0（2026-09-14 发布；`requires_python>=3.10`；唯一依赖 `httpx>=0.27`）——多引擎免密钥检索（DuckDuckGo lite/html、Mojeek、Bing、Wikipedia OpenSearch；wide 额外含 Marginalia、Hacker News）+ 排名融合（RRF + 查询词对齐加权）+ 页面转 Markdown 抓取（`fetch`）。纪律细节：非 200 一律判失败、解析为空判 `soft_block`、离线还原 DDG `uddg`/Bing `ck/a`、重试时轮换 UA、SSRF 防护（拒绝私网地址）。MIT 许可（sdist LICENSE 与 GitHub 均确认）。仓库 2026-09-13 建立、单作者、0 star/fork/issue。

**结论：暂不采纳为依赖/实现底座**，理由：

1. **覆盖缺口**——仅 4/6 引擎，无百度（中文市场核心）与 Google，恰是规格点名的两个；
2. **产品语义冲突**——融合并发模型（一次查询打全部引擎 + RRF 合并）与 FR-001/005/006 的"用户配置逐渠道优先级 + 顺序故障转移 + 逐渠道用量/健康记账"及既有渠道管理 UI 语义互斥；
3. **成熟度**——v0.1.0、单作者、发布仅约一月、无社区，宪法 IV"维护活跃度"评估不达作为桌面产品数据获取主干依赖的标准；
4. **纪律缺口（相对本契约）**——无引擎级节流、无百度 cookie/UA 配对、无 cn.bing.com 处理、Bing 仅靠"解析为空"兜底（无 captcha 标记扫描）、DDG 无 Referer。

**采纳的借鉴点（已并入本文件与任务）**:

- **Bing `format=rss` 形态**（R1 总表与 R4 已更新、T204 已调整）：免反爬标记、链接直链；作为首选形态 + HTML 回退，空 RSS 转 HTML 复核后再按空结果纪律判定；
- DDG 端点顺序（lite 先于 html）——登记为实现期微调备选（R5 保持 html 优先、lite 回退不变，避免改动既有已测实现）；
- Wikipedia OpenSearch 端点（`action=opensearch`）——较 `list=search` 更简但摘要信息更少；本实现保留 `list=search`（R7 已定），登记为备选。

**后续候选（不在本期范围）**: "融合检索渠道"——以 RRF 融合多引擎结果为单一渠道类型；需先解决融合语义与逐渠道记账的兼容设计；若立项可评估 webless 或仅借鉴其融合算法（`_engines.py` 的 `fuse`/`rank_by_relevance`，MIT 可参考）。
