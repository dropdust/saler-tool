"""T115 单元测试：发送引擎防重/守卫/失败重试（FR-048/049/050/051）。

- UNIQUE(campaign_id, round_no, contact_id) 从数据层防重复；
- 退订/排除命中 → suppressed/skipped（发送前二次校验，即时生效）；
- 失败重试不改变唯一键（始终同一条台账记录）。
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.exc import IntegrityError

from saler.core.sending import channel_service
from saler.db.models import Company, Contact, SendRecord, Suppression
from saler.providers.errors import ErrorKind, ProviderError
from saler.providers.registry import ProviderManifest, registry
from tests.fixtures.fakes.mail_fake import FakeMailSender


class StubCtx:
    """最小 JobContext 替身。"""

    def __init__(self) -> None:
        self.logs: list[str] = []
        self.progress_events: list[dict] = []

    def log(self, message: str, **extra) -> None:  # noqa: ANN003
        self.logs.append(message)

    def progress(self, **data) -> None:  # noqa: ANN003
        self.progress_events.append(data)

    async def checkpoint(self) -> None:
        await asyncio.sleep(0)


async def _no_sleep(_seconds: float) -> None:
    return None


@pytest.fixture()
def fake_mail() -> FakeMailSender:
    sender = FakeMailSender()
    registry.register(
        ProviderManifest(
            kind="mail", type_key="fake_mail_guard", display_name="假邮箱（守卫）",
            factory=lambda **kwargs: sender,
        )
    )
    return sender


@pytest.fixture()
def backup_fake() -> FakeMailSender:
    sender = FakeMailSender()
    registry.register(
        ProviderManifest(
            kind="mail", type_key="fake_mail_backup", display_name="假邮箱（备用）",
            factory=lambda **kwargs: sender,
        )
    )
    return sender


def make_channel(db, name, provider="fake_mail_guard", **overrides):
    kwargs = {
        "channel_type": "email",
        "config": {"provider": provider},
        "identity": {"from_name": "S", "from_addr": f"{name}@example.com", "signature": "SIG"},
        "rate_per_minute": 6000,
        "daily_limit": 500,
    }
    kwargs.update(overrides)
    return channel_service.create_channel(db, name=name, **kwargs)


def make_company(db, name, *, email, status="new") -> Company:
    company = Company(name=name, country="KE", language="en", status=status, source="crawl")
    db.add(company)
    db.commit()
    db.add(
        Contact(
            company_id=company.id, type="email", value=email,
            value_normalized=email.lower(), category="procurement", is_primary=True,
        )
    )
    db.commit()
    return company


def make_theme(db):
    from saler.core.content import service as content_service

    theme = content_service.create_theme(db, name="守卫主题", content_type="email", master_lang="zh")
    variant = content_service.create_variant(
        db, theme_id=theme.id, lang="en", subject="Hi {{company_name}}", body_md="Hello {{company_name}}"
    )
    content_service.set_status(db, variant.id, "published")
    return theme


def make_campaign(db, theme, channels, audience=None, **overrides):
    from saler.core.campaigns import service as campaign_service

    return campaign_service.create_campaign(
        db,
        name=overrides.pop("name", "守卫计划"),
        content_theme_id=theme.id,
        channel_ids=[c.id for c in channels],
        audience=audience or {"filters": {"status": ["new", "contacted"]}},
        **overrides,
    )


async def run_round(session_factory, campaign_id, round_no=1):
    from saler.core.sending.engine import run_campaign_round

    ctx = StubCtx()
    result = await run_campaign_round(
        ctx, session_factory, campaign_id, round_no, sleep=_no_sleep
    )
    return result, ctx


class TestUniqueKey:
    def test_duplicate_record_rejected_by_db(self, db, fake_mail, session_factory):
        channel = make_channel(db, "主通道")
        company = make_company(db, "A", email="a@x.com")
        theme = make_theme(db)
        campaign = make_campaign(db, theme, [channel])
        from saler.core.campaigns import service as campaign_service

        campaign_service.start_round(db, campaign, round_no=1)
        record = db.query(SendRecord).one()
        db.add(
            SendRecord(
                campaign_id=campaign.id, round_no=1, company_id=company.id,
                contact_id=record.contact_id, contact_value="a@x.com",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    @pytest.mark.asyncio
    async def test_materialize_twice_then_send_once(self, db, fake_mail, session_factory):
        channel = make_channel(db, "主通道")
        make_company(db, "A", email="a@x.com")
        theme = make_theme(db)
        campaign = make_campaign(db, theme, [channel])
        from saler.core.campaigns import audience as audience_service

        audience_service.materialize(db, campaign, round_no=1)
        audience_service.materialize(db, campaign, round_no=1)
        campaign.status = "running"
        db.commit()
        result, _ctx = await run_round(session_factory, campaign.id)
        assert result["sent"] == 1
        assert db.query(SendRecord).count() == 1
        assert len(fake_mail.sent) == 1


class TestSuppressionAtSendTime:
    @pytest.mark.asyncio
    async def test_suppression_added_after_materialize_takes_effect(self, db, fake_mail, session_factory):
        channel = make_channel(db, "主通道")
        make_company(db, "A", email="a@x.com")
        b = make_company(db, "B", email="b@x.com")
        theme = make_theme(db)
        campaign = make_campaign(db, theme, [channel])
        from saler.core.campaigns import service as campaign_service

        campaign_service.start_round(db, campaign, round_no=1)

        # 物化后再退订（S10⑦）：发送前二次校验必须命中
        db.add(Suppression(scope="email", target_value="b@x.com", reason="unsubscribed"))
        db.commit()

        result, _ctx = await run_round(session_factory, campaign.id)
        assert result["sent"] == 1
        assert result["suppressed"] == 1
        record_b = db.query(SendRecord).filter_by(company_id=b.id).one()
        assert record_b.status == "suppressed"
        assert len(fake_mail.sent) == 1

    @pytest.mark.asyncio
    async def test_company_status_replied_skips_pending_record(self, db, fake_mail, session_factory):
        channel = make_channel(db, "主通道")
        a = make_company(db, "A", email="a@x.com")
        make_company(db, "B", email="b@x.com")
        theme = make_theme(db)
        campaign = make_campaign(db, theme, [channel])
        from saler.core.campaigns import service as campaign_service

        campaign_service.start_round(db, campaign, round_no=1)
        a.status = "replied"  # FR-054：已回复即时生效
        db.commit()

        result, _ctx = await run_round(session_factory, campaign.id)
        assert result["sent"] == 1
        assert result["skipped"] == 1
        assert db.query(SendRecord).filter_by(company_id=a.id).one().skip_reason == "company_replied"


class TestFailureHandling:
    @pytest.mark.asyncio
    async def test_retryable_failure_retried_same_record(self, db, fake_mail, session_factory):
        channel = make_channel(db, "主通道")
        make_company(db, "A", email="a@x.com")
        theme = make_theme(db)
        campaign = make_campaign(db, theme, [channel])
        from saler.core.campaigns import service as campaign_service

        campaign_service.start_round(db, campaign, round_no=1)
        fake_mail.fail_next = ProviderError(ErrorKind.NETWORK, "临时网络错误")

        result, _ctx = await run_round(session_factory, campaign.id)
        assert result["sent"] == 1
        records = db.query(SendRecord).all()
        assert len(records) == 1  # 唯一键未被重试破坏
        assert records[0].status == "sent"

    @pytest.mark.asyncio
    async def test_recipient_rejected_no_retry_marks_bounced(self, db, fake_mail, session_factory):
        channel = make_channel(db, "主通道")
        make_company(db, "A", email="a@x.com")
        theme = make_theme(db)
        campaign = make_campaign(db, theme, [channel])
        from saler.core.campaigns import service as campaign_service

        campaign_service.start_round(db, campaign, round_no=1)

        class RejectingSender(FakeMailSender):
            def __init__(self):
                super().__init__()
                self.calls = 0

            def send(self, *, message, timeout_s: float = 60):
                self.calls += 1
                raise ProviderError(ErrorKind.RECIPIENT_REJECTED, "550 no such user")

        rejecting = RejectingSender()
        registry.register(
            ProviderManifest(
                kind="mail", type_key="fake_mail_reject", display_name="拒收假邮箱",
                factory=lambda **kwargs: rejecting,
            )
        )
        channel.config = {"provider": "fake_mail_reject"}
        db.commit()

        result, _ctx = await run_round(session_factory, campaign.id)
        assert result["bounced"] == 1
        assert rejecting.calls == 1  # recipient_rejected 不重试
        record = db.query(SendRecord).one()
        assert record.status == "bounced" and record.error_code == "recipient_rejected"

    @pytest.mark.asyncio
    async def test_exhausted_retries_mark_failed_then_manual_retry_sends(self, db, fake_mail, session_factory):
        channel = make_channel(db, "主通道")
        make_company(db, "A", email="a@x.com")
        theme = make_theme(db)
        campaign = make_campaign(db, theme, [channel])
        from saler.core.campaigns import service as campaign_service

        campaign_service.start_round(db, campaign, round_no=1)
        fake_mail.fail_next = ProviderError(ErrorKind.NETWORK, "持续网络错误")

        class AlwaysFailSender(FakeMailSender):
            def send(self, *, message, timeout_s: float = 60):
                raise ProviderError(ErrorKind.NETWORK, "持续网络错误")

        failing = AlwaysFailSender()
        registry.register(
            ProviderManifest(
                kind="mail", type_key="fake_mail_fail", display_name="故障假邮箱",
                factory=lambda **kwargs: failing,
            )
        )
        channel.config = {"provider": "fake_mail_fail"}
        db.commit()

        result, _ctx = await run_round(session_factory, campaign.id)
        assert result["failed"] == 1
        record = db.query(SendRecord).one()
        assert record.status == "failed" and record.error_code == "network"

        # 人工重试：重置为 pending 后重跑 → 成功（同一条记录）
        record_id = record.id
        campaign_service.retry_records(db, campaign.id, [record_id])
        assert db.get(SendRecord, record_id).status == "pending"
        channel.config = {"provider": "fake_mail_guard"}
        db.commit()
        result2, _ctx2 = await run_round(session_factory, campaign.id)
        assert result2["sent"] == 1
        db.expire_all()  # 引擎在独立会话中写入
        assert db.query(SendRecord).count() == 1
        assert db.get(SendRecord, record_id).status == "sent"


class TestChannelFallback:
    @pytest.mark.asyncio
    async def test_quota_switches_to_backup_channel(self, db, fake_mail, backup_fake, session_factory):
        primary = make_channel(db, "主通道")
        backup = make_channel(db, "备用通道", provider="fake_mail_backup")
        make_company(db, "A", email="a@x.com")
        theme = make_theme(db)
        campaign = make_campaign(db, theme, [primary, backup])
        from saler.core.campaigns import service as campaign_service

        campaign_service.start_round(db, campaign, round_no=1)

        class QuotaSender(FakeMailSender):
            def send(self, *, message, timeout_s: float = 60):
                raise ProviderError(ErrorKind.QUOTA, "额度耗尽")

        registry.register(
            ProviderManifest(
                kind="mail", type_key="fake_mail_quota", display_name="额度耗尽假邮箱",
                factory=lambda **kwargs: QuotaSender(),
            )
        )
        primary.config = {"provider": "fake_mail_quota"}
        db.commit()

        result, _ctx = await run_round(session_factory, campaign.id)
        assert result["sent"] == 1
        record = db.query(SendRecord).one()
        assert record.channel_id == backup.id  # primary→backup 换通道（FR-048）
        assert len(backup_fake.sent) == 1

    @pytest.mark.asyncio
    async def test_daily_limit_exhausted_stops_with_pending_left(self, db, fake_mail, session_factory):
        channel = make_channel(db, "限额通道", daily_limit=1)
        make_company(db, "A", email="a@x.com")
        make_company(db, "B", email="b@x.com")
        theme = make_theme(db)
        campaign = make_campaign(db, theme, [channel])
        from saler.core.campaigns import service as campaign_service

        campaign_service.start_round(db, campaign, round_no=1)

        result, _ctx = await run_round(session_factory, campaign.id)
        assert result["sent"] == 1
        assert result["stopped"] == "quota"
        assert db.query(SendRecord).filter_by(status="pending").count() == 1  # 断点待明日续发


class TestCompanyStatusLinkage:
    def test_mark_status_immediately_skips_pending_records(self, db, fake_mail):
        """FR-054：标记已回复 → 待发记录立即置为 skipped（不等发送引擎）。"""
        from saler.core.leads import company_service

        channel = make_channel(db, "联动通道")
        a = make_company(db, "A", email="a@x.com")
        make_company(db, "B", email="b@x.com")
        theme = make_theme(db)
        campaign = make_campaign(db, theme, [channel])
        from saler.core.campaigns import service as campaign_service

        campaign_service.start_round(db, campaign, round_no=1)
        assert db.query(SendRecord).filter_by(company_id=a.id, status="pending").count() == 1

        company_service.mark_status(db, a.id, "replied")
        rows = db.query(SendRecord).filter_by(company_id=a.id).all()
        assert rows[0].status == "skipped"
        assert rows[0].skip_reason == "company_replied"
        # 其他客户不受影响
        assert db.query(SendRecord).filter_by(status="pending").count() == 1
