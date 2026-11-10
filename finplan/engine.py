"""Calculations: what you have today three ways, monthly cash flow, and runway."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .models import PER_YEAR, Account, Assumptions, Frequency, Household, Kind, Tax


@dataclass
class AccountValue:
    account: Account
    market: float  # what statements show
    liquid: float  # what you could get today, after surrender charges
    after_tax: float  # liquid minus income tax, capital gains and early-withdrawal penalty
    to_heirs: float  # what beneficiaries get if you die today, after their tax
    notes: list[str] = field(default_factory=list)


@dataclass
class Snapshot:
    as_of: date
    age: float | None
    values: list[AccountValue]

    @property
    def market(self) -> float:
        return sum(v.market for v in self.values)

    @property
    def liquid(self) -> float:
        return sum(v.liquid for v in self.values)

    @property
    def after_tax(self) -> float:
        return sum(v.after_tax for v in self.values)

    @property
    def to_heirs(self) -> float:
        return sum(v.to_heirs for v in self.values)

    @property
    def cash(self) -> float:
        return sum(v.liquid for v in self.values if v.account.is_cash)


def _gain(liquid: float, basis: float | None, notes: list[str], what: str) -> float:
    if basis is None:
        notes.append(f"No {what} entered, so no taxable gain is assumed.")
        return 0.0
    return max(0.0, liquid - basis)


def value_account(
    a: Account, age: float | None, asm: Assumptions, as_of: date | None = None
) -> AccountValue:
    notes: list[str] = []
    if a.tax is Tax.NONE:
        heirs = 0.0
        if a.kind is Kind.TERM_LIFE:
            expired = a.premium_end is not None and as_of is not None and as_of > a.premium_end
            heirs = 0.0 if expired else (a.death_benefit or 0.0)
        return AccountValue(a, 0.0, 0.0, 0.0, heirs, notes)

    market = a.balance
    liquid = max(0.0, market - (a.surrender_charge or 0.0))
    if age is None:
        notes.append("No birth date, so the early-withdrawal penalty is assumed to apply.")
    early = age is None or age < asm.penalty_free_age
    pen = asm.early_withdrawal_penalty if early else 0.0
    ordinary, cg = asm.ordinary_tax_rate, asm.capital_gains_rate

    if a.tax is Tax.CASH:
        after = liquid
    elif a.tax is Tax.TAXABLE:
        after = liquid - _gain(liquid, a.cost_basis, notes, "cost basis") * cg
    elif a.tax in (Tax.PRE_TAX, Tax.ANNUITY_QUALIFIED):
        after = liquid * (1 - ordinary - pen)
    elif a.tax is Tax.ROTH:
        after = liquid if not early else liquid - _gain(
            liquid, a.cost_basis, notes, "contribution total"
        ) * (ordinary + pen)
    elif a.tax is Tax.EDUCATION:
        after = liquid
        notes.append("Tax-free only when spent on qualified education.")
    elif a.tax is Tax.HSA:
        after = liquid
        notes.append("Tax-free only when spent on medical costs.")
    elif a.tax is Tax.INSURANCE:
        after = liquid - _gain(liquid, a.cost_basis, notes, "premiums-paid total") * ordinary
    elif a.tax is Tax.ANNUITY_NONQUALIFIED:
        after = liquid - _gain(liquid, a.cost_basis, notes, "premium paid") * (ordinary + pen)
    else:  # pragma: no cover - every Tax is handled above
        raise ValueError(a.tax)

    # What beneficiaries receive. Life insurance death benefits are income-tax-free;
    # inherited pre-tax money is taxed as they withdraw it; brokerage gets a step-up in basis.
    death = a.death_benefit if a.death_benefit is not None else market
    if a.tax in (Tax.PRE_TAX, Tax.ANNUITY_QUALIFIED):
        heirs = death * (1 - ordinary)
    elif a.tax is Tax.ANNUITY_NONQUALIFIED:
        heirs = death - _gain(death, a.cost_basis, [], "") * ordinary
    else:
        heirs = death

    return AccountValue(a, market, liquid, max(0.0, after), heirs, notes)


def snapshot(h: Household, as_of: date | None = None) -> Snapshot:
    as_of = as_of or date.today()
    age = h.profile.age_on(as_of)
    return Snapshot(as_of, age, [value_account(a, age, h.assumptions, as_of) for a in h.accounts])


# ---------------------------------------------------------------- cash flow


@dataclass
class Line:
    name: str
    category: str
    amount: float


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _in_window(month: date, start: date | None, end: date | None) -> bool:
    if start and month < _month_start(start):
        return False
    if end and month > _month_start(end):
        return False
    return True


def month_lines(h: Household, month: date) -> list[Line]:
    """Every income and expense that lands in a given calendar month."""
    month = _month_start(month)
    lines: list[Line] = []
    for cf in h.cashflows:
        if not _in_window(month, cf.start, cf.end):
            continue
        if cf.frequency is Frequency.MONTHLY:
            amount = cf.amount
        elif cf.months:
            amount = cf.amount if month.month in cf.months else 0.0
        else:
            amount = cf.monthly_average  # no months given: spread it evenly
        if amount:
            lines.append(Line(cf.name, cf.category or "other", amount))
    for a in h.accounts:
        if a.premium and a.premium_active and _in_window(month, None, a.premium_end):
            per_month = (
                a.premium
                if a.premium_frequency is Frequency.MONTHLY
                else a.premium * PER_YEAR[a.premium_frequency] / 12
            )
            lines.append(Line(f"{a.name} premium", "insurance & annuities", -per_month))
    return lines


def average_month(h: Household, month: date | None = None) -> list[Line]:
    """A typical month: twice-a-year and yearly items spread evenly."""
    month = _month_start(month or date.today())
    lines: list[Line] = []
    for cf in h.cashflows:
        if _in_window(month, cf.start, cf.end) and cf.amount:
            lines.append(Line(cf.name, cf.category or "other", cf.monthly_average))
    lines += [ln for ln in month_lines(h, month) if ln.category == "insurance & annuities"]
    return lines


@dataclass
class Runway:
    months: int | None  # None = cash never runs out within the horizon
    runs_out: date | None
    path: list[tuple[date, float]]  # cash at the end of each month


def _add_month(d: date) -> date:
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)


def runway(h: Household, start: date | None = None, horizon_months: int = 600) -> Runway:
    """Months until checking and savings fall below the cash floor, with nothing else changing.

    Starts from the latest statement date on your cash accounts unless you give a start.
    """
    if start is None:
        dates = [a.as_of for a in h.accounts if a.is_cash and a.as_of]
        start = max(dates) if dates else date.today()
    start = _month_start(start)
    cash = sum(a.balance for a in h.accounts if a.is_cash)
    rate = h.assumptions.cash_interest_rate / 12
    month, path = start, []
    for n in range(1, horizon_months + 1):
        month = _add_month(month)
        cash += sum(ln.amount for ln in month_lines(h, month)) + cash * rate
        path.append((month, cash))
        if cash < h.assumptions.cash_floor:
            return Runway(n, month, path)
    return Runway(None, None, path)
