"""T050 单元测试：挖掘引擎——检索→域名→抓取→抽取→落库；断点续跑与失败重试。"""

from __future__ import annotations

from saler.core.leads.crawl_engine import CrawlConfig, CrawlEngine
from saler.core.seeds import service as seed_service
from saler.db.models import Company, Contact, Domain, Seed
from tests.fixtures.fakes.fetcher_fake import FakeFetcher
from tests.fixtures.fakes.search_fake import FakeSearchProvider

ACME_HOME = (
    '<html lang="en"><head><title>Acme Kenya</title></head><body>'
    '<a href="/contact">Contact us</a> '
    '<a href="mailto:sales@acme.co.ke">mail</a>'
    "</body></html>"
)
ACME_CONTACT = (
    '<html lang="en"><body><p>Tel: <a href="tel:+254712345678">+254</a></p>'
    '<a href="https://wa.me/254712345678">WhatsApp</a></body></html>'
)
BETA_HOME = '<html lang="sw"><body><p>info@beta.com</p></body></html>'


class _Ctx:
    """挖掘引擎用的 JobContext 轻量替身。"""

    job_id = None

    def __init__(self) -> None:
        self.checkpoints = 0
        self.progress_events: list[dict] = []
        self.logs: list[str] = []

    async def checkpoint(self) -> None:
        self.checkpoints += 1

    def progress(self, **data) -> None:
        self.progress_events.append(data)

    def log(self, message: str, **_kwargs) -> None:
        self.logs.append(message)


def _search() -> FakeSearchProvider:
    return FakeSearchProvider(
        {
            "q1": [
                {"url": "https://acme.co.ke/", "title": "Acme"},
                {"url": "https://beta.com/", "title": "Beta"},
            ],
            "q2": [{"url": "https://acme.co.ke/contact", "title": "Acme contact"}],
        }
    )


def _pages() -> dict[str, str]:
    return {
        "https://acme.co.ke/": ACME_HOME,
        "https://acme.co.ke/contact": ACME_CONTACT,
        "https://beta.com/": BETA_HOME,
    }


def _make_engine(session_factory, fetcher, *, max_attempts: int = 2) -> CrawlEngine:
    config = CrawlConfig(
        concurrency=2, per_host_delay_s=0, max_pages_per_site=4, max_attempts=max_attempts
    )
    return CrawlEngine(session_factory, _search(), fetcher, config=config)


def _seed(db, query: str, batch: str = "t"):
    return seed_service.create_seed(db, query=query, batch=batch)


async def test_full_run_creates_domains_companies_contacts(session_factory, db):
    _seed(db, "q1")
    _seed(db, "q2")
    fetcher = FakeFetcher(_pages())

    report = await _make_engine(session_factory, fetcher).run(_Ctx())

    assert report["seeds_processed"] == 2
    assert report["domains_found"] == 2          # acme 去重，命中计 1 次 new + 1 次 dup
    assert report["domains_done"] == 2
    assert report["contacts_created"] >= 3       # sales@ + phone + whatsapp + info@beta

    with session_factory() as check:
        acme = check.query(Domain).filter_by(domain="acme.co.ke").one()
        assert acme.status == "done"
        assert acme.country == "ke" and acme.country_source == "cctld"
        assert acme.language == "en" and acme.language_source == "html_lang"
        assert acme.fetched_pages == 2            # 首页 + /contact

        beta = check.query(Domain).filter_by(domain="beta.com").one()
        assert beta.status == "done"
        assert beta.language == "sw"

        company = check.query(Company).filter_by(name="Acme Kenya").one()
        emails = {
            c.value_normalized: c
            for c in check.query(Contact).filter_by(company_id=company.id, type="email")
        }
        assert "sales@acme.co.ke" in emails
        assert emails["sales@acme.co.ke"].category == "sales"
        types = {c.type for c in check.query(Contact).filter_by(company_id=company.id)}
        assert {"phone", "whatsapp"} <= types

        seed = check.query(Seed).filter_by(query="q1").one()
        assert seed.status == "done"


async def test_resume_skips_done_and_retries_pending(session_factory, db):
    _seed(db, "q1")
    failing = FakeFetcher(_pages(), failures={"https://beta.com/": "timeout"})
    report1 = await _make_engine(session_factory, failing, max_attempts=2).run(_Ctx())
    assert report1["domains_done"] == 1

    with session_factory() as check:
        beta = check.query(Domain).filter_by(domain="beta.com").one()
        assert beta.status == "pending" and beta.attempts == 1  # 未达上限 → 保持待重试

    healthy = FakeFetcher(_pages())
    await _make_engine(session_factory, healthy).run(_Ctx())
    with session_factory() as check:
        assert check.query(Domain).filter_by(domain="beta.com").one().status == "done"
    # 已完成的 acme 未被重新抓取
    assert all("acme.co.ke" not in url for url in healthy.calls)


async def test_attempts_exhausted_marks_failed(session_factory, db):
    _seed(db, "q1")
    failing = FakeFetcher(_pages(), failures={"https://beta.com/": "timeout"})
    await _make_engine(session_factory, failing, max_attempts=1).run(_Ctx())
    with session_factory() as check:
        beta = check.query(Domain).filter_by(domain="beta.com").one()
        assert beta.status == "failed"
        assert "timeout" in (beta.last_error or "")


async def test_checkpoints_are_called(session_factory, db):
    _seed(db, "q1")
    ctx = _Ctx()
    await _make_engine(session_factory, FakeFetcher(_pages())).run(ctx)
    assert ctx.checkpoints >= 3  # 种子循环 + 域名循环都设协作点
