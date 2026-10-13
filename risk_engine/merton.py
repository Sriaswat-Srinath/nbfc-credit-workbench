"""Merton / KMV structural credit risk from NSE prices and the archive accounts.

Equity is a call option on the firm's assets, struck at the face value of debt:

    E  = V*N(d1) - D*exp(-rT)*N(d2)
    sE = (V/E) * N(d1) * sV                     (Ito, on the same option)

Two equations, two unknowns (V, sV), solved by fixed-point iteration, which is
the standard KMV approach and is stable on this data.

    DD = [ln(V/D) + (r - sV^2/2)T] / (sV*sqrt(T))
    PD = N(-DD)

Market capitalisation versus volatility
---------------------------------------
Prices from NSE bhavcopy are not adjusted for corporate actions, and the two
uses of the price series need *different* treatment:

  * **Volatility** needs clean returns, so it uses prices adjusted for every
    mechanical action - splits, bonuses and rights alike.
  * **Market capitalisation** needs the true value of equity on the day, which
    is the raw close times the shares actually outstanding then.

Share count is equity_capital[t] / face_value[t], and face value moves only on
*splits*:

    face_value[t] = face_value_current * product of SPLIT factors after t
    shares[t]     = equity_capital[t] / face_value[t]
    E[t]          = raw_close[t] * shares[t]

Bonuses must be excluded from that product. A bonus capitalises reserves, so
equity capital already rises with the share count and counting the bonus again
would halve the market cap before the event. Splits leave equity capital
untouched, so they must be counted. resolve_splits.py separates the two by
checking whether equity capital jumped across the action.

Point-in-time
-------------
The debt figure and share count for a date come from the most recent fiscal
year already public on that date (FY ending 31 Mar is public from 30 Jun).
"""

import os
import math

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

TRADING_DAYS = 252
VOL_WINDOW = 250          # trading days of returns for the equity volatility
MIN_VOL_OBS = 120         # minimum observations inside that window
HORIZON_YEARS = 1.0
RISK_FREE = 0.065         # flat RBI repo-ish; adjustable in the dashboard
PUBLICATION_LAG_MONTHS = 3
MAX_ITER = 300
TOL = 1e-6

SPLITS_FILE = "splits.csv"   # produced by resolve_splits.py


# ----------------------------------------------------------------- solver ---
def solve_asset_value(E, D, r, T, sigma_E):
    """Fixed-point solve for (V, sigma_V). Returns (nan, nan) if it will not settle."""
    if not all(np.isfinite([E, D, r, T, sigma_E])) or E <= 0 or D <= 0 or sigma_E <= 0:
        return np.nan, np.nan

    V = E + D
    sV = sigma_E * E / (E + D)
    for _ in range(MAX_ITER):
        if sV <= 1e-9 or V <= 0:
            return np.nan, np.nan
        d1 = (math.log(V / D) + (r + 0.5 * sV * sV) * T) / (sV * math.sqrt(T))
        d2 = d1 - sV * math.sqrt(T)
        nd1 = 0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))
        nd2 = 0.5 * (1.0 + math.erf(d2 / math.sqrt(2.0)))
        if nd1 <= 1e-12:
            return np.nan, np.nan
        V_new = (E + D * math.exp(-r * T) * nd2) / nd1
        sV_new = sigma_E * E / (V_new * nd1)
        if abs(V_new - V) / max(V, 1.0) < TOL and abs(sV_new - sV) < TOL:
            return V_new, sV_new
        V, sV = V_new, sV_new
    return np.nan, np.nan


def distance_to_default(V, sV, D, r, T=HORIZON_YEARS):
    if not all(np.isfinite([V, sV, D])) or V <= 0 or D <= 0 or sV <= 0:
        return np.nan, np.nan
    dd = (math.log(V / D) + (r - 0.5 * sV * sV) * T) / (sV * math.sqrt(T))
    return dd, 0.5 * (1.0 + math.erf(-dd / math.sqrt(2.0)))


# ------------------------------------------------------------ price prep ---
def load_splits():
    """Corporate actions detected and classified by resolve_splits.py."""
    p = os.path.join(HERE, SPLITS_FILE)
    if not os.path.exists(p):
        return pd.DataFrame(columns=["symbol", "date", "factor", "kind"])
    s = pd.read_csv(p, parse_dates=["date"])
    if "kind" not in s.columns:
        s["kind"] = "unknown"
    return s[["symbol", "date", "factor", "kind"]]


def _cum_factor(index, actions):
    """Cumulative factor to divide prices before each action by."""
    cum = pd.Series(1.0, index=index)
    for _, ev in actions.sort_values("date").iterrows():
        cum[index < ev["date"]] *= ev["factor"]
    return cum


def price_series(px_sym, actions):
    """Return (raw_close, adjusted_close, split_only_factor) for one symbol.

    raw_close feeds market capitalisation; adjusted_close feeds returns and
    volatility; split_only_factor converts current face value back to the face
    value in force on each date.
    """
    s = px_sym.sort_values("date").set_index("date")["close"].astype(float)
    s = s[s > 0]
    if len(s) < MIN_VOL_OBS:
        return None, None, None

    all_adj = _cum_factor(s.index, actions)
    splits_only = _cum_factor(
        s.index, actions[actions["kind"].isin(["split"])])
    return s, s / all_adj, splits_only


# ------------------------------------------------------------------ core ---
def _fy_lookup(pc):
    """{date accounts became public -> row} for one company, oldest first."""
    rows = []
    for _, r in pc.sort_values("fy").iterrows():
        known = (pd.Timestamp(year=int(r["fy"]), month=3, day=31)
                 + pd.DateOffset(months=PUBLICATION_LAG_MONTHS))
        rows.append((known, r))
    return rows


def run_company(company, ticker, panel, prices, risk_free=RISK_FREE,
                debt_fraction=1.0, horizon=HORIZON_YEARS, vol_window=VOL_WINDOW,
                splits=None, freq="W-FRI"):
    """Distance-to-default series for one institution.

    Volatility is estimated on daily returns; the solver is then evaluated on a
    `freq` grid (weekly by default) because solving every trading day for every
    institution is slow and adds no information at a 1-year horizon.
    """
    pxs = prices[prices["symbol"] == ticker]
    if pxs.empty:
        return pd.DataFrame()
    if splits is None:
        splits = load_splits()
    actions = splits[splits["symbol"] == ticker]

    raw, adj, split_factor = price_series(pxs, actions)
    if raw is None:
        return pd.DataFrame()

    ret = np.log(adj).diff()
    sigma = (ret.rolling(vol_window, min_periods=MIN_VOL_OBS).std()
             * math.sqrt(TRADING_DAYS))

    pc = panel[panel["company"] == company].dropna(subset=["fy"])
    if pc.empty:
        return pd.DataFrame()
    fys = _fy_lookup(pc)

    grid = raw.resample(freq).last().dropna().index

    out = []
    for date in grid:
        if date not in raw.index:
            continue
        sE = sigma.get(date, np.nan)
        if not np.isfinite(sE) or sE <= 0:
            continue
        avail = [r for known, r in fys if known <= date]
        if not avail:
            continue
        fy = avail[-1]
        fv_now, eqc, debt = fy["face_value"], fy["equity_capital"], fy["borrowings"]
        if not np.isfinite(fv_now) or fv_now <= 0 or not np.isfinite(eqc) \
                or not np.isfinite(debt):
            continue

        # face value in force on this date, and the shares it implies
        fv_then = fv_now * split_factor.get(date, 1.0)
        if fv_then <= 0:
            continue
        shares_cr = eqc / fv_then
        E = raw.loc[date] * shares_cr
        D = debt * debt_fraction
        if E <= 0 or D <= 0:
            continue

        V, sV = solve_asset_value(E, D, risk_free, horizon, sE)
        dd, pdef = distance_to_default(V, sV, D, risk_free, horizon)
        if not np.isfinite(dd):
            continue
        out.append({
            "company": company, "ticker": ticker, "date": date,
            "close": raw.loc[date], "close_adj": adj.loc[date], "sigma_E": sE,
            "debt_fy": int(fy["fy"]), "market_cap_cr": E, "debt_cr": D,
            "asset_value_cr": V, "sigma_V": sV, "dd": dd, "pd": pdef,
        })
    return pd.DataFrame(out)


def load_prices():
    p = os.path.join(HERE, "prices_daily.csv")
    if not os.path.exists(p):
        return pd.DataFrame()
    px = pd.read_csv(p, parse_dates=["date"])
    return px


def main():
    panel = pd.read_csv(os.path.join(HERE, "panel.csv"))
    prices = load_prices()
    if prices.empty:
        raise SystemExit("prices_weekly.csv missing - run fetch_nse_prices.py first")

    tick = (panel.dropna(subset=["nse"])
                 .assign(nse=lambda d: d["nse"].astype(str).str.strip())
                 .query("nse != ''")
                 .groupby("company")["nse"].last())

    splits = load_splits()
    print(f"{len(splits)} confirmed corporate actions loaded")

    frames, skipped = [], 0
    for company, ticker in tick.items():
        df = run_company(company, ticker, panel, prices, splits=splits)
        if df.empty or df["dd"].notna().sum() == 0:
            skipped += 1
            continue
        frames.append(df)

    res = pd.concat(frames, ignore_index=True)
    out = os.path.join(HERE, "merton.csv")
    res.to_csv(out, index=False)
    print(f"solved {res['company'].nunique()} institutions, {len(res):,} weekly points "
          f"({skipped} skipped for missing price or accounts)")
    print(f"date range {res['date'].min():%Y-%m-%d} .. {res['date'].max():%Y-%m-%d}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
