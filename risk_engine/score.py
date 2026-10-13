"""Fundamental Distress Index (FDI) for Indian banks and NBFCs.

The deck's model is Merton/KMV: equity price + volatility + a debt figure -> PD.
That needs a listed, liquid share. Two thirds of the 556 financial institutions
in this archive have no NSE ticker, and Merton says nothing at all about asset
quality, which is what actually kills a lender.

This module scores distress from the accounts alone, so it covers every
institution in the archive and works for unlisted / thinly traded ones.

Design notes
------------
* Every input is point-in-time: a row for FY t uses only FY t and earlier.
* Raw ratios are turned into *within-year cross-sectional percentiles* against
  the rest of the financial sector, so the score self-calibrates to the credit
  cycle instead of relying on hand-set thresholds that drift.
* Each component is oriented so that higher = riskier, then weighted into a
  0-100 index. Component scores are kept in the output so any score can be
  explained ("this is an 88 because capital erosion and ROA are in the worst
  decile").
"""

import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

# component -> weight. Capital and its rate of change dominate, because an
# equity buffer is the thing that actually absorbs loss.
#
# Two components from the first cut were removed after backtesting rather than
# down-weighted (see validate.py, and NOTES.md for the numbers):
#
#   growth_burst   AUC 0.34   borrowings CAGR -- the "fast growth precedes
#                             blow-ups" intuition is backwards at this horizon.
#                             A lender still growing its book is one that
#                             wholesale markets still fund; the ones about to
#                             fail are already shrinking.
#   funding_stress AUC 0.44   operating cash flow / assets -- for a lender,
#                             CFO is dominated by loan-book movement, so it is
#                             noise, not a liquidity read.
#
# Both sat below 0.5 in the PSU-bank cluster and the idiosyncratic-failure
# cluster independently, so the sign is consistent rather than small-sample
# noise. Weights elsewhere are set on economic reasoning, not fitted.
WEIGHTS = {
    "capital_buffer": 0.30,   # equity / total assets, low is bad
    "capital_erosion": 0.20,  # 2y change in equity / total assets, negative is bad
    "leverage": 0.12,         # borrowings / equity, high is bad
    "profitability": 0.20,    # ROA, low is bad
    "earnings_trend": 0.08,   # 3y change in ROA, falling is bad
    "interest_burden": 0.10,  # interest expense / revenue, high is bad
}

# Capital adequacy is the one input with a real economic floor: thin equity is
# thin in absolute terms, not merely relative to whoever else is thin that year.
# Ranking it only inside a peer group hides exactly the cross-sector gap that
# separated the PCA banks from the private ones. These components are therefore
# scored as the mean of a peer-relative rank and a whole-universe rank.
DUAL_ANCHOR = {"capital_buffer", "leverage"}

MIN_PEERS = 20  # below this, a cross-sectional percentile is not meaningful


def _pct_rank(s):
    """Percentile in [0, 100] within the group. NaNs stay NaN."""
    return s.rank(pct=True, na_option="keep") * 100.0


def peer_group(d):
    """Rank a company only against institutions it is comparable to.

    Ranking all 556 financials together punishes every real lender: the
    "Finance" sector here is mostly small investment / holding companies that
    carry almost no borrowings, so a normally-funded bank lands in the worst
    quartile on leverage purely for being a bank. Banks are therefore ranked
    against banks, and NBFCs against NBFCs of a similar size.
    """
    grp = pd.Series(index=d.index, dtype=object)
    is_bank = d["sector"].eq("Banks")
    grp[is_bank] = "Banks"

    nbfc = ~is_bank
    size_tercile = (
        d.loc[nbfc]
        .groupby("fy", sort=False)["total_assets"]
        .transform(lambda s: pd.qcut(s.rank(method="first"), 3,
                                     labels=["Small", "Mid", "Large"]))
        .astype(object)
    )
    grp[nbfc] = "NBFC-" + size_tercile.fillna("Unsized")
    return grp.astype(str)


def build_features(df):
    """Add the raw (pre-ranking) risk ratios. Input is panel.csv."""
    d = df.sort_values(["company", "fy"]).copy()

    d["equity"] = d["equity_capital"].fillna(0) + d["reserves"].fillna(0)
    ta = d["total_assets"].replace(0, np.nan)

    d["f_capital_buffer"] = d["equity"] / ta

    g = d.groupby("company", sort=False)
    # 2-year change in equity, scaled by today's balance sheet
    d["equity_lag2"] = g["equity"].shift(2)
    d["f_capital_erosion"] = (d["equity"] - d["equity_lag2"]) / ta

    # Leverage. Negative or near-zero equity is the worst possible reading, not
    # a negative ratio, so clamp the denominator and flag it separately.
    eq_floor = d["equity"].where(d["equity"] > 0, np.nan)
    d["f_leverage"] = d["borrowings"] / eq_floor
    d["negative_equity"] = d["equity"] <= 0

    d["f_roa"] = d["net_profit"] / ta
    d["roa_lag3"] = g["f_roa"].shift(3)
    d["f_earnings_trend"] = d["f_roa"] - d["roa_lag3"]

    d["f_cfo_ta"] = d["cfo"] / ta

    borrow_lag2 = g["borrowings"].shift(2)
    with np.errstate(invalid="ignore", divide="ignore"):
        d["f_borrow_cagr2"] = (d["borrowings"] / borrow_lag2) ** 0.5 - 1.0
    d.loc[(borrow_lag2 <= 0) | borrow_lag2.isna(), "f_borrow_cagr2"] = np.nan

    rev = d["revenue"].replace(0, np.nan)
    d["f_interest_burden"] = d["interest_exp"] / rev

    return d


def score(df):
    """Return the panel with component percentiles and the composite FDI."""
    d = build_features(df)

    # orientation: +1 means "higher raw value = riskier"
    oriented = {
        "capital_buffer": -d["f_capital_buffer"],
        "capital_erosion": -d["f_capital_erosion"],
        "leverage": d["f_leverage"],
        "profitability": -d["f_roa"],
        "earnings_trend": -d["f_earnings_trend"],
        "interest_burden": d["f_interest_burden"],
        # Scored but unweighted. These two were dropped from the index after
        # backtesting (see WEIGHTS); they are still computed so premortem.py can
        # re-test the drop decision on development-only data.
        "funding_stress": -d["f_cfo_ta"],
        "growth_burst": d["f_borrow_cagr2"],
    }

    d["peer_group"] = peer_group(d)
    keys = ["fy", "peer_group"]
    thin = d.groupby(keys)["company"].transform("size") < MIN_PEERS

    for name, series in oriented.items():
        col = f"s_{name}"
        peer = d.assign(_v=series).groupby(keys, sort=False)["_v"].transform(_pct_rank)
        # a thin peer-year cannot support a cross-sectional rank
        peer = peer.mask(thin)
        if name in DUAL_ANCHOR:
            # ranked against the whole financial sector as well, so a sector
            # that is uniformly thin does not look safe by its own standards
            universe = d.assign(_v=series).groupby("fy", sort=False)["_v"].transform(_pct_rank)
            d[col] = pd.concat([peer, universe], axis=1).mean(axis=1, skipna=True)
        else:
            d[col] = peer

    # Negative equity is a hard fact, not a percentile: force the two capital
    # components to the top of the scale.
    d.loc[d["negative_equity"], ["s_capital_buffer", "s_leverage"]] = 100.0

    cols = [f"s_{k}" for k in WEIGHTS]
    w = np.array([WEIGHTS[k] for k in WEIGHTS])
    vals = d[cols].to_numpy(dtype=float)
    mask = ~np.isnan(vals)
    # re-weight over whichever components are available for that row
    wsum = (mask * w).sum(axis=1)
    num = np.nansum(np.where(mask, vals, 0) * w, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        fdi = np.where(wsum > 0, num / wsum, np.nan)

    d["coverage"] = mask.sum(axis=1) / len(cols)
    d["fdi"] = np.where(d["coverage"] >= 0.6, fdi, np.nan)

    # Materiality. Roughly a third of the "Finance" sector here is dormant
    # shells and defunct listed companies: no book, no income, often deeply
    # negative equity. They are genuinely insolvent and the score says so
    # correctly, but they swamp any ranked screen and nobody is exposed to
    # them. Flag rather than drop, so the user chooses.
    d["is_material"] = (
        (d["total_assets"] >= 500)       # ₹5bn balance sheet
        & (d["revenue"].fillna(0) >= 25)  # ₹250m of income
    )

    d["fdi_band"] = pd.cut(
        d["fdi"],
        bins=[-0.01, 60, 80, 90, 100],
        labels=["Low", "Watch", "Elevated", "High"],
    )

    # Alert rule: level OR deterioration.
    #
    # A level-only trigger misses the case the whole exercise is about. Yes
    # Bank's FY2019 accounts scored 69 -- below any sensible level threshold,
    # but far above its own 32-45 history. Adding a move-against-own-baseline
    # leg catches it 8 months before the moratorium, and costs about three
    # extra material names per year on the list.
    d = d.sort_values(["company", "fy"])
    d["fdi_base3"] = d.groupby("company")["fdi"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=2).median()
    )
    d["fdi_jump"] = d["fdi"] - d["fdi_base3"]
    d["alert"] = (d["fdi"] >= 80) | ((d["fdi"] >= 60) & (d["fdi_jump"] >= 15))
    return d


def top_drivers(row, n=3):
    """Which components actually pushed this row's score up.

    Ranking by weight * percentile just returns the heaviest component every
    time. What explains a score is the contribution *above neutral*: a
    component sitting at the 50th percentile moves the index nowhere, however
    heavily it is weighted.
    """
    items = []
    for k in WEIGHTS:
        v = row.get(f"s_{k}")
        if pd.notna(v):
            items.append((k, v, (v - 50.0) * WEIGHTS[k]))
    items.sort(key=lambda t: -t[2])
    return [(k, round(v, 1)) for k, v, _ in items[:n] if _ > 0]


def main():
    panel = pd.read_csv(os.path.join(HERE, "panel.csv"))
    d = score(panel)
    out = os.path.join(HERE, "scored.csv")
    d.to_csv(out, index=False)
    ok = d["fdi"].notna()
    print(f"scored {ok.sum()} of {len(d)} company-years "
          f"({d.loc[ok, 'company'].nunique()} institutions)")
    print(d.loc[ok].groupby("fdi_band", observed=True).size().to_string())
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
