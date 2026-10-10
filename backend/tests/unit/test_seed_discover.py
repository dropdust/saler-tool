"""T147 单元测试：检索扩充图谱（FR-013）——检索结果提炼候选实体/种子（全部待审核）。"""

from __future__ import annotations

import pytest

from saler.core.errors import ValidationFailed
from saler.db.models import GraphEdge, GraphNode, Seed
from tests.fixtures.fakes.search_fake import FakeSearchProvider


class StubCtx:
    def __init__(self) -> None:
        self.job_id = 1
        self.logs: list[str] = []
        self.progress_events: list[dict] = []

    def log(self, message: str, **extra) -> None:  # noqa: ANN003
        self.logs.append(message)

    def progress(self, **data) -> None:  # noqa: ANN003
        self.progress_events.append(data)

    async def checkpoint(self) -> None:
        pass


RESULTS = {
    "power line hardware distributor Kenya": [
        {
            "title": "Kenya Power Hardware Ltd - Electrical Supplies",
            "url": "https://kenyapowerhardware.co.ke/about",
            "snippet": "Distributor of transmission line hardware.",
        },
        {
            "title": "Nairobi Cable & Fittings Co. | Industrial Suppliers",
            "url": "https://nairobicable.co.ke",
            "snippet": "Cable accessories and fittings.",
        },
        {
            "title": "10 Best Suppliers in Kenya 2026 - Directory",
            "url": "https://some-directory.example/lists/kenya",
            "snippet": "A list of suppliers.",
        },
    ],
    "switchgear supplier Tanzania": [
        {
            "title": "Tanzania Switchgear Ltd",
            "url": "https://tzswitchgear.co.tz",
            "snippet": "Switchgear assembly and supply.",
        },
    ],
}


def _payload(**overrides):
    base = {
        "queries": ["power line hardware distributor Kenya", "switchgear supplier Tanzania"],
        "lang": "en",
        "per_query": 10,
    }
    base.update(overrides)
    return base


async def test_discover_creates_pending_orgs_and_seeds(db, session_factory):
    from saler.core.seeds import discover

    ctx = StubCtx()
    search = FakeSearchProvider(RESULTS)
    result = await discover.run_discover(ctx, session_factory, search, payload=_payload())

    assert result["nodes_created"] >= 3  # 三条具名公司（目录列表页被剔除）
    nodes = db.query(GraphNode).filter_by(source="search").all()
    names = {node.name for node in nodes}
    assert "Kenya Power Hardware Ltd" in names
    assert "Nairobi Cable & Fittings Co." in names
    assert all(node.review_status == "pending" for node in nodes)
    assert all(node.evidence_url for node in nodes)  # 来源记录
    assert not any("Best Suppliers" in name for name in names)  # 目录列表页不当实体

    seeds = db.query(Seed).filter_by(source="search").all()
    assert seeds and all(seed.review_status == "pending" for seed in seeds)
    queries = {seed.query for seed in seeds}
    assert '"Kenya Power Hardware Ltd" contact' in queries
    assert "power line hardware distributor Kenya" in queries  # 来源词本身也入种子（去重后）
    assert all(seed.note for seed in seeds if seed.query.startswith('"'))  # 种子带来源说明
    assert search.calls == list(RESULTS.keys())
    assert ctx.progress_events  # 进度可见


async def test_discover_dedups_across_runs(db, session_factory):
    from saler.core.seeds import discover

    search = FakeSearchProvider(RESULTS)
    ctx = StubCtx()
    first = await discover.run_discover(ctx, session_factory, search, payload=_payload())
    assert first["nodes_created"] >= 3 and first["seeds_created"] >= 3

    second = await discover.run_discover(StubCtx(), session_factory, search, payload=_payload())
    assert second["nodes_created"] == 0
    assert second["seeds_created"] == 0
    assert second["nodes_skipped"] == first["nodes_created"]
    assert second["seeds_skipped"] >= first["seeds_created"]
    # 库中无重复
    assert db.query(GraphNode).filter_by(source="search").count() == first["nodes_created"]
    assert db.query(Seed).filter_by(source="search").count() == first["seeds_created"]


async def test_discover_links_market_context(db, session_factory):
    from saler.core.graph import service as graph_service
    from saler.core.seeds import discover

    market = graph_service.create_node(db, node_type="market", name="肯尼亚", source="manual")
    search = FakeSearchProvider(RESULTS)
    await discover.run_discover(
        StubCtx(), session_factory, search, payload=_payload(from_node_ids=[market.id])
    )
    edges = db.query(GraphEdge).filter_by(relation_type="org_in_market", source="search").all()
    assert len(edges) >= 3
    org_ids = {node.id for node in db.query(GraphNode).filter_by(source="search").all()}
    assert {edge.to_node_id for edge in edges} <= org_ids
    seeds = db.query(Seed).filter_by(source="search").all()
    assert all(seed.market_id == market.id for seed in seeds if seed.query.startswith('"'))


async def test_discover_requires_queries(session_factory):
    from saler.core.seeds import discover

    with pytest.raises(ValidationFailed):
        await discover.run_discover(
            StubCtx(), session_factory, FakeSearchProvider({}), payload={"queries": []}
        )
