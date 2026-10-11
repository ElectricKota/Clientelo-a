# Report – Zadání A: Spolehlivá databáze investorů

> Stav k 2026-10-11 · vzorek: VC investoři s **českou správcovskou firmou**, aktivní v posledních 36 měsících
> (od 2023-10-11) · všechna data z veřejných a bezplatných zdrojů
>
> **§4 (naměřená přesnost) čeká na ruční ověření** formuláře `verification/form.csv`.
> Po jeho vyplnění se spustí `make metrics` a výsledky se doplní sem.

## 1. Shrnutí

| | |
|---|---|
| Zpracováno subjektů z registru ČNB | 1 355 (406 správců dle § 15 ZISIF, 62 investičních společností, 887 fondů/podfondů) |
| Zpracováno článků CzechCrunch | 904 (kategorie Startupy za 36 měsíců + články z 98 tagů investorů) |
| Kandidátů (značek) celkem | 1 425 |
| **Zařazeno do vzorku (český VC, doložená aktivita)** | **44** |
| z toho s investicí potvrzenou v obchodním rejstříku (tier A) | 16 |
| K ruční kontrole (`review`) | 31 |
| Vyřazeno (s kódem důvodu) | 1 350 |
| Doklady u zařazených | 641 dokladů investic (41 tier A z OR, 600 tier C z médií) + registr / ARES u každého |
| Náklady na data | 0 Kč (žádné placené API) |

Každý zařazený záznam má:
- českou správcovskou firmu s IČO (z ČNB nebo ARES),
- aspoň 1 investici potvrzenou zápisem v obchodním rejstříku, nebo aspoň 2 různé články o investicích v okně aktivity,
- URL, datum, doslovnou citaci a SHA-256 staženého obsahu u každého dokladu (`out/evidence.csv`).

## 2. Kdo ve vzorku je a kdo ne

Pravidla jsou v [PLAN.md §2](../PLAN.md) a jako konfigurace v [config/rules.yaml](../config/rules.yaml).
Rozpad nezařazených podle důvodu:

| Kód | Počet | Význam |
|---|---:|---|
| `NO_PUBLIC_EVIDENCE` | 880 | Subjekt je v registru ČNB, ale nemá žádný veřejný doklad investice. Typicky jde o rodinná investiční vehikla s registrací „osoba rizikového kapitálu“ |
| `EXCL_FOREIGN` | 179 | Investor bez české správcovské firmy (Sequoia, Index Ventures, Khosla…) |
| `EXCL_REAL_ESTATE` | 116 | Realitní fondy (podle názvu nebo kontextu investic) |
| `EXCL_PUBLIC_MARKETS` | 50 | Akciové, smíšené a penzijní fondy |
| `EXCL_DEBT` | 49 | Dluhopisové, úvěrové a mezaninové fondy |
| `EXCL_NOT_VC` | 26 | Private equity / buyout (Abris, Genesis, Jet Investment, Orbit Capital…) |
| `EXCL_COMMODITY_OTHER`, `EXCL_ENERGY_INFRA`, `EXCL_FUND_OF_FUNDS` | 50 | Komodity, krypto, energetika, fondy fondů |
| `INSUFFICIENT_EVIDENCE` (review) | 18 | Jen 1 článek v okně aktivity |
| `NO_CZ_ENTITY` (review) | 11 | Média ho označují jako tuzemského, ale česká firma se v ČNB ani ARES nenašla (např. **Kaya VC**) |
| `TYPE_UNCLEAR` (review) | 2 | Aktivní, typ nejasný (WOOD & Company, J&T Arch) |

**Zjištění o registru:** 404 ze 406 správců podle § 15 ZISIF má status „osoba rizikového kapitálu“.
Doložitelnou investici v okně aktivity má jen 14 z nich a zařazeno je 10. **Regulatorní status tedy pro spolehlivou
databázi nestačí**, rozhoduje doklad skutečné investice. Naopak 25 ze 44 zařazených investorů
v registru ČNB vůbec není (spravují zahraniční vehikla nebo investují přes běžné s.r.o./a.s.) a našla je
až média a ARES.

## 3. Jak se ověřuje pravost (automaticky)

1. **Existence a sídlo správce:** registr ČNB (tier A), jinak ARES. V ARES se vyžaduje shoda klíče značky,
   všech slov názvu a investiční charakter firmy. Díky tomu se „Index Ventures“ nespojí s „INDEX s.r.o.“.
2. **Doklad investice:** věta v článku, kde je investor jmenován v souvislosti s investicí (tier C), nebo
   **zápis fondu jako společníka portfoliové firmy v obchodním rejstříku** (ARES VR, tier A, datum zápisu).
   Příklad: *DEPO VENTURES AF II., osoba rizikového kapitálu, s.r.o. (IČO 11726377) zapsán jako společník KARDI AI Technologies s.r.o. od 2023-11-28* (do 2025-05 pod dřívějším názvem DEPO ANGEL FUND II.)
3. **Aktivita:** aspoň 1 doklad tier A/B, nebo aspoň 2 různé články v okně 36 měsíců.
4. **Typ:** profil CVCA (převaha VC vs. PE signálů), jinak kontext článků. Realitní kontext (haly, výstavba)
   znamená `other`.
5. **Audit:** vyřazené subjekty zůstávají v DB s důvodem (`out/all_candidates.csv`).

### Chyby nalezené a opravené při vývoji (před ručním ověřením)

Opravy jsou obecná pravidla, žádný záznam se neupravoval ručně:

| Chyba | Příčina | Oprava |
|---|---|---|
| Zahraniční „Vista Credit Partners“ splynulo s českým fondem „Vista“ | Slučování dílčích značek pod značku jen z registru | Slučovat jen pod značky z CVCA nebo z tagu médií |
| Jet Investment (buyout) a Jet Industrial Lease (realitní) zařazeny jako VC | „Late stage venture“ přebilo „Buy out“; realitní kontext se nevyhodnocoval | Typ podle převahy signálů a realitní kontext |
| Souhrny „dealy českých zakladatelů“ přiřazovaly investorům cizí firmy a částky | Tabulkové řádky bez tečky splynuly v jednu „větu“ | Dělení po odstavcích a parser řádku `Startup (obor): suma \| kolo \| investoři` |
| Lighthouse Ventures bez českého správce | Firma se jmenuje „Lighthouse Ventures **GP** s.r.o.“ | „GP“ přidáno mezi obecná slova |

## 4. Naměřená přesnost (ruční ověření)

**Čeká na vyplnění** `verification/form.csv` → uložit jako `verification/form_filled.csv` → `make metrics`.

Formulář má 45 řádků v náhodném pořadí (seed 20261011):
- 35 náhodně vybraných zařazených investorů (ze 44),
- 5 ze stavu `review` nebo vyřazených s nějakým dokladem,
- 5 náhodných „osob rizikového kapitálu“ bez dokladu, kvůli odhadu falešně negativních.

U každého řádku se vyplní:
- `is_real_vc`: skutečný aktivní VC/CVC s českým správcem? U nezařazených `Y` znamená chybu pipeline.
- `evidence_ok`: dokládá odkaz s datem investici?
- `fields_ok`: sedí sektor, ticket a AUM?

Hodnoty jsou `Y` / `N` / `?`.

| Metrika | Výsledek | 95% CI (Wilson) |
|---|---|---|
| Precision zařazení (`is_real_vc`) | _doplní `make metrics`_ | |
| Platnost dokladů (`evidence_ok`) | | |
| Správnost polí (`fields_ok`) | | |
| Falešně vyřazení ve vzorku nezařazených | | |

## 5. Pokrytí polí a úplnost

**Vyplněnost polí u 44 zařazených:**

| Pole | Vyplněno | Poznámka |
|---|---:|---|
| Český správce + IČO | 100 % | podmínka zařazení |
| Sektory | 95 % | taxonomie 16 kategorií z textů dokladů a profilu CVCA |
| Fáze (pre-seed…growth) | 70 % | |
| Výše investice | 91 % | 6× z profilu CVCA (stav 2020), 34× **proxy = rozpětí velikosti kol**, kterých se investor účastnil (celé kolo, ne jeho podíl) |
| Celkový kapitál (AUM) | 18 % | 5× z médií, 3× z CVCA (2020). Raději prázdné než odhad |
| Web | 14 % | jen z CVCA. Bez placeného vyhledávání se web dohledává špatně |

**Úplnost (recall):**
- **Referenční seznam:** čeští VC členové CVCA (Credo, Depo, Inven, Kaya, Nation1, Tensor, Tilia).
  Zařazeno je 6 ze 7 (86 %). Chybí Kaya VC: je aktivní, ale její česká správcovská firma se v ARES pod
  shodným názvem nenašla, proto skončila ve stavu `review`.
- **Capture–recapture** (registr ČNB × tagy CzechCrunch): Chapmanův odhad vychází 33 (CI 25–41), tedy
  **méně než 44 skutečně nalezených**. Oba kanály zachycují hlavně známé investory a nejsou nezávislé,
  proto odhad populace nelze použít. Uvádím ho pro úplnost.
- **Kvalitativně:** ve vzorku chybí investoři, o kterých CzechCrunch v posledních 36 měsících nepsal
  aspoň dvakrát, a ti, kdo investují jen do akciových společností (u a.s. se společníci v OR nezveřejňují).
  Odhaduji, že aktivních českých VC/CVC je 50–70, takže vzorek pokrývá zhruba 65–85 %.

## 6. Odhad dostupného okruhu ve světě (zpřesnění PLAN §5)

| Typ | Populace | Podklad | Dohledatelné z veřejných zdrojů s dokladem | Spolehlivost |
|---|---|---|---|---|
| VC | US ~1 300 firem / ~2 200 fondů (2019, NVCA). **EU: 1 369 fondů EuVECA od 527 správců** (ESMA, staženo 2026-10-11). Celosvětově řádově 5–10 tis. aktivních firem | NVCA Yearbook 2020, ESMA registr | 60–85 % | vysoká |
| PE | řádově 5–10 tis. firem; ESMA eviduje **106 650 AIF fondů** všech typů (VC/PE je jen menší část) | ESMA, SEC Form ADV | 50–75 % | vysoká |
| Family office | ~8 000 SFO (2024) | Deloitte | 15–30 % | střední |
| Angel | US ~335 tis. aktivních (2020) | UNH CVR | 1–5 % (jen veřejně vystupující) | nízká–střední; GDPR |

**Co z českého vzorku platí pro svět:**
- Registry dávají kandidáty a právní identitu, ale **ne doklad aktivity**. V ČR mělo doložené investice
  jen 14 ze 404 „osob rizikového kapitálu“. Bez médií nebo obchodního rejstříku by databáze byla plná
  neaktivních vehiklů.
- **Média jsou hlavní zdroj dokladů i objevování.** 25 ze 44 investorů našla jen média. Pro každou zemi je
  proto potřeba konektor na 1–3 hlavní startupová média a jazykově specifická pravidla.
- **Obchodní rejstřík se společníky** (CZ, SK, UK Companies House PSC, DE Handelsregister…) je nejsilnější
  nezávislé ověření. Dostupnost se liší podle země.
- **Celkem realisticky 15–30 tis. ověřených záznamů**, z toho 70–80 % VC a PE.

## 7. Odhad nákladů na rozšíření na celý svět

### Naměřeno na českém vzorku

| Položka | Hodnota |
|---|---|
| Síťové požadavky na první běh | ~1 550 (crawl 800 + pipeline 750), cca 30 min s rate-limitem 1 req / 1,5 s |
| Opakovaný běh z cache | 40 s |
| Cache | 188 MB HTML/JSON (854 článků, průměrně ~160 kB HTML na článek) |
| Infrastruktura | notebook, 0 Kč |
| Vývoj pipeline (Claude Code) | 1 pracovní den včetně zjišťování zdrojů |
| Ruční ověření | cíl ≤ 1 min/záznam (skutečný čas se doplní po vyplnění formuláře) |
| Podíl `review` vůči zařazeným | 31 / 44 ≈ 0,7 |

### Model (scénář A – zdarma, pravidla + ruční práce)

```
Náklady = (konektory + jazykové sady + entity resolution) × HOURLY_RATE        … jednorázově
        + N_review × min_review / 60 × HOURLY_RATE                            … jednorázově
        + N_included × podíl_QA × min_QA / 60 × HOURLY_RATE                   … na každé obnovení
        + údržba konektorů (20–30 % ročně) × HOURLY_RATE
        + provoz (VPS) 0–20 USD / měsíc
```

| Položka | Předpoklad | Hodiny |
|---|---|---:|
| Konektory registrů (~40 zemí × 1–3 dny) | US SEC Form D/ADV vyžaduje jen kontaktní e-mail v User-Agentu; UK Companies House zdarma s API klíčem; EU ESMA veřejné Solr API | 320–960 |
| Konektory médií (~50 zemí × 1–3 média × 1 den) | sitemap/RSS + parser článku | 400–800 |
| Jazykové sady pravidel (~20 jazyků × 2–3 dny) | vzory jmen, sloves, částek, národností | 320–480 |
| Globální entity resolution a deduplikace | | 120 |
| Ruční review (N_included 20 tis. × 0,7 × 3 min) | podíl review naměřený v ČR | ~700 |
| QA při každé obnově (5 % vzorek × 1 min) | | ~17 / obnova |
| **Jednorázově celkem** | | **~1 900–3 100 h** |
| Údržba ročně | weby a sitemapy se mění | ~400–800 h / rok |

Výsledek v penězích je parametr: **jednorázově ≈ (1 900–3 100) × HOURLY_RATE, ročně ≈ (400–800) × HOURLY_RATE**.

| HOURLY_RATE (příklad) | Jednorázově | Ročně |
|---:|---:|---:|
| 800 Kč | 1,5–2,5 mil. Kč | 0,3–0,6 mil. Kč |
| 1 200 Kč | 2,3–3,7 mil. Kč | 0,5–1,0 mil. Kč |
| 1 800 Kč | 3,4–5,6 mil. Kč | 0,7–1,4 mil. Kč |

### Scénář B – s placeným LLM (jen výhled)

LLM by nahradil jazykové sady pravidel a velkou část ručního review: vytahoval by z článku investora,
firmu, částku a roli a sám by hodnotil sporné případy.
- **Objem:** ~100–300 tis. článků o investicích za 36 měsíců ve světě × ~1,5–2 tis. tokenů čistého textu
  na článek ≈ **150–600 mil. vstupních tokenů** na úvodní běh. Obnova je řádově desetina.
- **Cena:** tokeny × ceník platný v době nasazení (parametr `PRICE_PER_MTOK`).
- **Úspora:** odpadne ~320–480 h jazykových pravidel a odhadem polovina review (~350 h). Ruční QA vzorku
  zůstává.

## 8. Omezení

- **Média:** tier C pochází jen z CzechCrunch. „2 nezávislé zdroje“ znamenají 2 různé články o různých
  investicích. Druhé médium (Forbes CZ, HN, StartupJobs Blog) by zvýšilo úplnost i nezávislost dokladů.
- **Datum investice:** u médií je to datum publikace článku. Článek může zmiňovat i starší investici
  („dříve investoval…“).
- **Profily CVCA jsou z roku 2020.** Ticket a AUM z nich jsou s datem a novější údaj z médií má přednost.
- **Výše investice z médií je velikost kola**, ne podíl investora. Pole se proto jmenuje `round_size_proxy`.
- **JERRS chrání automatizaci CAPTCHA**, proto se používá datovaný snapshot. Obnova je poloautomatická.
- **CVC se rozpoznává jen podle explicitních slov.** Inven Capital (ČEZ) je proto veden jako `vc`.
