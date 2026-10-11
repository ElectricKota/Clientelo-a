from investors.extract import investor_names, parse_amounts, parse_range_eur, sentences, startup_names
from investors.resolve import brand_key, display_name

TAPAYA = ("Na další rozvoj nyní Tapaya získala v úvodním, takzvaném pre-seed kole investici ve výši "
          "jeden milion eur, téměř 25 milionů korun. Investiční kolo vedl tuzemský fond Depo Ventures "
          "společně s britským Passion Capital, připojil se také lotyšský BADideas.fund.")


def test_investor_names_and_nationality():
    s = sentences(TAPAYA)[1]
    hits = {h.name: h.nationality for h in investor_names(s)}
    assert hits["Depo Ventures"] == "CZ"
    assert hits["Passion Capital"] == "FOREIGN"


def test_person_is_not_investor_org():
    s = "Do kola se zapojil i investor Pavel Novák a investiční skupina Rockaway."
    names = [h.name for h in investor_names(s)]
    assert "Pavel Novák" not in names
    assert "Rockaway" in names


def test_amounts_to_eur():
    assert parse_amounts("investici ve výši jeden milion eur") == [1_000_000]
    assert parse_amounts("25 milionů korun") == [1_000_000]
    assert parse_amounts("fond o velikosti 1,5 miliardy korun") == [60_000_000]


def test_ranges():
    assert parse_range_eur("50 000 – 300 000 EUR") == (50_000, 300_000)
    assert parse_range_eur("50k EUR – 10M EUR") == (50_000, 10_000_000)
    assert parse_range_eur("přes 2.5 miliard EUR") == (2.5e9, 2.5e9)
    assert parse_range_eur("1 mil Kč – 5 mil Kč") == (40_000, 200_000)


def test_brand_key_merges_registry_and_media_names():
    assert brand_key("DEPO VENTURES AF II., osoba rizikového kapitálu, s.r.o.") == brand_key("Depo Ventures")
    assert brand_key("Inven Capital - Podfond A") == brand_key("Inven Capital, SICAV, a.s.")
    assert brand_key("Reflex 2, osoba rizikového kapitálu SE") == brand_key("Reflex Capital")
    assert display_name("KAYA VC") == "Kaya VC"


def test_startup_names():
    assert "Gitgut" in startup_names("Do startupu Gitgut investovaly fondy Credo Ventures a Reflex Capital.")


def test_deal_roundup_line():
    from investors.extract import deal_line, is_investment_sentence
    s = ("Delta Green (energetika): 2,2 milionu eur (55 milionů korun) | seed | "
         "Tilia Impact Ventures, Credo Ventures, Purple Ventures")
    assert deal_line(s) == ("Delta Green", "energetika")
    assert is_investment_sentence("Product Fruits (B2B SaaS): 1,6 milionu dolarů (36 milionů korun) | Reflex Capital")
    assert deal_line("Startup (obor): suma | kolo | investoři") is None
