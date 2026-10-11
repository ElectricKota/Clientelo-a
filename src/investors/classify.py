"""Pravidla zařazení / vyřazení (PLAN.md §2) a odvození polí (sektor, ticket, AUM)."""

from __future__ import annotations

import re
from collections import Counter

from . import extract as X
from .config import rules, rx
from .models import TIER_A, TIER_B, TIER_C, Investor

STAGE_RX = {
    "pre-seed": r"pre-seed|preseed",
    "seed": r"(?<!pre-)\bseed",
    "series_a": r"série a|sérii a|series a|kolo a\b",
    "series_b_plus": r"série [b-e]|sérii [b-e]|series [b-e]",
    "growth": r"růstov|growth|expanz",
}


def _name_texts(i: Investor) -> str:
    return " | ".join([i.name, *i.aliases, *(e.name for e in i.jerrs)])


def fill_fields(i: Investor, cutoff: str) -> None:
    ctx = " ".join(i.text_context)
    # --- sektory: CVCA (váha 3) + kontext článků o investicích
    counts: Counter = Counter()
    if i.cvca and i.cvca.fields.get("sectors"):
        for k, n in X.sectors(i.cvca.fields["sectors"]).items():
            counts[k] += 3 * n
    for e in i.investments(cutoff):
        for k, n in X.sectors(e.snippet).items():
            counts[k] += n
    if counts.get("generalist") and len(counts) == 1:
        i.sectors = ["generalist"]
    else:
        counts.pop("generalist", None)
        i.sectors = [k for k, _ in counts.most_common(3)]
    # --- fáze
    i.stages = [k for k, pat in STAGE_RX.items() if re.search(pat, ctx, re.I)]
    # --- ticket: profil CVCA, jinak proxy z velikosti kol
    if i.cvca and i.cvca.fields.get("ticket"):
        lo, hi = X.parse_range_eur(i.cvca.fields["ticket"])
        if lo:
            i.ticket_min_eur, i.ticket_max_eur = lo, hi
            i.ticket_source, i.ticket_as_of = "cvca_profile", i.cvca.published
    if i.ticket_min_eur is None:
        amts = [e.amount_eur for e in i.investments(cutoff) if e.amount_eur]
        if amts:
            i.ticket_min_eur, i.ticket_max_eur = min(amts), max(amts)
            i.ticket_source = "round_size_proxy"
            i.ticket_as_of = max(e.published_date for e in i.investments(cutoff) if e.amount_eur)
    # --- AUM: nejnovější tvrzení (tisk vs. profil CVCA)
    cands = []
    if i.cvca and i.cvca.fields.get("aum"):
        lo, hi = X.parse_range_eur(i.cvca.fields["aum"])
        if hi:
            cands.append((i.cvca.published, hi, "cvca_profile"))
    for e in i.evidence:
        if e.claim == "aum" and e.amount_eur and e.amount_eur >= 1e6:
            cands.append((e.published_date, e.amount_eur, "press"))
    if cands:
        d, v, src = max(cands)
        i.aum_eur, i.aum_as_of, i.aum_source = v, d, src


def _type(i: Investor) -> str:
    vc, pe, cvc = rx("vc_signals"), rx("pe_signals"), rx("cvc_signals")
    names = _name_texts(i)
    if i.cvca:
        t = i.cvca.fields.get("investment_type", "") + " " + i.cvca.fields.get("sectors", "")
        if cvc.search(t):
            return "cvc"
        nv = len(vc.findall(t)) + 2 * len(vc.findall(i.cvca.name))
        npe = len(pe.findall(t))
        if nv or npe:
            return "vc" if nv >= npe else "pe"
    ctx = " ".join(i.text_context)
    if cvc.search(ctx):
        return "cvc"
    # investice do nemovitostí (haly, výstavba, ...) nejsou investice do firem
    if len(rx("real_estate_context").findall(ctx)) > len(vc.findall(ctx)):
        return "other"
    v = len(vc.findall(ctx)) + 3 * len(vc.findall(names))
    p = len(pe.findall(ctx)) + 3 * len(re.findall(r"equity|private equity|buyout", names, re.I))
    if v == 0 and p == 0:
        # zmínka v investiční větě v kategorii Startupy je slabý VC signál
        return "vc" if i.investments() else "other"
    return "pe" if p > 1.5 * v else "vc"


def _confidence(i: Investor, cutoff: str) -> float:
    inv = i.investments(cutoff)
    score = 0.0
    if any(e.tier == TIER_A for e in inv):
        score += 0.45
    n_c = len({e.source_url for e in inv if e.tier == TIER_C})
    score += min(0.4, 0.15 * n_c)
    if i.cvca:
        score += 0.1
    if i.manager_source in ("jerrs", "jerrs_fund_manager"):
        score += 0.1
    elif i.manager_source == "ares_name":
        score += 0.05
    return round(min(score, 1.0), 2)


def classify(i: Investor, cutoff: str) -> None:
    R = rules()
    i.type = _type(i)
    ctx = " ".join(i.text_context)
    if rx("accelerator_signals").search(ctx + " " + _name_texts(i)):
        i.tags.add("accelerator")
    i.confidence = _confidence(i, cutoff)

    names = _name_texts(i)
    vc_in_name = re.search(r"ventures?|\bvc\b|seed|startup|angels", names, re.I)

    def out(status: str, code: str, why: str) -> None:
        i.status, i.exclusion_code = status, code
        i.reasons.append(why)

    # 1) zjevně jiný typ fondu podle názvu (realitní, energetický, dluhový, ...)
    if not vc_in_name and (not i.investments() or i.type == "other"):
        for code, pat in R["exclude_name_patterns"].items():
            if re.search(pat, names, re.I):
                return out("excluded", code, f"název odpovídá vzoru {code}")

    inv_all = i.investments()
    inv_win = i.investments(cutoff)
    tier_a_win = [e for e in inv_win if e.tier in (TIER_A, TIER_B)]
    tier_c_win = {e.source_url for e in inv_win if e.tier == TIER_C}

    # 2) žádný veřejný doklad investice
    if not inv_all and not i.cvca:
        return out("excluded", "NO_PUBLIC_EVIDENCE",
                   "v registru, ale bez veřejného dokladu investice (média, OR)")

    # 3) typ investora mimo vzorek (PE, ostatní)
    if i.type == "pe":
        return out("excluded", "EXCL_NOT_VC", "typ investic odpovídá private equity / buyout")

    # 4) český správce (rozhoduje česká správcovská firma, PLAN §2.1)
    if i.manager_country != "CZ":
        if i.cvca and i.cvca.country_hint and i.cvca.country_hint != "CZ":
            return out("excluded", "EXCL_FOREIGN", f"sídlo správce dle CVCA: {i.cvca.country_hint}")
        if i.nationality["CZ"] > i.nationality["FOREIGN"]:
            return out("review", "NO_CZ_ENTITY",
                       "média ho označují jako tuzemského, ale v ČNB ani ARES nenalezena česká správcovská firma")
        return out("excluded", "EXCL_FOREIGN",
                   "v ČNB ani ARES není česká správcovská firma; v médiích zahraniční / bez národnosti")

    # 5) aktivita v okně 36 měsíců
    if tier_a_win or len(tier_c_win) >= R["evidence"]["min_tier_c_articles"]:
        if i.type == "other":
            return out("review", "TYPE_UNCLEAR", "aktivní investor, typ nejasný")
        i.status = "included"
        i.reasons.append(f"doklady v okně: tier A/B={len(tier_a_win)}, tier C článků={len(tier_c_win)}")
        return
    if inv_win:
        return out("review", "INSUFFICIENT_EVIDENCE", "jen 1 článek (tier C) v okně aktivity")
    if inv_all:
        return out("excluded", "EXCL_INACTIVE", "poslední doložená investice starší než okno aktivity")
    return out("review", "PROFILE_ONLY", "jen profil CVCA bez datovaného dokladu investice")
