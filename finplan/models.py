"""Data model for a household's accounts, policies and recurring cash flows.

Every record is flat (no nesting) so the same fields work in a YAML file,
a spreadsheet row, a form, or an editable table.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date
from enum import Enum
from typing import Any


class Kind(str, Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    BROKERAGE = "brokerage"
    CRYPTO = "crypto"
    IRA = "ira"
    ROTH_IRA = "roth_ira"
    K401 = "401k"
    ROTH_401K = "roth_401k"
    EDUCATION_529 = "529"
    HSA = "hsa"
    WHOLE_LIFE = "whole_life"
    TERM_LIFE = "term_life"
    DISABILITY = "disability"
    ANNUITY = "annuity"
    OTHER = "other"


class Tax(str, Enum):
    """How money coming out of an account is taxed."""

    CASH = "cash"  # already after tax
    TAXABLE = "taxable"  # capital gains on the gain only
    PRE_TAX = "pre_tax"  # ordinary income on everything, penalty before 59.5
    ROTH = "roth"  # contributions free; earnings taxed + penalty before 59.5
    EDUCATION = "education"  # tax-free for qualified education costs
    HSA = "hsa"  # tax-free for medical costs
    INSURANCE = "insurance"  # cash value: gain over premiums paid is ordinary income
    ANNUITY_NONQUALIFIED = "annuity_nonqualified"  # gain is ordinary income, penalty before 59.5
    ANNUITY_QUALIFIED = "annuity_qualified"  # held in an IRA: like pre_tax
    NONE = "none"  # no cash value (term life, disability)


DEFAULT_TAX: dict[Kind, Tax] = {
    Kind.CHECKING: Tax.CASH,
    Kind.SAVINGS: Tax.CASH,
    Kind.BROKERAGE: Tax.TAXABLE,
    Kind.CRYPTO: Tax.TAXABLE,
    Kind.IRA: Tax.PRE_TAX,
    Kind.ROTH_IRA: Tax.ROTH,
    Kind.K401: Tax.PRE_TAX,
    Kind.ROTH_401K: Tax.ROTH,
    Kind.EDUCATION_529: Tax.EDUCATION,
    Kind.HSA: Tax.HSA,
    Kind.WHOLE_LIFE: Tax.INSURANCE,
    Kind.TERM_LIFE: Tax.NONE,
    Kind.DISABILITY: Tax.NONE,
    Kind.ANNUITY: Tax.ANNUITY_NONQUALIFIED,
    Kind.OTHER: Tax.TAXABLE,
}

CASH_KINDS = {Kind.CHECKING, Kind.SAVINGS}


class Frequency(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    ANNUAL = "annual"


PER_YEAR = {
    Frequency.MONTHLY: 12,
    Frequency.QUARTERLY: 4,
    Frequency.SEMIANNUAL: 2,
    Frequency.ANNUAL: 1,
}


@dataclass
class Account:
    """Any account, policy or contract you own."""

    id: str
    name: str
    kind: Kind
    balance: float = 0.0  # market value, cash value or accumulation value
    institution: str = ""
    as_of: date | None = None
    tax: Tax | None = None  # defaults from kind
    cost_basis: float | None = None  # brokerage cost, Roth contributions, or premiums paid
    surrender_charge: float = 0.0  # what you lose if you cash out today
    death_benefit: float | None = None  # paid to beneficiaries; defaults to balance
    monthly_benefit: float = 0.0  # disability benefit while disabled
    benefit_end_age: float | None = None
    premium: float = 0.0  # what you pay, per premium_frequency
    premium_frequency: Frequency = Frequency.MONTHLY
    premium_end: date | None = None  # last premium date (pay period, term end)
    premium_active: bool = True  # false if you've stopped paying
    rate: float | None = None  # interest or expected growth, yearly
    owner: str = "self"
    ownership: str = "unknown"  # separate, community, joint, unknown
    beneficiary: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        self.kind = Kind(self.kind)
        if self.tax is None or self.tax == "":
            self.tax = DEFAULT_TAX[self.kind]
        self.tax = Tax(self.tax)
        self.premium_frequency = Frequency(self.premium_frequency or "monthly")

    @property
    def is_cash(self) -> bool:
        return self.kind in CASH_KINDS


@dataclass
class CashFlow:
    """A recurring income (positive) or expense (negative)."""

    name: str
    amount: float  # per occurrence; + income, - expense
    frequency: Frequency = Frequency.MONTHLY
    months: list[int] = field(default_factory=list)  # which months it hits; blank = spread evenly
    category: str = ""
    start: date | None = None
    end: date | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        self.frequency = Frequency(self.frequency or "monthly")
        if isinstance(self.months, str):
            self.months = [int(m) for m in self.months.replace(" ", "").split(",") if m]
        self.months = [int(m) for m in (self.months or [])]

    @property
    def monthly_average(self) -> float:
        return self.amount * PER_YEAR[self.frequency] / 12


@dataclass
class Assumptions:
    ordinary_tax_rate: float = 0.24  # combined federal + state marginal rate
    capital_gains_rate: float = 0.15  # combined federal + state
    early_withdrawal_penalty: float = 0.10
    penalty_free_age: float = 59.5
    cash_floor: float = 0.0  # runway ends when cash would drop below this
    cash_interest_rate: float = 0.0


@dataclass
class Profile:
    name: str = ""
    birth_date: date | None = None
    state: str = ""

    def age_on(self, when: date) -> float | None:
        if not self.birth_date:
            return None
        return (when - self.birth_date).days / 365.25


@dataclass
class Household:
    profile: Profile
    assumptions: Assumptions
    accounts: list[Account]
    cashflows: list[CashFlow]


def known_fields(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    """Keep only the keys a dataclass accepts, so extra columns don't break loading."""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}
