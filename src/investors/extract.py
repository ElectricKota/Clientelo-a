"""Pravidlová extrakce z českých textů (bez LLM): věty o investicích, jména investorů,
národnost, částky, názvy startupů a sektory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import rules, taxonomy

UP = "A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ"
TOKEN = rf"(?:[{UP}0-9][\w&\.\-']*|&)"
NAME = rf"{TOKEN}(?:\s+{TOKEN}){{0,3}}"

SUFFIX = (r"(?:Ventures|Venture Capital|Venture Partners|Capital Partners|Capital|VC|Partners|"
          r"Fund|Angels|Equity|Investments|Invest)")

# Silné indikátory věty o investici (nestačí samotné „miliony“).
INVEST_RX = re.compile(
    r"investic|investoval|investuj|investoři|investorů|investorem|investorsk|"
    r"\bkol[aeouě]\b|\bkole\b|kolem financování|vedl[aiy]?\b|vedou\b|připojil|"
    r"získal|získává|nabral|nabírá|financován|seed|series [a-d]|sérii [a-d]|"
    r"vstoupil|vložil|upsal|podpořil|kapitál od", re.I)
EXIT_RX = re.compile(r"\bexit|prodal[aiy]?\b|odprodal|akvizic|koupil[aiy]?\b|převzal", re.I)

CONTEXT_PREFIX = (r"(?:fond|fondy|fondu|fondem|fondů|investor|investoři|investorů|investorem|"
                  r"investiční skupina|investiční skupiny|investiční společnost|investorská skupina|"
                  r"akcelerátor|akcelerátoru|venture kapitálový fond|venture fond|VC fond)")

NATIONALITY = {
    "CZ": r"tuzemsk|česk|pražsk|brněnsk|ostravsk|domác",
    "FOREIGN": (r"slovensk|britsk|americk|německ|polsk|rakousk|lotyšsk|estonsk|francouzsk|"
                r"nizozemsk|holandsk|švédsk|finsk|izraelsk|maďarsk|rumunsk|ukrajinsk|švýcarsk|"
                r"dánsk|norsk|litevsk|španělsk|italsk|londýnsk|berlínsk|kalifornsk|newyorsk|"
                r"singapursk|japonsk|čínsk|kanadsk|irsk|portugalsk|chorvatsk|bulharsk|zahraniční"),
}

# Časté české křestní jméno na začátku = pravděpodobně fyzická osoba (anděl) -> mimo vzorek.
FIRST_NAMES = set("""jan petr pavel tomáš martin jakub josef jiří michal lukáš david ondřej
vojtěch filip adam marek daniel karel milan roman zdeněk radek jaroslav miroslav václav ladislav
aleš libor robert richard patrik dominik matěj šimon štěpán vít viktor marcel igor ivan oldřich
eva jana petra lucie kateřina martina veronika tereza barbora markéta hana lenka michaela
zuzana monika kristýna andrea klára alena simona nikola""".split())

STOPWORDS_NAME = set("""Česko Česku Praha Praze Evropa Evropě Brno Brně Slovensko Slovensku
Startup Startupy Firma Investice Kolo Fond Ten Ta To Podle Jeho Její Jejich Na Do V Ve S Se A I
Teď Nyní Letos Loni Celkem Mezi Kromě Díky Investiční Investoři Investor Společnost Spolu
CzechCrunch Forbes""".split())

AMOUNT_RX = re.compile(
    r"(\d+(?:[ ,\.]\d+)*|jed(?:en|na|no)|dv(?:a|ě)|tři|čtyři|pět|šest|sedm|osm|devět|deset|"
    r"patnáct|dvacet|třicet|čtyřicet|padesát|sto|stovky|desítky|půl)\s*"
    r"(tisíc\w*|milion\w*|milión\w*|mil\.|mil\b|miliard\w*|mld\.?|m\b|k\b)?\s*"
    r"(eur\w*|€|korun\w*|kč|czk|dolar\w*|usd|\$|liber|gbp)", re.I)
WORDNUM = {"jeden": 1, "jedna": 1, "jedno": 1, "dva": 2, "dvě": 2, "tři": 3, "čtyři": 4,
           "pět": 5, "šest": 6, "sedm": 7, "osm": 8, "devět": 9, "deset": 10, "patnáct": 15,
           "dvacet": 20, "třicet": 30, "čtyřicet": 40, "padesát": 50, "sto": 100, "půl": 0.5}


@dataclass
class NameHit:
    name: str
    nationality: str  # CZ | FOREIGN | ""
    start: int
    has_suffix: bool = True  # False = jméno nalezené jen podle kontextu („fond X“)


def sentences(text: str) -> list[str]:
    parts = re.split(rf"(?<=[\.!?])\s+(?=[{UP}„\"0-9])", text)
    return [p.strip() for p in parts if len(p.strip()) > 15]


def is_investment_sentence(s: str) -> bool:
    return bool(INVEST_RX.search(s))


def _looks_like_person(name: str) -> bool:
    toks = name.split()
    if len(toks) >= 2 and toks[0].lower() in FIRST_NAMES:
        return True
    return bool(len(toks) == 2 and re.search(r"ová$", toks[1]))


def _clean_name(n: str) -> str:
    n = re.sub(r"[\.,;:]+$", "", n.strip())
    toks = n.split()
    while toks and toks[0] in STOPWORDS_NAME:
        toks = toks[1:]
    return " ".join(toks)


def nationality_before(s: str, start: int) -> str:
    window = s[max(0, start - 45):start].lower()
    # bere se nejbližší přídavné jméno před jménem
    best, pos = "", -1
    for code, pat in NATIONALITY.items():
        for m in re.finditer(pat, window):
            if m.start() > pos:
                best, pos = code, m.start()
    return best


def investor_names(s: str) -> list[NameHit]:
    """Kandidátní jména investorů (organizací) ve větě."""
    hits: dict[str, NameHit] = {}
    for m in re.finditer(rf"({NAME})\s+({SUFFIX})\b", s):
        n = _clean_name(f"{m.group(1)} {m.group(2)}")
        if len(n.split()) >= 2 and not _looks_like_person(n):
            hits.setdefault(n, NameHit(n, nationality_before(s, m.start()), m.start()))
    for m in re.finditer(
            rf"\b{CONTEXT_PREFIX}\s+(?:[a-zěščřžýáíéúůťďň]+\s+){{0,2}}({NAME})", s):
        n = _clean_name(m.group(1))
        if not n or n in STOPWORDS_NAME or _looks_like_person(n) or len(n) < 3:
            continue
        if any(n in k or k in n for k in hits):
            continue
        hits.setdefault(n, NameHit(n, nationality_before(s, m.start(1)), m.start(1), False))
    return list(hits.values())


def startup_names(s: str) -> list[str]:
    out = []
    for m in re.finditer(
            rf"\b(?:startup(?:u|em|y|ů)?|firm[aěuy]|společnost(?:i)?|aplikac[eií]|platform[auy]|"
            rf"projekt(?:u)?|značk[auy])\s+({TOKEN}(?:\s+{TOKEN}){{0,2}})", s):
        n = _clean_name(m.group(1))
        if n and n not in STOPWORDS_NAME and not _looks_like_person(n):
            out.append(n)
    return out


def parse_amounts(s: str) -> list[float]:
    """Všechny částky ve větě převedené na EUR."""
    fx = rules()["fx_to_eur"]
    out = []
    for m in AMOUNT_RX.finditer(s):
        num_raw, unit, cur = m.group(1).lower(), (m.group(2) or "").lower(), m.group(3).lower()
        if num_raw in ("stovky", "desítky"):
            continue
        if num_raw in WORDNUM:
            num = WORDNUM[num_raw]
        else:
            t = num_raw.replace(" ", "")
            t = t.replace(",", ".") if t.count(",") == 1 and len(t.split(",")[1]) <= 2 else t.replace(",", "")
            if t.count(".") > 1:
                t = t.replace(".", "")
            try:
                num = float(t)
            except ValueError:
                continue
        mult = 1.0
        if unit.startswith(("miliard", "mld")):
            mult = 1e9
        elif unit.startswith(("tisíc", "k")):
            mult = 1e3
        elif unit.startswith(("milion", "milión", "mil", "m")):
            mult = 1e6
        code = ("EUR" if cur.startswith(("eur", "€")) else "CZK" if cur.startswith(("kor", "kč", "czk"))
                else "USD" if cur.startswith(("dol", "usd", "$")) else "GBP")
        val = num * mult * fx[code]
        if val >= 1000:
            out.append(round(val))
    return out


def parse_range_eur(text: str) -> tuple[float | None, float | None]:
    """Rozsah z textu typu „50k EUR – 10M EUR“, „2-30 milionů EUR“, „62,7 mil. Kč“."""
    if not text:
        return None, None
    t = text.replace("–", "-").replace("—", "-")
    cur = "EUR"
    if re.search(r"kč|korun|czk", t, re.I):
        cur = "Kč"
    elif re.search(r"usd|\$|dolar", t, re.I):
        cur = "USD"
    for _ in range(3):  # tisícové oddělovače „50 000“ -> „50000“
        t = re.sub(r"(\d)[ \u00a0](\d{3})\b", r"\1\2", t)
    unit_default = ""
    um = re.search(r"(tisíc|miliard\w*|mld|milion\w*|milión\w*|mil\b\.?|mio|\bm\b|\bk\b)", t, re.I)
    if um:
        unit_default = um.group(1)
    nums = re.findall(r"(\d+(?:[\.,]\d+)?)\s*(tisíc|miliard\w*|mld|milion\w*|milión\w*|mil\b\.?|mio|m\b|k\b)?", t, re.I)
    vals = []
    for n, u in nums:
        vals_txt = f"{n} {u or unit_default} {cur}"
        a = parse_amounts(vals_txt)
        if a:
            vals.append(a[0])
    if not vals:
        return None, None
    return min(vals), max(vals)


def sectors(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, pat in taxonomy().items():
        n = len(pat.findall(text))
        if n:
            counts[key] = n
    return counts
