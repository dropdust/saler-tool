"""语言匹配（FR-036）：按客户"使用语言"选版本；缺失回退并标注 fallback_used。

策略：``auto`` 按客户语言；``fixed`` 固定语言；两者都遵循 fallback_lang → en 的回退链。
"""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


def _pick(variants: dict[str, T], lang: str | None) -> str | None:
    if not lang:
        return None
    lang = lang.lower()
    if lang in variants:
        return lang
    main = lang.split("-")[0]
    return main if main in variants else None


def choose_variant(
    variants: dict[str, T],
    *,
    customer_lang: str | None,
    strategy: str = "auto",
    fixed_lang: str | None = None,
    fallback_lang: str = "en",
) -> tuple[T | None, str | None, bool]:
    """返回 (variant, 实际使用语言, 是否回退)。variants 的键为语言码。"""
    if not variants:
        return None, None, False
    target = fixed_lang if strategy == "fixed" else customer_lang
    hit = _pick(variants, target)
    if hit:
        return variants[hit], hit, False
    for candidate in (fallback_lang, "en"):
        hit = _pick(variants, candidate)
        if hit:
            return variants[hit], hit, True
    key = next(iter(variants))
    return variants[key], key, True
