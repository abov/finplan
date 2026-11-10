"""Read and write a household file (YAML).

Your real file lives outside this repository (for example in a private
`finplan-data` repo). Point the app at it with --data or FINPLAN_DATA.
"""

from __future__ import annotations

import os
from dataclasses import MISSING, asdict, fields
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from .models import Account, Assumptions, CashFlow, Household, Profile, known_fields

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "household.example.yaml"


def default_path() -> Path:
    env = os.environ.get("FINPLAN_DATA")
    return Path(env).expanduser() if env else EXAMPLE


def _to_date(value: Any) -> date | None:
    if value in (None, "") or value != value:  # None, blank, NaN
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):  # pandas Timestamp
        return value.date()
    return date.fromisoformat(str(value)[:10])


DATE_FIELDS = {"as_of", "premium_end", "start", "end", "birth_date"}


def _clean(record: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, float) and value != value:  # NaN from a table editor
            value = None
        if key in DATE_FIELDS:
            value = _to_date(value)
        out[key] = value
    return {k: v for k, v in out.items() if v is not None}


def household_from_dict(data: dict[str, Any]) -> Household:
    profile = Profile(**known_fields(Profile, _clean(data.get("profile") or {})))
    assumptions = Assumptions(**known_fields(Assumptions, _clean(data.get("assumptions") or {})))
    accounts = [Account(**known_fields(Account, _clean(a))) for a in data.get("accounts") or []]
    cashflows = [CashFlow(**known_fields(CashFlow, _clean(c))) for c in data.get("cashflows") or []]
    ids = [a.id for a in accounts]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"Account ids must be unique; repeated: {sorted(dupes)}")
    return Household(profile, assumptions, accounts, cashflows)


def load(path: str | Path | None = None) -> Household:
    path = Path(path) if path else default_path()
    with open(path) as fh:
        return household_from_dict(yaml.safe_load(fh) or {})


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _compact(obj: Any) -> dict[str, Any]:
    """Dataclass to dict, dropping fields left at their defaults."""
    defaults = {}
    for f in fields(obj):
        if f.default is not MISSING:
            defaults[f.name] = f.default
    out = {}
    for key, value in asdict(obj).items():
        value = _plain(value)
        if value in (None, "", []) or (key in defaults and _plain(defaults[key]) == value):
            continue
        out[key] = value
    return out


def household_to_dict(h: Household) -> dict[str, Any]:
    accounts = []
    for a in h.accounts:
        accounts.append({"id": a.id, "name": a.name, "kind": a.kind.value, **_compact(a)})
    return {
        "profile": _compact(h.profile),
        "assumptions": asdict(h.assumptions),
        "accounts": accounts,
        "cashflows": [
            {"name": c.name, "amount": c.amount, **_compact(c)} for c in h.cashflows
        ],
    }


def save(h: Household, path: str | Path) -> None:
    with open(path, "w") as fh:
        yaml.safe_dump(household_to_dict(h), fh, sort_keys=False, allow_unicode=True)
