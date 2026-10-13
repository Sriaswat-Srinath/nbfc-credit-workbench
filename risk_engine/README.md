# Bank & NBFC Risk Workbench

A Python tool for Indian banks and NBFCs that cleans a public financial archive,
computes descriptive statistics on demand, and offers **two distinct financial
analyses from a menu**:

| # | Analysis | Reads | Course topic |
|---|---|---|---|
| 1 | **Fundamental Distress Index** | published accounts | financial statement analysis |
| 2 | **Merton / KMV structural credit risk** | equity market prices | derivatives, option pricing |
| 3 | **Comparative assessment** | both, side by side | where the two disagree, and why |

Analysis 2 is Black-Scholes applied to the firm's balance sheet: equity is a call
option on assets struck at the face value of debt, solved for the market value and
volatility of assets, then converted to a distance-to-default.

## Running it

```bash
pip install pandas numpy streamlit jinja2   # add --break-system-packages on Debian/Ubuntu
#                                 jinja2 is required by pandas .style tables
streamlit run app.py
```

The app opens with a sidebar menu of the five pages. Everything it needs is
committed as CSV, so it runs offline.

## Rebuilding the data from scratch

```bash
python3 build_panel.py        # archive -> panel.csv        556 institutions, 6,139 company-years
python3 score.py              # index   -> scored.csv
python3 validate.py           # backtest-> lead_times.csv   11 labelled RBI events
python3 fetch_nse_prices.py   # NSE bhavcopy -> prices_daily.csv
python3 resolve_splits.py     # corporate actions -> splits.csv
python3 merton.py             # structural model -> merton.csv
python3 fdic_fetch.py         # US failures + call reports (external validation)
python3 fdic_validate.py      # frozen model on 547 US failures
python3 premortem.py          # three experiments against our own failure modes
```

`fetch_nse_prices.py` downloads weekly bhavcopy files from NSE's public archive
and caches them under `bhavcopy/`, so re-running is free. Yahoo/yfinance is not
used: its endpoint IP-throttled this machine, and NSE is the primary source
anyway.

## Files

| file | what it is |
|---|---|
| `app.py` | the Streamlit tool — menu, descriptive statistics, all analyses |
| `build_panel.py` | parses the per-company CSV folders into one tidy panel |
| `score.py` | Fundamental Distress Index: features, peer percentiles, weights, alert rule |
| `validate.py` | lead time, separation, persistence, cost of the alert list |
| `fetch_nse_prices.py` | daily price panel from NSE bhavcopy (303,995 closes) |
| `resolve_splits.py` | split/bonus detection and classification |
| `merton.py` | Merton/KMV solver, distance to default, implied PD |
| `premortem.py` | unseen-event, alert-utility and coverage tests |
| `events.csv` | 11 labelled distress events, each with a public source |
| `fdic_fetch.py` | US bank failures + quarterly call reports from the FDIC API |
| `fdic_validate.py` | the frozen methodology re-run on 547 US failures |
| `make_slides.py` | builds the IEEE conference deck |
| `make_report.py` | builds the methodology PDF |
| `NOTES.md` | **methodology, results, and what the evidence does not support** |

Start with `NOTES.md`.

## Data sources

| Source | Use | Access |
|---|---|---|
| Detailed Financials of 4,456 NSE & BSE companies | balance sheets, P&L, cash flow, ratios | local archive (Kaggle) |
| NSE daily bhavcopy archive | weekly closes and corporate actions | `nsearchives.nseindia.com`, public static files |
| RBI press releases, PCA list, public filings | distress event dates and types | documented per row in `events.csv` |

## Scope

Academic decision support built entirely from public data. Not investment advice
and not a credit rating. The model-implied probability from Analysis 2 is an
output of Merton's assumptions, not an observed or forecast default rate.
