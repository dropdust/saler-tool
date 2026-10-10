"""T116 集成测试：S10 营销计划全链路 + 多轮跟进（FR-046~054）。

流程：建计划→预估→试发→启动→台账→二次计划防重→退订排除；暂停/恢复；轮次跟进。
离线：假邮件适配器经 Provider Registry 注入。
"""

from __future__ import annotations

import time

import pytest

from saler.db.models import Company, Contact, SendRecord, Suppression
from saler.providers.errors import ProviderError
from saler.providers.registry import ProviderManifest, registry
from tests.conftest import wait_job
from tests.fixtures.fakes.mail_fake import FakeMailSender


@pytest.fixture()
def fake_mail() -> FakeMailSender:
    sender = FakeMailSender()
    registry.register(
        ProviderManifest(
            kind="mail", type_key="fake_mail_s10", display_name="假邮箱（S10）",
            factory=lambda **kwargs: sender,
        )
    )
    return sender


def make_channel(client, name, *, rate=6000):
    resp = client.post(
        "/api/v1/channels",
        json={
            "name": name, "channel_type": "email",
            "config": {"provider": "fake_mail_s10"},
            "identity": {"from_name": "Sales", "from_addr": "sales@example.com", "signature": "SIG"},
            "rate_per_minute": rate, "daily_limit": 500,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def make_company(db, name, *, email, language="en", status="new"):
    company = Company(name=name, country="KE", language=language, status=status, source="crawl")
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


def make_theme(client, *, langs=("en",)) -> int:
    resp = client.post("/api/v1/content/themes", json={"name": f"S10 主题{''.join(langs)}", "content_type": "email", "master_lang": "zh"})
    assert resp.status_code == 201, resp.text
    theme_id = resp.json()["id"]
    for lang in langs:
        variant = client.post(
            f"/api/v1/content/themes/{theme_id}/variants",
            json={"lang": lang, "subject": f"Hi {{{{company_name}}}} [{lang}]", "body_md": f"Hello {{{{company_name}}}} ({lang})"},
        ).json()
        client.post(f"/api/v1/content/variants/{variant['id']}/publish")
    return theme_id


def create_campaign(client, theme_id, channel_ids, *, name="S10 计划", audience=None, rounds=None):
    resp = client.post(
        "/api/v1/campaigns",
        json={
            "name": name,
            "content_theme_id": theme_id,
            "channel_ids": channel_ids,
            "audience": audience or {"filters": {"status": ["new", "contacted"]}},
            "lang_strategy": "auto",
        },
    )
    assert resp.status_code == 201, resp.text
    campaign = resp.json()
    for round_spec in rounds or []:
        r = client.post(f"/api/v1/campaigns/{campaign['id']}/rounds", json=round_spec)
        assert r.status_code in (200, 201), r.text
    return campaign


def start_campaign(client, campaign_id, *, round_no=1) -> dict:
    resp = client.post(f"/api/v1/campaigns/{campaign_id}/rounds/{round_no}/start")
    assert resp.status_code in (200, 202), resp.text
    job = wait_job(client, resp.json()["job_id"], timeout=30)
    return job


class TestS10Flow:
    def test_end_to_end_campaign(self, client, db, fake_mail):
        channel_id = make_channel(client, "S10 通道")
        theme_id = make_theme(client, langs=("en",))
        make_company(db, "A Co", email="a@x.com")
        make_company(db, "B Co", email="b@x.com", language="ru")  # 无 ru 版本 → 回退 en
        make_company(db, "C Co", email="c@x.com")

        campaign = create_campaign(client, theme_id, [channel_id])
        campaign_id = campaign["id"]

        # ① 预估
        est = client.post(f"/api/v1/campaigns/{campaign_id}/estimate").json()
        assert est["audience_count"] == 3
        assert est["message_count"] == 3
        assert est["by_lang"]["en"] == 3
        assert est["fallback_count"] == 1
        assert est["by_channel"] == {"email": 3}

        # ② 试发 2 封给自己（不写台账、不占计划额度）
        test_send = client.post(
            f"/api/v1/campaigns/{campaign_id}/test-send",
            json={"n": 2, "to": "me@example.com"},
        )
        assert test_send.status_code == 200, test_send.text
        assert test_send.json()["sent"] == 2
        assert len(fake_mail.sent) == 2
        assert client.get(f"/api/v1/campaigns/{campaign_id}/records").json()["total"] == 0

        # ③ 启动 → 完成
        job = start_campaign(client, campaign_id)
        assert job["status"] == "completed", job
        assert job["result"]["sent"] == 3

        records = client.get(f"/api/v1/campaigns/{campaign_id}/records").json()["items"]
        assert {r["status"] for r in records} == {"sent"}
        assert all(r["sent_at"] for r in records)
        assert all(r["content_version_id"] for r in records)  # 发送时冻结版本（FR-049）
        assert {r["lang_used"] for r in records} == {"en"}
        assert sum(1 for r in records if r["fallback_used"]) == 1

        # 触达联动 + 通道用量
        for company in db.query(Company).all():
            db.refresh(company)
            assert company.status == "contacted"
        usage = client.get(f"/api/v1/channels/{channel_id}/usage").json()
        assert usage["used_today"] == 3
        campaign_now = client.get(f"/api/v1/campaigns/{campaign_id}").json()
        assert campaign_now["status"] == "completed"
        assert campaign_now["stats"]["sent"] == 3

        # ⑥ 同一人群再建计划：默认跳过已触达（重复发送为 0）
        fake_mail.sent.clear()
        second = create_campaign(client, theme_id, [channel_id], name="S10 第二计划")
        est2 = client.post(f"/api/v1/campaigns/{second['id']}/estimate").json()
        assert est2["message_count"] == 0
        assert est2["skipped"] == 3
        job2 = start_campaign(client, second["id"])
        assert job2["result"].get("sent", 0) == 0
        assert len(fake_mail.sent) == 0

        # ⑦ 退订对象在所有计划中被排除（显式允许重发时也会被退订拦截）
        b = db.query(Company).filter_by(name="B Co").one()
        db.add(Suppression(scope="email", target_value="b@x.com", reason="unsubscribed", company_id=b.id))
        db.commit()
        third = create_campaign(
            client, theme_id, [channel_id], name="S10 第三计划",
            audience={"filters": {"status": ["new", "contacted"]}, "allow_resend": True},
        )
        job3 = start_campaign(client, third["id"])
        assert job3["result"]["sent"] == 2
        assert job3["result"]["suppressed"] == 1

    def test_pause_and_resume(self, client, db, fake_mail):
        channel_id = make_channel(client, "慢速通道", rate=60)  # 1 秒/封
        theme_id = make_theme(client)
        for index in range(4):
            make_company(db, f"P{index}", email=f"p{index}@x.com")
        campaign = create_campaign(client, theme_id, [channel_id], name="暂停计划")

        resp = client.post(f"/api/v1/campaigns/{campaign['id']}/rounds/1/start")
        job_id = resp.json()["job_id"]

        # 等首封发出后暂停
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            job = client.get(f"/api/v1/jobs/{job_id}").json()
            if job["status"] == "running" and (job["progress"].get("sent") or 0) >= 1:
                break
            time.sleep(0.05)
        client.post(f"/api/v1/campaigns/{campaign['id']}/pause")
        assert client.get(f"/api/v1/campaigns/{campaign['id']}").json()["status"] == "paused"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "paused":
                break
            time.sleep(0.05)
        assert client.get(f"/api/v1/jobs/{job_id}").json()["status"] == "paused"

        client.post(f"/api/v1/campaigns/{campaign['id']}/resume")
        job = wait_job(client, job_id, timeout=30)
        assert job["status"] == "completed"
        assert job["result"]["sent"] == 4
        assert client.get(f"/api/v1/campaigns/{campaign['id']}").json()["status"] == "completed"

    def test_multi_round_followup_excludes_replied(self, client, db, fake_mail):
        channel_id = make_channel(client, "跟进通道")
        theme_id = make_theme(client)
        a = make_company(db, "F1", email="f1@x.com")
        b = make_company(db, "F2", email="f2@x.com")
        c = make_company(db, "F3", email="f3@x.com")

        campaign = create_campaign(
            client, theme_id, [channel_id], name="多轮计划",
            rounds=[{"round_no": 2, "interval_days": 0, "condition": "no_reply_or_progress"}],
        )
        job1 = start_campaign(client, campaign["id"], round_no=1)
        assert job1["result"]["sent"] == 3

        # B 已回复 → 第二轮不进人群（FR-052/054）
        b.status = "replied"
        db.commit()

        job2 = start_campaign(client, campaign["id"], round_no=2)
        assert job2["result"]["sent"] == 2
        round2_records = (
            db.query(SendRecord).filter_by(campaign_id=campaign["id"], round_no=2).all()
        )
        assert len(round2_records) == 2
        assert b.id not in {r.company_id for r in round2_records}
        assert {r.company_id for r in round2_records} == {a.id, c.id}

    def test_retry_failed_from_api(self, client, db, fake_mail):
        channel_id = make_channel(client, "重试通道")
        theme_id = make_theme(client)
        make_company(db, "R1", email="r1@x.com")
        campaign = create_campaign(client, theme_id, [channel_id], name="重试计划")

        class AlwaysFailSender(FakeMailSender):
            def send(self, *, message, timeout_s: float = 60):
                raise ProviderError("network", "网络中断")

        failing = AlwaysFailSender()
        registry.register(
            ProviderManifest(
                kind="mail", type_key="fake_mail_fail_s10", display_name="故障邮箱",
                factory=lambda **kwargs: failing,
            )
        )
        from saler.db.models import Channel

        db.get(Channel, channel_id).config = {"provider": "fake_mail_fail_s10"}
        db.commit()

        job = start_campaign(client, campaign["id"])
        assert job["result"]["failed"] == 1
        record = client.get(f"/api/v1/campaigns/{campaign['id']}/records").json()["items"][0]
        assert record["status"] == "failed" and record["error_message"]

        # 修复通道后人工重试
        db.get(Channel, channel_id).config = {"provider": "fake_mail_s10"}
        db.commit()
        resp = client.post(
            f"/api/v1/campaigns/{campaign['id']}/records/retry",
            json={"record_ids": [record["id"]]},
        )
        assert resp.status_code == 200, resp.text
        job2 = wait_job(client, resp.json()["job_id"], timeout=30)
        assert job2["result"]["sent"] == 1
        record_now = client.get(f"/api/v1/campaigns/{campaign['id']}/records").json()["items"][0]
        assert record_now["status"] == "sent"


class TestCampaignValidation:
    def test_cannot_use_unpublished_content(self, client, db, fake_mail):
        channel_id = make_channel(client, "校验通道")
        resp = client.post("/api/v1/content/themes", json={"name": "未发布主题", "content_type": "email"})
        theme_id = resp.json()["id"]
        client.post(f"/api/v1/content/themes/{theme_id}/variants", json={"lang": "en", "body_md": "draft"})
        bad = client.post(
            "/api/v1/campaigns",
            json={"name": "非法计划", "content_theme_id": theme_id, "channel_ids": [channel_id],
                  "audience": {"filters": {}}},
        )
        assert bad.status_code == 422

    def test_report_and_export(self, client, db, fake_mail):
        channel_id = make_channel(client, "报表通道")
        theme_id = make_theme(client)
        make_company(db, "Rep1", email="rep1@x.com")
        make_company(db, "Rep2", email="rep2@x.com", language="ru")
        campaign = create_campaign(client, theme_id, [channel_id], name="报表计划")
        start_campaign(client, campaign["id"])

        report = client.get(f"/api/v1/campaigns/{campaign['id']}/report").json()
        assert report["totals"]["sent"] == 2
        assert report["by_lang"]["en"]["sent"] == 2
        assert report["by_channel"]["报表通道"]["sent"] == 2
        assert report["by_round"]["1"]["sent"] == 2

        export = client.post(f"/api/v1/campaigns/{campaign['id']}/report/export")
        assert export.status_code == 200, export.text
        assert export.json()["path"]
