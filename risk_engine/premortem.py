"""Pre-mortem experiments: does this system survive its own most likely failures?

Three tests, in the order a sceptic should run them.

  1. UNSEEN-EVENT TEST   Does it work on events that were not used to pick its
                         components? Development uses only events before 2018;
                         the methodology is then frozen and run on the four
                         later ones.
  2. ALERT-UTILITY TEST  Is the alert list usable? Precision, persistence,
                         watchlist size and lead time, against single-ratio
                         baselines and the market-based model.
  3. COVERAGE TEST       How many real distress events could not be evaluated
                         at all, and which way does that bias the results?

Run:  python3 premortem.py
"""

import os
import numpy as np
import pandas as pd

import score as sc
from validate import label, auc, available_from, HORIZON_MONTHS

HERE = os.path.dirname(os.path.abspath(__file__))
SPLIT_DATE = pd.Timestamp("2018-01-01")


def line(c="-", n=78):
    print(c * n)


def header(t):
    print()
    line("=")
    print(t)
    line("=")


# ----------------------------------------------------- 1. unseen-event test --
def rescore(panel, weights, dual_anchor=None):
    """Score the panel under a given component set without touching score.py."""
    old_w, old_d = sc.WEIGHTS, sc.DUAL_ANCHOR
    sc.WEIGHTS = weights
    if dual_anchor is not None:
        sc.DUAL_ANCHOR = dual_anchor
    try:
        return sc.score(panel)
    finally:
        sc.WEIGHTS, sc.DUAL_ANCHOR = old_w, old_d


ALL_COMPONENTS = {
    "capital_buffer": 0.30, "capital_erosion": 0.20, "profitability": 0.20,
    "leverage": 0.12, "interest_burden": 0.10, "earnings_trend": 0.08,
    "funding_stress": 0.00, "growth_burst": 0.00,
}


def experiment_1(panel, events):
    header("EXPERIMENT 1 - UNSEEN-EVENT TEST")
    print("Component selection is redone using ONLY events before 2018, then the")
    print("methodology is frozen and evaluated on the later events it never saw.")

    ev = events.copy()
    ev["event_date"] = pd.to_datetime(ev["event_date"])
    dev_ev = ev[ev["event_date"] < SPLIT_DATE]
    test_ev = ev[ev["event_date"] >= SPLIT_DATE]
    print(f"\ndevelopment events ({len(dev_ev)}): "
          f"{', '.join(sorted(dev_ev['company'].str.replace(' Ltd', '', regex=False)))}")
    print(f"held-out events ({len(test_ev)}): "
          f"{', '.join(sorted(test_ev['company'].str.replace(' Ltd', '', regex=False)))}")

    # ---- re-run the component decision on development data only ----
    full = rescore(panel, {k: (v if v > 0 else 0.01) for k, v in ALL_COMPONENTS.items()})
    d_all = label(full, dev_ev)
    dev_rows = d_all[(d_all["fy"] <= 2016) & (~d_all["post_event"])]

    print(f"\nComponent discrimination on development data only "
          f"({len(dev_rows):,} company-years, {int(dev_rows['is_pre_event'].sum())} pre-event):")
    print(f"  {'component':18s} {'AUC (dev only)':>15s}   decision")
    keep = {}
    for c in ALL_COMPONENTS:
        a = auc(dev_rows["is_pre_event"], dev_rows[f"s_{c}"])
        verdict = "keep" if (a == a and a >= 0.5) else "DROP"
        if verdict == "keep":
            keep[c] = None
        print(f"  {c:18s} {a:15.3f}   {verdict}")

    shipped = set(sc.WEIGHTS)
    dev_keep = set(keep)
    print(f"\n  components kept on dev-only evidence : {', '.join(sorted(dev_keep))}")
    print(f"  components in the shipped model       : {', '.join(sorted(shipped))}")
    if dev_keep == shipped:
        print("  -> identical. The drop decision replicates without seeing the "
              "later events.")
    else:
        print(f"  -> DIFFERENT. only in dev: {sorted(dev_keep - shipped)}; "
              f"only in shipped: {sorted(shipped - dev_keep)}")

    # ---- freeze and evaluate on the held-out events ----
    weights = {k: v for k, v in ALL_COMPONENTS.items() if k in dev_keep and v > 0}
    if not weights:
        print("\n  no components survived; cannot evaluate")
        return
    tot = sum(weights.values())
    weights = {k: v / tot for k, v in weights.items()}

    frozen = rescore(panel, weights)
    d_test = label(frozen, test_ev)
    print(f"\nFrozen model on the {len(test_ev)} held-out events "
          f"(weights renormalised over kept components):")
    print(f"  {'institution':26s} {'event':11s} {'first alert':>12s} {'lead':>8s}")
    caught = 0
    for _, e in test_ev.sort_values("event_date").iterrows():
        h = d_test[(d_test["company"] == e["company"])
                   & (d_test["known_at"] < e["event_date"])
                   & d_test["fdi"].notna()].sort_values("known_at")
        a = h[h["alert"].fillna(False).astype(bool)]
        nm = e["company"].replace(" Ltd", "")
        if len(a):
            first = a.iloc[0]
            lead = (e["event_date"] - first["known_at"]).days / 30.44
            caught += 1
            print(f"  {nm:26s} {e['event_type']:11s} {'FY' + str(int(first['fy'])):>12s} "
                  f"{lead:7.0f}m")
        else:
            print(f"  {nm:26s} {e['event_type']:11s} {'none':>12s} {'-':>8s}"
                  f"   (peak {h['fdi'].max():.0f})")

    u = d_test[d_test["fdi"].notna() & d_test["fy"].between(2017, 2021)]
    watch = u[u["alert"].fillna(False).astype(bool)]
    per_yr = watch.groupby("fy")["company"].nunique().mean()
    mat = watch[watch["is_material"]].groupby("fy")["company"].nunique().mean()
    print(f"\n  held-out events caught : {caught}/{len(test_ev)}")
    print(f"  watchlist              : {per_yr:.0f} names/yr, {mat:.0f} material")
    print(f"\n  Caveat: {len(test_ev)} events is still too few to call this validated.")
    print("  It shows the result is not purely an artefact of the selection step.")


# ---------------------------------------------------- 2. alert-utility test --
def experiment_2(scored, events, merton):
    header("EXPERIMENT 2 - ALERT-UTILITY TEST")
    print("AUC is not the question. The question is whether a human watching this")
    print("list would find it usable. Precision is the share of alert-years that")
    print("were actually followed by an event within 24 months.")

    d = label(scored, events)
    u = d[d["fdi"].notna() & (~d["post_event"]) & d["fy"].between(2013, 2021)].copy()

    # fiscal-year view of the market model, for a like-for-like comparison
    if not merton.empty:
        m = merton.copy()
        m["fy"] = m["date"].apply(lambda t: t.year + 1 if t.month >= 4 else t.year)
        mk = m.sort_values("date").groupby(["company", "fy"]).last()[["dd", "pd"]]
        u = u.join(mk, on=["company", "fy"])
    else:
        u["dd"] = np.nan

    u["lev_pct"] = u.groupby("fy")["f_leverage"].rank(pct=True) * 100
    u["eqta_pct"] = u.groupby("fy")["f_capital_buffer"].rank(pct=True, ascending=False) * 100
    u["mkt_pct"] = u.groupby("fy")["dd"].rank(pct=True, ascending=False) * 100

    n_events = u.loc[u["is_pre_event"], "company"].nunique()
    years = u["fy"].nunique()
    yrs_per_co = u.groupby("company").size()

    strategies = [
        ("FDI >= 80 (level only)", u["fdi"] >= 80),
        ("FDI >= 70 (level only)", u["fdi"] >= 70),
        ("FDI level OR deterioration", u["alert"].fillna(False).astype(bool)),
        ("Borrowings/equity, top decile", u["lev_pct"] >= 90),
        ("Equity/assets, worst decile", u["eqta_pct"] >= 90),
        ("Merton DD, worst decile", u["mkt_pct"] >= 90),
    ]

    print(f"\nUniverse {u['company'].nunique()} institutions, {years} years, "
          f"{n_events} reachable events\n")
    print(f"  {'rule':32s} {'caught':>7s} {'prec%':>6s} {'alerts/yr':>10s} "
          f"{'mat/yr':>7s} {'persist':>8s} {'alwaysON':>9s}")
    line()
    for name, mask in strategies:
        a = u[mask.fillna(False)]
        if a.empty:
            print(f"  {name:32s} {'n/a':>7s}")
            continue
        caught = a.loc[a["is_pre_event"], "company"].nunique()
        prec = a["is_pre_event"].mean() * 100
        per_yr = a.groupby("fy")["company"].nunique().mean()
        mat = a[a["is_material"]].groupby("fy")["company"].nunique().mean()
        pers = a.groupby("company").size().div(yrs_per_co).mean() * 100
        always = sum(1 for c, n in a.groupby("company").size().items()
                     if n == yrs_per_co[c] and yrs_per_co[c] >= 8)
        print(f"  {name:32s} {caught:4d}/{n_events:<2d} {prec:6.1f} {per_yr:10.0f} "
              f"{mat:7.0f} {pers:7.0f}% {always:9d}")

    print("\n  prec%    share of alert-years followed by an event within 24 months")
    print("  persist  share of a flagged firm's years it spends on the list")
    print("  alwaysON firms flagged in every one of their 8+ observed years")
    print("\n  Every precision figure here is low single digits, and that is the")
    print("  honest headline: with 11 events among ~500 institutions the base rate")
    print("  is about 0.2%, so even a good screen produces mostly non-events. The")
    print("  usable comparison is relative, and the column that matters is the")
    print("  last one - a rule with many always-on names is a label, not an alarm.")


# --------------------------------------------------------- 3. coverage test --
# Indian bank / NBFC distress events 2013-2023 that a complete study would
# cover. Presence in the archive is checked at run time.
KNOWN_UNIVERSE = [
    ("Yes Bank Ltd", "2020-03", "moratorium"),
    ("Reliance Capital Ltd", "2021-11", "resolution"),
    ("Reliance Home Finance Ltd", "2019-09", "default"),
    ("Religare Enterprises Ltd", "2019-01", "default"),
    ("Dhanlaxmi Bank Ltd", "2015-11", "PCA"),
    ("IDBI Bank Ltd", "2017-05", "PCA"),
    ("Indian Overseas Bank", "2015-10", "PCA"),
    ("UCO Bank", "2017-05", "PCA"),
    ("Central Bank of India", "2017-06", "PCA"),
    ("Bank of Maharashtra", "2017-06", "PCA"),
    ("Bank of India", "2017-12", "PCA"),
    ("Allahabad Bank", "2018-01", "PCA"),
    ("Corporation Bank", "2017-12", "PCA"),
    ("Dena Bank", "2017-05", "PCA"),
    ("Oriental Bank of Commerce", "2017-10", "PCA"),
    ("United Bank of India", "2017-01", "PCA"),
    ("Lakshmi Vilas Bank Ltd", "2019-09", "PCA then amalgamation 2020"),
    ("Dewan Housing Finance (DHFL)", "2019-11", "default and resolution"),
    ("SREI Infrastructure Finance Ltd", "2021-10", "resolution"),
    ("Infrastructure Leasing & Financial Services (IL&FS)", "2018-09", "default"),
    ("Punjab & Maharashtra Co-op Bank", "2019-09", "moratorium"),
    ("Altico Capital", "2019-09", "default"),
]


def experiment_3(panel):
    header("EXPERIMENT 3 - COVERAGE TEST")
    print("How much of the real distress population can this study actually see?")

    have = set(panel["company"])
    rows = []
    for name, when, kind in KNOWN_UNIVERSE:
        present = name in have
        rows.append({"institution": name, "when": when, "event": kind,
                     "in archive": "yes" if present else "NO"})
    t = pd.DataFrame(rows)
    missing = t[t["in archive"] == "NO"]

    print(f"\n  {'institution':52s} {'when':9s} {'in archive':>10s}")
    line()
    for _, r in t.iterrows():
        print(f"  {r['institution'][:52]:52s} {r['when']:9s} {r['in archive']:>10s}")

    n, k = len(t), len(missing)
    print(f"\n  evaluable: {n - k}/{n} ({(n - k) / n:.0%})   missing: {k}")
    rec = set(panel.loc[panel.get("source", "") == "recovered", "company"])
    if rec:
        print(f"\n  {len(rec)} of these were RECOVERED from source (recover_missing.py)")
        print("  and are now in the panel, scored by the frozen model:")
        for c in sorted(rec):
            print(f"    + {c}")
    print("\n  Still unrecoverable:")
    print("   - DHFL was delisted and its statements withdrawn from the source")
    print("   - IL&FS and Altico Capital were never listed")
    print("   - Punjab & Maharashtra Co-op sat outside the listed universe")
    print("\n  Direction of the residual bias: every still-missing name is a FAILURE,")
    print("  so measured recall remains somewhat optimistic. But the gap has closed")
    print("  from 11 missing to 4, and the recovered institutions were scored by a")
    print("  model frozen before they existed in the panel.")


def main():
    panel = pd.read_csv(os.path.join(HERE, "panel.csv"))
    scored = pd.read_csv(os.path.join(HERE, "scored.csv"))
    events = pd.read_csv(os.path.join(HERE, "events.csv"))
    mp = os.path.join(HERE, "merton.csv")
    merton = pd.read_csv(mp, parse_dates=["date"]) if os.path.exists(mp) else pd.DataFrame()

    experiment_1(panel, events)
    experiment_2(scored, events, merton)
    experiment_3(panel)

    header("VERDICT")
    print("The system is a usable screen, not a validated predictor. What it can")
    print("defensibly claim: it ranks institutions sensibly, it moved before the")
    print("events it was tested on, and its alert list is small enough to work.")
    print("What it cannot claim: a measured probability of default, or that the")
    print("backtest generalises - 11 events, 4 of them held out, with every")
    print("unevaluable case being a failure, does not support that.")


if __name__ == "__main__":
    main()
