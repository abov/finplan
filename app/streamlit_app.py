"""finplan screen: `streamlit run app/streamlit_app.py` (set FINPLAN_DATA to your private file)."""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import fields
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finplan import engine, storage  # noqa: E402
from finplan.models import Account, CashFlow, Frequency, Kind, Tax  # noqa: E402

ACCENT = "#2a6fdb"
st.set_page_config(page_title="finplan", layout="wide")


def money(x: float) -> str:
    return f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}"


# ------------------------------------------------------------------ data file
with st.sidebar:
    st.header("Your data")
    path = st.text_input(
        "Household file",
        value=str(storage.default_path()),
        help="A YAML file kept somewhere private, such as your finplan-data repo.",
    )
    as_of = st.date_input("Values as of", value=date.today())
    if Path(path).resolve() == storage.EXAMPLE.resolve():
        st.info("Showing the made-up example. Point this at your own private file.")

try:
    household = storage.load(path)
except FileNotFoundError:
    st.error(f"No file at {path}. Copy examples/household.example.yaml there to start.")
    st.stop()
except Exception as exc:  # show load errors plainly
    st.error(f"Couldn't read {path}: {exc}")
    st.stop()

snap = engine.snapshot(household, as_of)
st.title(f"{household.profile.name or 'Household'} finances")
if snap.age:
    st.caption(f"As of {snap.as_of:%b %d, %Y} · age {snap.age:.1f}")

tab_overview, tab_accounts, tab_budget, tab_heirs = st.tabs(
    ["Overview", "Accounts", "Monthly budget", "If I die tomorrow"]
)

# ------------------------------------------------------------------ overview
with tab_overview:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Market value", money(snap.market), help="What statements show.")
    c2.metric("Cash out today", money(snap.liquid), help="After surrender charges.")
    c3.metric("After tax", money(snap.after_tax), help="After income tax, capital gains and the early-withdrawal penalty.")
    c4.metric("To heirs", money(snap.to_heirs), help="Accounts plus life insurance, after your heirs' tax.")

    lines = engine.average_month(household, as_of)
    net = sum(ln.amount for ln in lines)
    run = engine.runway(household)
    cash = sum(a.balance for a in household.accounts if a.is_cash)
    if run.months is None:
        st.success(f"Typical month nets {money(net)}. Your {money(cash)} in cash does not run out.")
    else:
        st.warning(
            f"Typical month nets **{money(net)}**. With nothing else changing, your {money(cash)} "
            f"in checking and savings runs out in **{run.months} months ({run.runs_out:%B %Y})**."
        )

    left, right = st.columns(2)
    with left:
        st.subheader("After-tax value by account type")
        by_kind: dict[str, float] = defaultdict(float)
        for v in snap.values:
            if v.market:
                by_kind[v.account.kind.value] += v.after_tax
        items = sorted(by_kind.items(), key=lambda kv: kv[1])
        fig = go.Figure(
            go.Bar(
                x=[v for _, v in items],
                y=[k for k, _ in items],
                orientation="h",
                marker=dict(color=ACCENT, cornerradius=4),
                hovertemplate="%{y}: $%{x:,.0f}<extra></extra>",
            )
        )
        fig.update_layout(height=360, margin=dict(l=0, r=10, t=10, b=0), xaxis_tickprefix="$")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Checking + savings, month by month")
        months = [d for d, _ in run.path[:36]]
        values = [v for _, v in run.path[:36]]
        fig = go.Figure(
            go.Scatter(
                x=months, y=values, mode="lines", line=dict(color=ACCENT, width=2),
                hovertemplate="%{x|%b %Y}: $%{y:,.0f}<extra></extra>",
            )
        )
        fig.add_hline(y=household.assumptions.cash_floor, line=dict(color="#888", width=1, dash="dot"))
        fig.update_layout(height=360, margin=dict(l=0, r=10, t=10, b=0), yaxis_tickprefix="$", hovermode="x")
        st.plotly_chart(fig, use_container_width=True)

    todo = [(a.name, a.notes) for a in household.accounts if "CHECK" in (a.notes or "")]
    todo += [(c.name, c.notes) for c in household.cashflows if "CHECK" in (c.notes or "")]
    if todo:
        st.subheader("To confirm")
        for name, note in todo:
            st.markdown(f"- **{name}:** {note.replace('CHECK:', '').strip()}")

# ------------------------------------------------------------------ accounts
ACCOUNT_COLS = [f.name for f in fields(Account)]
CASHFLOW_COLS = [f.name for f in fields(CashFlow)]


def _save(accounts: pd.DataFrame | None = None, cashflows: pd.DataFrame | None = None) -> None:
    data = storage.household_to_dict(household)
    if accounts is not None:
        data["accounts"] = accounts.to_dict("records")
    if cashflows is not None:
        data["cashflows"] = cashflows.to_dict("records")
    try:
        storage.save(storage.household_from_dict(data), path)
    except Exception as exc:
        st.error(f"Not saved: {exc}")
        return
    st.success(f"Saved to {path}")
    st.rerun()


with tab_accounts:
    st.caption("Edit any cell, add rows at the bottom, then Save. Values are per the column names; premiums are per premium_frequency.")
    df = pd.DataFrame(storage.household_to_dict(household)["accounts"], columns=ACCOUNT_COLS)
    for col in ("as_of", "premium_end"):
        df[col] = pd.to_datetime(df[col])
    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "kind": st.column_config.SelectboxColumn(options=[k.value for k in Kind], required=True),
            "tax": st.column_config.SelectboxColumn(options=[t.value for t in Tax]),
            "premium_frequency": st.column_config.SelectboxColumn(options=[f.value for f in Frequency]),
            "ownership": st.column_config.SelectboxColumn(options=["separate", "community", "joint", "unknown"]),
            "balance": st.column_config.NumberColumn(format="$%.2f"),
            "as_of": st.column_config.DateColumn(),
            "premium_end": st.column_config.DateColumn(),
        },
        key="accounts",
    )
    if st.button("Save accounts", type="primary"):
        _save(accounts=edited)

    st.subheader("Each account three ways")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Account": v.account.name,
                    "Type": v.account.kind.value,
                    "Market": v.market,
                    "Cash out today": v.liquid,
                    "After tax": v.after_tax,
                    "Assumptions": " ".join(v.notes),
                }
                for v in snap.values
            ]
        ),
        use_container_width=True,
        hide_index=True,
        column_config={c: st.column_config.NumberColumn(format="$%.0f") for c in ["Market", "Cash out today", "After tax"]},
    )

# ------------------------------------------------------------------ budget
with tab_budget:
    st.caption("Income is positive, expenses negative. For twice-a-year or yearly items, list the months they hit, like 4,12.")
    cdf = pd.DataFrame(storage.household_to_dict(household)["cashflows"], columns=CASHFLOW_COLS)
    for col in ("start", "end"):
        cdf[col] = pd.to_datetime(cdf[col])
    cdf["months"] = cdf["months"].apply(lambda m: ",".join(str(x) for x in m) if isinstance(m, list) else (m or ""))
    cedited = st.data_editor(
        cdf,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "frequency": st.column_config.SelectboxColumn(options=[f.value for f in Frequency]),
            "amount": st.column_config.NumberColumn(format="$%.2f"),
            "start": st.column_config.DateColumn(),
            "end": st.column_config.DateColumn(),
        },
        key="cashflows",
    )
    if st.button("Save budget", type="primary"):
        _save(cashflows=cedited)

    st.subheader("Typical month by category")
    cats: dict[str, float] = defaultdict(float)
    for ln in engine.average_month(household, as_of):
        cats[ln.category] += ln.amount
    st.dataframe(
        pd.DataFrame(sorted(cats.items(), key=lambda kv: kv[1]), columns=["Category", "Per month"]),
        hide_index=True,
        column_config={"Per month": st.column_config.NumberColumn(format="$%.2f")},
    )
    st.caption("Insurance premiums come from the Accounts tab, so they aren't entered twice.")

# ------------------------------------------------------------------ heirs
with tab_heirs:
    st.metric("Beneficiaries would receive", money(snap.to_heirs))
    st.caption(
        "Life insurance death benefits are generally income-tax-free. Inherited pre-tax accounts "
        "are taxed as heirs withdraw them (estimated at your ordinary rate). Brokerage accounts "
        "get a step-up in cost basis."
    )
    st.dataframe(
        pd.DataFrame(
            [{"Account": v.account.name, "Type": v.account.kind.value, "To heirs": v.to_heirs, "Beneficiary": v.account.beneficiary}
             for v in sorted(snap.values, key=lambda v: -v.to_heirs) if v.to_heirs]
        ),
        use_container_width=True,
        hide_index=True,
        column_config={"To heirs": st.column_config.NumberColumn(format="$%.0f")},
    )
