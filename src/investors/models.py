from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .connectors.cnb_jerrs import JerrsEntity
from .connectors.cvca import CvcaProfile

TIER_A, TIER_B, TIER_C = "A", "B", "C"


@dataclass
class Evidence:
    claim: str            # investment | registry | czech_manager | profile | aum | ticket
    value: str
    source_url: str
    source_type: str      # registry | registry_vr | association | press
    tier: str
    published_date: str   # datum, ke kterému zdroj tvrzení dokládá (ISO); "" = neznámé
    retrieved_at: str
    snippet: str = ""
    sha256: str = ""
    company: str = ""     # u investic: název portfoliové firmy
    amount_eur: float | None = None


@dataclass
class Investor:
    key: str
    name: str
    aliases: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    jerrs: list[JerrsEntity] = field(default_factory=list)
    cvca: CvcaProfile | None = None
    cc_tags: set[str] = field(default_factory=set)
    nationality: Counter = field(default_factory=Counter)
    evidence: list[Evidence] = field(default_factory=list)
    text_context: list[str] = field(default_factory=list)   # věty pro sektory/typ

    manager_ico: str = ""
    manager_name: str = ""
    manager_source: str = ""   # jerrs | jerrs_fund_manager | ares_name | ""
    manager_country: str = ""
    known_icos: set[str] = field(default_factory=set)

    type: str = ""             # vc | cvc | pe | other
    tags: set[str] = field(default_factory=set)
    status: str = ""           # included | review | excluded
    exclusion_code: str = ""
    reasons: list[str] = field(default_factory=list)
    confidence: float = 0.0

    sectors: list[str] = field(default_factory=list)
    stages: list[str] = field(default_factory=list)
    ticket_min_eur: float | None = None
    ticket_max_eur: float | None = None
    ticket_source: str = ""    # cvca_profile | round_size_proxy
    ticket_as_of: str = ""
    aum_eur: float | None = None
    aum_source: str = ""
    aum_as_of: str = ""
    website: str = ""

    def investments(self, since: str = "") -> list[Evidence]:
        return [e for e in self.evidence
                if e.claim == "investment" and (not since or e.published_date >= since)]
