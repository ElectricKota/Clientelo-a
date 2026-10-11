"""ARES (Ministerstvo financí) – veřejné REST API ekonomických subjektů.

* /ekonomicke-subjekty/{ico}          – existence, sídlo, právní forma, datum zániku
* /ekonomicke-subjekty/vyhledat       – vyhledání podle obchodního jména
* /ekonomicke-subjekty-vr/{ico}       – výpis z obchodního rejstříku vč. společníků

Z výpisu VR se ukládají jen společníci – PRÁVNICKÉ osoby (žádné osobní údaje).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..http import Fetcher

BASE = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest"


@dataclass
class AresSubject:
    ico: str
    name: str
    country: str
    city: str
    legal_form: str
    founded: str
    dissolved: str
    url: str
    sha256: str


@dataclass
class Shareholder:
    ico: str
    name: str
    since: str
    until: str


def _subject(d: dict, url: str, sha: str) -> AresSubject:
    s = d.get("sidlo") or {}
    return AresSubject(
        ico=d.get("ico", ""), name=d.get("obchodniJmeno", ""),
        country=s.get("kodStatu", ""), city=s.get("nazevObce", ""),
        legal_form=d.get("pravniForma", ""), founded=d.get("datumVzniku", ""),
        dissolved=d.get("datumZaniku", ""), url=url, sha256=sha,
    )


def get(f: Fetcher, ico: str) -> AresSubject | None:
    url = f"{BASE}/ekonomicke-subjekty/{ico.zfill(8)}"
    r = f.get(url)
    if r.status != 200:
        return None
    return _subject(json.loads(r.text), url, r.sha256)


def search(f: Fetcher, name: str, limit: int = 10) -> list[AresSubject]:
    url = f"{BASE}/ekonomicke-subjekty/vyhledat"
    r = f.post(url, json_body={"obchodniJmeno": name, "pocet": limit})
    if r.status != 200:
        return []
    d = json.loads(r.text)
    return [_subject(x, f"{BASE}/ekonomicke-subjekty/{x.get('ico')}", r.sha256)
            for x in d.get("ekonomickeSubjekty", [])]


def shareholders(f: Fetcher, ico: str) -> tuple[list[Shareholder], str, str]:
    """Společníci-právnické osoby (aktuální i historičtí). Vrací (seznam, url, sha256)."""
    url = f"{BASE}/ekonomicke-subjekty-vr/{ico.zfill(8)}"
    r = f.get(url)
    if r.status != 200:
        return [], url, r.sha256
    out: list[Shareholder] = []
    for z in json.loads(r.text).get("zaznamy", []):
        for organ in z.get("spolecnici", []) or []:
            for sp in organ.get("spolecnik", []) or []:
                po = (sp.get("osoba") or {}).get("pravnickaOsoba")
                if not po:
                    continue
                out.append(Shareholder(
                    ico=po.get("ico", "") or "", name=po.get("obchodniJmeno", "") or "",
                    since=sp.get("datumZapisu", "") or "", until=sp.get("datumVymazu", "") or "",
                ))
    return out, url, r.sha256
