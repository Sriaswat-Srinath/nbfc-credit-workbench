"""Indian Bank & NBFC Risk Workbench — interactive Streamlit tool.

Run with:   streamlit run app.py

Menu of analyses (sidebar):
    1. Data Explorer                  descriptive statistics computed on demand
    2. Fundamental Distress Analysis  accounting-based composite distress index
    3. Structural Credit Risk         Merton / KMV distance-to-default
    4. Comparative Risk Assessment    where the two analyses disagree, and why
    5. Backtest & Validation          performance against real RBI actions

Analyses 2 and 3 are deliberately different instruments: one reads the
accounts, the other reads the equity market. Page 4 exists because the
disagreement between them is more informative than either alone.
"""

import os
import math

import numpy as np
import pandas as pd
import streamlit as st

import merton as mt
from score import WEIGHTS, top_drivers

HERE = os.path.dirname(os.path.abspath(__file__))

st.set_page_config(page_title="Bank & NBFC Risk Workbench",
                   page_icon="🏦", layout="wide")

COMPONENT_LABEL = {
    "capital_buffer": "Capital buffer (equity / assets)",
    "capital_erosion": "Capital erosion (2y change in equity)",
    "profitability": "Profitability (return on assets)",
    "leverage": "Leverage (borrowings / equity)",
    "interest_burden": "Interest burden (interest / revenue)",
    "earnings_trend": "Earnings trend (3y change in ROA)",
}
RAW_COL = {
    "capital_buffer": "f_capital_buffer",
    "capital_erosion": "f_capital_erosion",
    "profitability": "f_roa",
    "leverage": "f_leverage",
    "interest_burden": "f_interest_burden",
    "earnings_trend": "f_earnings_trend",
}
NUMERIC_LABEL = {
    "f_capital_buffer": "Equity / total assets",
    "f_capital_erosion": "Capital erosion (2y)",
    "f_roa": "Return on assets",
    "f_leverage": "Borrowings / equity",
    "f_interest_burden": "Interest expense / revenue",
    "f_earnings_trend": "ROA change (3y)",
    "total_assets": "Total assets (Rs cr)",
    "borrowings": "Borrowings (Rs cr)",
    "equity": "Equity (Rs cr)",
    "net_profit": "Net profit (Rs cr)",
    "revenue": "Revenue (Rs cr)",
    "fdi": "Fundamental Distress Index",
}


# --------------------------------------------------------------- loading ---
@st.cache_data(show_spinner=False)
def load_scored():
    return pd.read_csv(os.path.join(HERE, "scored.csv"))


@st.cache_data(show_spinner=False)
def load_panel():
    return pd.read_csv(os.path.join(HERE, "panel.csv"))


@st.cache_data(show_spinner=False)
def load_events():
    e = pd.read_csv(os.path.join(HERE, "events.csv"))
    e["event_date"] = pd.to_datetime(e["event_date"])
    return e


@st.cache_data(show_spinner=False)
def load_prices():
    return mt.load_prices()


@st.cache_data(show_spinner=False)
def load_splits():
    return mt.load_splits()


@st.cache_data(show_spinner=False)
def load_merton():
    p = os.path.join(HERE, "merton.csv")
    if not os.path.exists(p):
        return pd.DataFrame()
    return pd.read_csv(p, parse_dates=["date"])


def band_colour(band):
    return {"Low": "🟢", "Watch": "🟡", "Elevated": "🟠", "High": "🔴"}.get(band, "⚪")


# -------------------------------------------------------- 1. data explorer --
def page_explorer(d):
    st.header("Data Explorer")
    st.caption("Pick a slice of the panel and compute descriptive statistics on it. "
               "Nothing here is precomputed — every figure is calculated from the "
               "rows your filters select.")

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        sectors = st.multiselect("Sector", sorted(d["sector"].unique()),
                                 default=sorted(d["sector"].unique()))
        groups = st.multiselect("Peer group", sorted(d["peer_group"].dropna().unique()),
                                default=sorted(d["peer_group"].dropna().unique()))
    with c2:
        yrs = sorted(d["fy"].unique())
        y0, y1 = st.select_slider("Fiscal year range", options=yrs,
                                  value=(max(2013, yrs[0]), yrs[-1]))
        material_only = st.checkbox("Material institutions only", value=True,
                                    help="Total assets >= Rs 500 cr and revenue >= Rs 25 cr. "
                                         "Excludes dormant shells.")
    with c3:
        variables = st.multiselect(
            "Variables to describe",
            list(NUMERIC_LABEL),
            default=["f_capital_buffer", "f_roa", "f_leverage", "fdi"],
            format_func=lambda c: NUMERIC_LABEL[c],
        )

    sel = d[d["sector"].isin(sectors) & d["peer_group"].isin(groups)
            & d["fy"].between(y0, y1)]
    if material_only:
        sel = sel[sel["is_material"]]

    names = sorted(sel["company"].unique())
    focus = st.multiselect("Restrict to specific institutions (optional)", names)
    if focus:
        sel = sel[sel["company"].isin(focus)]

    if sel.empty or not variables:
        st.warning("No rows match these filters, or no variables selected.")
        return

    a, b, c, e = st.columns(4)
    a.metric("Institutions", f"{sel['company'].nunique():,}")
    b.metric("Company-years", f"{len(sel):,}")
    c.metric("Fiscal years", f"{sel['fy'].nunique()}")
    e.metric("Median index", f"{sel['fdi'].median():.1f}" if sel["fdi"].notna().any() else "—")

    tabs = st.tabs(["Summary statistics", "Distribution", "Correlation",
                    "Year-on-year change", "Data coverage", "Rows"])

    with tabs[0]:
        st.subheader("Summary statistics")
        rows = []
        for v in variables:
            s = pd.to_numeric(sel[v], errors="coerce").dropna()
            if s.empty:
                continue
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            rows.append({
                "Variable": NUMERIC_LABEL[v], "N": int(s.size),
                "Mean": s.mean(), "Median": s.median(), "Std dev": s.std(),
                "Min": s.min(), "Q1": q1, "Q3": q3, "IQR": q3 - q1,
                "Max": s.max(), "Skew": s.skew(),
            })
        stats = pd.DataFrame(rows).set_index("Variable")
        st.dataframe(stats.style.format(precision=4), use_container_width=True)
        st.download_button("Download these statistics (CSV)",
                           stats.to_csv().encode(), "descriptive_statistics.csv",
                           "text/csv")

    with tabs[1]:
        v = st.selectbox("Variable", variables, format_func=lambda c: NUMERIC_LABEL[c])
        s = pd.to_numeric(sel[v], errors="coerce").dropna()
        if s.empty:
            st.info("No values for this variable in the current selection.")
        else:
            lo, hi = s.quantile(0.01), s.quantile(0.99)
            clipped = s.clip(lo, hi)
            counts, edges = np.histogram(clipped, bins=40)
            hist = pd.DataFrame({"count": counts},
                                index=np.round((edges[:-1] + edges[1:]) / 2, 4))
            st.bar_chart(hist)
            st.caption(f"Clipped to the 1st–99th percentile ({lo:,.4f} to {hi:,.4f}) "
                       f"so a handful of extreme shells do not flatten the axis.")

    with tabs[2]:
        if len(variables) < 2:
            st.info("Select at least two variables to compute correlations.")
        else:
            method = st.radio("Method", ["spearman", "pearson"], horizontal=True)
            corr = sel[variables].apply(pd.to_numeric, errors="coerce").corr(method=method)
            corr.index = [NUMERIC_LABEL[c] for c in corr.index]
            corr.columns = [NUMERIC_LABEL[c] for c in corr.columns]
            st.dataframe(
                corr.style.format(precision=3)
                    .background_gradient(cmap="RdBu", vmin=-1, vmax=1),
                use_container_width=True)
            st.caption("Spearman is the safer default here: several of these ratios have "
                       "heavy tails, and equity/assets against borrowings/equity is close "
                       "to a monotone inverse rather than a linear one.")

    with tabs[3]:
        v = st.selectbox("Variable ", variables, format_func=lambda c: NUMERIC_LABEL[c],
                         key="yoy")
        w = sel.sort_values(["company", "fy"]).copy()
        w["change"] = w.groupby("company")[v].diff()
        agg = w.groupby("fy")["change"].agg(["median", "mean", "count"]).dropna()
        st.line_chart(agg[["median", "mean"]])
        worst = (w.dropna(subset=["change"])
                   .nlargest(15, "change")[["company", "fy", v, "change"]])
        st.caption("Largest single-year deteriorations in the current selection")
        st.dataframe(worst.style.format({v: "{:.4f}", "change": "{:+.4f}"}),
                     use_container_width=True, hide_index=True)

    with tabs[4]:
        cov = pd.DataFrame({
            "Non-null": sel[variables].notna().sum(),
            "Missing": sel[variables].isna().sum(),
        })
        cov["Coverage %"] = (cov["Non-null"] / len(sel) * 100).round(1)
        cov.index = [NUMERIC_LABEL[c] for c in cov.index]
        st.dataframe(cov, use_container_width=True)
        st.caption(f"{len(sel):,} rows in the current selection. Missing values are left "
                   "missing throughout — nothing is imputed.")

    with tabs[5]:
        show = ["company", "fy", "peer_group", "total_assets", "revenue",
                "net_profit", "fdi", "fdi_band"] + [v for v in variables
                                                    if v not in ("fdi",)]
        show = [c for c in dict.fromkeys(show) if c in sel.columns]
        st.dataframe(sel[show].sort_values(["company", "fy"]),
                     use_container_width=True, hide_index=True)
        st.download_button("Download selected rows (CSV)",
                           sel[show].to_csv(index=False).encode(),
                           "selection.csv", "text/csv")


# ------------------------------------------------ 2. fundamental distress --
def page_fdi(d, events):
    st.header("Analysis 1 — Fundamental Distress Analysis")
    st.caption("How distressed does this institution look on its published accounts, "
               "against comparable institutions in the same year?")

    c1, c2 = st.columns([2, 1])
    with c1:
        avail = sorted(d[d["fdi"].notna()]["company"].unique())
        default = avail.index("Yes Bank Ltd") if "Yes Bank Ltd" in avail else 0
        company = st.selectbox("Institution", avail, index=default)
    g = d[(d["company"] == company) & d["fdi"].notna()].sort_values("fy")
    with c2:
        fy = st.selectbox("Fiscal year", g["fy"].astype(int).tolist()[::-1])

    row = g[g["fy"] == fy].iloc[0]
    peers = d[(d["fy"] == fy) & (d["peer_group"] == row["peer_group"])
              & d["fdi"].notna()]

    m = st.columns(5)
    m[0].metric("Distress index", f"{row['fdi']:.1f}",
                help="0–100 percentile-based composite. Higher is worse.")
    m[1].metric("Band", f"{band_colour(row['fdi_band'])} {row['fdi_band']}")
    m[2].metric("Alert", "YES" if row["alert"] else "no")
    m[3].metric("Peer group", row["peer_group"], help=f"{len(peers)} institutions")
    m[4].metric("Rank in group",
                f"{int((peers['fdi'] > row['fdi']).sum()) + 1} of {len(peers)}",
                help="1 = riskiest in the peer group that year")

    ev = events[events["company"] == company]
    if not ev.empty:
        e = ev.iloc[0]
        st.warning(f"**Recorded distress event:** {e['description']} "
                   f"({e['event_date']:%d %b %Y}). Scores after that date describe the "
                   f"aftermath, not a forecast.")

    left, right = st.columns([3, 2])

    with left:
        st.subheader("Index trajectory")
        hist = g.set_index("fy")["fdi"].rename(company)
        peer_med = (d[(d["peer_group"] == row["peer_group"]) & d["fdi"].notna()]
                    .groupby("fy")["fdi"].median().rename("Peer-group median"))
        chart = pd.concat([hist, peer_med], axis=1).dropna(how="all")
        chart = chart[chart.index >= 2013]
        st.line_chart(chart)

        base = row.get("fdi_base3")
        jump = row.get("fdi_jump")
        if pd.notna(base):
            st.caption(f"Own 3-year median before FY{fy}: **{base:.1f}** · "
                       f"move against itself: **{jump:+.1f}** points. The alert rule is "
                       f"index ≥ 80, or index ≥ 60 together with a move of +15 or more.")

    with right:
        st.subheader("What drives the score")
        comp = []
        for k, w in WEIGHTS.items():
            pct = row.get(f"s_{k}")
            comp.append({
                "Component": COMPONENT_LABEL[k],
                "Raw": row.get(RAW_COL[k]),
                "Percentile": pct,
                "Weight": w,
                "Contribution": (pct * w) if pd.notna(pct) else np.nan,
            })
        comp = pd.DataFrame(comp).sort_values("Contribution", ascending=False)
        st.dataframe(
            comp.style.format({"Raw": "{:.4f}", "Percentile": "{:.1f}",
                               "Weight": "{:.2f}", "Contribution": "{:.2f}"})
                .bar(subset=["Percentile"], vmin=0, vmax=100, color="#B8603A"),
            use_container_width=True, hide_index=True)
        st.caption("Percentile is against the peer group that year; 100 = worst in group. "
                   "Capital components are additionally anchored against the whole sector.")

    st.subheader(f"Peer comparison — {row['peer_group']}, FY{fy}")
    tbl = (peers[["company", "fdi", "f_capital_buffer", "f_roa", "f_leverage",
                  "total_assets"]]
           .sort_values("fdi", ascending=False)
           .rename(columns={"company": "Institution", "fdi": "Index",
                            "f_capital_buffer": "Equity/assets", "f_roa": "ROA",
                            "f_leverage": "Borrowings/equity",
                            "total_assets": "Assets (Rs cr)"}))
    st.dataframe(tbl.style.format({"Index": "{:.1f}", "Equity/assets": "{:.3f}",
                                   "ROA": "{:.4f}", "Borrowings/equity": "{:.1f}",
                                   "Assets (Rs cr)": "{:,.0f}"}),
                 use_container_width=True, hide_index=True, height=320)


# --------------------------------------------------- 3. structural credit --
def page_merton(d, panel, prices, events, splits):
    st.header("Analysis 2 — Structural Credit Risk (Merton / KMV)")
    st.caption("Equity as a call option on the firm's assets. Solves the market value "
               "and volatility of assets from the observed equity, then measures how "
               "many standard deviations of asset value sit above the debt.")

    if prices.empty:
        st.error("No price data found. Run `python3 fetch_nse_prices.py` first.")
        return

    listed = (panel.dropna(subset=["nse"])
                   .assign(nse=lambda x: x["nse"].astype(str).str.strip())
                   .query("nse != ''"))
    listed = listed[listed["nse"].isin(set(prices["symbol"]))]
    names = sorted(listed["company"].unique())
    if not names:
        st.error("No institution in the panel matches a symbol in the price file.")
        return

    c1, c2 = st.columns([2, 3])
    with c1:
        default = names.index("Yes Bank Ltd") if "Yes Bank Ltd" in names else 0
        company = st.selectbox("Listed institution", names, index=default)
        ticker = listed[listed["company"] == company]["nse"].iloc[-1]
        st.caption(f"NSE symbol **{ticker}** · weekly closes from NSE bhavcopy")
        sp = splits[splits["symbol"] == ticker]
        if len(sp):
            acts = ", ".join(f"{r.factor:g}x on {r.date:%b %Y}" for r in sp.itertuples())
            st.caption(f"Corporate actions adjusted for: {acts}")
    with c2:
        st.markdown("**Model assumptions** — move these to test sensitivity")
        a, b, c = st.columns(3)
        rf = a.slider("Risk-free rate", 0.02, 0.10, mt.RISK_FREE, 0.005,
                      format="%.3f")
        horizon = b.slider("Horizon (years)", 0.5, 3.0, 1.0, 0.5)
        debt_frac = c.slider("Default point (× borrowings)", 0.5, 1.0, 1.0, 0.05,
                             help="KMV convention is short-term debt plus half of "
                                  "long-term. The archive reports only total "
                                  "borrowings, so this scales it.")

    res = mt.run_company(company, ticker, panel, prices, risk_free=rf,
                         debt_fraction=debt_frac, horizon=horizon, splits=splits)
    if res.empty or res["dd"].notna().sum() == 0:
        st.warning("The solver did not converge for this institution under these "
                   "assumptions. This usually means equity value is tiny relative to "
                   "debt, which is itself informative.")
        return

    res = res.dropna(subset=["dd"]).set_index("date")
    last = res.iloc[-1]

    m = st.columns(5)
    m[0].metric("Distance to default", f"{last['dd']:.2f}", help="Standard deviations")
    m[1].metric("Model-implied 1y PD", f"{last['pd'] * 100:.2f}%")
    m[2].metric("Asset volatility", f"{last['sigma_V'] * 100:.1f}%")
    m[3].metric("Equity volatility", f"{last['sigma_E'] * 100:.1f}%")
    m[4].metric("Market cap", f"Rs {last['market_cap_cr']:,.0f} cr")

    st.info("The probability is a **model output under Merton's assumptions**, not an "
            "observed or forecast default rate. It assumes lognormal asset value, a "
            "single debt maturity and no support from a parent or the state — all of "
            "which are strong assumptions for a bank.")

    ev = events[events["company"] == company]
    t1, t2, t3 = st.tabs(["Distance to default", "Implied PD", "Model inputs"])
    with t1:
        st.line_chart(res[["dd"]].rename(columns={"dd": "Distance to default"}))
        if not ev.empty:
            st.caption(f"Distress event on {ev.iloc[0]['event_date']:%d %b %Y}: "
                       f"{ev.iloc[0]['description']}")
    with t2:
        st.line_chart((res[["pd"]] * 100).rename(columns={"pd": "Implied PD (%)"}))
    with t3:
        st.line_chart(res[["market_cap_cr", "debt_cr", "asset_value_cr"]].rename(
            columns={"market_cap_cr": "Market cap (Rs cr)",
                     "debt_cr": "Debt / default point (Rs cr)",
                     "asset_value_cr": "Implied asset value (Rs cr)"}))
        st.line_chart((res[["sigma_E", "sigma_V"]] * 100).rename(
            columns={"sigma_E": "Equity volatility (%)",
                     "sigma_V": "Asset volatility (%)"}))

    with st.expander("Sensitivity — how the latest estimate moves with assumptions"):
        grid = []
        for f in (0.6, 0.8, 1.0):
            for r_ in (0.04, 0.065, 0.09):
                rr = mt.run_company(company, ticker, panel, prices, risk_free=r_,
                                    debt_fraction=f, horizon=horizon, splits=splits)
                rr = rr.dropna(subset=["dd"])
                if rr.empty:
                    continue
                t = rr.iloc[-1]
                grid.append({"Default point": f"{f:.1f} x borrowings",
                             "Risk-free": f"{r_:.1%}",
                             "Distance to default": t["dd"],
                             "Implied PD %": t["pd"] * 100})
        if grid:
            st.dataframe(pd.DataFrame(grid).style.format(
                {"Distance to default": "{:.2f}", "Implied PD %": "{:.2f}"}),
                use_container_width=True, hide_index=True)
            st.caption("If the ordering of institutions survives these shifts, the "
                       "ranking is robust even where the level is not.")


# ---------------------------------------------------------- 4. comparative --
def page_compare(d, merton, events):
    st.header("Analysis 3 — Comparative Risk Assessment")
    st.caption("The two analyses read different evidence. Where they disagree is "
               "usually where something interesting is happening.")

    if merton.empty:
        st.error("merton.csv not found. Run `python3 merton.py` after fetching prices.")
        return

    merton = merton.copy()
    merton["fy"] = merton["date"].apply(
        lambda t: t.year + 1 if t.month >= 4 else t.year)
    yrs = sorted(set(merton["fy"]) & set(d["fy"]))
    fy = st.select_slider("Fiscal year", options=yrs, value=yrs[-1])

    mk = (merton[merton["fy"] == fy].sort_values("date")
                .groupby("company").last()[["dd", "pd", "sigma_E", "market_cap_cr"]])
    fd = (d[(d["fy"] == fy) & d["fdi"].notna()]
          .set_index("company")[["fdi", "peer_group", "total_assets", "is_material",
                                 "fdi_band"]])
    j = fd.join(mk, how="inner").dropna(subset=["dd"])
    if st.checkbox("Material institutions only", value=True):
        j = j[j["is_material"]]
    if j.empty:
        st.warning("No institutions have both analyses available for this year.")
        return

    # rank both on a common 0-100 scale so they can be compared directly
    j["fund_rank"] = j["fdi"].rank(pct=True) * 100
    j["mkt_rank"] = (-j["dd"]).rank(pct=True) * 100
    j["divergence"] = j["mkt_rank"] - j["fund_rank"]

    st.subheader("Fundamental risk against market-implied risk")
    st.scatter_chart(j.reset_index(), x="fund_rank", y="mkt_rank", size="total_assets",
                     color="peer_group", height=420)
    st.caption("Both axes are percentile ranks within this year's comparable set, 100 = "
               "riskiest. Points on the diagonal mean the accounts and the market agree. "
               "Above the line, the market is more worried than the books; below it, the "
               "books look worse than the share price does.")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Market more worried than the accounts")
        st.caption("Candidates for problems not yet visible in reported figures.")
        top = j.nlargest(10, "divergence")[["fdi", "dd", "pd", "fund_rank",
                                            "mkt_rank", "divergence"]]
        st.dataframe(top.style.format({"fdi": "{:.1f}", "dd": "{:.2f}", "pd": "{:.3f}",
                                       "fund_rank": "{:.0f}", "mkt_rank": "{:.0f}",
                                       "divergence": "{:+.0f}"}),
                     use_container_width=True)
    with c2:
        st.subheader("Accounts worse than the market believes")
        st.caption("Often thin-capital institutions the market treats as state-backed.")
        bot = j.nsmallest(10, "divergence")[["fdi", "dd", "pd", "fund_rank",
                                             "mkt_rank", "divergence"]]
        st.dataframe(bot.style.format({"fdi": "{:.1f}", "dd": "{:.2f}", "pd": "{:.3f}",
                                       "fund_rank": "{:.0f}", "mkt_rank": "{:.0f}",
                                       "divergence": "{:+.0f}"}),
                     use_container_width=True)

    corr = j[["fund_rank", "mkt_rank"]].corr(method="spearman").iloc[0, 1]
    st.metric("Rank correlation between the two analyses", f"{corr:.3f}")
    st.caption("A correlation well below 1 is the point: if the market simply repeated "
               "the accounts, the second analysis would add nothing.")


# ------------------------------------------------------------ 5. backtest --
def page_backtest(d, events):
    st.header("Backtest & Validation")
    st.caption("Performance of the fundamental index against real RBI actions and "
               "defaults, under point-in-time rules.")

    lt_path = os.path.join(HERE, "lead_times.csv")
    if os.path.exists(lt_path):
        lt = pd.read_csv(lt_path)
        st.subheader("Lead time to each event")
        st.dataframe(lt.rename(columns={
            "company": "Institution", "event": "Event", "event_date": "Date",
            "last_fy": "Last FY before event", "fdi_at_last_fy": "Index then",
            "first_alert_fy": "First alert FY",
            "alert_lead_months": "Warning (months)"})
            .drop(columns=["peer_pctile", "lead_months"], errors="ignore"),
            use_container_width=True, hide_index=True)

    st.subheader("Distressed institutions against healthy controls")
    controls = ["HDFC Bank Ltd", "ICICI Bank Ltd", "Kotak Mahindra Bank Ltd",
                "State Bank of India", "Axis Bank Ltd", "Bajaj Finance Ltd"]
    pick_d = st.multiselect("Institutions that later failed",
                            sorted(events["company"].unique()),
                            default=["Yes Bank Ltd", "Reliance Capital Ltd"])
    pick_c = st.multiselect("Healthy controls", controls,
                            default=["HDFC Bank Ltd", "Kotak Mahindra Bank Ltd"])
    sel = d[d["company"].isin(pick_d + pick_c) & d["fy"].between(2013, 2023)]
    if not sel.empty:
        st.line_chart(sel.pivot_table(index="fy", columns="company", values="fdi"))
        st.caption("Alert threshold is 80. Controls stay well below it throughout; the "
                   "highest reading any control produced across the window is 76.")

    st.subheader("Why accuracy alone is the wrong test")
    st.markdown(
        "A single leverage ratio scores a **higher** AUC than the composite index "
        "(0.972 against 0.912) and is still the worse instrument. Seven of the eleven "
        "events are thinly capitalised public-sector banks placed under Prompt "
        "Corrective Action in 2015–17, so any ratio that effectively detects *is this "
        "a PSU bank* scores well without having predicted anything. At a matched alert "
        "rate, leverage alone flags 26 institutions continuously for eight years or "
        "more — HDFC Bank, ICICI, Axis, Canara and Bank of Baroda among them — and "
        "**none of the institutions it permanently flags ever failed**. It never "
        "changes its mind, so it carries no timing.")


# ----------------------------------------------------------------- shell ---
def main():
    d = load_scored()
    panel = load_panel()
    events = load_events()
    prices = load_prices()
    merton = load_merton()
    splits = load_splits()

    st.sidebar.title("🏦 Risk Workbench")
    st.sidebar.caption("Indian banks & NBFCs · FY2013–FY2023")
    page = st.sidebar.radio("Choose an analysis", [
        "Data Explorer",
        "1 · Fundamental Distress",
        "2 · Structural Credit Risk",
        "3 · Comparative Assessment",
        "Backtest & Validation",
    ])

    st.sidebar.divider()
    st.sidebar.metric("Institutions", f"{d['company'].nunique():,}")
    st.sidebar.metric("Company-years", f"{len(d):,}")
    st.sidebar.metric("Listed with prices",
                      f"{prices['symbol'].nunique() if not prices.empty else 0:,}")
    st.sidebar.metric("Labelled events", f"{len(events)}")
    st.sidebar.divider()
    st.sidebar.caption("Academic decision support built from public data. "
                       "Not investment advice and not a credit rating.")

    if page == "Data Explorer":
        page_explorer(d)
    elif page.startswith("1"):
        page_fdi(d, events)
    elif page.startswith("2"):
        page_merton(d, panel, prices, events, splits)
    elif page.startswith("3"):
        page_compare(d, merton, events)
    else:
        page_backtest(d, events)


if __name__ == "__main__":
    main()
