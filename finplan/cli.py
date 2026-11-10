"""Command line: `python -m finplan summary --data path/to/household.yaml`."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date

from . import engine, storage


def _money(x: float) -> str:
    return f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}"


def summary(path: str | None, as_of: date | None) -> str:
    h = storage.load(path)
    snap = engine.snapshot(h, as_of)
    out = []
    age = f", age {snap.age:.1f}" if snap.age else ""
    out.append(f"{h.profile.name or 'Household'} as of {snap.as_of}{age}\n")
    out.append(f"  Market value          {_money(snap.market):>14}")
    out.append(f"  Cash out today        {_money(snap.liquid):>14}   after surrender charges")
    out.append(f"  After tax             {_money(snap.after_tax):>14}   after tax and penalties")
    out.append(f"  To heirs if I die     {_money(snap.to_heirs):>14}   incl. life insurance\n")

    by_kind: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for v in snap.values:
        row = by_kind[v.account.kind.value]
        row[0] += v.market
        row[1] += v.liquid
        row[2] += v.after_tax
    out.append(f"  {'Type':<14}{'Market':>12}{'Cash out':>12}{'After tax':>12}")
    for kind, (m, liq, at) in sorted(by_kind.items(), key=lambda kv: -kv[1][0]):
        if m:
            out.append(f"  {kind:<14}{_money(m):>12}{_money(liq):>12}{_money(at):>12}")

    lines = engine.average_month(h, snap.as_of)
    income = sum(ln.amount for ln in lines if ln.amount > 0)
    spend = sum(ln.amount for ln in lines if ln.amount < 0)
    out.append(f"\n  Typical month: {_money(income)} in, {_money(spend)} out, net {_money(income + spend)}")
    r = engine.runway(h)
    cash = sum(a.balance for a in h.accounts if a.is_cash)
    if r.months is None:
        out.append(f"  Cash runway: {_money(cash)} in cash does not run out in 50 years")
    else:
        out.append(f"  Cash runway: {_money(cash)} in cash runs out in {r.months} months ({r.runs_out:%b %Y})")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="finplan")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("summary", help="net worth three ways, monthly cash flow and runway")
    s.add_argument("--data", help="household YAML file (default: $FINPLAN_DATA or the example)")
    s.add_argument("--as-of", type=date.fromisoformat, help="YYYY-MM-DD (default: today)")
    args = parser.parse_args(argv)
    if args.cmd == "summary":
        print(summary(args.data, args.as_of))
