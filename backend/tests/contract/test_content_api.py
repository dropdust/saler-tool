"""T092 契约测试：内容版本/发布流转/恢复=新版本/未发布不可用于计划（FR-037）。"""

from __future__ import annotations


def _mk_theme(client, name="首轮开发信"):
    resp = client.post(
        "/api/v1/content/themes", json={"name": name, "content_type": "email", "master_lang": "zh"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _mk_variant(client, theme_id, lang="zh", subject="你好", body="买 {{product}}"):
    resp = client.post(
        f"/api/v1/content/themes/{theme_id}/variants",
        json={"lang": lang, "subject": subject, "body_md": body},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestThemeVariantCrud:
    def test_create_theme_and_unique_name(self, client):
        theme = _mk_theme(client)
        assert theme["master_lang"] == "zh"
        dup = client.post("/api/v1/content/themes", json={"name": "首轮开发信"})
        assert dup.status_code == 409

    def test_variant_unique_per_lang(self, client):
        theme = _mk_theme(client)
        _mk_variant(client, theme["id"], lang="zh")
        dup = client.post(
            f"/api/v1/content/themes/{theme['id']}/variants",
            json={"lang": "zh", "subject": "x", "body_md": "y"},
        )
        assert dup.status_code == 409

    def test_detail_includes_current_version_and_variables(self, client):
        theme = _mk_theme(client)
        _mk_variant(client, theme["id"], body="Hi {{company_name}} from {{sender_name}}")
        detail = client.get(f"/api/v1/content/themes/{theme['id']}/variants").json()
        assert detail[0]["current"]["body_md"].startswith("Hi")
        assert detail[0]["current"]["variables"] == ["company_name", "sender_name"]


class TestVersioning:
    def test_edit_creates_new_version_and_restore_creates_another(self, client):
        theme = _mk_theme(client)
        variant = _mk_variant(client, theme["id"], body="V1 内容")
        client.put(
            f"/api/v1/content/variants/{variant['id']}",
            json={"body_md": "V2 内容", "change_note": "二稿"},
        )
        versions = client.get(f"/api/v1/content/variants/{variant['id']}/versions").json()
        assert [v["version_no"] for v in versions] == [2, 1]

        restored = client.post(
            f"/api/v1/content/variants/{variant['id']}/restore", json={"version_no": 1}
        ).json()
        assert restored["version_no"] == 3
        assert restored["body_md"] == "V1 内容"  # 恢复=以旧内容创建新版本
        detail = client.get(f"/api/v1/content/variants/{variant['id']}").json()
        assert detail["current"]["version_no"] == 3

    def test_editing_published_variant_returns_to_draft(self, client):
        theme = _mk_theme(client)
        variant = _mk_variant(client, theme["id"])
        client.post(f"/api/v1/content/variants/{variant['id']}/publish")
        assert client.get(f"/api/v1/content/variants/{variant['id']}").json()["status"] == "published"
        client.put(f"/api/v1/content/variants/{variant['id']}", json={"body_md": "改一版"})
        assert client.get(f"/api/v1/content/variants/{variant['id']}").json()["status"] == "draft"


class TestPublishFlow:
    def test_publish_archive(self, client):
        theme = _mk_theme(client)
        variant = _mk_variant(client, theme["id"])
        assert client.post(f"/api/v1/content/variants/{variant['id']}/publish").json()["status"] == "published"
        assert client.post(f"/api/v1/content/variants/{variant['id']}/archive").json()["status"] == "archived"

    def test_publish_requires_nonempty_content(self, client):
        theme = _mk_theme(client)
        variant = _mk_variant(client, theme["id"], subject="", body="")
        resp = client.post(f"/api/v1/content/variants/{variant['id']}/publish")
        assert resp.status_code == 422

    def test_published_variants_listing_gate(self, client):
        theme = _mk_theme(client)
        draft = _mk_variant(client, theme["id"], lang="zh")
        published = _mk_variant(client, theme["id"], lang="en")
        client.post(f"/api/v1/content/variants/{published['id']}/publish")
        rows = client.get("/api/v1/content/published").json()
        langs = {row["lang"] for row in rows}
        assert langs == {"en"}
        assert draft["status"] == "draft"


class TestPreview:
    def test_preview_renders_variables_with_warnings(self, client):
        theme = _mk_theme(client)
        variant = _mk_variant(
            client, theme["id"], subject="To {{company_name}}", body="Hello {{company_name}} / {{missing_x}}"
        )
        body = client.post(
            f"/api/v1/content/variants/{variant['id']}/preview",
            json={"vars": {"company_name": "Acme"}},
        ).json()
        assert body["subject"] == "To Acme"
        assert "Hello Acme" in body["body"]
        assert body["warnings"]

    def test_preview_with_company_id(self, client):
        theme = _mk_theme(client)
        variant = _mk_variant(client, theme["id"], body="Hello {{company_name}}")
        import_resp = client.post(
            "/api/v1/companies/import",
            json={"content": "email,company_name\nbuyer@acme.com,Acme Importer\n"},
        )
        from tests.conftest import wait_job

        wait_job(client, import_resp.json()["job_id"])
        company_id = client.get("/api/v1/companies").json()["items"][0]["id"]
        body = client.post(
            f"/api/v1/content/variants/{variant['id']}/preview",
            json={"company_id": company_id},
        ).json()
        assert "Acme Importer" in body["body"]
