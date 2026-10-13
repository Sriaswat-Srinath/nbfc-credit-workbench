"""Build the distress system from scratch on US data, then test it out of sample.

fdic_validate.py asked a narrow question: does the frozen Indian model transfer?
It does. This asks a different one: what does the same design produce when the
data is actually good enough to build on?

Three things change versus the transferred model:

  1. ASSET QUALITY IS INCLUDED. Call reports carry a non-performing-assets ratio
     and loan-loss reserves for every bank-quarter. The Indian archive has the
     former only from 2020 for a tenth of the panel, so it was excluded there.
     It is the strongest single signal available, and leaving it out was a data
     limitation, not a modelling choice.

  2. FUNDING IS OBSERVABLE. Deposits are reported quarterly, so deposit flight --
     the mechanism that actually closes a bank -- can be measured directly
     rather than proxied by a shrinking loan book.

  3. THE SPLIT IS ACROSS TWO CRISES. Components and thresholds are derived on
     failures before 2013 (the 2008-12 wave, 488 events) and tested on 2013-2023
     (76 events, including the 2023 regional bank failures). Development and
     test are therefore different regimes, not merely different dates.

Weights remain set by economic reasoning rather than fitted; with 488 events
they could be fitted, but then the comparison against the Indian model would be
measuring the fitting rather than the design.
"""

import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

SPLIT = pd.Timestamp("2013-01-01")
HORIZON_MONTHS = 24
FILING_LAG_DAYS = 45
MIN_PEERS = 20
N_PERM = 1000
MAX_WATCHLIST = 0.05   # a list larger than this is not something anyone works through
RNG = np.random.default_rng(20261012)

# Nine candidates. The first six are the Indian set; the last three are the ones
# Indian data could not support.
CANDIDATES = {
    "capital_buffer": "equity / assets",
    "capital_erosion": "8-quarter change in equity",
    "profitability": "return on assets",
    "leverage": "(assets - equity) / equity",
    "interest_burden": "interest expense / interest income",
    "earnings_trend": "12-quarter change in ROA",
    "npa_ratio": "non-performing assets ratio",          # new
    "reserve_shortfall": "non-performing assets not covered by reserves",  # new
    "funding_contraction": "4-quarter fall in deposits",  # new
}

# Economic weights by family, not fitted.
WEIGHTS = {
    "capital_buffer": 0.20, "capital_erosion": 0.14, "leverage": 0.08,   # capital .42
    "npa_ratio": 0.18, "reserve_shortfall": 0.08,                        # asset quality .26
    "profitability": 0.14, "earnings_trend": 0.06,                       # earnings .20
    "funding_contraction": 0.06, "interest_burden": 0.06,                # funding .12
}
DUAL_ANCHOR = {"capital_buffer", "leverage"}


def line(c="-", n=78):
    print(c * n)


def header(t):
    print()
    line("=")
    print(t)
    line("=")


def auc(y, s):
    m = ~(pd.isna(y) | pd.isna(s))
    y, s = np.asarray(y)[m].astype(bool), np.asarray(s)[m]
    if y.sum() == 0 or (~y).sum() == 0:
        return np.nan
    r = pd.Series(s).rank().to_numpy()
    n1, n0 = y.sum(), (~y).sum()
    return (r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def features(panel):
    d = panel.copy()
    d["REPDTE"] = pd.to_datetime(d["REPDTE"].astype(str), format="%Y%m%d")
    d = d.sort_values(["CERT", "REPDTE"]).reset_index(drop=True)
    for c in ("ASSET", "EQ", "DEP", "ROA", "INTINC", "EINTEXP", "NPERFV", "LNATRES"):
        d[c] = pd.to_numeric(d.get(c), errors="coerce")

    g = d.groupby("CERT", sort=False)
    asset = d["ASSET"].replace(0, np.nan)

    d["f_capital_buffer"] = d["EQ"] / asset
    d["f_capital_erosion"] = (d["EQ"] - g["EQ"].shift(8)) / asset
    eq_pos = d["EQ"].where(d["EQ"] > 0, np.nan)
    d["f_leverage"] = (d["ASSET"] - d["EQ"]) / eq_pos
    d["negative_equity"] = d["EQ"] <= 0
    d["f_profitability"] = d["ROA"] / 100.0
    d["f_earnings_trend"] = d["f_profitability"] - g["f_profitability"].shift(12)
    d["f_interest_burden"] = d["EINTEXP"] / d["INTINC"].replace(0, np.nan)

    # the three the Indian data could not support
    d["f_npa_ratio"] = d["NPERFV"]
    d["f_reserve_shortfall"] = d["NPERFV"] - (d["LNATRES"] / asset * 100.0)
    prev_dep = g["DEP"].shift(4)
    d["f_funding_contraction"] = -(d["DEP"] / prev_dep - 1.0)
    d.loc[(prev_dep <= 0) | prev_dep.isna(), "f_funding_contraction"] = np.nan

    d["peer_group"] = (d.groupby("REPDTE", sort=False)["ASSET"]
                        .transform(lambda s: pd.qcut(s.rank(method="first"), 3,
                                                     labels=["Small", "Mid", "Large"]))
                        .astype(str))
    d["known_at"] = d["REPDTE"] + pd.Timedelta(days=FILING_LAG_DAYS)
    return d


# orientation: larger = riskier
NEGATE = {"capital_buffer", "capital_erosion", "profitability", "earnings_trend"}


def percentiles(d, components):
    keys = ["REPDTE", "peer_group"]
    thin = d.groupby(keys)["CERT"].transform("size") < MIN_PEERS
    for name in components:
        raw = d[f"f_{name}"]
        v = d.assign(_v=(-raw if name in NEGATE else raw))
        peer = v.groupby(keys, sort=False)["_v"].transform(
            lambda s: s.rank(pct=True, na_option="keep") * 100).mask(thin)
        if name in DUAL_ANCHOR:
            uni = v.groupby("REPDTE", sort=False)["_v"].transform(
                lambda s: s.rank(pct=True, na_option="keep") * 100)
            d[f"s_{name}"] = pd.concat([peer, uni], axis=1).mean(axis=1, skipna=True)
        else:
            d[f"s_{name}"] = peer
    d.loc[d["negative_equity"], ["s_capital_buffer", "s_leverage"]] = 100.0
    return d


def composite(d, weights):
    cols = [f"s_{k}" for k in weights]
    w = np.array([weights[k] for k in weights])
    vals = d[cols].to_numpy(dtype=float)
    mask = ~np.isnan(vals)
    wsum = (mask * w).sum(axis=1)
    num = np.nansum(np.where(mask, vals, 0) * w, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.where(wsum > 0, num / wsum, np.nan)
    return np.where(mask.sum(axis=1) / len(cols) >= 0.6, s, np.nan)


def add_alert(d, score_col, level, deter, jump):
    g = d.sort_values(["CERT", "REPDTE"]).groupby("CERT", sort=False)
    base = g[score_col].transform(
        lambda s: s.shift(1).rolling(12, min_periods=4).median())
    jmp = d[score_col] - base
    return ((d[score_col] >= level) |
            ((d[score_col] >= deter) & (jmp >= jump))), base, jmp


def label(d, fail):
    f = fail.copy()
    f["FAILDATE"] = pd.to_datetime(f["FAILDATE"], errors="coerce")
    first = f.dropna(subset=["FAILDATE"]).groupby("CERT")["FAILDATE"].min()
    d["fail_date"] = d["CERT"].map(first)
    delta = (d["fail_date"] - d["known_at"]).dt.days
    d["is_pre_event"] = (delta > 0) & (delta <= HORIZON_MONTHS * 30.44)
    d["post_event"] = delta <= 0
    return d


def recall(d, alert_col, certs):
    hit, leads = set(), []
    sub = d[d["is_pre_event"].fillna(False) & d[alert_col].fillna(False)]
    for cert, g in sub.groupby("CERT"):
        r = g.sort_values("known_at").iloc[0]
        hit.add(cert)
        leads.append((r["fail_date"] - r["known_at"]).days / 30.44)
    return hit, np.array(leads) if leads else np.array([])


def main():
    panel = pd.read_csv(os.path.join(HERE, "fdic_panel.csv"))
    fail = pd.read_csv(os.path.join(HERE, "fdic", "failures.csv"))

    d = features(panel)
    d = percentiles(d, list(CANDIDATES))
    d = label(d, fail)
    d = d[d["ASSET"].notna()]

    dev = d[(d["REPDTE"] < SPLIT) & (~d["post_event"].fillna(False))]
    tst = d[(d["REPDTE"] >= SPLIT) & (~d["post_event"].fillna(False))]
    dev_fail = sorted(set(dev.loc[dev["is_pre_event"].fillna(False), "CERT"]))
    tst_fail = sorted(set(tst.loc[tst["is_pre_event"].fillna(False), "CERT"]))

    header("1. DEVELOPMENT AND TEST ARE DIFFERENT CRISES")
    print(f"  development  quarters < 2013 : {len(dev):,} bank-quarters, "
          f"{len(dev_fail):,} failures")
    print(f"  held-out     quarters >= 2013: {len(tst):,} bank-quarters, "
          f"{len(tst_fail):,} failures")
    print("  The development half is the 2008-12 wave; the held-out half is the")
    print("  post-crisis tail and the 2023 regional bank failures.")

    header("2. COMPONENT SELECTION, ON DEVELOPMENT DATA ONLY")
    print(f"  {'component':22s} {'definition':42s} {'AUC':>6s}  keep")
    line()
    keep = []
    for c, desc in CANDIDATES.items():
        a = auc(dev["is_pre_event"].fillna(False), dev[f"s_{c}"])
        k = (a == a) and a >= 0.5
        if k:
            keep.append(c)
        tag = "yes" if k else "DROP"
        new = " *" if c in ("npa_ratio", "reserve_shortfall", "funding_contraction") else ""
        print(f"  {c + new:22s} {desc[:42]:42s} {a:6.3f}  {tag}")
    print("\n  * component unavailable in the Indian data")

    weights = {k: v for k, v in WEIGHTS.items() if k in keep}
    tot = sum(weights.values())
    weights = {k: v / tot for k, v in weights.items()}
    d["fdi_us"] = composite(d, weights)

    header("3. THRESHOLDS, DERIVED ON DEVELOPMENT DATA ONLY")
    print("  Selection rule fixed before searching: maximise development recall")
    print(f"  SUBJECT TO a watchlist no larger than {MAX_WATCHLIST:.0%} of banks.")
    print("  An unconstrained search maximises recall by loosening the threshold")
    print("  until almost everything is flagged - the precise failure this project")
    print("  argues against elsewhere.")
    dev = d[(d["REPDTE"] < SPLIT) & (~d["post_event"].fillna(False))].copy()
    best = None
    for level in (70, 75, 80, 85, 90):
        for deter in (50, 55, 60, 65):
            for jump in (10, 15, 20, 25):
                if deter >= level:
                    continue
                al, _, _ = add_alert(d, "fdi_us", level, deter, jump)
                d["_a"] = al
                dv = d[(d["REPDTE"] < SPLIT) & (~d["post_event"].fillna(False))]
                hit, _ = recall(dv, "_a", dev_fail)
                wl = dv[dv["_a"].fillna(False)].groupby("REPDTE")["CERT"].nunique().mean()
                share = wl / dv.groupby("REPDTE")["CERT"].nunique().mean()
                if share > MAX_WATCHLIST:
                    continue
                cand = (len(hit), -wl, level, deter, jump, wl)
                if best is None or cand > best:
                    best = cand
    if best is None:
        raise SystemExit("no threshold meets the watchlist constraint")
    n_hit, _, level, deter, jump, wl = best
    print(f"\n  chosen: FDI >= {level}  OR  (FDI >= {deter} AND jump >= +{jump})")
    print(f"  catches {n_hit:,}/{len(dev_fail):,} development failures, "
          f"{wl:,.0f} banks on the list per quarter")

    d["alert_us"], _, _ = add_alert(d, "fdi_us", level, deter, jump)
    tst = d[(d["REPDTE"] >= SPLIT) & (~d["post_event"].fillna(False))].copy()

    header("4. HELD-OUT RESULT  (2013-2023, a different regime)")
    hit, leads = recall(tst, "alert_us", tst_fail)
    al = tst[tst["alert_us"].fillna(False)]
    base = tst["is_pre_event"].fillna(False).mean() * 100
    prec = al["is_pre_event"].fillna(False).mean() * 100
    print(f"  failures alerted within {HORIZON_MONTHS} months : "
          f"{len(hit):,} / {len(tst_fail):,}  ({len(hit)/max(1,len(tst_fail)):.0%})")
    if leads.size:
        print(f"  median lead time                   : {np.median(leads):.1f} months "
              f"(quartiles {np.percentile(leads,25):.1f} / {np.percentile(leads,75):.1f})")
    print(f"  watchlist                          : "
          f"{al.groupby('REPDTE')['CERT'].nunique().mean():,.0f} of "
          f"{tst.groupby('REPDTE')['CERT'].nunique().mean():,.0f} banks per quarter")
    print(f"  precision                          : {prec:.2f}% against a "
          f"{base:.2f}% base rate  (lift {prec/max(base,1e-9):.1f}x)")

    header("5. WHAT THE THREE NEW COMPONENTS BOUGHT")
    old = {k: v for k, v in WEIGHTS.items()
           if k in keep and k not in ("npa_ratio", "reserve_shortfall",
                                      "funding_contraction")}
    t2 = sum(old.values())
    old = {k: v / t2 for k, v in old.items()}
    d["fdi_six"] = composite(d, old)
    d["alert_six"], _, _ = add_alert(d, "fdi_six", level, deter, jump)
    tst = d[(d["REPDTE"] >= SPLIT) & (~d["post_event"].fillna(False))].copy()
    h6, l6 = recall(tst, "alert_six", tst_fail)
    a6 = tst[tst["alert_six"].fillna(False)]
    p6 = a6["is_pre_event"].fillna(False).mean() * 100
    print(f"  {'model':34s} {'caught':>12s} {'median lead':>12s} {'precision':>10s} {'AUC':>7s}")
    line()
    for nm, h, l, p, col in [("Six components (as in India)", h6, l6, p6, "fdi_six"),
                             ("Nine, with asset quality", hit, leads, prec, "fdi_us")]:
        a_ = auc(tst["is_pre_event"].fillna(False), tst[col])
        med = f"{np.median(l):.1f} mo" if l.size else "-"
        print(f"  {nm:34s} {len(h):5,d}/{len(tst_fail):<5,d} {med:>12s} "
              f"{p:9.2f}% {a_:7.3f}")

    header("6. PERMUTATION TEST ON THE HELD-OUT PERIOD")
    ev = (d[d["CERT"].isin(tst_fail)].sort_values("known_at")
            .groupby("CERT").last()[["fail_date", "peer_group"]])
    uu = tst.reset_index(drop=True)
    cert_arr = uu["CERT"].to_numpy()
    known_arr = uu["known_at"].to_numpy()
    alert_arr = uu["alert_us"].fillna(False).to_numpy()
    grp_arr = uu["peer_group"].to_numpy()
    idx_by = {c: np.where(cert_arr == c)[0] for c in np.unique(cert_arr)}
    hz = np.timedelta64(int(HORIZON_MONTHS * 30.44 * 86400 * 1e9), "ns")

    def caught(assign):
        n = 0
        for cert, fd in assign:
            ix = idx_by.get(cert)
            if ix is None:
                continue
            k = known_arr[ix]
            sel = ix[(k < np.datetime64(fd)) & (np.datetime64(fd) - k <= hz)]
            if sel.size and alert_arr[sel].any():
                n += 1
        return n

    real = [(c, r.fail_date) for c, r in ev.iterrows()]
    obs = caught(real)
    pools = {g_: np.unique(cert_arr[grp_arr == g_]) for g_ in ev["peer_group"].unique()}
    null = np.array([caught([(RNG.choice(pools[r.peer_group]), r.fail_date)
                             for _, r in ev.iterrows()]) for _ in range(N_PERM)])
    p = (null >= obs).mean()
    print(f"  observed : {obs:,} of {len(ev):,}")
    print(f"  null mean: {null.mean():.1f}   95th pct: {np.percentile(null,95):.0f}")
    print(f"  p-value  : {'< ' + str(round(1/N_PERM,4)) if p == 0 else round(p,4)}")

    out = os.path.join(HERE, "fdic_us_model.csv.gz")
    cols = ["CERT", "REPDTE", "known_at", "peer_group", "ASSET", "fdi_us", "fdi_six",
            "alert_us", "fail_date", "is_pre_event"] + [f"s_{k}" for k in keep]
    d[cols].to_csv(out, index=False, compression="gzip")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
