"""Metriky přesnosti z ručně vyplněného formuláře (PLAN.md §9.3)."""

from __future__ import annotations

import csv
import json
import math
import sqlite3
from pathlib import Path


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def _rate(rows: list[dict], col: str) -> dict:
    vals = [r[col].strip().upper() for r in rows if r.get(col, "").strip().upper() in ("Y", "N")]
    k, n = vals.count("Y"), len(vals)
    lo, hi = wilson(k, n)
    return {"yes": k, "n": n, "unknown": len(rows) - n,
            "rate": round(k / n, 3) if n else None,
            "ci95": [round(lo, 3), round(hi, 3)] if n else None}


def from_form(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    inc = [r for r in rows if r["skupina"] == "included"]
    exc = [r for r in rows if r["skupina"] != "included"]
    filled = [r for r in rows if r.get("is_real_vc", "").strip()]
    return {
        "rows": len(rows),
        "filled_rows": len(filled),
        "precision_is_real_vc": _rate(inc, "is_real_vc"),
        "evidence_valid": _rate(inc, "evidence_ok"),
        "fields_correct": _rate(inc, "fields_ok"),
        "false_negative_rate_in_sample": _rate(exc, "is_real_vc"),
        "errors": [{"row": r["row"], "investor": r["investor"], "skupina": r["skupina"],
                    "is_real_vc": r["is_real_vc"], "evidence_ok": r["evidence_ok"],
                    "fields_ok": r["fields_ok"], "note": r["note"]}
                   for r in rows if "N" in (r["is_real_vc"].upper(), r["evidence_ok"].upper(), r["fields_ok"].upper())
                   or (r["skupina"] != "included" and r["is_real_vc"].upper() == "Y")],
    }


def from_db(db: Path) -> dict:
    con = sqlite3.connect(db)
    q = lambda s: con.execute(s).fetchall()  # noqa: E731
    status = dict(q("SELECT status, COUNT(*) FROM investor GROUP BY status"))
    codes = dict(q("SELECT exclusion_code, COUNT(*) FROM investor WHERE status!='included' GROUP BY exclusion_code"))
    sample_where = "status='included' AND type IN ('vc','cvc')"
    n = q(f"SELECT COUNT(*) FROM investor WHERE {sample_where}")[0][0]
    fill = {}
    for col in ["sectors", "stages", "ticket_min_eur", "aum_eur", "website", "manager_ico"]:
        k = q(f"SELECT COUNT(*) FROM investor WHERE {sample_where} AND {col} IS NOT NULL AND {col} != ''")[0][0]
        fill[col] = round(k / n, 3) if n else None
    ticket_src = dict(q(f"SELECT ticket_source, COUNT(*) FROM investor WHERE {sample_where} GROUP BY ticket_source"))
    aum_src = dict(q(f"SELECT aum_source, COUNT(*) FROM investor WHERE {sample_where} GROUP BY aum_source"))
    tier_a = q(f"""SELECT COUNT(DISTINCT i.id) FROM investor i JOIN evidence e ON e.investor_id=i.id
                  WHERE {sample_where.replace('status', 'i.status').replace('type', 'i.type')}
                  AND e.claim='investment' AND e.tier='A'""")[0][0]
    by_source = q(f"SELECT sources, COUNT(*) FROM investor WHERE {sample_where} GROUP BY sources")
    con.close()
    return {"status": status, "not_included_codes": codes, "sample_size": n, "fill_rates": fill,
            "ticket_sources": ticket_src, "aum_sources": aum_src,
            "sample_with_tier_a_investment": tier_a, "sample_by_discovery_sources": dict(by_source)}


def write(metrics: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
