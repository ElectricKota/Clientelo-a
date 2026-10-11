# Clientelo – Zadání A: Spolehlivá databáze investorů

Ověřený vzorek **českých VC investorů** postavený výhradně z veřejných a bezplatných zdrojů.
Do databáze se nedostane nic bez doloženého zdroje a data. Každé tvrzení má v tabulce `evidence`
URL, datum, citaci a SHA-256 otisk staženého obsahu.

- Plán a metodika: [PLAN.md](PLAN.md)
- Výsledky, přesnost a odhad nákladů pro celý svět: [reports/REPORT.md](reports/REPORT.md)
- Data: [out/investors_cz_vc.csv](out/investors_cz_vc.csv) (vzorek), [out/all_candidates.csv](out/all_candidates.csv)
  (všichni kandidáti i s důvodem vyřazení), [out/evidence.csv](out/evidence.csv) (doklady),
  [out/investors_cz_vc.xlsx](out/investors_cz_vc.xlsx) (vše v jednom sešitu),
  [data/investors.sqlite](data/investors.sqlite) (tabulky `investor`, `fund`, `evidence`)
- Ruční ověření: [verification/form.csv](verification/form.csv) → vyplnit a uložit jako `verification/form_filled.csv` → `make metrics`

## Spuštění

```bash
make all            # uv sync + testy + celý běh
make build-offline  # zopakuje běh jen z cache (bez sítě)
make metrics        # po vyplnění verification/form_filled.csv
```

Vyžaduje [uv](https://docs.astral.sh/uv/) (Python 3.12 si stáhne sám). První běh trvá asi 30 minut,
protože požadavky jsou záměrně zpomalené (1 požadavek / 1,5 s na doménu). Opakované běhy jedou z cache
v `data/cache/`.

## Zdroje

| Zdroj | Tier | Co dává | Přístup |
|---|---|---|---|
| ČNB JERRS – správci dle § 15 ZISIF („osoby rizikového kapitálu“), investiční společnosti, fondy a jejich obhospodařovatelé | A | kandidáti, český správce, IČO | veřejné HTML; JERRS chrání automatizaci CAPTCHA, kterou **neobcházíme** → datovaný snapshot v `data/snapshots/jerrs/` |
| ARES REST API (MF ČR) | A | existence a sídlo správce, **společníci portfoliových firem** (potvrzení investice v obchodním rejstříku) | veřejné API |
| CVCA – profily řádných členů | B | typ investic, ticket, AUM, sektory, web | HTML (profily z roku 2020, proto u polí uvádíme datum) |
| CzechCrunch – kategorie Startupy a tagy investorů | C | datované zprávy o investičních kolech | HTML, robots.txt povoluje |

## Jak pipeline rozhoduje

1. **Discovery:** registr ČNB, CVCA, tagy investorů na CzechCrunch a jména fondů nalezená v článcích.
2. **Resolve:** sjednocení názvů do jedné značky. Například „DEPO VENTURES AF II., osoba rizikového
   kapitálu, s.r.o.“, „Depo Ventures“ i tag `depo-ventures` se spojí pod jednu značku `depo`.
3. **Evidence:** věty o investicích, ve kterých je investor jmenován, s datem článku, částkou a firmou.
4. **Český správce:** z registru ČNB, jinak dohledáním v ARES s přísnou shodou názvu.
5. **Potvrzení v obchodním rejstříku:** u portfoliové firmy se v ARES ověří, zda je fond zapsán jako
   společník a od kdy (tier A).
6. **Klasifikace** podle `config/rules.yaml`:
   - `included` = český správce + VC/CVC + aktivita za posledních 36 měsíců (≥ 1 doklad tier A, nebo ≥ 2 články tier C).
   - `review` = něco chybí.
   - `excluded` = s kódem důvodu.

Pravidla a slovníky jsou v `config/`. Kód je v `src/investors/`, testy v `tests/`.
