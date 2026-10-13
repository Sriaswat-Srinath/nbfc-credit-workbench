"""Export a compact JSON bundle for the dashboard.

Carries both analyses on a common time axis: the fundamental index moves once a
year when accounts are published, the Merton probability moves every month.
Seeing them together is the whole point of the page.
"""

import os
import json

import numpy as np
import pandas as pd

from score import top_drivers, WEIGHTS

HERE = os.path.dirname(os.path.abspath(__file__))
FIRST_FY, LAST_FY = 2013, 2023


def r(x, n=1):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(v) else round(v, n)


def main():
    d = pd.read_csv(os.path.join(HERE, "scored.csv"))
    ev = pd.read_csv(os.path.join(HERE, "events.csv"))
    lt_path = os.path.join(HERE, "lead_times.csv")
    lt = pd.read_csv(lt_path) if os.path.exists(lt_path) else pd.DataFrame()

    mp = os.path.join(HERE, "merton.csv")
    merton = pd.read_csv(mp, parse_dates=["date"]) if os.path.exists(mp) else pd.DataFrame()

    d = d[d["fy"].between(FIRST_FY, LAST_FY)]
    ev_map = ev.groupby("company")["event_date"].min().to_dict()
    ev_type = ev.groupby("company")["event_type"].first().to_dict()

    # ---- monthly grid for the market series ----
    months, mser = [], {}
    if not merton.empty:
        m = merton.copy()
        m["ym"] = m["date"].dt.to_period("M").astype(str)
        g = m.sort_values("date").groupby(["company", "ym"]).last().reset_index()
        months = sorted(g["ym"].unique())
        midx = {v: i for i, v in enumerate(months)}
        for comp, sub in g.groupby("company"):
            arr = [None] * len(months)
            dda = [None] * len(months)
            for row in sub.itertuples():
                i = midx[row.ym]
                if np.isfinite(row.pd):
                    arr[i] = int(round(row.pd * 10000))      # basis points
                if np.isfinite(row.dd):
                    dda[i] = round(float(row.dd), 2)
            mser[comp] = {"pd": arr, "dd": dda}

    companies = []
    for name, grp in d.groupby("company"):
        grp = grp.sort_values("fy")
        last = grp.iloc[-1]
        if not np.isfinite(last.get("fdi", np.nan)):
            continue
        series = [[int(x.fy), r(x.fdi)] for x in grp.itertuples()
                  if np.isfinite(getattr(x, "fdi", np.nan))]
        if not series:
            continue

        comps = []
        for k in WEIGHTS:
            comps.append([k, r(last.get(f"s_{k}")), r(last.get({
                "capital_buffer": "f_capital_buffer",
                "capital_erosion": "f_capital_erosion",
                "profitability": "f_roa",
                "leverage": "f_leverage",
                "interest_burden": "f_interest_burden",
                "earnings_trend": "f_earnings_trend"}[k]), 4)])

        mk = mser.get(name)
        last_pd = last_dd = None
        if mk:
            for v in reversed(mk["pd"]):
                if v is not None:
                    last_pd = v
                    break
            for v in reversed(mk["dd"]):
                if v is not None:
                    last_dd = v
                    break

        companies.append({
            "n": name,
            "t": last["nse"] if isinstance(last["nse"], str) else "",
            "sec": "Bank" if last["sector"] == "Banks" else "NBFC",
            "pg": last["peer_group"],
            "mat": bool(last["is_material"]),
            "rec": str(last.get("source", "")) == "recovered",
            "ta": r(last["total_assets"], 0),
            "fdi": r(last["fdi"]),
            "band": last["fdi_band"] if isinstance(last["fdi_band"], str) else None,
            "alert": bool(last["alert"]) if pd.notna(last["alert"]) else False,
            "base3": r(last.get("fdi_base3")),
            "jump": r(last.get("fdi_jump")),
            "eqta": r(last["f_capital_buffer"], 4),
            "roa": r(last["f_roa"], 4),
            "lev": r(last["f_leverage"], 2),
            "gnpa": r(last.get("gnpa_last"), 2),
            "comp": comps,
            "drv": [[k, v] for k, v in top_drivers(last, 3)],
            "s": series,
            "m": mk,
            "pd": last_pd,
            "dd": last_dd,
            "ev": ev_map.get(name),
            "evt": ev_type.get(name),
        })

    companies.sort(key=lambda c: -c["fdi"])

    med = d[d["is_material"]].groupby("fy")["fdi"].median().round(1).dropna()

    bundle = {
        "as_of_fy": LAST_FY,
        "as_of_market": months[-1] if months else None,
        "n_companies": len(companies),
        "n_material": sum(c["mat"] for c in companies),
        "n_market": len(mser),
        "n_events": len(ev),
        "weights": WEIGHTS,
        "months": months,
        "median_by_fy": {int(k): float(v) for k, v in med.items()},
        "events": [{"company": e["company"], "date": e["event_date"],
                    "type": e["event_type"], "desc": e["description"]}
                   for _, e in ev.iterrows()],
        "lead_times": ([{k: (None if (isinstance(v, float) and not np.isfinite(v)) else v)
                         for k, v in row.items()} for _, row in lt.iterrows()]
                       if len(lt) else []),
        "companies": companies,
    }

    out = os.path.join(HERE, "dashboard_data.json")
    with open(out, "w") as fh:
        json.dump(bundle, fh, separators=(",", ":"), default=str)
    print(f"wrote {out} ({os.path.getsize(out)/1024:.0f} KB) "
          f"{len(companies)} institutions, {len(mser)} with a market series, "
          f"{len(months)} months")


if __name__ == "__main__":
    main()
