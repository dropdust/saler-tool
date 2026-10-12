"""T213 集成测试：混合链故障转移 + 运行时记账闭环（FR-005/006 / SC-004；R9）。

真实 `SearchFailover` + `RecordingSearchAdapter` + 临时 SQLite（conftest 夹具）+ respx 回放：
链 [渠道A(限流) → 渠道B(成功)] ——调用不中断返回结果；A 行记账失败（rate_limit）、B 行成功；
used_today 按**渠道调用尝试**计一次（契约 §3：形态回退不重复计数）。
"""

from __future__ import annotations

import httpx
import respx

from saler.core.leads.search_setup import resolve_search_chain
from saler.db.models import SearchProvider

DDG_URL = "https://html.duckduckgo.com/html/"
DDG_LITE = "https://lite.duckduckgo.com/lite/"
NORMAL_HTML = '<html><body><a class="result__a" href="https://ok.example/">Ok</a></body></html>'


def test_mixed_chain_failover_records_stats(db, session_factory):
    db.add(SearchProvider(type_key="ddg_html", name="A-限流", priority=10, params={"interval_s": 0}))
    db.add(SearchProvider(type_key="ddg_html", name="B-可用", priority=20, params={"interval_s": 0}))
    db.commit()

    with respx.mock:
        # A：html 429 → lite 429（同一次 search() 内的形态回退）；B：html 直接成功
        respx.get(DDG_URL).mock(
            side_effect=[httpx.Response(429), httpx.Response(200, text=NORMAL_HTML)]
        )
        respx.get(DDG_LITE).mock(return_value=httpx.Response(429))

        chain = resolve_search_chain(db, session_factory=session_factory)
        assert chain is not None
        items = chain.search(query="混合链测试")

    assert [i.url for i in items] == ["https://ok.example/"]  # 单渠道失败 0 中断，B 出结果

    db.expire_all()
    rows = {r.name: r for r in db.query(SearchProvider).all()}
    a, b = rows["A-限流"], rows["B-可用"]
    assert (a.used_today, a.health, a.last_error_kind) == (1, "failing", "rate_limit")
    assert a.last_error_at is not None
    assert (b.used_today, b.health, b.last_error_kind) == (1, "healthy", None)
    assert b.last_error_at is None
