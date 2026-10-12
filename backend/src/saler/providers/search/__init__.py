"""检索适配器（Brave / Serper / Tavily / DDG 兜底 + 免密钥渠道）。

导入子模块即注册 manifest——**新增渠道只需在此登记一行**，注册表即全量可见
（约定大于配置，004 R8）。
"""

import saler.providers.search.brave  # noqa: F401
import saler.providers.search.ddg_fallback  # noqa: F401
import saler.providers.search.serper  # noqa: F401
import saler.providers.search.tavily  # noqa: F401
