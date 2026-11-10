# finplan

A free calculator for your whole financial picture. Enter every account you own once
(checking, savings, brokerage, crypto, IRA, Roth, 401(k), 529, whole life, term life,
disability, annuities) plus your monthly budget, and finplan shows:

- **Net worth three ways:** market value, what you could cash out today after surrender
  charges, and what you'd keep after income tax, capital gains and early-withdrawal penalties.
- **Cash runway:** month by month, when checking and savings would run out if nothing changed.
  Twice-a-year bills (like property tax) land in the months they're due, and insurance
  premiums stop when their pay period ends.
- **If I die tomorrow:** what beneficiaries would receive, with life insurance counted
  tax-free and inherited pre-tax accounts taxed.

Not financial or tax advice. The tax math uses simple flat rates you set yourself.

## Your data stays private

This repository holds the **program only**, with a made-up example household.
Keep your real file somewhere private, such as a separate **private** GitHub repo
(`your-name/finplan-data`) or just a folder on your computer. The `.gitignore` here
blocks `household.yaml` and `*.private.yaml` so real data can't be committed by mistake.

## Start

```bash
git clone https://github.com/<you>/finplan.git
cd finplan
pip install -e ".[dev]"

# try the example
python -m finplan summary

# make your own private copy and use it
cp examples/household.example.yaml ~/finplan-data/household.yaml
export FINPLAN_DATA=~/finplan-data/household.yaml
python -m finplan summary
streamlit run app/streamlit_app.py      # opens the screen in your browser
```

The screen lets you edit accounts and the budget in a table and save back to your file.

## The household file

One YAML file with four parts. Every account uses the same flat fields; leave out what
doesn't apply. See [examples/household.example.yaml](examples/household.example.yaml).

| Field | Meaning |
| --- | --- |
| `kind` | checking, savings, brokerage, crypto, ira, roth_ira, 401k, roth_401k, 529, hsa, whole_life, term_life, disability, annuity, other |
| `balance` | Market value, cash value, or annuity accumulation value |
| `cost_basis` | Brokerage cost, Roth contributions, or premiums paid (used to find the taxable gain) |
| `surrender_charge` | What you'd lose cashing out today |
| `death_benefit` | Paid to beneficiaries (life insurance, annuities) |
| `premium`, `premium_frequency`, `premium_end`, `premium_active` | What you pay and until when |
| `monthly_benefit`, `benefit_end_age` | Disability benefit |
| `tax` | Override the default tax treatment (for example `annuity_qualified` for an annuity inside an IRA) |
| `ownership` | separate, community, joint or unknown |

Cash flows are `name`, `amount` (+ income, − expense), `frequency` (monthly, quarterly,
semiannual, annual) and optional `months` (for example `[4, 12]`), `start`, `end`, `category`.

## Roadmap

1. **Track today** (this release): accounts, budget, three net worth totals, runway.
2. **Projections:** growth per account, policy cash value schedules, annuity crediting, and
   scenarios side by side (job, disability, death, retirement age, keep or drop a policy).
3. **Ranges and odds:** Monte Carlo simulation of returns and inflation, the odds your money
   lasts, and a sensitivity (tornado) chart.
4. **Spending:** import bank CSVs, auto-categorize, forecast the next 12 months.

## Tests

```bash
pytest
```
