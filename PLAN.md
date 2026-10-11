# Zadání A – Spolehlivá databáze investorů: analýza a realizační plán

> Stav: v1.0, odsouhlaseno · datum: 2026-10-10 · odevzdání: **do 2026-10-17**
> Realizace (2026-10-11): F0–F7 hotovo, výsledky v [reports/REPORT.md](reports/REPORT.md); **F8 ruční ověření čeká na Michala**

---

## 0. Rozhodnutí, která už padla

| Téma | Rozhodnutí |
|---|---|
| Vzorek pro ověření | VC fondy v **Česku** |
| Kdo patří do vzorku | Jen **právně české subjekty** (registrované v ČR, mají IČO v justice.cz / evidenci ČNB) |
| Stack | **Python + SQLite**, extrakce pravidly (bez placeného LLM) |
| Rozpočet | **0 Kč**. Žádné placené API ani placené zdroje. Scraping musí být automatizovaný a zdarma, i za cenu menšího objemu dat. |
| Ruční ověření (ground truth) | Provede **zadavatel úlohy (Michal)** podle připraveného ověřovacího formuláře |
| Jazyk výstupů | Čeština (kód a schéma anglicky) |
| Výstup | Repo `Clientelo-a`: kód pipeline, tento plán, report s měřením přesnosti a export vzorku (CSV/XLSX) se zdroji a daty |
| „Český“ investor | Rozhoduje **česká správcovská firma** (obhospodařovatel/GP). Fond může být zahraniční (LU, NL, …) |
| Okno aktivity | **36 měsíců** |
| Korporátní VC | Ano, samostatný typ `cvc` |
| Akcelerátory s equity fondem | Ano, jako `vc` s tagem `accelerator` |
| LLM | **Žádné** (ani lokální) |
| Hodinová sazba v nákladovém modelu | Volitelný **parametr** |
| Časový rozpočet | Termín odevzdání je 2026-10-17. Michal má na úlohu **max. 1 h** vlastního času (kontrola plánu, ruční ověření, převzetí). Vývoj a běh pipeline dělá Claude Code |

---

## 1. Rozbor zadání: co se odevzdává

| # | Požadavek zadání | Kde ho plán řeší |
|---|---|---|
| 1 | Plán: **kdo v DB bude a kdo ne** (pravidla zařazení/vyřazení) | §2 |
| 2 | **Jak ověříme pravost** a správné zařazení záznamů | §4 |
| 3 | **Odhad okruhu** investorů z veřejných zdrojů: kolik jich bude, jaká spolehlivost a z čeho odhad vychází | §5 |
| 4 | Ověření plánu na **vzorku** (VC v ČR), u každého záznamu **zdroj + datum**, které dokládají, že subjekt investuje | §7, §8 |
| 5 | **Změřit přesnost** na ručně ověřeném vzorku | §9 |
| 6 | **Odhad nákladů** na rozšíření na celý svět | §10 |
| — | Povinná pole záznamu: sektor, do čeho investuje, výše investic (ticket), celkový kapitál (AUM), zdroj | §3 |
| — | Výhradně **veřejně dostupná data** | §6.2 |

Jádro hodnocení je **spolehlivost**: každý záznam musí být skutečný investor, nikoli náhodná firma s „Capital“ v názvu. Proto pipeline navrhuji obráceně, než bývá zvykem. Nezačíná se „sesbírej co nejvíc a pak čisti“. Platí **„nic nevstoupí do DB bez doložené investice“**. Recall je až druhý cíl.

---

## 2. Kdo v databázi bude a kdo ne

### 2.1 Jednotka záznamu
- **Investor** = subjekt, který rozhoduje o investicích (správce / investiční skupina / osoba).
- **Fond** = podřízený záznam investora (vehikl s vlastním IČO/LEI, velikostí a vintage).
- **Pravidlo vzorku:** investor do vzorku patří, pokud je jeho **správcovská firma česká právnická osoba** (IČO, sídlo v ČR). Na domicilu fondu nezáleží. Příklad: DEPO Ventures má fond *DEPO Ventures One SCSp* (Lucembursko). Je-li správce česká s.r.o., investor ve vzorku je a lucemburský fond je jeho podřízený záznam. Zahraniční správce s českým fondem dostane stav `review` s poznámkou.

### 2.2 Typy investorů (cílová taxonomie celé DB)
| Typ | Definice |
|---|---|
| `vc` | Fond/správce investující equity do startupů a rostoucích firem (pre-seed až growth) |
| `cvc` | Korporátní VC: investiční rameno nefinanční firmy (např. Inven Capital, ČEZ) |
| `pe` | Private equity: buyouty, majoritní/minoritní podíly ve zralých firmách |
| `family_office` | Single/multi family office s doloženými **přímými** investicemi do firem |
| `angel` | Fyzická osoba, která **sama veřejně vystupuje** jako investor a má ≥ 2 doložené investice |
| `private_investor` | Velký soukromý investor / holding jednotlivce s doloženými přímými investicemi do soukromých firem |

### 2.3 Pravidla zařazení (všechna musí platit)
1. **Hlavní činnost je investování** kapitálu (equity / kvazi-equity) do **soukromých firem**.
2. Existuje **alespoň 1 doložená investice za posledních 36 měsíců** (zdroj + datum). Kratší okno (24 měsíců) by vyřadilo legitimní, ale pomalu investující české fondy.
3. Subjekt je **identifikovatelný**: má IČO/LEI/registrační číslo, nebo u fyzických osob veřejný profesní profil.
4. U vzorku: **česká správcovská firma** podle §2.1 a typ `vc` / `cvc`.

### 2.4 Pravidla vyřazení (stačí jedno)
| Vyřazujeme | Důvod |
|---|---|
| Realitní, energetické, infrastrukturní, komoditní fondy | Neinvestují do firem (je to nejčastější šum v seznamech ČNB) |
| Hedge fondy a fondy investující jen do kotovaných akcií/dluhopisů | Neinvestují do soukromých firem |
| Banky, leasing, čistě dluhové fondy | Nejde o equity investory |
| **Fondy fondů** (např. NRI, EIF) | Investují do fondů, ne do firem. Použijeme je ale **jako zdroj** pro objevování kandidátů |
| Crowdfundingové platformy (samotný provozovatel) | Zprostředkovatel, ne investor |
| Poradci, M&A boutiques, konzultanti, „Capital s.r.o.“ bez investic | Nejsou investoři |
| Neaktivní subjekty (bez investice v okně aktivity, v likvidaci, zaniklé) | Neplní pravidlo 2 |
| Akcelerátory bez vlastního equity fondu | Neinvestují kapitál. Akcelerátor, který investuje equity (např. StartupYard), se **zařazuje** jako `vc` s tagem `accelerator` |

### 2.5 Stavy záznamu
`included` (splňuje vše, má doklad) · `review` (kandidát, chybí doklad nebo je sporný) · `excluded` (s kódem důvodu, např. `EXCL_REAL_ESTATE`, `EXCL_INACTIVE`, `EXCL_FOREIGN`).
Vyřazené záznamy **zůstávají v DB** i s důvodem. Je to auditní stopa a slouží k měření falešně negativních případů.

---

## 3. Datový model (SQLite)

```
investor(id, name, legal_name, type, country, reg_id /*IČO*/, lei, website,
         status, exclusion_code, sectors[], stages[],
         ticket_min, ticket_max, ticket_currency,
         aum, aum_currency, aum_as_of,
         confidence, first_seen, last_verified)

fund(id, investor_id, name, reg_id, lei, domicile, vintage, size, currency, size_as_of)

evidence(id, investor_id, claim /*is_investor|investment|sector|ticket|aum|...*/,
         value, source_url, source_type /*registry|own_site|press|association|...*/,
         source_tier /*A|B|C*/, published_date, retrieved_at,
         snippet /*doslovná citace*/, content_sha256, archive_url)

investment(id, investor_id, company_name, company_reg_id, date, round, amount, evidence_id)
```

**Zásada:** Každá hodnota v `investor` musí mít alespoň jeden řádek v `evidence`. Pole bez dokladu zůstane `NULL`. Neodhadujeme ho.
**Sektory:** pevná taxonomie (`config/taxonomy.yaml`, cca 20 kategorií: fintech, healthtech, deeptech, SaaS/B2B software, energy/cleantech, …), mapovaná slovníkem klíčových slov CZ/EN.

---

## 4. Ověření pravosti a zařazení

### 4.1 Úrovně důvěryhodnosti zdroje
| Tier | Zdroj | Příklad |
|---|---|---|
| **A** | Regulátor / veřejný rejstřík | ČNB JERRS, justice.cz (fond je **společníkem** startupu, datum zápisu), ESMA, SEC Form D/ADV |
| **B** | Vlastní zveřejnění subjektu nebo oborové asociace | Web fondu (portfolio, tisková zpráva), profil v CVCA, výroční zpráva ve Sbírce listin |
| **C** | Nezávislá média | CzechCrunch, Forbes CZ, Hospodářské noviny (článek o kole s datem) |

### 4.2 Automatické kontroly (v pipeline)
1. **Existence a právní stav:** IČO ověřené v ARES (subjekt existuje, není v likvidaci/zaniklý), u vzorku i sídlo v ČR.
2. **Regulatorní status:** záznam v ČNB JERRS (obhospodařovatel / §15 ZISIF / investiční fond).
3. **Doklad investice:** ≥ 1 investice v okně aktivity z tieru A nebo B, **nebo** ≥ 2 nezávislé zdroje tieru C.
4. **Typ (VC vs. ne-VC):** pravidlový klasifikátor nad texty webu a profilu (klíčová slova *seed, startup, venture, Series A* vs. *nemovitost, rezidenční, FVE, buyout*) a nad portfoliem (podíl mladých firem).
5. **Konzistence:** sedí název ↔ IČO ↔ doména webu (fuzzy match `rapidfuzz`), deduplikace přes IČO/LEI.
6. **Archivace dokladu:** u každého URL se uloží SHA-256 obsahu a odkaz do Wayback Machine (Save Page Now, zdarma). Doklad tak jde zpětně ověřit, i když web zmizí.
7. **Skóre spolehlivosti** záznamu (0–1) z tierů a počtu nezávislých zdrojů. Bez aspoň jednoho dokladu investice záznam **nikdy** nedostane stav `included`.

### 4.3 Ruční ověření
Viz §9. Ověřuje se **každý** záznam `included` a náhodný vzorek `excluded`/`review`.

---

## 5. Odhad dostupného okruhu (celý svět)

> **Předběžné.** Čísla vycházejí z veřejných přehledů uvedených ve sloupci „Podklad“. V kroku F8 se zpřesní přímým spočítáním ve volných registrech (Form D, Form ADV, ESMA, Companies House).

| Typ | Odhad populace | Podklad | Z veřejných zdrojů dohledatelných s dokladem | Očekávaná spolehlivost |
|---|---|---|---|---|
| VC | US ~1 300 firem / 2 200 aktivních fondů (data 2019, definice „fund v posledních 8 vintage letech“). Celosvětově řádově **5–10 tis.** aktivních firem | NVCA Yearbook 2020; neověřený odhad ~9 000 celosvětově; ESMA: ~1 370 EuVECA fondů v EU | **70–90 %** (VC se samy prezentují, mají portfolio na webu, v USA Form D) | Vysoká (precision ≥ 95 %) |
| PE | Řádově **5–10 tis.** firem | SEC Form ADV (US privátní fondy podle typu), ESMA AIFM registr | 60–80 % | Vysoká; AUM často jen jako horní řád |
| Family office | ~**8 000** SFO (2024), z toho ~3 200 Sev. Amerika, ~2 000 Evropa, ~2 300 APAC | Deloitte *Defining the Family Office Landscape* 2024 | **20–35 %** (FO jsou z principu diskrétní, doklad je hlavně v médiích) | Střední; ticket a AUM často chybí |
| Angel | US ~**335 tis.** aktivních (2020); celosvětově násobky | UNH Center for Venture Research | **1–5 %** (jen ti, kdo se sami veřejně prezentují: angel sítě, vlastní web, média) | Nízká až střední; GDPR omezení v EU (§11) |
| Velký soukromý investor | Překryv s FO, řádově tisíce | Veřejné žebříčky miliardářů, média | 30–50 % (s doloženou přímou investicí) | Střední |

**Celkem realisticky:** zhruba **15–30 tis. ověřených záznamů**, z toho naprostá většina VC a PE. Úplnost bude nejvyšší v USA, UK a EU (strojově čitelné registry), nejnižší v Asii, na Blízkém východě a v Africe.

**Očekávané vyplnění polí (VC):** sektor ~90 %, ticket ~50–70 %, AUM ~50–70 %. Ověří se na vzorku a čísla se v reportu nahradí naměřenými.

---

## 6. Technologie (vše zdarma)

### 6.1 Stack
| Vrstva | Nástroj | Proč |
|---|---|---|
| Prostředí | Python 3.12, `uv` | Rychlá a reprodukovatelná instalace |
| HTTP + cache | `httpx` + `hishel` (HTTP cache) | Šetrné opakované běhy, žádné zbytečné dotazy |
| Parsování HTML | `selectolax`, `trafilatura` (čistý text článků) | Rychlé a robustní |
| JS weby | `playwright` (jen kde je nutné) | Část webů fondů je SPA |
| PDF | `pdfplumber`, volitelně `tesseract` OCR | Výroční zprávy ze Sbírky listin |
| Validace | `pydantic` v2 | Schéma záznamu, typová kontrola |
| DB | SQLite + `sqlite-utils`; prohlížení přes `datasette` | Nula infrastruktury, snadné sdílení |
| Deduplikace | `rapidfuzz` | Fuzzy shoda názvů |
| Analýza a export | `pandas`, `openpyxl` | Metriky, CSV/XLSX |
| Orchestrace | CLI (`typer`) + `Makefile` | `make all` = celý běh |
| Testy | `pytest` + uložené HTML fixtures | Parsery testované offline |

**Bez LLM** (ani lokálního). Extrakce stojí na pravidlech, regexech a slovnících. Proto jsou výsledky deterministické a jdou kdykoli zopakovat.

### 6.2 Etika a legalita sběru
- Respektujeme `robots.txt`, máme rate-limit (1 požadavek / 2 s na doménu) a identifikovatelný User-Agent.
- **Nescrapujeme** LinkedIn, Crunchbase, PitchBook, Dealroom ani Preqin. Data jsou sice „vidět“, ale jejich podmínky scraping zakazují nebo jsou placené. „Veřejně dostupné“ v tomto projektu znamená **volně dostupné a legálně strojově zpracovatelné**.
- Ukládáme jen krátké citace (snippet) jako doklad, ne celé texty článků.

---

## 7. Zdroje pro český vzorek (ověřeno 2026-10-10)

| Zdroj | Co dá | Přístup | Role |
|---|---|---|---|
| **ČNB JERRS** – seznamy subjektů (obhospodařovatelé, správci dle §15 ZISIF, investiční fondy / FKI) | Úplný seznam regulovaných fondů a správců v ČR → **kandidáti** + status (tier A) | HTML „Základní seznamy“ (scraping). Webové služby WS JERRS vyžadují certifikát a žádost, proto je **nepoužijeme** | Kandidáti |
| **CVCA** – řádní členové (27, ověřeno) | Profil s **typem investic a preferovanou výší investice** → ticket, typ (tier B) | HTML | Kandidáti + obohacení |
| **ARES REST API** | Existence, právní stav, sídlo, NACE (64.30, 66.30) | Veřejné REST API, zdarma | Validace |
| **justice.cz – otevřená data VR** (dataor.justice.cz) | Společníci s.r.o. → **fond jako společník startupu + datum zápisu** = nejsilnější doklad investice (tier A) | Hromadné CSV/XML zdarma | Doklady investic |
| **Sbírka listin** | Výroční zprávy fondů → AUM / vlastní kapitál | PDF (často skeny) | Volitelně AUM |
| **Weby fondů** | Portfolio, tým, sektory, ticket, tiskové zprávy s daty (tier B) | Scraping | Obohacení + doklady |
| **Média s RSS/sitemap** (CzechCrunch, Forbes CZ, …) | Články o investičních kolech s datem (tier C) | RSS/sitemap | Doklady + objevování |
| **Fond fondů RRF / NRI / EIF** – vybraní správci | Seznamy VC správců podpořených státem/EU | HTML/PDF | Objevování + kontrola úplnosti |
| **ESMA registry** (Solr API) | EuVECA/AIFM manažeři | Veřejné API | Kontrola. **Ověřeno: 0 EuVECA fondů s domicilem v ČR** (EuVECA celkem ~1 370 v EU) |

Odhad velikosti vzorku: kandidátů z JERRS bude stovky (převážně realitní fondy). Po filtraci zbude **~30–60 zařazených českých VC**.

---

## 8. Pipeline (průběh dat)

```
 [1 Discovery]        JERRS + CVCA + RRF/NRI seznamy + média  → candidates (high recall)
        ↓
 [2 Resolve]          IČO přes ARES, deduplikace, právní stav, sídlo CZ
        ↓
 [3 Pre-filter]       vyřazení zjevných ne-VC (realitní, energetické, …) podle názvu/NACE/textu
        ↓
 [4 Enrich]           web fondu (najít doménu → portfolio, sektory, ticket, AUM),
                      CVCA profil, justice.cz společníci, články z RSS
        ↓
 [5 Evidence]         každé tvrzení → evidence(url, datum, snippet, tier, hash, archive)
        ↓
 [6 Classify]         pravidla §2 → included / review / excluded + kód důvodu + confidence
        ↓
 [7 Export]           out/investors_cz_vc.csv|xlsx, out/evidence.csv, verification/form.csv
        ↓
 [8 Human verify]     Michal vyplní form.csv
        ↓
 [9 Metrics+Report]   reports/REPORT.md (přesnost, CI, pokrytí, čas, náklady)
```

Dohledání webu fondu bez placeného vyhledávání: CVCA profil → Wikidata (P856) → doména odvozená z názvu (`{slug}.cz/.com/.vc`) a ověřená obsahem stránky. Co se nepodaří, označí se `website=NULL` a doplní se ručně s příznakem `manual`.

---

## 9. Měření přesnosti

### 9.1 Ověřovací formulář (`verification/form.csv`)
Formulář je navržený tak, aby se **vešel do ~40 min** Michalova času (cílově ≤ 1 min na záznam):
- Každý řádek ukazuje to, co pipeline tvrdí (typ, sektor, ticket, AUM), **jeden hlavní doklad** (URL + datum + citace snippetu) a odkaz na ARES.
- Michal vyplní jen **3 povinné sloupce**: `is_real_vc` (skutečný aktivní VC / CVC s českým správcem), `evidence_ok` (URL a datum opravdu dokládají investici), `fields_ok` (sektor / ticket / AUM sedí, jinak napíše, které pole je špatně). K tomu volitelně `note`.
- Hodnoty: `Y` / `N` / `?` (nelze ověřit).
- Pořadí řádků je náhodné (seed uložený v repu), aby únava neovlivnila výsledek systematicky.

### 9.2 Co ověřujeme (rozpočet ~40 min)
- `included`: **všechny, pokud jich je ≤ 35**. Jinak náhodný vzorek 35 (stratifikovaný podle confidence).
- `excluded` + `review`: **náhodný vzorek 10** → orientační odhad falešně negativních.
- Kvůli malému vzorku budou intervaly spolehlivosti široké. Report je uvede poctivě (např. 34/35 → precision 97 %, 95% CI ≈ 85–100 %).

### 9.3 Metriky
| Metrika | Výpočet | Cíl |
|---|---|---|
| **Precision zařazení** | TP / (TP + FP), s **95% Wilsonovým intervalem** | ≥ 95 % |
| Míra falešného vyřazení | FN ve vzorku `excluded` / velikost vzorku | ≤ 10 % |
| Přesnost polí | správně / ověřitelné, zvlášť pro sektor, ticket, AUM, typ | ≥ 85 % |
| Vyplněnost polí | non-null / included | naměřit |
| Platnost dokladů | URL skutečně dokládá investici a datum sedí | ≥ 95 % |
| **Odhad recall** | (a) vůči referenčnímu seznamu (CVCA VC členové + RRF/NRI správci); (b) **capture–recapture (Lincoln–Petersen)** mezi nezávislými kanály objevování (JERRS vs. média) | naměřit |
| Čas a objem | běh pipeline, počet požadavků, ruční minuty na záznam | vstup pro §10 |

Výsledky půjdou do `reports/REPORT.md` včetně tabulky chyb (každý FP/FN s příčinou a navrženou úpravou pravidla).

---

## 10. Odhad nákladů na celý svět (metodika)

Software i zdroje jsou zdarma, takže náklady jsou hlavně **lidská práce + provoz**. Model:

```
Náklady = Σ_zdroj (vývoj konektoru + údržba/rok)
        + N_záznamů × (podíl ruční kontroly × min/záznam)  ← naměříme na vzorku
        + N_záznamů × podíl review × min/záznam             ← naměříme na vzorku
        + provoz (VPS / scheduler)  ≈ 0–20 USD/měsíc
```

| Položka | Vstup |
|---|---|
| Konektory na strukturované registry | US: SEC Form D (čtvrtletní datasety), Form ADV (měsíční CSV vč. Schedule D 7.B.1, privátní fondy podle typu a velikosti); UK: Companies House API (zdarma, SIC 64303); EU: ESMA Solr; další země: národní regulátoři. **Odhad 1–3 dny na konektor**, cca 30–50 konektorů |
| Weby investorů a média | Generický scraper + jazykové slovníky; každý nový jazyk zhruba 1–2 dny |
| Ruční kontrola | Na vzorku naměříme min/záznam a podíl `review`; extrapolujeme na 15–30 tis. záznamů. Při plošné kontrole jen **náhodného 5% vzorku** pro QA |
| Obnova dat | Měsíční re-crawl, kontrola okna aktivity |

Report uvede **dva scénáře**:
- **A – zdarma (jako vzorek):** pravidla + ruční review. Hlavním nákladem jsou člověkohodiny. Výsledek se uvede v hodinách a jako vzorec s parametrem `HOURLY_RATE`, s ukázkovou tabulkou pro několik sazeb.
- **B – s placeným LLM** (jen jako výhled, pro porovnání): náklad = počet záznamů × naměřený objem textu na záznam (tokeny) × ceník platný v době odhadu. Ukáže, kolik ruční práce by LLM ušetřilo.

---

## 11. Rizika a jak je řešíme

| Riziko | Dopad | Opatření |
|---|---|---|
| JERRS bez exportu, HTML se může změnit | Výpadek discovery | Cache surových HTML, testy parserů na fixtures, záložní discovery přes CVCA a média |
| Weby fondů bez dat u portfolia | Chybí datum investice | Doklad z justice.cz (zápis společníka) nebo z médií |
| Česká VC jsou často v LU/NL vehiklech | Fond chybí v ČNB seznamech | Pravidlo §2.1 (rozhoduje český správce). Správce dohledat přes CVCA, média a ARES. Zahraniční správce zaznamenat jako `EXCL_FOREIGN` pro transparentnost |
| Michalův čas je max. 1 h | Malý ověřený vzorek, široké CI | Formulář na ≤ 1 min/záznam (§9), vzorek 35 + 10, CI uvést v reportu |
| AUM a ticket nejsou veřejné | Nízká vyplněnost | Raději `NULL` než odhad; vyplněnost reportovat jako metriku |
| Bez placeného vyhledávání se hůř hledají weby | Nižší recall | Wikidata + odvozené domény + ruční doplnění s příznakem |
| GDPR u andělů (při světové škále) | Právní riziko | Jen osoby, které se samy veřejně prezentují jako investoři; jen profesní údaje; oprávněný zájem (čl. 6 odst. 1 f) + informační povinnost (čl. 14). Ve vzorku (právnické osoby) nehrozí |
| Sbírka listin = naskenovaná PDF | Pracné AUM | Mimo rozsah vzorku (OCR se nedělá). AUM bereme z webů, CVCA a médií; v reportu se zmíní jako zdroj pro světovou škálu |

---

## 12. Rozhodnutí z 2026-10-10 (dřív otevřené body)

1. „Český“ investor = **česká správcovská firma** stačí, na domicilu fondu nezáleží.
2. Okno aktivity **36 měsíců**.
3. **CVC** se zahrnují jako typ `cvc`.
4. **Akcelerátory s equity fondem** se zahrnují jako `vc` + tag `accelerator`.
5. **Žádné LLM**, ani lokální.
6. Hodinová sazba je **parametr** nákladového modelu.
7. Odevzdání **do 2026-10-17**. Michal má na úlohu max. **1 h** vlastního času.

---

## 13. Realizační kroky

Vývoj a běh dělá **Claude Code**. Michalův čas je jen tam, kde je ve sloupci „Michal“ uvedena hodnota (celkem ≤ 60 min).

| Fáze | Obsah | Výstup | Michal |
|---|---|---|---|
| **F0 Setup** | `uv`, struktura, `Makefile`, `.gitignore` (raw data mimo git), README | Kostra projektu | – |
| **F1 Pravidla** | Pravidla z §2 do `config/rules.yaml`, taxonomie do `config/taxonomy.yaml` | Konfigurace | – |
| **F2 Datový model** | Pydantic modely, SQLite schéma, evidence s hashem a Wayback archivací | `models.py`, `db.py` | – |
| **F3 Discovery** | JERRS (správci + fondy), CVCA, RRF/NRI, média (RSS) | Tabulka `candidates` | – |
| **F4 Resolve + pre-filter** | ARES, deduplikace, vyřazení zjevného šumu s kódem důvodu | Zúžený seznam s důvody | – |
| **F5 Enrich + evidence** | Weby fondů (portfolio, sektory, ticket, AUM), justice.cz společníci, články | Tabulky `evidence`, `investment` | – |
| **F6 Klasifikace** | Pravidla §2 a §4.2, confidence skóre, unit testy pravidel | `included/review/excluded` | – |
| **F7 Export** | CSV/XLSX vzorku, `evidence.csv`, ověřovací formulář | `out/`, `verification/form.csv` | – |
| **F8a Kontrola průběžného výsledku** | Michal projde seznam zařazených a vyřazených (sanity check, žádné detaily) | Případné úpravy pravidel **před** ověřením | ~10 min |
| **F8b Ruční ověření** | Michal vyplní formulář (§9). Mezitím Claude spočítá světové registry (Form D/ADV, ESMA, Companies House) pro zpřesnění §5 | Vyplněný formulář, zpřesněný §5 | ~40 min |
| **F9 Metriky + report** | Precision s CI, přesnost polí, recall, rozbor chyb, nákladový model (§10) | `reports/REPORT.md` | – |
| **F10 Převzetí** | README s návodem `make all`, běh z čistého klonu, Michal přečte shrnutí reportu | Hotové repo | ~10 min |

**Harmonogram do 2026-10-17:** F0–F7 hned (stejný den) → F8 podle Michalovy dostupnosti → F9–F10 do 1 dne po vyplnění formuláře. Rezerva na opravy zůstává.

**Zúžení rozsahu kvůli 1h limitu:** vypadlo OCR výročních zpráv a ověřovaný vzorek je max. 35 + 10 záznamů. Doklady z médií se berou jen ze zdrojů s RSS/sitemap.

### Struktura repa
```
Clientelo-a/
├── PLAN.md                 ← tento dokument
├── README.md
├── pyproject.toml / uv.lock / Makefile
├── config/                 rules.yaml, taxonomy.yaml, sources.yaml
├── src/investors/
│   ├── connectors/         cnb_jerrs.py, cvca.py, ares.py, justice_or.py,
│   │                       esma.py, news_rss.py, websites.py, wayback.py
│   ├── models.py  db.py  resolve.py  classify.py  evidence.py
│   ├── export.py  metrics.py  cli.py
├── tests/                  fixtures/ (uložená HTML), test_*.py
├── data/                   raw/ (cache, mimo git), investors.sqlite
├── out/                    investors_cz_vc.csv|xlsx, evidence.csv
├── verification/           form.csv (k vyplnění), form_filled.csv
└── reports/REPORT.md
```

---

## 14. Podklady použité při sestavení plánu
- ČNB JERRS – úvod a seznamy: https://jerrs.cnb.cz/apljerrsdad/JERRS.WEB07.INTRO_PAGE?p_lang=cz
- ČNB WS JERRS (podmínky přístupu k webovým službám): https://www.cnb.cz/cs/dohled-financni-trh/seznamy/webove-sluzby-ws-jerrs/
- CVCA – řádní členové: https://cvca.cz/clenstvi/radni-clenove/
- ESMA Registers – A2A (Solr) dokumentace: https://registers.esma.europa.eu/publication/helpApp
- SEC Form D Data Sets: https://www.sec.gov/dera/data/form-d
- SEC Form ADV Data: https://www.sec.gov/foia-services/frequently-requested-documents/form-adv-data
- NVCA 2020 Yearbook (US VC firmy a fondy): https://nvca.org/?p=1139
- Deloitte – počty family offices (shrnutí): https://www.dakota.com/fundraising-news/deloitte-number-of-family-offices-to-grow-75-by-2030
- UNH Center for Venture Research – počty andělů 2020: https://www.unh.edu/unhtoday/node/18769
- Fond fondů RRF – Tensor Ventures: https://www.businessinfo.cz/clanky/prvni-investicni-vc-fond-z-narodniho-planu-obnovy-cr-bude-spravovat-tensor-ventures/
- NRI – Fond Ukrajina (DEPO Ventures One SCSp): https://www.businessinfo.cz/clanky/nri-dokoncila-vyber-venture-kapitaloveho-fondu-pro-program-fond-ukrajina/
- Otevřená data veřejného rejstříku: https://dataor.justice.cz/
- ARES REST API: https://ares.gov.cz/ekonomicke-subjekty-v-be/rest

---

## 15. Poznámky z realizace (odchylky od plánu)

| Plán | Skutečnost | Dopad |
|---|---|---|
| JERRS seznamy scrapovat živě | Při strojovém přístupu JERRS zobrazuje **CAPTCHA**. Neobcházíme ji, pipeline čte datovaný snapshot sestav z 2026-10-11 (`data/snapshots/jerrs/`). Při obnově se snapshot uloží ručně z prohlížeče | Obnova registru je poloautomatická |
| Justice.cz – hromadná otevřená data (společníci) | Místo stahování celých dumpů: **ARES REST `ekonomicke-subjekty-vr`** cíleně pro portfoliové firmy z článků | Stejný tier A doklad (zápis společníka s datem), mnohem méně dat |
| CVCA jako aktuální tier B | Všechny profily řádných členů jsou z **ledna 2020**. Ticket/AUM z CVCA se proto exportují s datem 2020 a novější údaj z médií má přednost | Hodnoty z CVCA jsou orientační |
| „≥ 2 nezávislé zdroje tieru C“ | Implementováno jako **≥ 2 různé články o různých investicích** (CzechCrunch). Jiná média nebyla v rozsahu 1h limitu | Uvedeno jako omezení v reportu |
| Datum investice | U tier C = **datum publikace článku** (proxy). U tier A = datum zápisu společníka v OR | |
| Archivace dokladů ve Wayback Machine | **Neprovedeno.** Save Page Now je zápis do veřejné služby a s 1h limitem nebyl prioritou. Doklady mají SHA-256 a lokální cache | Doplnitelné jedním příkazem |
| Pydantic, Datasette | Nahrazeno `dataclasses` a exportem do XLSX | Méně závislostí |
| Spočítat SEC Form D / ADV | SEC vyžaduje v User-Agentu kontaktní e-mail. Bez souhlasu ho nevyplňujeme, čísla pro US se berou z publikovaných přehledů | Uvedeno v §10 reportu |
