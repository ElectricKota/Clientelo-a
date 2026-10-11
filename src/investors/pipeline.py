"""Hlavní pipeline (PLAN.md §8): discovery -> resolve -> evidence -> ověření v ARES -> klasifikace."""

from __future__ import annotations

import re
import time
from collections import defaultdict

from . import extract as X
from .classify import classify, fill_fields
from .config import activity_cutoff, reference_date
from .connectors import ares, cnb_jerrs, cvca
from .connectors import czechcrunch as cc
from .http import Fetcher
from .models import TIER_A, TIER_B, TIER_C, Evidence, Investor
from .resolve import brand_key, display_name, is_reliable_key, slug_to_name, tokens

SUFFIX_RX = re.compile(r"\b(ventures?|capital|vc|fund|angels|partners|equity|investments?)\b", re.I)
SLUG_SUFFIX_RX = re.compile(r"(^|-)(ventures?|capital|vc|fund|angels|equity|investments?)(-|$)")
FUND_SIZE_RX = re.compile(r"fond\w*.{0,80}(velikost|objem|upsal|uzavřel|uzavřela|spustil|"
                          r"spustila|představil|nový fond|druhý fond|třetí fond|čtvrtý fond)|"
                          r"(nový|druhý|třetí|čtvrtý) fond", re.I)


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class Pipeline:
    def __init__(self, f: Fetcher, log=print):
        self.f = f
        self.log = log
        self.cutoff = activity_cutoff()
        self.inv: dict[str, Investor] = {}
        self.channels: dict[str, set[str]] = defaultdict(set)   # kanál objevení -> klíče
        self.articles: dict[str, cc.Article] = {}
        self.stats: dict[str, int] = {}

    # ------------------------------------------------------------------ helpers
    def _get(self, key: str, name: str) -> Investor:
        if key not in self.inv:
            self.inv[key] = Investor(key=key, name=name)
        return self.inv[key]

    @staticmethod
    def _alias_ok(alias: str, curated: bool) -> bool:
        toks = alias.split()
        if not is_reliable_key(brand_key(alias), alias):
            return False   # např. samotné „Partners“ nebo „Capital“
        if len(toks) >= 2 or SUFFIX_RX.search(alias):
            return True
        # jednoslovný alias jen z kurátorovaných zdrojů (CVCA, tag CzechCrunch) a dost výrazný
        return curated and len(alias) >= 5 and (alias[0].isupper() or alias[0].isdigit())

    # ------------------------------------------------------------------ 1 discovery
    def load_registry(self) -> None:
        ents = cnb_jerrs.fetch_all(self.f, reference_date())
        for e in ents:
            base = e.parent_name or e.name
            key = brand_key(base)
            if not is_reliable_key(key, base):
                key = f"ico:{e.ico}"
            i = self._get(key, display_name(base))
            i.sources.add("jerrs")
            i.jerrs.append(e)
            i.known_icos.add(e.ico)
            if self._alias_ok(display_name(base), curated=False):
                i.aliases.add(display_name(base))
            i.evidence.append(Evidence(
                claim="registry", value=f"{e.list_code}: {e.name} (IČO {e.ico})",
                source_url=e.source_url, source_type="registry", tier=TIER_A,
                published_date=e.since, retrieved_at=reference_date().isoformat(),
                snippet=f"{e.name}; IČO {e.ico}" + (f"; obhospodařovatel {e.manager_name}" if e.manager_name else ""),
                sha256=e.sha256))
            self.channels["registry"].add(key)
        self.stats["registry_entities"] = len(ents)
        self.log(f"[registr] {len(ents)} subjektů ČNB -> {len(self.channels['registry'])} značek")

    def load_cvca(self) -> None:
        profiles = cvca.fetch_all(self.f)
        for p in profiles:
            name = display_name(p.name)
            key = brand_key(p.name)
            i = self._get(key, name)
            i.cvca = p
            i.sources.add("cvca")
            i.aliases.add(name)
            i.website = i.website or p.website
            summary = "; ".join(f"{k}: {v}" for k, v in p.fields.items()
                                if k in ("investment_type", "ticket", "aum", "sectors"))
            i.evidence.append(Evidence(
                claim="profile", value=summary[:300], source_url=p.url, source_type="association",
                tier=TIER_B, published_date=p.published, retrieved_at=now(),
                snippet=summary[:400], sha256=p.sha256))
            i.text_context.append(" ".join(p.fields.values()))
            self.channels["association"].add(key)
        self.stats["cvca_profiles"] = len(profiles)
        self.log(f"[cvca] {len(profiles)} profilů řádných členů")

    def load_tags(self) -> list[cc.ArticleRef]:
        slugs = cc.investor_tags(self.f)
        known = {k for k, i in self.inv.items() if is_reliable_key(k) and (
            i.cvca or any(e.list_code == "ZISIF_PAR15" for e in i.jerrs))}
        selected = [s for s in slugs if SLUG_SUFFIX_RX.search(s) or brand_key(slug_to_name(s)) in known]
        refs: list[cc.ArticleRef] = []
        for s in selected:
            title, r = cc.fetch_tag(self.f, s, self.cutoff)
            refs.extend(r)
            if not SLUG_SUFFIX_RX.search(s):
                # tag vybraný jen shodou klíče s registrem (např. „kaya“, „biotech“): použije se
                # pouze k nalezení článků, jako alias by chytal obecná slova
                continue
            name = title or slug_to_name(s)
            key = brand_key(name)
            if not is_reliable_key(key):
                continue
            i = self._get(key, name)
            i.sources.add("cc_tag")
            i.cc_tags.add(s)
            if self._alias_ok(name, curated=True):
                i.aliases.add(name)
            self.channels["press_tag"].add(key)
        self.stats["cc_tags_selected"] = len(selected)
        self.log(f"[cc] {len(slugs)} tagů, vybráno {len(selected)} investorských, {len(refs)} článků v okně")
        return refs

    def load_articles(self, extra_refs: list[cc.ArticleRef]) -> None:
        refs = cc.crawl_category(self.f, "startupy", self.cutoff)
        seen: dict[str, cc.ArticleRef] = {}
        for r in refs + extra_refs:
            seen.setdefault(r.url, r)
        for n, (url, ref) in enumerate(seen.items()):
            try:
                a = cc.fetch_article(self.f, url)
            except Exception as ex:  # noqa: BLE001 – jednotlivý článek nesmí shodit běh
                self.log(f"  ! {url}: {ex}")
                continue
            a.date = a.date or ref.date
            self.articles[url] = a
            if n and n % 200 == 0:
                self.log(f"  články {n}/{len(seen)}")
        self.stats["articles"] = len(self.articles)
        self.log(f"[cc] {len(self.articles)} článků (Startupy + tagy investorů)")

    # ------------------------------------------------------------------ 2 media discovery
    def discover_from_text(self) -> None:
        new = 0
        for a in self.articles.values():
            for s in X.sentences(" ".join(a.paragraphs)):
                if not X.is_investment_sentence(s):
                    continue
                for h in X.investor_names(s):
                    key = brand_key(h.name)
                    if not is_reliable_key(key, h.name):
                        continue
                    if key not in self.inv:
                        if not h.has_suffix:
                            # „fond X“ bez přípony Ventures/Capital/... nové značky nezakládá
                            # (často jde o osoby nebo firmy) – jen doplní alias známé značce
                            continue
                        new += 1
                    i = self._get(key, display_name(h.name))
                    i.sources.add("cc_text")
                    if self._alias_ok(h.name, curated=False):
                        i.aliases.add(h.name)
                    self.channels["press_text"].add(key)
        self.log(f"[cc] z textů článků objeveno {new} nových značek")
        self._merge_sub_brands()

    def _merge_sub_brands(self) -> None:
        """„Presto Tech Horizons“ (jen z textu) -> „Presto“ (registr/CVCA), „Credo Stage“ -> „Credo“."""
        anchors = {k for k, i in self.inv.items()
                   if " " not in k and not k.startswith("ico:") and i.sources & {"jerrs", "cvca", "cc_tag"}}
        merged = 0
        for k in list(self.inv):
            i = self.inv[k]
            first = k.split(" ")[0]
            if " " in k and i.sources == {"cc_text"} and first in anchors:
                parent = self.inv[first]
                parent.aliases |= i.aliases
                parent.sources |= i.sources
                del self.inv[k]
                merged += 1
        self.log(f"[resolve] {merged} dílčích značek (fondů) sloučeno s mateřskou značkou")

    # ------------------------------------------------------------------ 3 evidence (gazetteer)
    def collect_evidence(self) -> None:
        # Aliasy z kurátorovaných zdrojů (CVCA, tagy, texty médií) se hledají bez ohledu na velikost
        # písmen; aliasy pouze z registru ČNB přesně (jinak „Naše ČESKO“ chytá běžný text).
        alias_ci: dict[str, str] = {}
        alias_cs: dict[str, str] = {}
        for k, i in self.inv.items():
            curated = bool(i.sources & {"cvca", "cc_tag", "cc_text"})
            for al in i.aliases:
                if len(al) < 4:
                    continue
                if curated:
                    alias_ci.setdefault(al.lower(), k)
                else:
                    alias_cs.setdefault(al, k)

        def build(keys, flags):
            pats = sorted(keys, key=len, reverse=True)
            return re.compile(r"(?<![\w&])(" + "|".join(re.escape(p).replace(r"\ ", r"\s+") for p in pats)
                              + r")(?![\w&])", flags) if pats else None
        rx_ci, rx_cs = build(alias_ci, re.I), build(alias_cs, 0)

        def find(s: str):
            out, taken = [], []
            for rx, amap, fold in ((rx_ci, alias_ci, True), (rx_cs, alias_cs, False)):
                if rx is None:
                    continue
                for m in rx.finditer(s):
                    if not (m.group(1)[0].isupper() or m.group(1)[0].isdigit()):
                        continue
                    if any(a <= m.start() < b for a, b in taken):
                        continue
                    al = re.sub(r"\s+", " ", m.group(1))
                    out.append((m, amap[al.lower() if fold else al]))
                    taken.append((m.start(), m.end()))
            return out
        found = 0
        for a in self.articles.values():
            head = f"{a.title}. {a.paragraphs[0] if a.paragraphs else ''}"
            head_startups = X.startup_names(head)
            per_article: set[str] = set()
            for s in X.sentences(" ".join(a.paragraphs)):
                matches = find(s)
                if not matches:
                    continue
                is_inv = X.is_investment_sentence(s)
                is_exit = bool(X.EXIT_RX.search(s)) and not re.search(r"investic|investoval|\bkol[oae]\b", s, re.I)
                amounts = X.parse_amounts(s)
                for m, key in matches:
                    i = self.inv[key]
                    nat = X.nationality_before(s, m.start())
                    if nat:
                        i.nationality[nat] += 1
                    i.text_context.append(f"{a.title}. {s}")
                    if amounts and FUND_SIZE_RX.search(s):
                        i.evidence.append(Evidence(
                            claim="aum", value=str(max(amounts)), source_url=a.url, source_type="press",
                            tier=TIER_C, published_date=a.date, retrieved_at=now(), snippet=s[:500],
                            sha256=a.sha256, amount_eur=max(amounts)))
                    if not is_inv or is_exit or key in per_article:
                        continue
                    per_article.add(key)
                    startups = [n for n in X.startup_names(s) if brand_key(n) != key] or \
                               [n for n in head_startups if brand_key(n) != key]
                    i.evidence.append(Evidence(
                        claim="investment", value=f"{startups[0] if startups else '?'} ({a.date})",
                        source_url=a.url, source_type="press", tier=TIER_C, published_date=a.date,
                        retrieved_at=now(), snippet=s[:500], sha256=a.sha256,
                        company=startups[0] if startups else "",
                        amount_eur=max(amounts) if amounts else None))
                    found += 1
        self.log(f"[evidence] {found} zmínek o investicích (tier C)")

    # ------------------------------------------------------------------ 4 český správce
    def resolve_managers(self) -> None:
        searched = 0
        for i in self.inv.values():
            par15 = [e for e in i.jerrs if e.list_code in ("ZISIF_PAR15", "IS")]
            funds = [e for e in i.jerrs if e.list_code == "IF_MANAGERS"]
            if par15:
                e = par15[0]
                i.manager_ico, i.manager_name, i.manager_source, i.manager_country = e.ico, e.name, "jerrs", "CZ"
            elif funds:
                e = funds[0]
                i.manager_ico, i.manager_name = e.manager_ico, e.manager_name
                i.manager_source, i.manager_country = "jerrs_fund_manager", "CZ"
            if i.manager_ico:
                i.evidence.append(Evidence(
                    claim="czech_manager", value=f"{i.manager_name} (IČO {i.manager_ico})",
                    source_url=i.jerrs[0].source_url, source_type="registry", tier=TIER_A,
                    published_date=i.jerrs[0].since, retrieved_at=reference_date().isoformat(),
                    snippet=i.manager_name, sha256=i.jerrs[0].sha256))
                continue
            if not (i.investments() or i.cvca):
                continue
            queries = []
            if i.cvca and re.search(r"s\.r\.o\.|a\.s\.|SE\b|k\.s\.", i.cvca.legal_name):
                queries.append(i.cvca.legal_name)
            if i.cvca:
                queries.append(re.sub(r"\s+[–-]\s+.*$", "", i.cvca.name))
            queries += sorted((a for a in i.aliases if SUFFIX_RX.search(a)), key=len)[:2]
            queries.append(i.name)
            for q in dict.fromkeys(queries):
                searched += 1
                hits = [h for h in ares.search(self.f, q)
                        if h.country == "CZ" and self._ares_match(q, h.name, i.key)]
                active = [h for h in hits if not h.dissolved]
                if active:
                    h = min(active, key=lambda h: (len(h.name), h.name))
                    i.manager_ico, i.manager_name, i.manager_source, i.manager_country = h.ico, h.name, "ares_name", "CZ"
                    i.known_icos.update(x.ico for x in active)
                    i.evidence.append(Evidence(
                        claim="czech_manager", value=f"{h.name} (IČO {h.ico})", source_url=h.url,
                        source_type="registry", tier=TIER_A, published_date=h.founded,
                        retrieved_at=now(), snippet=f"{h.name}, {h.city}, vznik {h.founded}",
                        sha256=h.sha256))
                    break
                if hits and not i.manager_ico:
                    i.reasons.append(f"ARES: nalezen jen zaniklý subjekt {hits[0].name}")
        self.log(f"[ares] dohledání českého správce: {searched} dotazů")

    @staticmethod
    def _ares_match(query: str, hit_name: str, key: str) -> bool:
        """Shoda značky s firmou v ARES: stejný klíč značky A všechny tokeny dotazu v názvu firmy
        A investiční charakter názvu (jinak by „Index Ventures“ našlo „INDEX s.r.o.“)."""
        if brand_key(hit_name) != key:
            return False
        q, h = set(tokens(query)), set(tokens(hit_name))
        if not q <= h:
            return False
        return bool(SUFFIX_RX.search(hit_name) or re.search(
            r"rizikov|invest|fond|holding|management|vc\b", hit_name, re.I))

    # ------------------------------------------------------------------ 5 potvrzení v OR (tier A)
    def confirm_in_commercial_register(self, max_companies: int = 6) -> None:
        confirmed = 0
        calls = 0
        for i in self.inv.values():
            if i.manager_country != "CZ" or not i.known_icos:
                continue
            inv_ev = [e for e in i.investments(self.cutoff) if e.company]
            seen: set[str] = set()
            for e in inv_ev:
                comp = e.company
                if comp.lower() in seen or len(seen) >= max_companies:
                    continue
                seen.add(comp.lower())
                calls += 1
                ckey = " ".join(tokens(comp))
                hits = [h for h in ares.search(self.f, comp, limit=5)
                        if " ".join(tokens(h.name)).startswith(ckey) and h.country == "CZ"][:2]
                for h in hits:
                    calls += 1
                    shs, url, sha = ares.shareholders(self.f, h.ico)
                    for sh in shs:
                        if sh.ico in i.known_icos or (sh.name and brand_key(sh.name) == i.key):
                            i.known_icos.add(sh.ico)
                            i.evidence.append(Evidence(
                                claim="investment", value=f"{h.name} (společník od {sh.since})",
                                source_url=url, source_type="registry_vr", tier=TIER_A,
                                published_date=sh.since, retrieved_at=now(),
                                snippet=f"{sh.name} (IČO {sh.ico}) zapsán jako společník {h.name} "
                                        f"(IČO {h.ico}) od {sh.since}" + (f" do {sh.until}" if sh.until else ""),
                                sha256=sha, company=h.name))
                            confirmed += 1
        self.stats["or_confirmations"] = confirmed
        self.log(f"[ares-vr] {confirmed} investic potvrzeno v obchodním rejstříku ({calls} dotazů)")

    # ------------------------------------------------------------------ run
    def run(self) -> list[Investor]:
        self.load_registry()
        self.load_cvca()
        tag_refs = self.load_tags()
        self.load_articles(tag_refs)
        self.discover_from_text()
        self.collect_evidence()
        self.resolve_managers()
        self.confirm_in_commercial_register()
        for i in self.inv.values():
            fill_fields(i, self.cutoff)
            classify(i, self.cutoff)
        self.stats["network_requests"] = self.f.network_requests
        return list(self.inv.values())
