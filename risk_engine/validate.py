"""Backtest the Fundamental Distress Index against real RBI actions and defaults.

Three questions, in order of how much the answers are worth:

1. Lead time   -- on the last accounts published before the event, where did the
                  institution rank? How many months of warning was that?
2. Separation  -- do distressed institutions score higher than everyone else?
                  Reported as AUC, with the honest caveat that 11 events is a
                  small sample.
3. Cost        -- what does the alert list look like in practice: how many names
                  must a user watch to catch the failures?

Point-in-time discipline: FY-ending-March accounts are not public until roughly
the end of the following June, so a FY2019 score is only treated as "known" from
2019-06-30. Nothing is credited with warning that it could not have given.
"""

import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

PUBLICATION_LAG_MONTHS = 3  # FY ends 31 Mar; results out by ~30 Jun
HORIZON_MONTHS = 24         # window in which an event counts as "predicted"
ALERT_THRESHOLD = 80        # FDI at or above this raises an alert


def available_from(fy):
    """Date the FY-t accounts become public."""
    return pd.Timestamp(year=int(fy), month=3, day=31) + pd.DateOffset(
        months=PUBLICATION_LAG_MONTHS
    )


def label(scored, events):
    """Mark each company-year that is followed by an event within the horizon."""
    d = scored.copy()
    d["known_at"] = d["fy"].map(available_from)
    ev = events.copy()
    ev["event_date"] = pd.to_datetime(ev["event_date"])
    first = ev.groupby("company")["event_date"].min()

    d["event_date"] = d["company"].map(first)
    delta = (d["event_date"] - d["known_at"]).dt.days
    d["months_to_event"] = delta / 30.44
    d["is_pre_event"] = (delta > 0) & (d["months_to_event"] <= HORIZON_MONTHS)
    # Accounts published after the event are contaminated; exclude from scoring.
    d["post_event"] = delta <= 0
    return d


def auc(y, s):
    """Mann-Whitney AUC. Returns NaN if either class is empty."""
    m = ~(pd.isna(y) | pd.isna(s))
    y, s = np.asarray(y)[m].astype(bool), np.asarray(s)[m]
    if y.sum() == 0 or (~y).sum() == 0:
        return np.nan
    r = pd.Series(s).rank().to_numpy()
    n1, n0 = y.sum(), (~y).sum()
    return (r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def lead_time_table(d, events):
    """For each event, the last score published before it happened."""
    rows = []
    ev = events.copy()
    ev["event_date"] = pd.to_datetime(ev["event_date"])
    for _, e in ev.sort_values("event_date").iterrows():
        h = d[(d["company"] == e["company"]) & (d["known_at"] < e["event_date"])]
        h = h[h["fdi"].notna()]
        if h.empty:
            continue
        last = h.sort_values("known_at").iloc[-1]
        # first time the alert rule (level OR deterioration) fired
        run = h.sort_values("known_at")
        crossed = run[run["alert"].fillna(False).astype(bool)]
        first_alert = crossed.iloc[0] if len(crossed) else None
        rows.append({
            "company": e["company"],
            "event": e["event_type"],
            "event_date": e["event_date"].date(),
            "last_fy": int(last["fy"]),
            "fdi_at_last_fy": round(last["fdi"], 1),
            "peer_pctile": round(last["fdi"], 0),
            "lead_months": round((e["event_date"] - last["known_at"]).days / 30.44, 1),
            "first_alert_fy": int(first_alert["fy"]) if first_alert is not None else None,
            "alert_lead_months": (
                round((e["event_date"] - first_alert["known_at"]).days / 30.44, 1)
                if first_alert is not None else None
            ),
        })
    return pd.DataFrame(rows)


def main():
    scored = pd.read_csv(os.path.join(HERE, "scored.csv"))
    events = pd.read_csv(os.path.join(HERE, "events.csv"))
    d = label(scored, events)

    # evaluation universe: scored rows, pre-event only, in the years where the
    # panel is dense enough to rank against
    u = d[(d["fdi"].notna()) & (~d["post_event"]) & d["fy"].between(2013, 2021)].copy()

    print("=" * 72)
    print("1. LEAD TIME  (last accounts published before the event)")
    print("=" * 72)
    lt = lead_time_table(d, events)
    print(lt.to_string(index=False))
    lt.to_csv(os.path.join(HERE, "lead_times.csv"), index=False)

    hit = lt["first_alert_fy"].notna()
    print(f"\nalerted at some point before the event : {hit.sum()}/{len(lt)}")
    # The stricter, more honest reading: did it fire inside the window where a
    # warning is actually actionable, rather than having been flagged for years?
    inwin = d[d["is_pre_event"] & d["alert"].fillna(False).astype(bool)]
    print(f"alerted inside the {HORIZON_MONTHS}-month pre-event window : "
          f"{inwin['company'].nunique()}/{len(lt)}")
    if hit.any():
        print(f"median warning from first alert       : "
              f"{lt.loc[hit, 'alert_lead_months'].median():.0f} months")
    miss = lt.loc[~hit, "company"].tolist()
    if miss:
        print(f"never alerted                         : {', '.join(miss)}")

    print()
    print("=" * 72)
    print("2. SEPARATION")
    print("=" * 72)
    n_pos = int(u["is_pre_event"].sum())
    print(f"company-years: {len(u)}   pre-event (within {HORIZON_MONTHS}m): {n_pos}")
    print(f"AUC, FDI level              : {auc(u['is_pre_event'], u['fdi']):.3f}")

    # Is the *change* in score a better signal than the level?
    u = u.sort_values(["company", "fy"])
    u["fdi_chg2"] = u.groupby("company")["fdi"].diff(2)
    print(f"AUC, 2y change in FDI       : {auc(u['is_pre_event'], u['fdi_chg2']):.3f}")

    # single-ratio baselines, to show the composite is earning its keep.
    # equity/TA and borrowings/equity are the same ratio inverted (Spearman
    # -0.86), so they are one baseline reported two ways, not two.
    for col, name in [("f_capital_buffer", "equity / total assets"),
                      ("f_roa", "return on assets"),
                      ("f_leverage", "borrowings / equity")]:
        sign = 1 if col == "f_leverage" else -1
        print(f"AUC, {name:24s}: {auc(u['is_pre_event'], sign * u[col]):.3f}")

    print()
    print("=" * 72)
    print("2b. IS THE ALARM TIME-VARYING, OR A PERMANENT LABEL?")
    print("=" * 72)
    n_psu = int(events["event_type"].eq("regulatory").sum())
    print(f"A capital ratio scores a high AUC here because {n_psu} of {len(events)} events")
    print("are thinly-capitalised banks put under PCA. It separates")
    print("them -- but it says the same thing every year, so it carries no")
    print("timing. Persistence below is the share of a flagged firm's observed")
    print("years that it spends on the alert list.")
    print()
    u["lev_pct"] = u.groupby("fy")["f_leverage"].rank(pct=True) * 100
    years_per_co = u.groupby("company").size()
    for name, col in [("FDI composite", "fdi"), ("leverage alone", "lev_pct")]:
        thr = np.nanpercentile(u[col], 90)
        a = u[u[col] >= thr]
        caught = a.loc[a["is_pre_event"], "company"].nunique()
        pers = a.groupby("company").size().div(years_per_co).mean()
        always = [c for c, n in a.groupby("company").size().items()
                  if n == years_per_co[c] and years_per_co[c] >= 8]
        ev_names = set(events["company"])
        n_ev_total = u.loc[u["is_pre_event"], "company"].nunique()
        print(f"  {name:16s} top decile: catches {caught}/{n_ev_total}   "
              f"persistence {pers:.0%}   "
              f"permanently flagged for 8+ yrs: {len(always)} firms, "
              f"{len([c for c in always if c in ev_names])} of which failed")
    print("\n  -> leverage alone permanently flags HDFC Bank, ICICI, Axis,")
    print("     Canara and Bank of Baroda, none of which failed. Higher AUC,")
    print("     unusable as an alarm. AUC is the wrong metric on a clustered")
    print("     event set; it is reported above for completeness only.")

    print()
    print("=" * 72)
    print("3. COST OF THE ALERT LIST")
    print("=" * 72)
    total_ev = u.loc[u["is_pre_event"], "company"].nunique()
    uni = u.groupby("fy")["company"].nunique().mean()
    mat_uni = u[u["is_material"]].groupby("fy")["company"].nunique().mean()
    print(f"  universe: {uni:.0f} institutions/yr, of which {mat_uni:.0f} material")
    print(f"  {'rule':42s} {'caught':>8s} {'names/yr':>9s} {'material/yr':>12s}")

    def row(mask, lbl):
        a = u[mask]
        c = a.loc[a["is_pre_event"], "company"].nunique()
        n = a.groupby("fy")["company"].nunique().mean()
        nm = a[a["is_material"]].groupby("fy")["company"].nunique().mean()
        print(f"  {lbl:42s} {c:4d}/{total_ev:<3d} {n:9.0f} {nm:12.0f}")

    for thr in (70, 80, 90):
        row(u["fdi"] >= thr, f"level only: FDI >= {thr}")
    row(u["alert"].fillna(False).astype(bool),
        "level OR deterioration  (the rule used)")

    print()
    print("=" * 72)
    print("4. CONTROLS  (should stay low throughout)")
    print("=" * 72)
    controls = ["HDFC Bank Ltd", "ICICI Bank Ltd", "Kotak Mahindra Bank Ltd",
                "State Bank of India", "Axis Bank Ltd", "Bajaj Finance Ltd"]
    c = d[d["company"].isin(controls) & d["fy"].between(2013, 2023)]
    piv = c.pivot_table(index="company", columns="fy", values="fdi").round(0)
    print(piv.to_string())
    print(f"\nmax control score over the window: {piv.max().max():.0f}")


if __name__ == "__main__":
    main()
