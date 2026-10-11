"""CzechCrunch (cc.cz) – zprávy o investičních kolech (tier C).

Dva vstupy:
  * kategorie „Startupy“ (stránkovaná, s datem) – objevování investorů nezávisle na registrech,
  * stránky tagů investorů (/tag/<slug>/) – cílené dohledání dokladů ke konkrétnímu investorovi.
robots.txt cc.cz tyto stránky povoluje.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from ..http import Fetcher

BASE = "https://cc.cz"


@dataclass
class ArticleRef:
    url: str
    title: str
    date: str  # ISO datum publikace


@dataclass
class Article:
    url: str
    title: str
    date: str
    paragraphs: list[str] = field(default_factory=list)
    sha256: str = ""


def _text(node) -> str:
    return re.sub(r"\s+", " ", html.unescape(node.text(separator=" "))).replace("\xa0", " ").strip()


def _listing(page_html: str) -> list[ArticleRef]:
    tree = HTMLParser(page_html)
    out = []
    for post in tree.css("div.b-post"):
        a = post.css_first(".b-post__title a")
        t = post.css_first("time.entry-date")
        if not a or not t:
            continue
        out.append(ArticleRef(a.attributes.get("href", ""), _text(a),
                              (t.attributes.get("datetime") or "")[:10]))
    return out


def crawl_category(f: Fetcher, category: str, since: str, max_pages: int = 120) -> list[ArticleRef]:
    """Projde stránky kategorie od nejnovějších, dokud nenarazí na články starší než `since`."""
    out: list[ArticleRef] = []
    for page in range(1, max_pages + 1):
        url = f"{BASE}/{category}/" if page == 1 else f"{BASE}/{category}/page/{page}/"
        r = f.get(url)
        if r.status != 200:
            # první stránka kategorie občas vrací prázdnou odpověď – zkus /page/1/
            if page == 1:
                r = f.get(f"{BASE}/{category}/page/1/")
            if r.status != 200:
                break
        refs = _listing(r.text)
        if not refs:
            break
        out.extend(x for x in refs if x.date >= since)
        if min(x.date for x in refs) < since:
            break
    return out


def investor_tags(f: Fetcher) -> list[str]:
    """Slugy všech tagů z tagových sitemap (deduplikované)."""
    idx = f.get(f"{BASE}/sitemap_index.xml").text
    slugs: set[str] = set()
    for sm in re.findall(r"<loc>(https://cc\.cz/post_tag-sitemap\d*\.xml)</loc>", idx):
        for u in re.findall(r"<loc>https://cc\.cz/tag/([^/<]+)/</loc>", f.get(sm).text):
            slugs.add(u)
    return sorted(slugs)


def fetch_tag(f: Fetcher, slug: str, since: str, max_pages: int = 3) -> tuple[str, list[ArticleRef]]:
    """Vrátí (název tagu, články v okně aktivity)."""
    out: list[ArticleRef] = []
    title = ""
    for page in range(1, max_pages + 1):
        url = f"{BASE}/tag/{slug}/" + ("" if page == 1 else f"page/{page}/")
        r = f.get(url)
        if r.status != 200:
            break
        if page == 1:
            h = HTMLParser(r.text).css_first("h1.b-title")
            title = _text(h) if h else ""
        refs = _listing(r.text)
        if not refs:
            break
        out.extend(x for x in refs if x.date >= since)
        if min(x.date for x in refs) < since:
            break
    return title, out


def fetch_article(f: Fetcher, url: str) -> Article:
    r = f.get(url)
    tree = HTMLParser(r.text)
    meta = tree.css_first('meta[property="article:published_time"]')
    date = (meta.attributes.get("content") or "")[:10] if meta else ""
    h1 = tree.css_first("h1")
    a = Article(url=url, title=_text(h1) if h1 else "", date=date, sha256=r.sha256)
    perex = tree.css_first(".b-content__hd .b-content__perex, .b-content__hd p")
    if perex:
        a.paragraphs.append(_text(perex))
    body = tree.css_first(".b-content__bd")
    if body:
        for p in body.css("p, li, h2, h3"):
            if _in_widget(p):
                continue
            t = _text(p)
            if len(t) > 20:
                a.paragraphs.append(t)
    return a


_WIDGET = re.compile(r"\b(b-google-follow|c-widget|b-newsletter|b-related|b-ad)")


def _in_widget(node) -> bool:
    par = node.parent
    while par is not None and par.tag != "body":
        cls = (par.attributes or {}).get("class") or ""
        if _WIDGET.search(cls):
            return True
        par = par.parent
    return False
