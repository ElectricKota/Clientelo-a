"""Uložení výsledku do SQLite (PLAN.md §3)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import Investor

SCHEMA = """
DROP TABLE IF EXISTS investor;
DROP TABLE IF EXISTS fund;
DROP TABLE IF EXISTS evidence;
CREATE TABLE investor (
  id INTEGER PRIMARY KEY, key TEXT UNIQUE, name TEXT, type TEXT, tags TEXT, status TEXT,
  exclusion_code TEXT, reasons TEXT, confidence REAL,
  manager_name TEXT, manager_ico TEXT, manager_source TEXT, country TEXT,
  sectors TEXT, stages TEXT,
  ticket_min_eur REAL, ticket_max_eur REAL, ticket_source TEXT, ticket_as_of TEXT,
  aum_eur REAL, aum_source TEXT, aum_as_of TEXT, website TEXT,
  sources TEXT, aliases TEXT, n_investments_window INTEGER, last_investment_date TEXT
);
CREATE TABLE fund (
  investor_id INTEGER, ico TEXT, name TEXT, list_code TEXT, since TEXT,
  manager_ico TEXT, manager_name TEXT, source_url TEXT
);
CREATE TABLE evidence (
  investor_id INTEGER, claim TEXT, value TEXT, tier TEXT, source_type TEXT,
  published_date TEXT, retrieved_at TEXT, source_url TEXT, snippet TEXT, sha256 TEXT,
  company TEXT, amount_eur REAL
);
CREATE INDEX ev_inv ON evidence(investor_id);
"""


def save(investors: list[Investor], path: Path, cutoff: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    for n, i in enumerate(sorted(investors, key=lambda x: x.key), start=1):
        inv = i.investments(cutoff)
        con.execute(
            "INSERT INTO investor VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (n, i.key, i.name, i.type, ",".join(sorted(i.tags)), i.status, i.exclusion_code,
             " | ".join(i.reasons), i.confidence, i.manager_name, i.manager_ico, i.manager_source,
             i.manager_country, ",".join(i.sectors), ",".join(i.stages),
             i.ticket_min_eur, i.ticket_max_eur, i.ticket_source, i.ticket_as_of,
             i.aum_eur, i.aum_source, i.aum_as_of, i.website,
             ",".join(sorted(i.sources)), json.dumps(sorted(i.aliases), ensure_ascii=False),
             len(inv), max((e.published_date for e in inv), default="")))
        for e in i.jerrs:
            con.execute("INSERT INTO fund VALUES (?,?,?,?,?,?,?,?)",
                        (n, e.ico, e.name, e.list_code, e.since, e.manager_ico, e.manager_name, e.source_url))
        for e in i.evidence:
            con.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (n, e.claim, e.value, e.tier, e.source_type, e.published_date, e.retrieved_at,
                         e.source_url, e.snippet, e.sha256, e.company, e.amount_eur))
    con.commit()
    con.close()
