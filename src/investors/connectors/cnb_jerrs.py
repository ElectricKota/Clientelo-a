"""ČNB JERRS – veřejné „Základní seznamy“ regulovaných a registrovaných subjektů.

Webové služby WS JERRS vyžadují certifikát a žádost, proto čteme veřejné HTML
sestavy (nestránkované, p_rec_per_page=108).
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..http import Fetcher

BASE = "https://jerrs.cnb.cz/apljerrsdad/"

# Index sestavy (p_ses_idx) -> (kód seznamu, popis). Indexy ověřeny 2026-10-11.
LISTS = {
    238: ("ZISIF_PAR15", "Osoby dle § 15 odst. 1 ZISIF (správci pod rozhodným limitem)"),
    53: ("IS", "Investiční společnosti"),
    375: ("IF_MANAGERS", "Investiční fondy vč. podfondů a jejich obhospodařovatel"),
}


@dataclass
class JerrsEntity:
    ico: str
    name: str
    list_code: str
    city: str = ""
    country: str = ""
    since: str = ""          # datum zápisu do seznamu (ISO)
    manager_ico: str = ""    # jen pro fondy
    manager_name: str = ""
    parent_name: str = ""    # u podfondu název mateřského fondu
    source_url: str = ""
    sha256: str = ""


def _clean(s: str) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def _iso(d: str) -> str:
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", d)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def list_url(idx: int, on: date) -> str:
    return (f"{BASE}JERRS.WEB15.BASIC_LISTINGS_RESPONSE_3?p_lang=cz"
            f"&p_DATUM={on:%d.%m.%Y}&p_hie=HI&p_rec_per_page=108&p_ses_idx={idx}")


def _rows(page: str) -> list[list[str]]:
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", page, re.S):
        cells = re.findall(r"<td class=\"tableDetail[^\"]*\"[^>]*>(.*?)</td>", tr, re.S)
        if cells:
            rows.append([_clean(c) for c in cells])
    return rows


SNAPSHOT_DIR = Path(__file__).resolve().parents[3] / "data" / "snapshots" / "jerrs"


class CaptchaRequired(RuntimeError):
    pass


def _load(f: Fetcher, idx: int, on: date) -> tuple[str, str, str]:
    """Vrátí (html, url, sha256). Přednost má datovaný snapshot v repu.

    JERRS při strojovém přístupu zobrazuje CAPTCHA. Tu NEOBCHÁZÍME: pokud
    snapshot chybí a server vrátí CAPTCHA, je potřeba sestavu otevřít
    v prohlížeči a uložit HTML do data/snapshots/jerrs/jerrs_<idx>_<datum>.html.
    """
    url = list_url(idx, on)
    snaps = sorted(SNAPSHOT_DIR.glob(f"jerrs_{idx}_*.html"))
    if snaps:
        text = snaps[-1].read_text(encoding="utf-8")
        snap_date = snaps[-1].stem.split("_")[-1]
        return text, list_url(idx, date.fromisoformat(snap_date)), hashlib.sha256(text.encode()).hexdigest()
    r = f.get(url, use_cache=False)
    if "CAPTCHA" in r.text:
        raise CaptchaRequired(
            f"JERRS vyžaduje CAPTCHA. Otevřete {url} v prohlížeči a uložte HTML do "
            f"{SNAPSHOT_DIR}/jerrs_{idx}_{on.isoformat()}.html")
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    (SNAPSHOT_DIR / f"jerrs_{idx}_{on.isoformat()}.html").write_text(r.text, encoding="utf-8")
    return r.text, url, r.sha256


def fetch_list(f: Fetcher, idx: int, on: date) -> list[JerrsEntity]:
    code, _ = LISTS[idx]
    text, url, sha = _load(f, idx, on)
    out: list[JerrsEntity] = []
    for c in _rows(text):
        if idx == 375:
            # Fond IČO | Fond název | Podfond IČO | Podfond název | Obhosp. IČO | Obhosp. název | ...
            if len(c) < 6:
                continue
            fund_ico, fund_name, sub_ico, sub_name, m_ico, m_name = c[:6]
            ico, name = (sub_ico, sub_name) if sub_name else (fund_ico, fund_name)
            if not name:
                continue
            out.append(JerrsEntity(ico=ico, name=name, list_code=code,
                                   parent_name=fund_name if sub_name else "",
                                   manager_ico=m_ico, manager_name=m_name,
                                   country="CZ", source_url=url, sha256=sha))
        else:
            # IČO | název | ulice | obec | PSČ | země | datum od
            if len(c) < 7:
                continue
            out.append(JerrsEntity(ico=c[0], name=c[1], list_code=code, city=c[3],
                                   country=c[5], since=_iso(c[6]),
                                   source_url=url, sha256=sha))
    return out


def fetch_all(f: Fetcher, on: date) -> list[JerrsEntity]:
    out: list[JerrsEntity] = []
    for idx in LISTS:
        out.extend(fetch_list(f, idx, on))
    return out
