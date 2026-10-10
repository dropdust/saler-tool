"""T048 单元测试：联系方式抽取（FR-020/021）——反混淆/JS 拼接/防爬噪点/分类/去重。"""

from __future__ import annotations

from pathlib import Path

from saler.core.leads.extractor import ExtractedContact, extract_contacts

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "html"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _by_value(contacts: list[ExtractedContact]) -> dict[str, ExtractedContact]:
    return {contact.value_normalized: contact for contact in contacts}


class TestSimplePage:
    def test_emails_phones_whatsapp_socials(self):
        contacts = extract_contacts(_load("simple.html"), page_url="https://acme.co.ke/contact")
        by_value = _by_value(contacts)

        sales = by_value["sales@acme.co.ke"]
        assert sales.type == "email" and sales.category == "sales"
        purchase = by_value["purchase.manager@acme.co.ke"]
        assert purchase.category == "procurement"
        assert purchase.source_url == "https://acme.co.ke/contact"

        phone = by_value["+254712345678"]
        assert phone.type == "phone"

        whatsapp = [c for c in contacts if c.type == "whatsapp"]
        assert whatsapp and whatsapp[0].value_normalized == "254712345678"

        facebook = [c for c in contacts if c.type == "facebook"]
        assert facebook and "acmekenya" in facebook[0].value_normalized
        linkedin = [c for c in contacts if c.type == "linkedin"]
        assert linkedin and "acme-limited" in linkedin[0].value_normalized
        assert "trk=abc" not in linkedin[0].value_normalized  # 查询串去除


class TestDeobfuscation:
    def test_at_dot_patterns_and_zero_width(self):
        contacts = extract_contacts(_load("obfuscated.html"), page_url="https://acme.de/kontakt")
        emails = {c.value_normalized for c in contacts if c.type == "email"}
        assert {"info@acme.de", "verkauf@acme.de", "support@acme.de", "presse@acme.de"} <= emails

    def test_image_like_address_not_treated_as_email(self):
        contacts = extract_contacts(_load("obfuscated.html"), page_url="https://acme.de/kontakt")
        assert all(not c.value_normalized.endswith(".png") for c in contacts)


class TestJsJoin:
    def test_concatenated_email_reconstructed(self):
        contacts = extract_contacts(_load("jsjoin.html"), page_url="https://acme-tools.com/")
        emails = {c.value_normalized: c for c in contacts if c.type == "email"}
        assert "export@acme-tools.com" in emails
        assert emails["export@acme-tools.com"].category == "sales"


class TestNoiseFiltering:
    def test_placeholders_and_decoys(self):
        contacts = extract_contacts(_load("noise.html"), page_url="https://acme.cn/")
        by_value = _by_value(contacts)

        # 占位/示例/诱饵：保留但标 suspicious
        assert by_value["your.name@yourdomain.com"].validity == "suspicious"
        assert by_value["info@example.com"].validity == "suspicious"
        assert by_value["info@foo.com.nospam"].validity == "suspicious"

        # 噪音：直接丢弃
        assert "noreply@acme.com" not in by_value
        assert "hero@3x.webp" not in by_value

        # 中文语境：微信 ID
        wechat = [c for c in contacts if c.type == "wechat"]
        assert wechat and wechat[0].value_normalized == "acmecn"


class TestDedupe:
    def test_duplicates_collapse(self):
        html = (
            '<p><a href="mailto:Sales@Acme.co.ke">Sales@Acme.co.ke</a></p>'
            '<p>销售邮箱 sales@acme.co.ke</p>'
        )
        contacts = extract_contacts(html, page_url="https://acme.co.ke/")
        emails = [c for c in contacts if c.type == "email"]
        assert len(emails) == 1
        assert emails[0].value_normalized == "sales@acme.co.ke"
