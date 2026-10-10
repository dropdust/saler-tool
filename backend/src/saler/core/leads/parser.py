"""页面解析：语言/标题提取与联系页候选发现（selectolax lexbor 后端）。"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

from selectolax.lexbor import LexborHTMLParser

CONTACT_HINTS = (
    "contact",
    "kontakt",
    "kontak",
    "contato",
    "contacto",
    "联系",
    "문의",
)

_SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:")


def _strip_www(netloc: str) -> str:
    return netloc.lower().removeprefix("www.")


def html_language(html: str) -> str | None:
    """从 <html lang> 取主语言（如 en-US → en）。"""
    tree = LexborHTMLParser(html)
    node = tree.css_first("html")
    if node is None:
        return None
    lang = (node.attributes or {}).get("lang")
    if not lang:
        return None
    return lang.split("-")[0].strip().lower() or None


def page_title(html: str) -> str | None:
    tree = LexborHTMLParser(html)
    node = tree.css_first("title")
    if node is None:
        return None
    title = node.text(strip=True)
    return title[:300] if title else None


def contact_page_links(html: str, *, base_url: str, limit: int = 4) -> list[str]:
    """发现同站联系页候选（href 或锚文本含 contact 等关键词）。"""
    if limit <= 0:
        return []
    tree = LexborHTMLParser(html)
    base_host = _strip_www(urlparse(base_url).netloc)
    found: list[str] = []
    seen: set[str] = set()
    for node in tree.css("a"):
        href = (node.attributes or {}).get("href", "")
        if not href or href.startswith(_SKIP_SCHEMES):
            continue
        href_lower = href.lower()
        text_lower = (node.text(strip=True) or "").lower()
        if not any(hint in href_lower or hint in text_lower for hint in CONTACT_HINTS):
            continue
        absolute = urljoin(base_url, href).split("#")[0]
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        if _strip_www(parsed.netloc) != base_host:
            continue  # 只走同站联系页
        if absolute in seen or absolute.rstrip("/") == base_url.rstrip("/"):
            continue
        seen.add(absolute)
        found.append(absolute)
        if len(found) >= limit:
            break
    return found
