"""Independent distress signals, tested one module at a time.

The fundamental index and the Merton model both have a known blind spot: one
reads the accounts, the other needs a liquid listed share, and neither sees
funding pressure or earnings quality directly. This module builds three further
signal families from data already in hand and asks, for each one, the only
question that matters:

    does it catch events the existing model misses, warn earlier, or cut the
    watchlist - beyond what the FDI already achieves?

Modules
-------
  A  MARKET STRESS       drawdown, abnormal return against a sector index, and
                         a volatility spike ratio. Independent of the accounts.
  B  FUNDING / LIQUIDITY  a shrinking loan book, financing cash outflow and a
                         thin liquid-asset buffer. Solvency and liquidity are
                         different ways to fail.
  C  EARNINGS QUALITY    the gap between reported profit and operating cash,
                         which is where delayed loss recognition shows up.

Each is scored on the same peer-relative percentile scale as the FDI, measured
at the same point-in-time date, and evaluated against the same 18 events.

Not built, and why:
  credit-rating actions   no free, consistent historical feed of Indian rating
                          actions with dates; would need licensed data
  bond / CDS spreads      Indian corporate bond price history is not publicly
                          available at the instrument level
  trading volume          the cached bhavcopy extracts kept only close and
                          previous close; volume would need a full re-fetch

Run: python3 signals.py
"""

import os
import math

import numpy as np
import pandas as pd

from validate import label, auc, available_from, HORIZON_MONTHS

HERE = os.path.dirname(os.path.abspath(__file__))
SPLIT_DATE = pd.Timestamp("2018-01-01")
TRADING_DAYS = 252


def line(c="-", n=78):
    print(c * n)


def header(t):
    print()
    line("=")
    print(t)
    line("=")


def pct_rank_within(d, col, keys=("fy", "peer_group")):
    return d.groupby(list(keys), sort=False)[col].transform(
        lambda s: s.rank(pct=True, na_option="keep") * 100)


# ------------------------------------------------------- A. market stress ---
def market_signals(scored, prices, splits):
    """Drawdown, abnormal return and volatility spike at each FY's publication date."""
    import merton as mt

    px = prices.copy()
    sym_dates = sorted(px["date"].unique())

    # equal-weighted sector index from the panel's own symbols
    adj = {}
    for sym, g in px.groupby("symbol"):
        _, a, _ = mt.price_series(g, splits[splits["symbol"] == sym])
        if a is not None and len(a) > 200:
            adj[sym] = a
    wide = pd.DataFrame(adj).sort_index()
    rets = np.log(wide).diff()
    index = rets.mean(axis=1).cumsum()          # equal-weighted log index

    roll_max = wide.cummax()
    drawdown = 1 - wide / roll_max
    vol_short = rets.rolling(60, min_periods=40).std() * math.sqrt(TRADING_DAYS)
    vol_long = rets.rolling(250, min_periods=150).std() * math.sqrt(TRADING_DAYS)
    vol_ratio = vol_short / vol_long
    ret_12m = np.log(wide).diff(TRADING_DAYS)
    idx_12m = index.diff(TRADING_DAYS)
    abn_12m = ret_12m.sub(idx_12m, axis=0)

    def at(frame, sym, when):
        if sym not in frame.columns:
            return np.nan
        s = frame[sym].dropna()
        s = s[s.index <= when]
        return s.iloc[-1] if len(s) else np.nan

    out = []
    for r in scored.itertuples():
        sym = str(getattr(r, "nse", "") or "").strip()
        when = available_from(r.fy)
        if not sym or sym not in wide.columns:
            out.append((np.nan, np.nan, np.nan))
            continue
        out.append((at(drawdown, sym, when), at(abn_12m, sym, when),
                    at(vol_ratio, sym, when)))
    dd, ab, vr = zip(*out)
    return pd.DataFrame({"m_drawdown": dd, "m_abnormal_ret": ab,
                         "m_vol_spike": vr}, index=scored.index)


# -------------------------------------------------- B. funding / liquidity ---
def funding_signals(d):
    g = d.sort_values(["company", "fy"]).groupby("company", sort=False)
    out = pd.DataFrame(index=d.index)

    prev_b = g["borrowings"].shift(1)
    # positive when the book is SHRINKING - a lender that cannot refinance
    out["l_book_contraction"] = -(d["borrowings"] / prev_b - 1.0)
    out.loc[(prev_b <= 0) | prev_b.isna(), "l_book_contraction"] = np.nan

    ta = d["total_assets"].replace(0, np.nan)
    out["l_financing_outflow"] = -d["cff"] / ta      # positive when repaying, not raising
    out["l_thin_liquidity"] = -d["investments"] / ta  # positive when the buffer is thin
    return out


# ------------------------------------------------------ C. earnings quality ---
def quality_signals(d):
    ta = d["total_assets"].replace(0, np.nan)
    out = pd.DataFrame(index=d.index)
    # profit the business did not convert into cash
    out["q_accrual_gap"] = (d["net_profit"] - d["cfo"]) / ta
    rev = d["revenue"].replace(0, np.nan)
    out["q_other_income_reliance"] = d["other_income"] / rev
    return out


SIGNALS = {
    "m_drawdown": "Market: drawdown from peak",
    "m_abnormal_ret": "Market: abnormal 12m return",
    "m_vol_spike": "Market: volatility spike",
    "l_book_contraction": "Funding: loan book shrinking",
    "l_financing_outflow": "Funding: financing cash outflow",
    "l_thin_liquidity": "Funding: thin liquid buffer",
    "q_accrual_gap": "Quality: profit minus cash",
    "q_other_income_reliance": "Quality: other-income reliance",
}
# orientation: these are built so larger = riskier, except abnormal return
NEGATE = {"m_abnormal_ret"}


def build(scored, prices, splits):
    d = scored.copy()
    feats = [funding_signals(d), quality_signals(d)]
    if not prices.empty:
        feats.append(market_signals(d, prices, splits))
    for f in feats:
        for c in f.columns:
            d[c] = f[c]
    for c in SIGNALS:
        if c not in d.columns:
            d[c] = np.nan
        v = -d[c] if c in NEGATE else d[c]
        d[f"s_{c}"] = pct_rank_within(d.assign(_v=v), "_v")
    return d


def main():
    scored = pd.read_csv(os.path.join(HERE, "scored.csv"))
    events = pd.read_csv(os.path.join(HERE, "events.csv"))
    pp = os.path.join(HERE, "prices_daily.csv")
    prices = pd.read_csv(pp, parse_dates=["date"]) if os.path.exists(pp) else pd.DataFrame()
    sp = os.path.join(HERE, "splits.csv")
    splits = (pd.read_csv(sp, parse_dates=["date"]) if os.path.exists(sp)
              else pd.DataFrame(columns=["symbol", "date", "factor", "kind"]))

    print("building signal modules...")
    d = build(scored, prices, splits)
    d.to_csv(os.path.join(HERE, "signals.csv"), index=False)

    ev = events.copy()
    ev["event_date"] = pd.to_datetime(ev["event_date"])
    lab = label(d, ev)
    u = lab[lab["fdi"].notna() & (~lab["post_event"]) & lab["fy"].between(2013, 2021)]
    dev = u[u["fy"] <= 2016]
    tst = u[u["fy"] >= 2017]

    header("1. DOES EACH SIGNAL DISCRIMINATE ON ITS OWN?")
    print("AUC against the 18 events, split by period so the development half is")
    print("separable from the later half. Coverage matters as much as AUC: a signal")
    print("that only exists for a third of the panel cannot replace the index.\n")
    print(f"  {'signal':34s} {'coverage':>9s} {'AUC dev':>9s} {'AUC later':>10s}")
    line()
    rows = []
    for c, name in SIGNALS.items():
        cov = u[f"s_{c}"].notna().mean() * 100
        a_d = auc(dev["is_pre_event"], dev[f"s_{c}"])
        a_t = auc(tst["is_pre_event"], tst[f"s_{c}"])
        rows.append((c, name, cov, a_d, a_t))
        print(f"  {name:34s} {cov:8.0f}% {a_d:9.3f} {a_t:10.3f}")
    print(f"\n  {'FDI composite (reference)':34s} "
          f"{u['fdi'].notna().mean()*100:8.0f}% "
          f"{auc(dev['is_pre_event'], dev['fdi']):9.3f} "
          f"{auc(tst['is_pre_event'], tst['fdi']):10.3f}")

    header("2. DOES ANY SIGNAL CATCH WHAT THE INDEX MISSES?")
    missed = ["IDBI Bank Ltd", "Central Bank of India", "Bank of Maharashtra",
              "Allahabad Bank"]
    print("The alert rule misses four events, all PCA banks in 2017-18. For each,")
    print("the signal's percentile on the last accounts published beforehand")
    print("(100 = worst in peer group that year):\n")
    cols = [c for c in SIGNALS]
    print(f"  {'institution':24s} " + " ".join(f"{c.split('_')[0][:4]+c.split('_',1)[1][:6]:>11s}"
                                               for c in cols))
    line()
    for comp in missed:
        e = ev[ev["company"] == comp].iloc[0]
        h = lab[(lab["company"] == comp) & (lab["known_at"] < e["event_date"])]
        if h.empty:
            continue
        r = h.sort_values("known_at").iloc[-1]
        vals = " ".join(f"{r[f's_{c}']:11.0f}" if pd.notna(r[f"s_{c}"]) else f"{'-':>11s}"
                        for c in cols)
        print(f"  {comp.replace(' Ltd',''):24s} {vals}")
    print(f"\n  {'(FDI for comparison)':24s} " +
          " ".join(f"{lab[(lab.company==c)].fdi.max():11.0f}" for c in missed[:1]))

    header("3. INCREMENTAL VALUE OVER THE INDEX")
    print("A signal earns its place only if adding it changes outcomes. Each row")
    print("adds one signal to the existing alert rule as an OR condition, firing")
    print("when that signal is in the worst decile, and reports what changes.\n")
    base = u["alert"].fillna(False).astype(bool)
    n_ev = u.loc[u["is_pre_event"], "company"].nunique()
    b_caught = u.loc[base & u["is_pre_event"], "company"].nunique()
    b_yr = u[base].groupby("fy")["company"].nunique().mean()
    b_mat = u[base & u["is_material"]].groupby("fy")["company"].nunique().mean()
    print(f"  {'added signal':34s} {'caught':>8s} {'names/yr':>9s} {'material':>9s}")
    line()
    print(f"  {'(baseline: FDI alert rule)':34s} {b_caught:4d}/{n_ev:<3d} "
          f"{b_yr:9.0f} {b_mat:9.0f}")
    for c, name in SIGNALS.items():
        m = base | (u[f"s_{c}"] >= 90)
        caught = u.loc[m & u["is_pre_event"], "company"].nunique()
        yr = u[m].groupby("fy")["company"].nunique().mean()
        mat = u[m & u["is_material"]].groupby("fy")["company"].nunique().mean()
        flag = "  <-- adds events" if caught > b_caught else ""
        print(f"  + {name:32s} {caught:4d}/{n_ev:<3d} {yr:9.0f} {mat:9.0f}{flag}")

    print("\n  A row that catches no more events while enlarging the watchlist is a")
    print("  cost with no benefit, however sensible the signal sounds.")


if __name__ == "__main__":
    main()
