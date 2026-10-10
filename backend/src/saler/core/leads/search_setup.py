"""从 `search_provider` 表构建检索链（failover）——路由与任务层共用。"""

from __future__ import annotations

from sqlalchemy.orm import Session

# 导入即注册 manifest（约定：新增渠道在注册表可见）
import saler.providers.search.brave  # noqa: F401
import saler.providers.search.ddg_fallback  # noqa: F401
import saler.providers.search.serper  # noqa: F401
import saler.providers.search.tavily  # noqa: F401
from saler.db.models import SearchProvider
from saler.providers.registry import registry
from saler.providers.search.failover import SearchFailover


def resolve_search_chain(db: Session, config=None) -> SearchFailover | None:
    """按 priority 升序构建渠道链；未配置任何启用渠道时返回 None。"""
    rows = (
        db.query(SearchProvider)
        .filter_by(enabled=True)
        .order_by(SearchProvider.priority.asc(), SearchProvider.id.asc())
        .all()
    )
    providers = []
    for row in rows:
        manifest = registry.get("search", row.type_key)
        if manifest is None or manifest.factory is None:
            continue
        kwargs: dict = {"proxy": getattr(config, "proxy", None)}
        if row.type_key != "ddg_html":
            kwargs["api_key"] = row.secret_encrypted or ""
        if row.endpoint:
            kwargs["base_url"] = row.endpoint
        providers.append(manifest.factory(**kwargs))
    return SearchFailover(providers) if providers else None
