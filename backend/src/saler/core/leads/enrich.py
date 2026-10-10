"""国家/语言富化（来源优先级：ccTLD > 手动；html lang；均记录来源字段）。"""

from __future__ import annotations

from sqlalchemy.orm import Session

# 二级公共域名 → 国家（ISO 3166-1 alpha-2）
CC_SECOND_LEVEL = {
    "co.uk": "gb",
    "com.au": "au",
    "co.nz": "nz",
    "co.za": "za",
    "com.br": "br",
    "co.jp": "jp",
    "co.kr": "kr",
    "com.cn": "cn",
    "com.mx": "mx",
    "com.tr": "tr",
    "co.in": "in",
    "com.my": "my",
    "com.sg": "sg",
    "com.hk": "hk",
    "com.tw": "tw",
    "co.id": "id",
    "com.ph": "ph",
    "com.pk": "pk",
    "com.bd": "bd",
    "com.eg": "eg",
    "com.sa": "sa",
    "co.il": "il",
    "com.ar": "ar",
    "com.co": "co",
    "com.pe": "pe",
    "com.ng": "ng",
    "com.vn": "vn",
}


def country_from_domain(domain: str) -> str | None:
    parts = domain.lower().split(".")
    if len(parts) >= 3:
        second_level = ".".join(parts[-2:])
        if second_level in CC_SECOND_LEVEL:
            return CC_SECOND_LEVEL[second_level]
    tld = parts[-1]
    if tld == "uk":
        return "gb"
    if len(tld) == 2 and tld.isalpha():
        return tld
    return None


def enrich_domain(db: Session, domain_row, *, html: str | None = None) -> None:
    """就地富化 domain 行（不 commit；由调用方统一提交）。"""
    from saler.core.leads.parser import html_language

    if not domain_row.country:
        cc = country_from_domain(domain_row.domain)
        if cc:
            domain_row.country = cc
            domain_row.country_source = "cctld"
    if html and not domain_row.language:
        lang = html_language(html)
        if lang:
            domain_row.language = lang
            domain_row.language_source = "html_lang"
