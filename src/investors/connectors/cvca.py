"""CVCA (Czech Private Equity & Venture Capital Association) – profily řádných členů.

Profil obsahuje strukturovaná pole (objem ve správě, typ investic, preferovaná výše
investice, odvětví, portfolio). Kontaktní osoby se záměrně neukládají; z e-mailu
se bere jen doména jako nápověda k webu investora.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from ..http import Fetcher

LIST_URL = "https://cvca.cz/clenstvi/radni-clenove/"

LABELS = {
    "Objem prostředků ve správě": "aum",
    "Typ investic": "investment_type",
    "Preferovaná výše jedné investice": "ticket",
    "Preferovaná odvětví": "sectors",
    "Geografické zaměření": "geography",
    "Počet transakcí v ČR": "deals_cz",
    "Stávající portfolio v ČR": "portfolio_cz",
    "Stávající portfolio mimo ČR": "portfolio_abroad",
}
STOP_LABELS = ["Adresa", "Kontaktní osoba", "Informace o společnosti"]


@dataclass
class CvcaProfile:
    name: str
    url: str
    published: str = ""            # datum vydání profilu na webu CVCA (ISO)
    address: str = ""
    legal_name: str = ""
    country_hint: str = ""
    website: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    text: str = ""
    sha256: str = ""


def _iso(d: str) -> str:
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", d)
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else ""


def list_members(f: Fetcher) -> list[tuple[str, str, str]]:
    """[(název, url profilu, datum)]"""
    r = f.get(LIST_URL)
    tree = HTMLParser(r.text)
    out = []
    for item in tree.css("div.rt-grid-item"):
        a = item.css_first("h2.entry-title a")
        if not a:
            continue
        date_el = item.css_first("span.date")
        out.append((a.text(strip=True), a.attributes.get("href", ""),
                    _iso(date_el.text() if date_el else "")))
    return out


def _lines(node_html: str) -> list[str]:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", node_html, flags=re.S)
    t = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>|</div>|</tr>|</td>|</strong>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).replace("\xa0", " ")
    return [re.sub(r"\s+", " ", x).strip() for x in t.split("\n") if x.strip()]


def fetch_profile(f: Fetcher, name: str, url: str, published: str) -> CvcaProfile:
    r = f.get(url)
    tree = HTMLParser(r.text)
    art = tree.css_first("article") or tree.body
    lines = _lines(art.html)
    p = CvcaProfile(name=name, url=url, published=published, sha256=r.sha256,
                    text="\n".join(lines))
    # Adresa: řádky mezi "Adresa" a "Kontaktní osoba"
    if "Adresa" in lines:
        i = lines.index("Adresa")
        addr = []
        for x in lines[i + 1:]:
            if x in STOP_LABELS or x in LABELS:
                break
            addr.append(x)
        p.address = ", ".join(addr)
        if addr:
            p.legal_name = addr[0]
        low = p.address.lower()
        if re.search(r"praha|brno|ostrava|plzeň|olomouc|česk|\b\d{3}\s?\d{2}\b", low):
            p.country_hint = "CZ"
        for cc, pat in {"PL": "poland|polsko|warsaw|varšava", "SK": "slovensk|bratislava",
                        "UK": "london|united kingdom", "AT": "wien|vienna|austria",
                        "HU": "budapest|hungary"}.items():
            if re.search(pat, low):
                p.country_hint = cc
    for i, x in enumerate(lines):
        key = LABELS.get(x)
        if key and i + 1 < len(lines) and lines[i + 1] not in LABELS:
            p.fields[key] = lines[i + 1]
    # web: explicitní www odkaz, jinak doména z e-mailu
    m = re.search(r"\b(www\.[a-z0-9\-\.]+\.[a-z]{2,})", p.text, re.I)
    if m:
        p.website = "https://" + m.group(1).lower()
    else:
        m = re.search(r"@([a-z0-9\-]+\.[a-z0-9\-\.]+)", p.text, re.I)
        if m and not re.search(r"gmail|seznam|email|outlook", m.group(1), re.I):
            p.website = "https://" + m.group(1).lower()
    return p


def fetch_all(f: Fetcher) -> list[CvcaProfile]:
    return [fetch_profile(f, n, u, d) for n, u, d in list_members(f)]
