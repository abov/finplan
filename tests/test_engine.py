from datetime import date

import pytest

from finplan import engine, storage
from finplan.models import Account, Assumptions, CashFlow, Household, Profile

ASM = Assumptions(ordinary_tax_rate=0.25, capital_gains_rate=0.15, early_withdrawal_penalty=0.10)


def household(accounts=(), cashflows=(), born=date(1977, 10, 1), **asm):
    return Household(Profile("Test", born), Assumptions(**{**ASM.__dict__, **asm}), list(accounts), list(cashflows))


def value(account, age=49):
    return engine.value_account(account, age, ASM, date(2026, 11, 10))


def test_cash_is_taken_at_face_value():
    v = value(Account("c", "Checking", "checking", balance=1000))
    assert (v.market, v.liquid, v.after_tax, v.to_heirs) == (1000, 1000, 1000, 1000)


def test_pre_tax_before_59_pays_tax_and_penalty():
    v = value(Account("i", "IRA", "ira", balance=10000))
    assert v.after_tax == pytest.approx(10000 * (1 - 0.25 - 0.10))
    assert v.to_heirs == pytest.approx(7500)  # heirs pay tax, no penalty


def test_pre_tax_after_59_has_no_penalty():
    v = value(Account("i", "IRA", "ira", balance=10000), age=60)
    assert v.after_tax == pytest.approx(7500)


def test_brokerage_taxes_only_the_gain():
    v = value(Account("b", "Brokerage", "brokerage", balance=10000, cost_basis=6000))
    assert v.after_tax == pytest.approx(10000 - 4000 * 0.15)
    assert v.to_heirs == 10000  # step-up in basis


def test_missing_basis_is_flagged_not_guessed():
    v = value(Account("b", "Brokerage", "brokerage", balance=10000))
    assert v.after_tax == 10000
    assert any("cost basis" in n for n in v.notes)


def test_roth_before_59_taxes_earnings_only():
    v = value(Account("r", "Roth", "roth_ira", balance=30000, cost_basis=20000))
    assert v.after_tax == pytest.approx(30000 - 10000 * 0.35)
    assert value(Account("r", "Roth", "roth_ira", balance=30000, cost_basis=20000), age=60).after_tax == 30000


def test_whole_life_surrender_and_death_benefit():
    wl = Account("w", "WL", "whole_life", balance=15924.62, surrender_charge=160, cost_basis=30753.65, death_benefit=251748)
    v = value(wl)
    assert v.liquid == pytest.approx(15764.62)
    assert v.after_tax == pytest.approx(15764.62)  # cash value below premiums paid: no gain
    assert v.to_heirs == 251748


def test_term_life_pays_only_before_it_ends():
    term = Account("t", "Term", "term_life", death_benefit=1_000_000, premium_end=date(2042, 12, 1))
    assert value(term).market == 0
    assert value(term).to_heirs == 1_000_000
    assert engine.value_account(term, 70, ASM, date(2047, 1, 1)).to_heirs == 0


def test_annuity_gain_taxed_with_penalty():
    v = value(Account("a", "FIA", "annuity", balance=50000, surrender_charge=3000, cost_basis=40000))
    assert v.liquid == 47000
    assert v.after_tax == pytest.approx(47000 - 7000 * 0.35)


def test_premiums_stop_after_pay_period_and_when_inactive():
    wl = Account("w", "WL", "whole_life", premium=683.45, premium_end=date(2047, 12, 1))
    lapsed = Account("x", "Old WL", "whole_life", premium=49.80, premium_active=False)
    h = household([wl, lapsed])
    assert [ln.amount for ln in engine.month_lines(h, date(2047, 12, 1))] == [-683.45]
    assert engine.month_lines(h, date(2048, 1, 1)) == []


def test_semiannual_items_land_in_their_months_and_average_evenly():
    tax = CashFlow("Property tax", -4840.38, "semiannual", months="12,4")
    h = household(cashflows=[tax])
    assert sum(ln.amount for ln in engine.month_lines(h, date(2026, 12, 1))) == -4840.38
    assert engine.month_lines(h, date(2027, 1, 1)) == []
    assert engine.average_month(h)[0].amount == pytest.approx(-4840.38 / 6)


def test_runway_counts_months_until_cash_runs_out():
    h = household(
        [Account("c", "Checking", "checking", balance=10000, as_of=date(2026, 9, 15))],
        [CashFlow("Spending", -3000)],
    )
    r = engine.runway(h)
    assert r.months == 4 and r.runs_out == date(2027, 1, 1)


def test_runway_never_runs_out_with_positive_cash_flow():
    h = household([Account("c", "Checking", "checking", balance=100)], [CashFlow("Pay", 50)])
    assert engine.runway(h, horizon_months=24).months is None


def test_example_file_round_trips(tmp_path):
    h = storage.load(storage.EXAMPLE)
    out = tmp_path / "h.yaml"
    storage.save(h, out)
    again = storage.load(out)
    assert engine.snapshot(again, date(2026, 11, 10)).after_tax == pytest.approx(
        engine.snapshot(h, date(2026, 11, 10)).after_tax
    )
    assert len(again.cashflows) == len(h.cashflows)


def test_duplicate_ids_are_rejected():
    with pytest.raises(ValueError):
        storage.household_from_dict({"accounts": [{"id": "a", "name": "A", "kind": "checking"}] * 2})
