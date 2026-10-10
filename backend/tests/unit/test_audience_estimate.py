"""T114 单元测试：人群圈选物化与影响范围预估（FR-046/047/050）。

直接经服务层（db fixture），离线。
"""

from __future__ import annotations

import pytest

from saler.core.sending import channel_service
from saler.db.models import Company, Contact, SendRecord, Suppression
from saler.providers.registry import ProviderManifest, registry
from tests.fixtures.fakes.mail_fake import FakeMailSender


@pytest.fixture()
def fake_mail() -> FakeMailSender:
    sender = FakeMailSender()
    registry.register(
        ProviderManifest(
            kind="mail", type_key="fake_mail_us6", display_name="假邮箱（US6）",
            factory=lambda **kwargs: sender,
        )
    )
    return sender


@pytest.fixture()
def channel(db, fake_mail):
    return channel_service.create_channel(
        db, name="US6 通道", channel_type="email",
        config={"provider": "fake_mail_us6"}, identity={"from_name": "Sales", "from_addr": "sales@example.com", "signature": "Sales Team"},
        rate_per_minute=6000, daily_limit=500,
    )


def make_company(db, name, *, country="KE", language="en", status="new", emails=(), tags=None) -> Company:
    company = Company(name=name, country=country, language=language, status=status, tags=tags or [], source="crawl")
    db.add(company)
    db.commit()
    for index, email in enumerate(emails):
        db.add(
            Contact(
                company_id=company.id, type="email", value=email,
                value_normalized=email.lower(), category="procurement" if index == 0 else "general",
                is_primary=index == 0,
            )
        )
    db.commit()
    return company


def make_theme(db, langs=("en",), *, publish=True):
    from saler.core.content import service as content_service

    theme = content_service.create_theme(db, name=f"主题-{'-'.join(langs)}", content_type="email", master_lang="zh")
    for lang in langs:
        variant = content_service.create_variant(
            db, theme_id=theme.id, lang=lang, subject=f"Hi {{{{company_name}}}} [{lang}]", body_md=f"Body {lang} {{{{company_name}}}}"
        )
        if publish:
            content_service.set_status(db, variant.id, "published")
    return theme


def make_campaign(db, theme, channel, audience, **overrides):
    from saler.core.campaigns import service as campaign_service

    return campaign_service.create_campaign(
        db,
        name=overrides.pop("name", "测试计划"),
        content_theme_id=theme.id,
        channel_ids=[channel.id],
        audience=audience,
        **overrides,
    )


BASE_AUDIENCE = {"filters": {"status": ["new", "contacted"]}}


class TestMaterialize:
    def test_one_contact_per_company_with_snapshot(self, db, channel):
        from saler.core.campaigns import audience as audience_service

        a = make_company(db, "A Co", emails=("a1@a.com", "a2@a.com"))
        make_company(db, "B Co", emails=("b@b.com",))
        make_company(db, "NoMail Co", emails=())  # 无联系方式 → 不产生记录
        theme = make_theme(db)
        campaign = make_campaign(db, theme, channel, BASE_AUDIENCE)

        report = audience_service.materialize(db, campaign, round_no=1)
        assert report["planned"] == 2
        records = db.query(SendRecord).filter_by(campaign_id=campaign.id).all()
        assert len(records) == 2
        record_a = next(r for r in records if r.company_id == a.id)
        assert record_a.contact_value == "a1@a.com"  # 首选联系方式快照
        assert record_a.status == "pending"

    def test_suppressed_contact_marked_suppressed(self, db, channel):
        from saler.core.campaigns import audience as audience_service

        b = make_company(db, "B Co", emails=("b@b.com",))
        db.add(Suppression(scope="email", target_value="b@b.com", reason="unsubscribed"))
        db.commit()
        theme = make_theme(db)
        campaign = make_campaign(db, theme, channel, BASE_AUDIENCE)
        report = audience_service.materialize(db, campaign, round_no=1)
        assert report["suppressed"] == 1
        record = db.query(SendRecord).filter_by(campaign_id=campaign.id, company_id=b.id).one()
        assert record.status == "suppressed"

    def test_excluded_and_progress_status_not_in_audience(self, db, channel):
        from saler.core.campaigns import audience as audience_service

        company_x = make_company(db, "X Co", emails=("x@x.com",))
        company_x.is_excluded = True
        make_company(db, "Replied Co", status="replied", emails=("r@r.com",))
        make_company(db, "Won Co", status="won", emails=("w@w.com",))
        keep = make_company(db, "Keep Co", emails=("k@k.com",))
        db.commit()
        theme = make_theme(db)
        campaign = make_campaign(db, theme, channel, BASE_AUDIENCE)
        audience_service.materialize(db, campaign, round_no=1)
        company_ids = {r.company_id for r in db.query(SendRecord).filter_by(campaign_id=campaign.id)}
        assert company_ids == {keep.id}

    def test_already_contacted_skipped_across_campaigns(self, db, channel):
        from saler.core.campaigns import audience as audience_service

        company = make_company(db, "A Co", emails=("a@a.com",))
        theme = make_theme(db)
        first = make_campaign(db, theme, channel, BASE_AUDIENCE, name="第一炮")
        audience_service.materialize(db, first, round_no=1)
        record = db.query(SendRecord).filter_by(campaign_id=first.id).one()
        record.status = "sent"
        db.commit()

        second = make_campaign(db, theme, channel, BASE_AUDIENCE, name="第二炮")
        report = audience_service.materialize(db, second, round_no=1)
        assert report["planned"] == 0 and report["skipped"] == 1
        row = db.query(SendRecord).filter_by(campaign_id=second.id, company_id=company.id).one()
        assert row.status == "skipped" and row.skip_reason == "already_contacted"

        # allow_resend 显式允许重发
        third = make_campaign(db, theme, channel, {**BASE_AUDIENCE, "allow_resend": True}, name="重发")
        report = audience_service.materialize(db, third, round_no=1)
        assert report["planned"] == 1

    def test_materialize_is_idempotent(self, db, channel):
        from saler.core.campaigns import audience as audience_service

        make_company(db, "A Co", emails=("a@a.com",))
        make_company(db, "B Co", emails=("b@b.com",))
        theme = make_theme(db)
        campaign = make_campaign(db, theme, channel, BASE_AUDIENCE)
        first = audience_service.materialize(db, campaign, round_no=1)
        second = audience_service.materialize(db, campaign, round_no=1)
        assert first["planned"] == 2
        assert second["created"] == 0
        assert db.query(SendRecord).filter_by(campaign_id=campaign.id).count() == 2

    def test_filters_and_max_count(self, db, channel):
        from saler.core.campaigns import audience as audience_service

        make_company(db, "KE1", country="KE", language="en", emails=("1@k.com",), tags=["vip"])
        make_company(db, "KE2", country="KE", language="en", emails=("2@k.com",))
        make_company(db, "NG1", country="NG", language="en", emails=("3@n.com",))
        theme = make_theme(db)
        campaign = make_campaign(
            db, theme, channel,
            {"filters": {"country": ["KE"], "tags": ["vip"]}, "max_count": 5},
        )
        report = audience_service.materialize(db, campaign, round_no=1)
        assert report["planned"] == 1


class TestEstimate:
    def test_estimate_counts_languages_channels_and_eta(self, db, channel):
        from saler.core.campaigns import estimate as estimate_service

        make_company(db, "EN Co", language="en", emails=("en@x.com",))
        make_company(db, "RU Co", language="ru", emails=("ru@x.com",))
        make_company(db, "SW Co", language="sw", emails=("sw@x.com",))  # 无 sw 版本 → 回退 en
        make_company(db, "NoMail", emails=())
        theme = make_theme(db, langs=("en", "ru"))
        campaign = make_campaign(db, theme, channel, BASE_AUDIENCE)

        est = estimate_service.estimate(db, campaign)
        assert est["audience_count"] == 3
        assert est["message_count"] == 3
        assert est["by_lang"] == {"en": 2, "ru": 1}
        assert est["by_channel"] == {"email": 3}
        assert est["fallback_count"] == 1
        assert est["eta_minutes"] >= 1

    def test_estimate_counts_suppressed_and_skipped(self, db, channel):
        from saler.core.campaigns import estimate as estimate_service

        make_company(db, "OK Co", emails=("ok@x.com",))
        make_company(db, "Sup Co", emails=("sup@x.com",))
        db.add(Suppression(scope="email", target_value="sup@x.com", reason="manual"))
        db.commit()
        theme = make_theme(db)
        campaign = make_campaign(db, theme, channel, BASE_AUDIENCE)
        est = estimate_service.estimate(db, campaign)
        assert est["audience_count"] == 1
        assert est["suppressed"] == 1
