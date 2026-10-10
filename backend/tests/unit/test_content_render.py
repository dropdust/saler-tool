"""T091 单元测试：内容渲染（变量/告警）与语言匹配回退（FR-035/036/039）。"""

from __future__ import annotations

from saler.core.content.match import choose_variant
from saler.core.content.render import parse_variables, render

# ---------- 渲染 ----------


def test_parse_variables_unique_and_ordered():
    text = "Hi {{company_name}}, {{ contact_name }} again {{company_name}}"
    assert parse_variables(text) == ["company_name", "contact_name"]


def test_render_replaces_and_warns_missing():
    rendered, warnings = render(
        "Hello {{company_name}}, buy from {{sender_name}} in {{country}}",
        {"company_name": "Acme", "sender_name": "Runte"},
    )
    assert rendered == "Hello Acme, buy from Runte in "
    assert len(warnings) == 1
    assert "country" in warnings[0]


def test_render_warns_unknown_variable():
    rendered, warnings = render("{{weird_token}} ok", {"company_name": "Acme"})
    assert rendered == " ok"
    assert any("weird_token" in w for w in warnings)


def test_render_no_variables_passthrough():
    rendered, warnings = render("plain text", {})
    assert rendered == "plain text"
    assert warnings == []


# ---------- 语言匹配 ----------


VARIANTS = {"en": "EN_CARD", "zh": "ZH_CARD"}


def test_auto_match_by_customer_language():
    card, lang, fallback = choose_variant(VARIANTS, customer_lang="en")
    assert (card, lang, fallback) == ("EN_CARD", "en", False)


def test_auto_fallback_marked_when_language_missing():
    card, lang, fallback = choose_variant(VARIANTS, customer_lang="ru", fallback_lang="en")
    assert (card, lang, fallback) == ("EN_CARD", "en", True)


def test_language_region_falls_back_to_main_code():
    card, lang, fallback = choose_variant(VARIANTS, customer_lang="zh-CN")
    assert (card, lang, fallback) == ("ZH_CARD", "zh", False)


def test_fixed_strategy_overrides_customer_language():
    card, lang, fallback = choose_variant(
        VARIANTS, customer_lang="ru", strategy="fixed", fixed_lang="zh"
    )
    assert (card, lang, fallback) == ("ZH_CARD", "zh", False)


def test_fixed_language_missing_uses_fallback():
    card, lang, fallback = choose_variant(
        VARIANTS, customer_lang="ru", strategy="fixed", fixed_lang="ar", fallback_lang="en"
    )
    assert (card, lang, fallback) == ("EN_CARD", "en", True)


def test_empty_variants_returns_none():
    assert choose_variant({}, customer_lang="en") == (None, None, False)
