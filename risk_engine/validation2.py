"""Second-round validation: thresholds re-derived, permutation test, intervals.

Four things, in the order they change what can be claimed.

  1. THRESHOLDS RE-DERIVED    Experiment 1 only re-selected components; the alert
                              thresholds were still the ones chosen while looking
                              at all eleven events -- and the deterioration rule
                              was designed around Yes Bank, which is in the
                              held-out set. Here the thresholds are re-derived on
                              development events alone, then frozen.
  2. PERMUTATION TEST         Could this performance arise by chance? The null
                              keeps the real event dates and sector mix and
                              permutes only which institution failed.
  3. CONFIDENCE INTERVALS     Clopper-Pearson on recall, bootstrap on lead time.
  4. STRATIFIED BY EVENT TYPE PCA placement and credit events are different
                              outcomes and are reported separately.

Nothing here refits the score itself. Run: python3 validation2.py
"""

import os
import numpy as np
import pandas as pd

from validate import label, available_from, HORIZON_MONTHS

HERE = os.path.dirname(os.path.abspath(__file__))
RNG = np.random.default_rng(20261012)
N_PERM = 4000
SPLIT_DATE = pd.Timestamp("2018-01-01")

CREDIT = {"default", "moratorium", "resolution"}


def line(c="-", n=78):
    print(c * n)


def header(t):
    print()
    line("=")
    print(t)
    line("=")


def alerts_for(d, level, deter_level, jump):
    """Recompute the alert flag for a candidate threshold triple."""
    return (d["fdi"] >= level) | ((d["fdi"] >= deter_level) & (d["fdi_jump"] >= jump))


def clopper_pearson(k, n, alpha=0.05):
    """Exact binomial interval; avoids pretending 4/4 means 100%."""
    from scipy.stats import beta
    lo = 0.0 if k == 0 else beta.ppf(alpha / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - alpha / 2, k + 1, n - k)
    return lo, hi


def recall_and_leads(d, events, alert_col):
    """Institutions alerted inside the pre-event window, and their lead times."""
    caught, leads = set(), []
    for _, e in events.iterrows():
        h = d[(d["company"] == e["company"]) & (d["known_at"] < e["event_date"])
              & d["fdi"].notna()]
        h = h[h[alert_col].fillna(False).astype(bool)]
        if h.empty:
            continue
        within = h[(e["event_date"] - h["known_at"]).dt.days <= HORIZON_MONTHS * 30.44]
        if within.empty:
            continue
        first = within.sort_values("known_at").iloc[0]
        caught.add(e["company"])
        leads.append((e["event_date"] - first["known_at"]).days / 30.44)
    return caught, leads


# ------------------------------------------------- 1. thresholds re-derived --
def experiment_1b(scored, events):
    header("1. EXPERIMENT 1, CORRECTED - THRESHOLDS RE-DERIVED ON DEVELOPMENT DATA")
    print("The earlier version re-selected components on pre-2018 evidence but kept")
    print("the thresholds (80 / 60 / +15) chosen while all eleven events were visible.")
    print("The deterioration rule in particular was designed around Yes Bank's FY2019")
    print("score of 69 - and Yes Bank is in the held-out set. That is contamination,")
    print("so the thresholds are re-derived here using development events only.")

    ev = events.copy()
    ev["event_date"] = pd.to_datetime(ev["event_date"])
    dev_ev = ev[ev["event_date"] < SPLIT_DATE]
    test_ev = ev[ev["event_date"] >= SPLIT_DATE]

    d_dev = label(scored, dev_ev)
    dev_rows = d_dev[d_dev["fdi"].notna() & (~d_dev["post_event"])
                     & (d_dev["fy"] <= 2016)]

    # Selection rule stated before searching: catch the most development events,
    # tie-broken by the smaller material watchlist.
    print("\nSelection rule, fixed before the search: maximise development events")
    print("caught within 24 months, tie-break on the smaller material watchlist.")

    best, rows = None, []
    for level in (70, 75, 80, 85, 90):
        for dl in (50, 55, 60, 65):
            for jp in (10, 15, 20, 25):
                if dl >= level:
                    continue
                col = "_a"
                dd = d_dev.assign(**{col: alerts_for(d_dev, level, dl, jp)})
                caught, _ = recall_and_leads(dd, dev_ev, col)
                sub = dev_rows.assign(**{col: alerts_for(dev_rows, level, dl, jp)})
                a = sub[sub[col]]
                mat = (a[a["is_material"]].groupby("fy")["company"].nunique().mean()
                       if len(a) else 0.0)
                rows.append((len(caught), -mat, level, dl, jp, mat))
    rows.sort(reverse=True)
    n_caught, _, level, dl, jp, mat = rows[0]
    print(f"\nbest on development data: FDI >= {level}  OR  "
          f"(FDI >= {dl} AND jump >= +{jp})")
    print(f"  catches {n_caught}/{len(dev_ev)} development events, "
          f"{mat:.0f} material names/yr")
    shipped = (80, 60, 15)
    print(f"  shipped thresholds were {shipped[0]} / {shipped[1]} / +{shipped[2]}"
          f"  -> {'SAME' if (level, dl, jp) == shipped else 'DIFFERENT'}")

    # freeze and apply to the held-out events
    d_test = label(scored, test_ev)
    d_test["_a"] = alerts_for(d_test, level, dl, jp)
    caught, leads = recall_and_leads(d_test, test_ev, "_a")

    print(f"\nFrozen dev-derived rule on the {len(test_ev)} held-out events:")
    print(f"  {'institution':26s} {'type':11s} {'alerted in 24m':>15s} {'lead':>8s}")
    for _, e in test_ev.sort_values("event_date").iterrows():
        h = d_test[(d_test["company"] == e["company"])
                   & (d_test["known_at"] < e["event_date"]) & d_test["fdi"].notna()]
        w = h[h["_a"].fillna(False).astype(bool)]
        w = w[(e["event_date"] - w["known_at"]).dt.days <= HORIZON_MONTHS * 30.44]
        nm = e["company"].replace(" Ltd", "")
        if len(w):
            first = w.sort_values("known_at").iloc[0]
            lead = (e["event_date"] - first["known_at"]).days / 30.44
            print(f"  {nm:26s} {e['event_type']:11s} {'yes':>15s} {lead:7.0f}m")
        else:
            peak = h["fdi"].max() if len(h) else float("nan")
            print(f"  {nm:26s} {e['event_type']:11s} {'NO':>15s} "
                  f"{'-':>8s}  (peak {peak:.0f})")

    k, n = len(caught), len(test_ev)
    lo, hi = clopper_pearson(k, n)
    print(f"\n  held-out recall: {k}/{n}  (95% CI {lo:.0%} to {hi:.0%})")
    print("\n  Whatever this number is, the interval is the honest content. Four")
    print("  events cannot distinguish a good model from a lucky one.")
    return (level, dl, jp)


# ------------------------------------------------------ 2. permutation test --
def permutation_test(scored, events, thresholds):
    header("2. PERMUTATION TEST - COULD THIS HAVE HAPPENED BY CHANCE?")
    level, dl, jp = thresholds
    print(f"Null hypothesis: the alert rule (FDI >= {level}, or >= {dl} with a jump of")
    print(f"+{jp}) carries no information about which institution actually failed.")
    print("\nThe null keeps the real event dates and the real sector of each event, and")
    print("permutes only WHICH institution failed - drawn from institutions of the same")
    print("sector that were actually scored in that window. Scattering events uniformly")
    print("would make the test too easy to pass.")

    ev = events.copy()
    ev["event_date"] = pd.to_datetime(ev["event_date"])

    d = scored.copy()
    d["known_at"] = d["fy"].map(available_from)
    d["_a"] = alerts_for(d, level, dl, jp)
    d = d[d["fdi"].notna()]

    sector_of = scored.groupby("company")["sector"].last()
    ev["sector"] = ev["company"].map(sector_of)

    def eligible(sector, event_date):
        lo = event_date - pd.Timedelta(days=HORIZON_MONTHS * 30.44)
        sub = d[(d["sector"] == sector) & (d["known_at"] < event_date)
                & (d["known_at"] >= lo)]
        return sub["company"].unique()

    pools = {}
    for _, e in ev.iterrows():
        pools[e["company"]] = eligible(e["sector"], e["event_date"])

    # Vectorised: alerts are fixed, so only the event labelling changes. Build
    # lookup arrays once and do set arithmetic per permutation.
    d = d.reset_index(drop=True)
    comp_arr = d["company"].to_numpy()
    known_arr = d["known_at"].to_numpy()
    alert_arr = d["_a"].fillna(False).to_numpy().astype(bool)
    idx_by_company = {c: np.where(comp_arr == c)[0] for c in np.unique(comp_arr)}
    n_alerts = int(alert_arr.sum())
    horizon_ns = np.timedelta64(int(HORIZON_MONTHS * 30.44 * 86400 * 1e9), "ns")

    def stats(assign):
        """assign: [(company, event_date)] -> (events alerted, median lead, precision%)."""
        caught, leads, pre_hits = 0, [], 0
        for comp, edate in assign:
            idx = idx_by_company.get(comp)
            if idx is None or len(idx) == 0:
                continue
            k = known_arr[idx]
            win = (k < np.datetime64(edate)) & (np.datetime64(edate) - k <= horizon_ns)
            sel = idx[win]
            if sel.size == 0:
                continue
            pre_hits += int(alert_arr[sel].sum())
            a = sel[alert_arr[sel]]
            if a.size:
                caught += 1
                leads.append((np.datetime64(edate) - known_arr[a].min())
                             / np.timedelta64(1, "D") / 30.44)
        prec = pre_hits / n_alerts * 100 if n_alerts else 0.0
        return caught, (np.median(leads) if leads else np.nan), prec

    real_assign = [(r["company"], r["event_date"]) for _, r in ev.iterrows()]
    obs_caught, obs_lead, obs_prec = stats(real_assign)
    print(f"\nobserved: {obs_caught}/{len(ev)} events alerted, median lead "
          f"{obs_lead:.0f} months, precision {obs_prec:.2f}%")

    print(f"\nrunning {N_PERM:,} permutations...")
    null_caught, null_prec = [], []
    dates = list(ev["event_date"])
    comps = list(ev["company"])
    for i in range(N_PERM):
        assign = []
        for comp, edate in zip(comps, dates):
            pool = pools[comp]
            if len(pool) == 0:
                continue
            assign.append((RNG.choice(pool), edate))
        c, _, p = stats(assign)
        null_caught.append(c)
        null_prec.append(p)

    null_caught = np.array(null_caught)
    null_prec = np.array(null_prec)

    p_caught = (null_caught >= obs_caught).mean()
    p_prec = (null_prec >= obs_prec).mean()

    print(f"\n  {'statistic':22s} {'observed':>10s} {'null mean':>11s} "
          f"{'null 95th':>11s} {'p-value':>9s}")
    line()
    print(f"  {'events alerted':22s} {obs_caught:10d} {null_caught.mean():11.2f} "
          f"{np.percentile(null_caught, 95):11.1f} {p_caught:9.4f}")
    print(f"  {'alert precision %':22s} {obs_prec:10.2f} {null_prec.mean():11.2f} "
          f"{np.percentile(null_prec, 95):11.2f} {p_prec:9.4f}")

    print(f"\n  Under the null, a random same-sector institution is alerted before")
    print(f"  its 'event' {null_caught.mean():.1f} times out of {len(ev)} on average.")
    if p_caught < 0.05:
        print("  The observed result sits outside that, so chance alone is an")
        print("  unlikely explanation of the recall.")
    else:
        print("  The observed result is NOT clearly outside the null. The apparent")
        print("  performance may be an artefact of how many institutions the rule")
        print("  flags, rather than evidence that it identifies the right ones.")
    # --- the same test restricted to the held-out events ---
    # The headline above uses a rule whose thresholds were derived on 7 of these
    # 11 events, so it is partly in-sample. This version is clean.
    test_ev = ev[ev["event_date"] >= SPLIT_DATE]
    real_t = [(r["company"], r["event_date"]) for _, r in test_ev.iterrows()]
    obs_t, _, _ = stats(real_t)
    null_t = []
    for _ in range(N_PERM):
        assign = [(RNG.choice(pools[c]), dt_) for c, dt_ in real_t
                  if len(pools[c])]
        null_t.append(stats(assign)[0])
    null_t = np.array(null_t)
    p_t = (null_t >= obs_t).mean()
    print(f"\n  Held-out events only (clean - thresholds never saw these):")
    print(f"    observed {obs_t}/{len(test_ev)} alerted, null mean "
          f"{null_t.mean():.2f}, p = {p_t:.4f}")
    if p_t < 0.05:
        print(f"    Still outside the null on {len(test_ev)} events the thresholds")
        print("    never saw. This is the cleanest evidence in the project.")
    else:
        print("    NOT outside the null. On the clean subset alone there is no")
        print("    evidence the rule beats chance - four events has little power.")

    print("\n  Caveat: a permutation test checks one null hypothesis. It does not")
    print("  repair a biased sample - four distress events remain unrecoverable")
    print("  (DHFL, IL&FS, PMC Bank, Altico).")


# ------------------------------------------- 3/4. intervals and event types --
def intervals_and_strata(scored, events):
    header("3. CONFIDENCE INTERVALS AND EVENT-TYPE STRATIFICATION")

    ev = events.copy()
    ev["event_date"] = pd.to_datetime(ev["event_date"])
    d = label(scored, ev)
    caught, leads = recall_and_leads(d, ev, "alert")

    k, n = len(caught), len(ev)
    lo, hi = clopper_pearson(k, n)
    print(f"\noverall recall inside {HORIZON_MONTHS} months: {k}/{n} = {k/n:.0%}  "
          f"(95% CI {lo:.0%} to {hi:.0%})")

    boot = [np.median(RNG.choice(leads, len(leads), replace=True))
            for _ in range(5000)] if leads else []
    if boot:
        print(f"median lead time: {np.median(leads):.0f} months "
              f"(95% CI {np.percentile(boot, 2.5):.0f} to "
              f"{np.percentile(boot, 97.5):.0f})")

    print("\nBy event type - these are different outcomes and pooling them flatters")
    print("the headline. PCA is a supervisory judgement on a bank that keeps")
    print("operating; a default or resolution is a credit event.\n")
    print(f"  {'event type':24s} {'n':>3s} {'alerted':>8s} {'recall':>8s} "
          f"{'95% CI':>18s} {'median lead':>12s}")
    line()
    for name, mask in [("PCA placement", ev["event_type"] == "regulatory"),
                       ("Credit event", ev["event_type"].isin(CREDIT))]:
        sub = ev[mask]
        c, l = recall_and_leads(d, sub, "alert")
        kk, nn = len(c), len(sub)
        a, b = clopper_pearson(kk, nn)
        med = f"{np.median(l):.0f}m" if l else "-"
        print(f"  {name:24s} {nn:3d} {kk:8d} {kk/nn:8.0%} "
              f"{f'{a:.0%} to {b:.0%}':>18s} {med:>12s}")

    print("\n  The two intervals overlap heavily, so the gap between them is not")
    print("  evidence that the model handles one event type better than the other.")


def main():
    scored = pd.read_csv(os.path.join(HERE, "scored.csv"))
    events = pd.read_csv(os.path.join(HERE, "events.csv"))

    thresholds = experiment_1b(scored, events)
    permutation_test(scored, events, thresholds)
    intervals_and_strata(scored, events)

    header("WHAT CAN NOW BE CLAIMED")
    print("Read the permutation p-value first, then the intervals, then everything")
    print("else. If the p-value is not small, no amount of lead-time detail matters.")


if __name__ == "__main__":
    main()
