from __future__ import annotations

import re
from datetime import date
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


@cache
def rules() -> dict:
    return yaml.safe_load((CONFIG_DIR / "rules.yaml").read_text(encoding="utf-8"))


@cache
def taxonomy() -> dict[str, re.Pattern]:
    raw = yaml.safe_load((CONFIG_DIR / "taxonomy.yaml").read_text(encoding="utf-8"))
    return {k: re.compile(v, re.I) for k, v in raw.items()}


def reference_date() -> date:
    return date.fromisoformat(rules()["reference_date"])


def activity_cutoff() -> str:
    ref = reference_date()
    months = rules()["activity_window_months"]
    y, m = divmod(ref.month - 1 - months, 12)
    return date(ref.year + y, m + 1, min(ref.day, 28)).isoformat()


def rx(name: str) -> re.Pattern:
    return re.compile(rules()[name], re.I)
