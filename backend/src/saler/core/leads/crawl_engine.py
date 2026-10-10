"""挖掘引擎（FR-019/024/026）：种子 → 检索 → 域名 → 抓取 → 抽取 → 落库。

断点续跑的设计要点：**任务状态全部落在数据库**（seed.status / domain.status /
domain.attempts），进程中断后重跑只处理 pending 项；协作点（ctx.checkpoint）
支撑暂停/取消。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from saler.core.leads import domain_service
from saler.core.leads.company_service import get_or_create_company_for_domain, upsert_contact
from saler.core.leads.enrich import enrich_domain
from saler.core.leads.extractor import extract_contacts
from saler.core.leads.parser import contact_page_links, page_title
from saler.db.models import Domain, DomainSeedHit, Seed
from saler.jobs.engine import JobContext
from saler.providers.errors import ProviderError
from saler.services.operation_log import log_op


@dataclass
class CrawlConfig:
    results_per_query: int = 20
    concurrency: int = 5
    per_host_delay_s: float = 1.0
    max_pages_per_site: int = 6
    respect_robots: bool = True
    timeout_s: float = 20.0
    proxy: str | None = None
    max_attempts: int = 2

    def to_dict(self) -> dict:
        return {
            "results_per_query": self.results_per_query,
            "concurrency": self.concurrency,
            "per_host_delay_s": self.per_host_delay_s,
            "max_pages_per_site": self.max_pages_per_site,
            "respect_robots": self.respect_robots,
            "timeout_s": self.timeout_s,
            "proxy": self.proxy,
            "max_attempts": self.max_attempts,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> CrawlConfig:
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in (data or {}).items() if k in known and v is not None})


@dataclass
class _Report:
    data: dict = field(default_factory=dict)

    def bump(self, key: str, amount: int = 1) -> None:
        self.data[key] = self.data.get(key, 0) + amount


class CrawlEngine:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        search,
        fetcher,
        *,
        config: CrawlConfig | None = None,
    ) -> None:
        self._sf = session_factory
        self._search = search
        self._fetcher = fetcher
        self._cfg = config or CrawlConfig()

    # ---------- 对外入口 ----------

    async def run(
        self,
        ctx: JobContext,
        *,
        seed_ids: list[int] | None = None,
        job_id: int | None = None,
    ) -> dict:
        report = _Report()
        seed_list = await self._run_search_phase(ctx, report, seed_ids=seed_ids, job_id=job_id)
        await self._run_fetch_phase(ctx, report)
        self._recompute_seed_yield(seed_list)
        if job_id is not None:
            with self._sf() as db:
                log_op(
                    db,
                    "crawl",
                    f"挖掘完成：种子 {report.data.get('seeds_processed', 0)}，"
                    f"新增域名 {report.data.get('domains_found', 0)}，"
                    f"联系方式 {report.data.get('contacts_created', 0)}",
                    ref_type="job",
                    ref_id=job_id,
                    payload=report.data,
                )
        ctx.progress(phase="done", **report.data)
        return report.data

    # ---------- 阶段 1：种子 → 检索 → 域名 ----------

    async def _run_search_phase(
        self,
        ctx: JobContext,
        report: _Report,
        *,
        seed_ids: list[int] | None,
        job_id: int | None,
    ) -> list[int]:
        with self._sf() as db:
            query = db.query(Seed).filter(
                Seed.review_status == "approved", Seed.status != "invalid"
            )
            query = (
                query.filter(Seed.id.in_(seed_ids)) if seed_ids else query.filter(Seed.status == "pending")
            )
            seed_pairs = [(seed.id, seed.query) for seed in query.order_by(Seed.id.asc()).all()]

        for index, (seed_id, query_text) in enumerate(seed_pairs, start=1):
            await ctx.checkpoint()
            with self._sf() as db:
                seed = db.get(Seed, seed_id)
                if seed is None or seed.status == "invalid":
                    continue
                seed.status = "running"
                db.commit()
            try:
                items = self._search.search(query=query_text, count=self._cfg.results_per_query)
            except ProviderError as exc:
                with self._sf() as db:
                    seed = db.get(Seed, seed_id)
                    if seed is not None:
                        seed.status = "pending"  # 保留待重试
                        seed.note = f"检索失败：{exc}"
                        db.commit()
                report.bump("search_failures")
                ctx.log(f"检索失败（保留待重试）：{query_text} — {exc}")
                continue

            for item in items:
                url = getattr(item, "url", "")
                if not url:
                    continue
                with self._sf() as db:
                    domain_row, created = domain_service.get_or_create_domain(
                        db,
                        domain=url,
                        homepage_url=url,
                        title=getattr(item, "title", None),
                        snippet=getattr(item, "snippet", None),
                        source=getattr(self._search, "type_key", "search"),
                        job_id=job_id,
                    )
                    hit = (
                        db.query(DomainSeedHit)
                        .filter_by(domain_id=domain_row.id, seed_id=seed_id)
                        .first()
                    )
                    if hit is None:
                        db.add(DomainSeedHit(domain_id=domain_row.id, seed_id=seed_id, job_id=job_id))
                        db.commit()
                report.bump("domains_found" if created else "domains_duplicate")

            with self._sf() as db:
                seed = db.get(Seed, seed_id)
                if seed is not None:
                    seed.status = "done"
                    seed.last_run_at = datetime.now(UTC)
                    db.commit()
            report.bump("seeds_processed")
            ctx.progress(
                phase="search",
                seeds_processed=report.data.get("seeds_processed", 0),
                total_seeds=len(seed_pairs),
                domains_found=report.data.get("domains_found", 0),
            )
        return [seed_id for seed_id, _ in seed_pairs]

    # ---------- 阶段 2：抓取与抽取 ----------

    async def _run_fetch_phase(self, ctx: JobContext, report: _Report) -> None:
        with self._sf() as db:
            pending_ids = [
                row.id
                for row in db.query(Domain)
                .filter(Domain.status == "pending", Domain.is_excluded.is_(False))
                .order_by(Domain.id.asc())
                .all()
            ]
        if not pending_ids:
            return
        semaphore = asyncio.Semaphore(max(1, self._cfg.concurrency))
        processed = 0

        async def worker(domain_id: int) -> dict:
            nonlocal processed
            async with semaphore:
                delta = await self._process_domain(ctx, domain_id)
            processed += 1
            ctx.progress(phase="fetch", fetched_domains=processed, total_domains=len(pending_ids))
            return delta

        results = await asyncio.gather(*(worker(domain_id) for domain_id in pending_ids))
        for delta in results:
            for key, value in delta.items():
                report.bump(key, value)

    async def _process_domain(self, ctx: JobContext, domain_id: int) -> dict:
        await ctx.checkpoint()
        with self._sf() as db:
            domain_row = db.get(Domain, domain_id)
            if (
                domain_row is None
                or domain_row.status != "pending"
                or domain_row.is_excluded
            ):
                return {}
            domain_name = domain_row.domain
            homepage = domain_row.homepage_url or f"https://{domain_name}/"

        cfg = self._cfg
        pages: list[tuple[str, str]] = []  # (url, html)
        first = await self._fetcher.fetch(homepage)
        if first.error is None and first.status == 200:
            pages.append((homepage, first.text))
            links = contact_page_links(
                first.text, base_url=homepage, limit=max(0, cfg.max_pages_per_site - 1)
            )
            for link in links:
                sub = await self._fetcher.fetch(link)
                if sub.error is None and sub.status == 200:
                    pages.append((link, sub.text))

        if not pages:
            with self._sf() as db:
                row = db.get(Domain, domain_id)
                if row is None:
                    return {}
                row.attempts += 1
                row.last_error = first.error or f"http_{first.status}"
                if row.attempts >= cfg.max_attempts:
                    row.status = "failed"
                db.commit()
                failed = row.status == "failed"
            return {"domains_failed": 1} if failed else {"domains_retry": 1}

        seen: set[tuple[str, str]] = set()
        contacts = []
        for page_url, html_text in pages:
            for contact in extract_contacts(html_text, page_url=page_url):
                key = (contact.type, contact.value_normalized)
                if key not in seen:
                    seen.add(key)
                    contacts.append(contact)

        delta = {"pages_fetched": len(pages)}
        with self._sf() as db:
            row = db.get(Domain, domain_id)
            if row is None:
                return {}
            row.attempts += 1
            row.fetched_pages = len(pages)
            row.status = "done" if contacts else "no_contact"
            row.last_crawled_at = datetime.now(UTC)
            row.last_error = None
            title = page_title(pages[0][1])
            if title and not row.title:
                row.title = title
            enrich_domain(db, row, html=pages[0][1])
            company, created_company = get_or_create_company_for_domain(
                db, domain_row=row, name=title
            )
            db.commit()
            delta["companies_created"] = 1 if created_company else 0
            created_contacts = 0
            for contact in contacts:
                _row, created = upsert_contact(
                    db,
                    company_id=company.id,
                    domain_id=row.id,
                    type_=contact.type,
                    value=contact.value,
                    value_normalized=contact.value_normalized,
                    category=contact.category,
                    source_url=contact.source_url,
                    validity=contact.validity,
                )
                created_contacts += 1 if created else 0
            delta["contacts_created"] = created_contacts
        delta["domains_done" if contacts else "domains_no_contact"] = 1
        return delta

    def _recompute_seed_yield(self, seed_ids: list[int]) -> None:
        if not seed_ids:
            return
        from saler.core.seeds.yield_stats import recompute_seed_yield

        with self._sf() as db:
            recompute_seed_yield(db, seed_ids)
