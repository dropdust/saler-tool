"""T027 单元测试：产量归因口径（COUNT DISTINCT，不跨种子求和）与分组统计。"""

from __future__ import annotations

from saler.core.graph import service as graph_service
from saler.core.seeds import service as seed_service
from saler.core.seeds.yield_stats import recompute_seed_yield
from saler.db.models import Company, Contact, Domain, DomainSeedHit


def _domain(db, name: str) -> Domain:
    row = Domain(domain=name, status="done")
    db.add(row)
    db.commit()
    return row


def test_yield_counts_distinct_domains_and_contacts(db):
    product_line = graph_service.create_node(db, node_type="product_line", name="PL1")
    seed1 = seed_service.create_seed(db, query="q1", product_line_id=product_line.id, batch="b1")
    seed2 = seed_service.create_seed(db, query="q2", product_line_id=product_line.id, batch="b1")

    domain_a = _domain(db, "a.com")
    domain_b = _domain(db, "b.com")
    # seed1 命中两个域名；seed2 复命中 domain_a（去重不应重复计数）
    db.add_all(
        [
            DomainSeedHit(domain_id=domain_a.id, seed_id=seed1.id),
            DomainSeedHit(domain_id=domain_b.id, seed_id=seed1.id),
            DomainSeedHit(domain_id=domain_a.id, seed_id=seed2.id),
        ]
    )
    company = Company(name="Acme")
    db.add(company)
    db.commit()
    db.add_all(
        [
            Contact(
                company_id=company.id,
                domain_id=domain_a.id,
                type="email",
                value="a@a.com",
                value_normalized="a@a.com",
            ),
            Contact(
                company_id=company.id,
                domain_id=domain_b.id,
                type="email",
                value="b@b.com",
                value_normalized="b@b.com",
            ),
        ]
    )
    db.commit()

    recompute_seed_yield(db)
    db.refresh(seed1)
    db.refresh(seed2)
    assert seed1.n_candidates == 2
    assert seed1.n_contacts == 2
    assert seed2.n_candidates == 1
    assert seed2.n_contacts == 1


def test_stats_grouping_and_sums(db):
    market_a = graph_service.create_node(db, node_type="market", name="肯尼亚")
    market_b = graph_service.create_node(db, node_type="market", name="沙特")
    seed1 = seed_service.create_seed(
        db, query="s1", market_id=market_a.id, batch="b1", priority=1
    )
    seed2 = seed_service.create_seed(
        db, query="s2", market_id=market_a.id, batch="b2", priority=2
    )
    seed_service.create_seed(db, query="s3", market_id=market_b.id, batch="b2")
    seed1.status = "done"
    seed1.n_candidates, seed1.n_contacts = 3, 5
    seed2.n_candidates, seed2.n_contacts = 2, 4
    db.commit()

    by_batch = {row["name"]: row for row in seed_service.stats(db, group_by="batch")}
    assert by_batch["b1"]["seeds"] == 1 and by_batch["b1"]["done"] == 1
    assert by_batch["b1"]["contacts"] == 5
    assert by_batch["b2"]["seeds"] == 2 and by_batch["b2"]["candidates"] == 2

    by_market = {row["name"]: row for row in seed_service.stats(db, group_by="market")}
    assert by_market["肯尼亚"]["seeds"] == 2
    assert by_market["肯尼亚"]["contacts"] == 9
    assert by_market["沙特"]["seeds"] == 1
    # 产量排序：contacts 降序
    top = seed_service.list_seeds(db, sort="yield").first()
    assert top.query == "s1"
