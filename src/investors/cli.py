"""CLI: `uv run investors build` (celý běh), `investors metrics` (po vyplnění formuláře)."""

from __future__ import annotations

import argparse
import json
import time

from . import db, export, metrics
from .config import ROOT, activity_cutoff
from .http import Fetcher
from .pipeline import Pipeline

DB_PATH = ROOT / "data" / "investors.sqlite"
OUT = ROOT / "out"
FORM = ROOT / "verification" / "form.csv"
FORM_FILLED = ROOT / "verification" / "form_filled.csv"
REPORTS = ROOT / "reports"


def cmd_build(args) -> None:
    t0 = time.time()
    f = Fetcher(offline=args.offline)
    p = Pipeline(f)
    investors = p.run()
    cutoff = activity_cutoff()
    db.save(investors, DB_PATH, cutoff)
    counts = export.export_all(investors, cutoff, OUT)
    n_form = 0
    if not FORM_FILLED.exists() or args.force_form:
        n_form = export.verification_form(investors, cutoff, FORM)
    run = {**p.stats, **counts, "verification_rows": n_form, "seconds": round(time.time() - t0, 1),
           "activity_cutoff": cutoff}
    run["db"] = metrics.from_db(DB_PATH)
    metrics.write(run, REPORTS / "run_stats.json")
    print(json.dumps(run, ensure_ascii=False, indent=2))


def cmd_metrics(args) -> None:
    m = {"form": metrics.from_form(FORM_FILLED if FORM_FILLED.exists() else FORM),
         "db": metrics.from_db(DB_PATH)}
    metrics.write(m, REPORTS / "metrics.json")
    print(json.dumps(m, ensure_ascii=False, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(prog="investors")
    sub = ap.add_subparsers(required=True)
    b = sub.add_parser("build", help="stáhne zdroje (s cache), sestaví DB, exporty a ověřovací formulář")
    b.add_argument("--offline", action="store_true", help="jen z cache, bez síťových požadavků")
    b.add_argument("--force-form", action="store_true", help="přegenerovat formulář i když existuje vyplněný")
    b.set_defaults(func=cmd_build)
    m = sub.add_parser("metrics", help="spočítá přesnost z verification/form_filled.csv")
    m.set_defaults(func=cmd_metrics)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
