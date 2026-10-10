"""T093 集成测试：S8 全流程——AI 起草母版 → 主题级多语言生成 → 审校 → 发布。"""

from __future__ import annotations

import pytest

from tests.conftest import wait_job


@pytest.fixture()
def fake_llm(monkeypatch):
    from tests.fixtures.fakes.llm_fake import FakeLLMProvider

    provider = FakeLLMProvider(
        script=[
            {"subject": "紧固件工厂直供", "body_md": "您好 {{company_name}}：工厂直供，欢迎来图定制。"},
            {"subject": "Factory Direct Fasteners", "body_md": "Hello {{company_name}}, factory-direct OEM."},
            {"subject": "Крепёж напрямую с завода", "body_md": "Здравствуйте, {{company_name}}!"},
        ]
    )
    monkeypatch.setattr(
        "saler.api.routes.ai.resolve_llm_provider",
        lambda db, provider_id=None: provider,
    )
    return provider


def test_s8_content_flow(client, fake_llm):
    # 1) 建主题（中文母版为源）
    theme = client.post(
        "/api/v1/content/themes",
        json={"name": "首轮开发信", "content_type": "email", "master_lang": "zh"},
    ).json()

    # 2) AI 起草中文母版（job）
    resp = client.post(
        "/api/v1/ai/content/draft",
        json={"theme_id": theme["id"], "brief": "电力金具与紧固件工厂直供，面向东非买家", "tone": "专业克制"},
    )
    assert resp.status_code == 202
    job = wait_job(client, resp.json()["job_id"])
    assert job["status"] == "completed", job

    variants = client.get(f"/api/v1/content/themes/{theme['id']}/variants").json()
    master = next(v for v in variants if v["lang"] == "zh")
    assert master["source"] == "llm_assisted"
    assert "工厂直供" in master["current"]["body_md"]
    assert master["current"]["variables"] == ["company_name"]

    # 3) 主题级多语言生成（一次产出 en/ru，血缘指向母版）
    resp = client.post(
        "/api/v1/ai/content/translate",
        json={"theme_id": theme["id"], "master_variant_id": master["id"], "targets": ["en", "ru"]},
    )
    job = wait_job(client, resp.json()["job_id"])
    assert job["status"] == "completed", job

    variants = client.get(f"/api/v1/content/themes/{theme['id']}/variants").json()
    by_lang = {v["lang"]: v for v in variants}
    assert {"zh", "en", "ru"} <= set(by_lang)
    assert by_lang["en"]["parent_variant_id"] == master["id"]
    assert by_lang["en"]["source"] == "llm_translated"

    # 4) 预览（变量渲染 + 告警）
    preview = client.post(
        f"/api/v1/content/variants/{by_lang['en']['id']}/preview",
        json={"vars": {"company_name": "Acme Kenya"}},
    ).json()
    assert "Acme Kenya" in preview["body"]
    assert preview["warnings"] == []

    # 5) 审校：修改一处并发布（版本+1）
    client.put(
        f"/api/v1/content/variants/{by_lang['en']['id']}",
        json={"body_md": "Hello {{company_name}}, factory-direct OEM. Best regards.", "change_note": "审校后定稿"},
    )
    published = client.post(f"/api/v1/content/variants/{by_lang['en']['id']}/publish").json()
    assert published["status"] == "published"
    versions = client.get(f"/api/v1/content/variants/{by_lang['en']['id']}/versions").json()
    assert versions[0]["version_no"] == 2
    assert "Best regards" in versions[0]["body_md"]

    # 6) 已发布清单（供营销计划选用；未发布的母版不出现在清单中）
    listing = client.get("/api/v1/content/published").json()
    assert {row["lang"] for row in listing} == {"en"}
