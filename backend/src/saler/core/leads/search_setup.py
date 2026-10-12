"""从 `search_provider` 表构建检索链（failover）——路由与任务层共用。"""

from __future__ import annotations

from sqlalchemy.orm import Session

import saler.providers.search  # noqa: F401  # 导入包即注册全部 manifest（约定）
from saler.core.leads.search_stats import RecordingSearchAdapter, SearchStatsRecorder
from saler.db.models import SearchProvider
from saler.providers.registry import registry
from saler.providers.search.failover import SearchFailover


def resolve_search_chain(db: Session, config=None, session_factory=None) -> SearchFailover | None:
    """按 priority 升序构建渠道链；未配置任何启用渠道时返回 None。

    `session_factory` 提供时（路由/任务运行时），每个渠道以 `RecordingSearchAdapter`
    包装——按尝试记账用量/健康/最近失败（R9）；缺省（单元测试）不包装、行为不变。
    """
    rows = (
        db.query(SearchProvider)
        .filter_by(enabled=True)
        .order_by(SearchProvider.priority.asc(), SearchProvider.id.asc())
        .all()
    )
    recorder = SearchStatsRecorder(session_factory)
    providers = []
    for row in rows:
        manifest = registry.get("search", row.type_key)
        if manifest is None or manifest.factory is None:
            continue
        kwargs: dict = {"proxy": getattr(config, "proxy", None), "params": row.params or {}}
        if manifest.secret_fields:  # 需密钥类型才注入（免密钥渠道由 manifest 驱动，免特判）
            kwargs["api_key"] = row.secret_encrypted or ""
        if row.endpoint:
            kwargs["base_url"] = row.endpoint
        adapter = manifest.factory(**kwargs)
        if session_factory is not None:
            adapter = RecordingSearchAdapter(adapter, row_id=row.id, recorder=recorder)
        providers.append(adapter)
    return SearchFailover(providers) if providers else None
