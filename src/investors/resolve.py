"""Normalizace názvů a klíč značky (brand key) pro spojování záznamů z různých zdrojů.

„DEPO VENTURES AF II., osoba rizikového kapitálu, s.r.o.“, „Depo Ventures“ (CVCA)
a tag „depo-ventures“ (CzechCrunch) dostanou stejný klíč „depo“.
"""

from __future__ import annotations

import re
import unicodedata

from .config import rules

LEGAL_PATTERNS = [
    r",?\s*osoba rizikového kapitálu,?", r"\bosoba rizikoveho kapitalu\b",
    r",?\s*investiční společnost,?", r"\binvesticni spolecnost\b",
    r"\botevřený podílový fond\b", r"\bfond kvalifikovaných investorů\b",
    r"\bspol\.\s*s\s*r\.\s*o\.", r"\bs\.\s*r\.\s*o\.", r"\ba\.\s*s\.", r"\bk\.\s*s\.",
    r"\bv\.\s*o\.\s*s\.", r"\bSE\b", r"\bSICAV\b", r"\bSCSp\b", r"\bS\.?C\.?A\.?\b",
    r"\bLtd\.?\b", r"\bLimited\b", r"\bGmbH\b", r"\bS\.?à\.?\s?r\.?l\.?\b", r"\bB\.V\.\b",
    r"\bInc\.?\b", r"\bLLC\b", r"\bL\.?P\.?\b",
    r"\s+[–-]\s+podfond\b.*$", r"\bpodfond\b", r"\s+[–-]\s+čestný člen\b.*$",
]
ROMAN = r"\b(?:I{1,3}|IV|V|VI{0,3}|IX|X)\b\.?"


def ascii_fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def strip_legal(name: str) -> str:
    s = name
    for p in LEGAL_PATTERNS:
        s = re.sub(p, " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" ,.-–")
    return s


def display_name(name: str) -> str:
    """Čitelný název značky bez právní formy a pořadových čísel fondu."""
    s = strip_legal(name)
    s = re.sub(ROMAN, " ", s)
    s = re.sub(r"\b(?:AF|Fund|Fond)\b\.?\s*$", " ", s, flags=re.I)
    s = re.sub(r"\s+\d+\.?\s*$", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" ,.-–")
    if sum(c.isupper() for c in s) > 0.7 * sum(c.isalpha() for c in s) and len(s) > 4:
        s = s.title()
    s = re.sub(r"\bVc\b", "VC", s)
    return s


def tokens(name: str) -> list[str]:
    s = ascii_fold(strip_legal(name)).lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return [t for t in s.split() if t]


def brand_key(name: str) -> str:
    generic = set(rules()["generic_brand_words"])
    toks = [t for t in tokens(name)
            if t not in generic and not re.fullmatch(r"(?:i{1,3}|iv|v|vi{0,3}|ix|x|\d+|af)", t)]
    # „Nation1“ i „Nation 1“ -> „nation“ (číslo fondu/značky na konci tokenu se ignoruje)
    toks = [re.sub(r"(?<=[a-z]{4})\d+$", "", t) for t in toks]
    # „J&T“ -> tokeny j, t (and je generické) – spojit jednopísmenné tokeny
    joined: list[str] = []
    for t in toks:
        if len(t) == 1 and joined and len(joined[-1]) <= 2:
            joined[-1] += t
        else:
            joined.append(t)
    return " ".join(joined)


def is_reliable_key(key: str, name: str = "") -> bool:
    min_len = 2 if "&" in name else 3   # „J&T“ -> „jt“
    if not key or len(key.replace(" ", "")) < min_len:
        return False
    return key not in set(rules()["ambiguous_brand_keys"])


def slug_to_name(slug: str) -> str:
    return " ".join(w.capitalize() if w not in {"vc"} else "VC" for w in slug.split("-"))
