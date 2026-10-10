"""联系方式抽取（FR-020/021）：正则 + 反混淆 + JS 拼接重建 + 分类 + 去重。

工程要点（承自既有行业项目经验）：
- mailto:/tel: 链接是最强信号，优先采集；
- 反混淆：``(at)``/``[at]``/``(dot)``、零宽字符、``js 字符串拼接`` 全部还原后再匹配；
- 噪音过滤：图片伪邮箱（logo@2x.png）、角色噪声（noreply@）、占位域名（example 等）；
- 占位/可疑地址保留但标记 ``suspicious``（人工复核），误伤与漏采都可控。
"""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from urllib.parse import unquote

from selectolax.lexbor import LexborHTMLParser

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
MAILTO_RE = re.compile(r"mailto:([^?\"'<>\s]+)", re.IGNORECASE)
TEL_RE = re.compile(r"tel:([+0-9()\-.\s]{7,20})", re.IGNORECASE)
INTL_PHONE_RE = re.compile(r"\+\d[\d\s\-().]{8,17}\d")
WA_LINK_RE = re.compile(
    r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp://send\?phone=)(\+?\d{7,15})",
    re.IGNORECASE,
)
_JS_SIDE = r"(?:'([^']{1,64})'|\"([^\"]{1,64})\"|\b([A-Za-z_$][\w$]{0,40})\b)"
JS_JOIN_RE = re.compile(
    rf"{_JS_SIDE}\s*\+\s*['\"]@['\"]\s*\+\s*{_JS_SIDE}", re.IGNORECASE
)
JS_STRING_VAR_RE = re.compile(
    r"(?:var|let|const)\s+([A-Za-z_$][\w$]{0,40})\s*=\s*(?:'([^']{1,64})'|\"([^\"]{1,64})\")"
)
FB_RE = re.compile(r"https?://(?:www\.|m\.|web\.)?facebook\.com/([A-Za-z0-9._\-/]+)", re.IGNORECASE)
LI_RE = re.compile(
    r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:company|in)/([A-Za-z0-9._\-]+)", re.IGNORECASE
)
X_RE = re.compile(r"https?://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]{2,30})", re.IGNORECASE)
IG_RE = re.compile(r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9._]{2,30})", re.IGNORECASE)
WECHAT_RE = re.compile(r"(?:微信|wechat|weixin)[:：\s]*(?:id[:：\s]*)?([A-Za-z][A-Za-z0-9_\-]{4,20})", re.IGNORECASE)

ZERO_WIDTH_TABLE = dict.fromkeys(map(ord, "​‌‍﻿"), None)
OBS_AT = re.compile(r"\s*(?:\(at\)|\[at\]|\{at\})\s*", re.IGNORECASE)
OBS_DOT = re.compile(r"\s*(?:\(dot\)|\[dot\]|\{dot\})\s*", re.IGNORECASE)

ASSET_TLDS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "css", "js", "ico", "bmp", "avif"}
DROP_LOCAL_PARTS = {
    "noreply", "no-reply", "donotreply", "do-not-reply", "postmaster", "abuse",
    "privacy", "webmaster", "hostmaster",
}
SUSPICIOUS_DOMAINS = (
    "example.com", "yourdomain", "your-domain", "domain.com", "mydomain", "test.com", "nospam",
)
PROCUREMENT_WORDS = (
    "purchase", "purchasing", "procure", "procurement", "sourcing", "buyer", "buying",
)
SALES_WORDS = ("sales", "market", "export", "trade", "business", "commercial", "order")
GENERAL_WORDS = ("info", "contact", "hello", "office", "enquir", "enquiry", "inquiry", "admin")

SOCIAL_HOSTS = {
    "facebook": "www.facebook.com",
    "linkedin": "www.linkedin.com",
    "x": "x.com",
    "instagram": "www.instagram.com",
}
SOCIAL_BLOCKLIST = {
    "sharer", "share", "dialog", "plugins", "tr", "intent", "profile.php", "pages", "groups",
}


@dataclass
class ExtractedContact:
    type: str
    value: str
    value_normalized: str
    category: str = "general"
    validity: str = "valid"
    source_url: str | None = None


def classify_email(local_part: str) -> str:
    local = local_part.lower()
    for word in PROCUREMENT_WORDS:
        if word in local:
            return "procurement"
    for word in SALES_WORDS:
        if word in local:
            return "sales"
    for word in GENERAL_WORDS:
        if word in local:
            return "general"
    return "other"


def normalize_email(raw: str) -> str | None:
    """规范化邮箱；返回 None 表示应丢弃（资源伪邮箱/角色噪声/格式错误）。"""
    value = raw.strip().strip(".,;:()<>\"'").lower()
    if value.count("@") != 1:
        return None
    local, _, domain = value.partition("@")
    if not local or not domain or "." not in domain or " " in value:
        return None
    tld = domain.rsplit(".", 1)[-1]
    if tld in ASSET_TLDS:
        return None
    if local in DROP_LOCAL_PARTS:
        return None
    return f"{local}@{domain}"


_clean_email = normalize_email  # 兼容内部旧引用


def _is_suspicious(domain: str) -> bool:
    return any(marker in domain for marker in SUSPICIOUS_DOMAINS)


def _normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if not (7 <= len(digits) <= 15):
        return None
    if raw.strip().startswith("+") or len(digits) >= 10:
        return f"+{digits}" if len(digits) >= 10 else None
    return None


def _plain_text(html: str) -> str:
    tree = LexborHTMLParser(html)
    body = tree.body or tree.root
    if body is None:
        return html
    return html_lib.unescape(body.text(deep=True, separator=" ") or "")


def extract_contacts(html: str, *, page_url: str) -> list[ExtractedContact]:
    raw = html.translate(ZERO_WIDTH_TABLE)
    collected: dict[tuple[str, str], ExtractedContact] = {}

    def add(contact: ExtractedContact) -> None:
        collected.setdefault((contact.type, contact.value_normalized), contact)

    def add_email(candidate: str, original: str) -> None:
        normalized = _clean_email(candidate)
        if normalized is None:
            return
        local, _, domain = normalized.partition("@")
        add(
            ExtractedContact(
                type="email",
                value=original.strip(),
                value_normalized=normalized,
                category=classify_email(local),
                validity="suspicious" if _is_suspicious(domain) else "valid",
                source_url=page_url,
            )
        )

    # 1) mailto: 链接（最强信号）
    for match in MAILTO_RE.finditer(raw):
        add_email(html_lib.unescape(match.group(1)), match.group(1))
    # 2) JS 字符串拼接还原（支持一层变量：var user = 'export'）
    js_vars: dict[str, str] = {}
    for var_match in JS_STRING_VAR_RE.finditer(raw):
        js_vars[var_match.group(1)] = var_match.group(2) or var_match.group(3) or ""

    def _js_side(match, base: int) -> str:
        return (
            match.group(base)
            or match.group(base + 1)
            or js_vars.get(match.group(base + 2), "")
        )

    for join_match in JS_JOIN_RE.finditer(raw):
        local_part = _js_side(join_match, 1)
        domain_part = _js_side(join_match, 4)
        if local_part and domain_part:
            add_email(f"{local_part}@{domain_part}", f"{local_part}@{domain_part}")
    # 3) 文本通道：原文 + 反混淆还原文本
    text = _plain_text(raw)
    obfuscated = OBS_DOT.sub(".", OBS_AT.sub("@", text))
    for corpus in (text, obfuscated):
        for match in EMAIL_RE.finditer(corpus):
            add_email(match.group(0), match.group(0))
    # 4) 电话：tel: 链接 + 文本中的国际号码
    for match in TEL_RE.finditer(raw):
        phone = _normalize_phone(match.group(1))
        if phone:
            add(ExtractedContact("phone", match.group(1).strip(), phone, "general", "valid", page_url))
    for match in INTL_PHONE_RE.finditer(text):
        phone = _normalize_phone(match.group(0))
        if phone:
            add(ExtractedContact("phone", match.group(0).strip(), phone, "general", "valid", page_url))
    # 5) WhatsApp 链接（含 wa.me / api.whatsapp）
    for match in WA_LINK_RE.finditer(raw + " " + unquote(raw)):
        digits = re.sub(r"\D", "", match.group(1))
        if 7 <= len(digits) <= 15:
            add(ExtractedContact("whatsapp", match.group(0), digits, "general", "valid", page_url))
    # 6) 社媒链接
    for regex, type_key in ((FB_RE, "facebook"), (LI_RE, "linkedin"), (X_RE, "x"), (IG_RE, "instagram")):
        for match in regex.finditer(raw):
            handle = match.group(1).strip("/").lower()
            if not handle or handle.split("/")[0] in SOCIAL_BLOCKLIST:
                continue
            normalized = f"https://{SOCIAL_HOSTS[type_key]}/{handle}"
            add(ExtractedContact(type_key, normalized, normalized, "general", "valid", page_url))
    # 7) 微信 ID
    for match in WECHAT_RE.finditer(text):
        handle = match.group(1).strip().lower()
        add(ExtractedContact("wechat", handle, handle, "general", "valid", page_url))

    return list(collected.values())
