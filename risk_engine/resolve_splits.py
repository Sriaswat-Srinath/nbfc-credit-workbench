"""Detect corporate actions in the daily price series, and classify them.

The earlier approach was wrong
------------------------------
It assumed NSE bhavcopy's PREVCLOSE was adjusted for corporate actions, so that
CLOSE/PREVCLOSE gave a clean return. It does not. On Yes Bank's split day the
file reports CLOSE 377.05 against PREVCLOSE 1880.10 -- the raw drop. That made
every computed "split factor" collapse to 1 and the detector found nothing but
noise from illiquid symbols.

What works instead
------------------
With the full daily series, a corporate action is visible as a single-day ratio
that sits almost exactly on a conventional fraction, because the opening price
is adjusted mechanically:

    Yes Bank  21 Sep 2017:  377.05 / 1880.10 = 0.2005   (1/5, 0.25% off)
    HDFC Bank 19 Sep 2019: 1101.05 / 2187.75 = 0.5033   (1/2, 0.66% off)

A genuine crash almost never lands within ~1.5% of an exact fraction on a
single day, which is what separates this from the weekly ratio heuristic that
would have deleted Yes Bank's real 2019 collapse.

Splits versus bonuses
---------------------
Both halve the price, but they do different things to the share count, so they
cannot be treated alike:

    split  face value falls, equity capital unchanged
    bonus  reserves capitalised, equity capital rises by the same factor

The archive reports equity capital annually, so the two are told apart by
checking whether equity capital jumped across the action date. Market
capitalisation then uses raw prices with a share count derived from the
split-adjusted face value, while volatility uses returns adjusted for both.
"""

import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

# 1.25 is deliberately absent: 0.80 is exactly India's 20% circuit limit, so a
# stock locked at lower circuit lands on it precisely. Including it labelled
# three of Reliance Capital's 2019 crash days as "bonus issues".
RATIOS = [1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 20]
TOL = 0.015          # single-day ratio must sit this close to an exact fraction
MIN_MOVE = 0.18      # and the move must be at least this large, either way
EC_TOL = 0.25        # equity-capital jump within this of the factor => bonus

# Three guards against coincidence, each added after inspecting a real false
# positive in the detected list:
BREADTH_FRAC = 0.06  # if this share of the market moved >10% that day it is a
                     # market-wide event, not a corporate action. Genuine split
                     # days show 1.4-3.4% breadth; 19 Mar 2020 showed 12.5% and
                     # was labelling Indiabulls Housing's COVID crash a 1.5x
                     # split because it landed within 0.6% of 1/1.5.
MIN_HISTORY = 60     # trading days the symbol must already have (caught
                     # Ujjivan Small Finance Bank's listing-day pop)
CLUSTER_DAYS = 30    # two "actions" this close together are an artefact of an
                     # illiquid quote, not two corporate actions


def classify(symbol, date, factor, panel_by_symbol):
    """split | bonus | unknown, from the equity-capital path around the action."""
    pc = panel_by_symbol.get(symbol)
    if pc is None or pc.empty:
        return "unknown"
    before = pc[pc["known_before"] < date]
    after = pc[pc["known_before"] >= date]
    if before.empty or after.empty:
        return "unknown"
    ec0 = before.iloc[-1]["equity_capital"]
    ec1 = after.iloc[0]["equity_capital"]
    if not (np.isfinite(ec0) and np.isfinite(ec1)) or ec0 <= 0:
        return "unknown"
    jump = ec1 / ec0
    if abs(jump - factor) / factor <= EC_TOL:
        return "bonus"
    if abs(jump - 1.0) <= EC_TOL:
        return "split"
    return "unknown"


def main():
    px = pd.read_csv(os.path.join(HERE, "prices_daily.csv"), parse_dates=["date"])
    px = px.dropna(subset=["close", "prevclose"])
    px = px[(px["close"] > 0) & (px["prevclose"] > 0)].sort_values(["symbol", "date"])

    px["ratio"] = px["close"] / px["prevclose"]
    px["obs_no"] = px.groupby("symbol").cumcount()

    # market breadth: share of quoted symbols moving more than 10% each day
    big = (px["ratio"].sub(1).abs() > 0.10)
    breadth = big.groupby(px["date"]).mean()
    stressed = set(breadth[breadth > BREADTH_FRAC].index)
    print(f"{len(stressed)} market-wide stress days excluded "
          f"(>{BREADTH_FRAC:.0%} of symbols moving >10%)")

    moved = px[(px["ratio"] < 1 - MIN_MOVE) | (px["ratio"] > 1 + MIN_MOVE)].copy()
    moved = moved[~moved["date"].isin(stressed)]
    moved = moved[moved["obs_no"] >= MIN_HISTORY]
    print(f"{len(moved):,} single-day moves beyond {MIN_MOVE:.0%} to test")

    hits = []
    for r in moved.itertuples():
        for k in RATIOS:
            for target, factor in ((1.0 / k, k), (float(k), 1.0 / k)):
                if abs(r.ratio - target) / target <= TOL:
                    hits.append({"symbol": r.symbol, "date": r.date,
                                 "ratio": round(r.ratio, 5), "factor": factor,
                                 "miss_pct": round(abs(r.ratio - target) / target * 100, 2)})
                    break
            else:
                continue
            break

    res = pd.DataFrame(hits)
    if res.empty:
        print("no corporate actions detected")
        res = pd.DataFrame(columns=["symbol", "date", "ratio", "factor", "kind"])
        res.to_csv(os.path.join(HERE, "splits.csv"), index=False)
        return

    # classify each action using the annual equity-capital path
    panel = pd.read_csv(os.path.join(HERE, "panel.csv"))
    panel = panel.dropna(subset=["nse"]).copy()
    panel["nse"] = panel["nse"].astype(str).str.strip()
    panel["known_before"] = panel["fy"].map(
        lambda y: pd.Timestamp(year=int(y), month=3, day=31))
    by_symbol = {s: g.sort_values("fy") for s, g in panel.groupby("nse")}

    res["kind"] = [classify(r.symbol, r.date, r.factor, by_symbol)
                   for r in res.itertuples()]
    res = res.sort_values(["symbol", "date"])

    # drop clustered pairs: a real corporate action does not repeat within a month
    gap = res.groupby("symbol")["date"].diff().dt.days
    clustered = gap.le(CLUSTER_DAYS).fillna(False)
    clustered = clustered | clustered.shift(-1).fillna(False)
    if clustered.any():
        print(f"dropped {int(clustered.sum())} clustered detections as artefacts: "
              f"{sorted(set(res.loc[clustered, 'symbol']))}")
        res = res[~clustered]

    path = os.path.join(HERE, "splits.csv")
    res.to_csv(path, index=False)

    print(f"\ndetected {len(res)} corporate actions in {res['symbol'].nunique()} symbols")
    print(res["kind"].value_counts().to_string())
    print("\nactions in the institutions that matter most:")
    key = ["YESBANK", "HDFCBANK", "KOTAKBANK", "ICICIBANK", "AXISBANK", "SBIN",
           "RELCAPITAL", "RHFL", "RELIGARE", "BAJFINANCE"]
    k = res[res["symbol"].isin(key)]
    print(k.to_string(index=False) if len(k) else "  none")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
