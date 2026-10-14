"""单测：检索适配器共用的幌子结果判定（query_terms / looks_like_decoy）。"""

from __future__ import annotations

from saler.providers.search._common import looks_like_decoy, query_terms
from saler.providers.search.base import SearchItem


def item(title: str, url: str = "https://x.example/", snippet: str = "") -> SearchItem:
    return SearchItem(title=title, url=url, snippet=snippet)


class TestQueryTerms:
    def test_strips_quotes_negations_and_operators(self):
        terms = query_terms('"pole line hardware" distributor OR -alibaba contact')
        assert terms == {"pole", "line", "hardware", "distributor", "contact"}

    def test_drops_short_words_and_cjk_runs(self):
        assert query_terms("电气电缆 cable 中国 输电线") == {"cable"}

    def test_empty_when_no_judicable_terms(self):
        assert query_terms("q -x") == set()
        assert query_terms("电气设备") == set()
        assert query_terms("") == set()


class TestLooksLikeDecoy:
    def test_zero_overlap_across_all_items_is_decoy(self):
        items = [item("Pizza in London"), item("Coffee shops in Seattle")]
        assert looks_like_decoy("pole line hardware", items)

    def test_any_overlap_is_not_decoy(self):
        items = [item("Pizza in London"), item("Pole line suppliers")]
        assert not looks_like_decoy("pole line hardware", items)

    def test_url_and_snippet_count_as_overlap(self):
        assert not looks_like_decoy("pole line", [item("Supplier", url="https://pole-line.example/")])
        assert not looks_like_decoy("pole line", [item("Supplier", snippet="pole fittings")])

    def test_word_prefix_counts_but_substring_does_not(self):
        # "poles"≈"pole"（词面前缀）；"online" 含 "line" 子串但不计（实证漏网原因）
        assert not looks_like_decoy("pole line", [item("Pole suppliers", snippet="poles & fittings")])
        assert looks_like_decoy(
            "pole line hardware",
            [item("Get help online", url="https://support.example/online-help")],
        )

    def test_no_terms_or_no_items_never_decoy(self):
        assert not looks_like_decoy("q", [item("Whatever")])
        assert not looks_like_decoy("pole line hardware", [])
