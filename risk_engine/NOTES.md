# Bank & NBFC Default Risk — what the data actually supports

Working notes for Team B-15. This records what was built, what the backtest
said, and which claims in the current deck the evidence does not support.

## What changed versus the deck

The deck specifies a Merton/KMV model on five companies (Yes Bank, Reliance
Capital, plus HDFC/ICICI/Kotak as controls), using yfinance prices and the
Kaggle balance sheets.

Three problems with that as stated:

1. **Five companies cannot validate a model.** Two distressed names and three
   controls is an anecdote. The archive contains **556 banks and NBFCs**
   (39 banks, 517 finance companies) with **6,139 company-years, 2006–2023**.
   All of it was left on the table.
2. **Merton needs a liquid listed share.** Only 32% of the financial
   institutions in the archive carry an NSE ticker. A fundamentals-based score
   covers all 556 and works for unlisted and thinly traded ones.
3. **The deck's illustrative chart is made up.** Slide 10's "Yes Bank PD rises
   to 42%" is labelled *illustrative* in small print, but it reads as a result.
   Everything below is computed from the archive and can be re-run.

The build keeps Merton as a second, market-based layer (`merton.py`) and adds
a **Fundamental Distress Index (FDI)** as the primary engine.

## Pipeline

```
build_panel.py   556 institutions × 18 years → panel.csv
score.py         ratios → peer percentiles → FDI 0–100 → scored.csv
validate.py      backtest against 11 real RBI actions / defaults
merton.py        market-based distance-to-default (needs prices/)
```

Point-in-time throughout: FY-ending-March accounts are treated as public from
30 June, so nothing is credited with warning it could not have given.

## The index

Eight candidate components were cut to six after backtesting:

| component | weight | what it measures |
|---|---|---|
| capital_buffer | 0.30 | equity / total assets |
| capital_erosion | 0.20 | 2-year change in equity, scaled by assets |
| profitability | 0.20 | return on assets |
| leverage | 0.12 | borrowings / equity |
| interest_burden | 0.10 | interest expense / revenue |
| earnings_trend | 0.08 | 3-year change in ROA |

Two components were **removed, not down-weighted**:

- `growth_burst` (borrowings CAGR), AUC **0.34**. The "aggressive growth
  precedes blow-ups" intuition is backwards at this horizon. A lender still
  growing its book is one that wholesale markets still fund; the ones about to
  fail are already shrinking.
- `funding_stress` (operating cash flow / assets), AUC **0.44**. For a lender,
  CFO is dominated by loan-book movement, so it is noise rather than a
  liquidity read.

Both sat below 0.5 in the PSU-bank cluster and the idiosyncratic-failure
cluster independently, so the sign is consistent rather than small-sample
noise. The remaining weights are set on economic reasoning, not fitted.

### Two design decisions that mattered

**Peer-group ranking.** Ranking all 556 financials together punished every real
lender: the "Finance" sector is mostly small investment and holding companies
carrying almost no borrowings, so a normally-funded bank landed in the worst
quartile on leverage purely for being a bank. HDFC Bank scored 66 against a
sector median of 50. Banks are now ranked against banks and NBFCs against
NBFCs of similar size; HDFC Bank sits at 30–43 across the window.

**Dual anchoring on capital.** Peer-ranking then hid the opposite problem: a
sector that is uniformly thin looks safe by its own standards, which is exactly
the gap that separated the PCA banks from the private ones. Capital components
are therefore the mean of a peer-relative rank and a whole-universe rank. This
moved AUC from 0.859 to 0.912 and alerts from 6/11 to 9/11.

### Alert rule: level **or** deterioration

`FDI >= 80` **or** (`FDI >= 60` **and** FDI is 15+ points above its own
trailing 3-year median).

A level-only trigger misses the case the whole exercise is about. Yes Bank's
FY2019 accounts scored 69 — below any sensible level threshold, but far above
its own 32–45 history. The deterioration leg catches it 8 months before the
moratorium at a cost of about three extra material names per year.

## Backtest

Labelled set: **11 events** — 3 defaults/moratoria plus 8 RBI Prompt Corrective
Action placements (`events.csv`, each with a public source).

### Lead time

| institution | event | date | first alert | lead |
|---|---|---|---|---|
| Indian Overseas Bank | PCA | 2015-10 | FY2012 | 39 mo |
| Dhanlaxmi Bank | PCA | 2015-11 | FY2012 | 40 mo |
| UCO Bank | PCA | 2017-05 | FY2012 | 58 mo |
| IDBI Bank | PCA | 2017-05 | — | **missed** |
| Central Bank of India | PCA | 2017-06 | FY2012 | 59 mo |
| Bank of Maharashtra | PCA | 2017-06 | FY2012 | 59 mo |
| Bank of India | PCA | 2017-12 | FY2013 | 53 mo |
| Religare Enterprises | default | 2019-01 | FY2013 | 67 mo |
| Reliance Home Finance | default | 2019-09 | FY2019 | 2 mo |
| Yes Bank | moratorium | 2020-03 | FY2019 | **8 mo** |
| Reliance Capital | resolution | 2021-11 | FY2018 | 41 mo |

- alerted at some point before the event: **10/11**
- alerted inside the 24-month pre-event window: **8/11**
- controls (HDFC, ICICI, Kotak, Axis, SBI, Bajaj Finance) never exceed **76**

### The AUC trap — the most important finding here

| signal | AUC |
|---|---|
| FDI composite | 0.912 |
| equity / total assets alone | 0.941 |
| borrowings / equity alone | 0.972 |
| return on assets alone | 0.748 |

Read naively, a single leverage ratio beats the whole model and the project is
pointless. It does not, for two reasons:

1. **The event set is clustered.** 7 of 11 events are thinly-capitalised
   public-sector banks placed under PCA in 2015–17. Any ratio that identifies
   "is this a PSU bank" scores well. Note also that equity/TA and
   borrowings/equity are the *same ratio* inverted (Spearman −0.86) — one
   baseline reported twice, not two independent confirmations.
2. **It is a permanent label, not an alarm.** At a matched top-decile alert
   rate, leverage alone flags 26 institutions continuously for 8+ years —
   HDFC Bank, ICICI, Axis, Canara, Bank of Baroda among them — and **none of
   the firms it permanently flags ever failed**. Persistence 61% versus 38%
   for the FDI. It never changes its mind, so it carries no timing.

**AUC is the wrong headline metric for an early-warning system on a clustered
event set.** Lead time, persistence, and the size of the resulting watchlist
are what matter. This is worth a slide of its own — it is a more interesting
result than the model itself.

### Cost of the alert list

Universe 498 institutions/yr, of which 108 material.

| rule | caught | names/yr | material/yr |
|---|---|---|---|
| FDI ≥ 70 | 10/11 | 82 | 34 |
| FDI ≥ 80 | 7/11 | 32 | 11 |
| FDI ≥ 90 | 5/11 | 11 | 3 |
| level **or** deterioration (used) | 8/11 | 53 | 14 |

## Materiality

About a third of the "Finance" sector is dormant shells and defunct listed
companies — no book, no income, often deeply negative equity. The score
correctly calls them insolvent, and they swamp any ranked screen: the raw
FY2023 top 10 is almost entirely micro-caps nobody is exposed to. They are
flagged (`is_material`: total assets ≥ ₹500 cr **and** revenue ≥ ₹25 cr)
rather than dropped, so the user chooses. 151 of 552 FY2023 institutions are
material.

## Honest limitations

- **11 events is a small sample.** Every number above has wide error bars.
  Treat the ranking as indicative, not as a probability.
- **Survivorship bias in the archive.** The five PCA banks merged away before
  the 2023 snapshot (Allahabad, Corporation, Dena, OBC, United Bank of India)
  are simply absent, which removes five genuine positives and almost certainly
  flatters the false-positive rate.
- **Component selection used the same 11 events it was tested on.** Dropping
  two components is a mild form of fitting. The drops are defensible (both
  below 0.5 in two independent clusters) but there is no held-out set.
- **No notion of sovereign or parent support.** IRFC and LIC Housing score in
  the 80s on leverage and thin equity; both are government-linked and were
  never close to distress. The model sees a balance sheet, not a backstop.
- **Annual data only.** The archive's balance sheets are yearly, so the fastest
  the index can move is once a year. Quarterly NPA data exists but only from
  2020 and for 10% of the panel — used as a current-state overlay, not in the
  backtest.
- **Yes Bank is the model's weakest case, not its strongest.** The deck
  presents it as the flagship. Its reported accounts looked unremarkable until
  FY2019 because the problem was under-reported NPAs; the index only catches it
  through the deterioration leg, 8 months out. This is the honest argument for
  the market-based layer — equity markets repriced Yes Bank long before the
  accounts did.

## Analysis 2 — Merton / KMV structural credit risk

The brief asks for two distinct financial analyses. The second one reads the
equity market rather than the accounts, which matters because the fundamental
index's single biggest weakness is that it inherits whatever the filings
conceal — exactly what happened at Yes Bank.

### Getting the price data

The deck specified yfinance. Yahoo's endpoint IP-throttled this machine (HTTP
429 on every attempt over roughly 45 tries) and the usual fallback gates behind
a bot-detection challenge, which is not something to work around.

NSE publishes its **daily bhavcopy** as plain static ZIP files, and that is the
primary source Yahoo itself derives from. One file holds every symbol traded
that day, so a single request covers all ~180 listed institutions in the panel
at once. Sampling one file per week over 2013-2023 gives **64,362 weekly price
observations across 180 symbols** for 574 requests, rather than the ~2,700 a
daily series would need. Annualised volatility uses 52-week windows scaled by
sqrt(52).

### The corporate-action bug, and two wrong fixes before the right one

The first run produced nonsense: Yes Bank showed 170% equity volatility through
mid-2018 and an implied PD of 68% at a point when it traded at Rs 170 and was
considered healthy. HDFC Bank's price appeared to halve in September 2019.
Both were **missed stock splits** (Yes Bank 5:1 in 2017, HDFC 1:2 in 2019) left
in the return series as fake crashes, poisoning rolling volatility for a year.

**Wrong fix 1 — the ratio heuristic.** Treating any large drop near a round
number as a split is unsafe: Yes Bank genuinely halved in a single week in 2019
on real news, and "correcting" that deletes the collapse the project exists to
detect.

**Wrong fix 2 — PREVCLOSE.** The second attempt assumed NSE bhavcopy's
PREVCLOSE was already corporate-action adjusted, so CLOSE/PREVCLOSE would give
a clean return across a split. **It is not adjusted.** On Yes Bank's split day
the file reports CLOSE 377.05 against PREVCLOSE 1880.10 — the raw drop. Every
computed factor collapsed to 1 and the detector returned only noise from
illiquid symbols. Weekly sampling was abandoned and the full daily series
collected instead: 303,995 closes, 180 symbols, 2,713 trading days.

**What works — the single-day ratio.** The opening price is adjusted
mechanically on the ex-date, so an action lands almost exactly on a
conventional fraction while a crash does not:

```
Yes Bank   21 Sep 2017:   377.05 / 1880.10 = 0.2005   (1/5, 0.25% off)
HDFC Bank  19 Sep 2019:  1101.05 / 2187.75 = 0.5033   (1/2, 0.66% off)
```

Accept within 1.5% of 1/k or k. Three guards, each added after a real false
positive appeared in the output:

| Guard | Threshold | False positive removed |
|---|---|---|
| no 20% circuit band | drop ratio 1.25 | 0.80 is exactly the lower circuit limit — it was calling three of Reliance Capital's 2019 crash days bonus issues |
| market breadth | reject days where >6% of symbols moved >10% | 19 Mar 2020 (12.5% breadth) read Indiabulls Housing's COVID crash as a 1.5x split; real split days show 1.4–3.4% |
| minimum history | 60 prior trading days | Ujjivan SFB's listing-day pop |
| no clustering | drop pairs within 30 days | two opposite 1.5x "actions" five days apart in a micro-cap |

Result: **12 corporate actions**, all verifiable against the public record.

### Splits versus bonuses

They need different handling and conflating them is a real error. A split cuts
face value and leaves equity capital untouched; a bonus capitalises reserves so
equity capital rises with the share count. The archive reports equity capital
annually, so the two are separated by checking whether it jumped across the
action date.

### Market capitalisation

Two corrections are applied together and have to stay consistent:

* prices are divided by the cumulative split factor after date t, putting the
  series in **current share denomination**;
* share count is `equity_capital[t] / face_value_current`.

The second line is exact, not an approximation: a split changes face value and
share count but never equity capital, so that ratio is precisely the number of
current-denomination shares the then-outstanding capital corresponds to.
Genuine issuance does move equity capital, so Yes Bank's 5x FY2021 dilution is
tracked correctly rather than being mistaken for a price collapse.

### What it produces

152 institutions solved, roughly 47,600 weekly distance-to-default and
implied-PD points. For Yes Bank the series does what the deck only claimed
illustratively:

| Date | Price | Market cap (Rs cr) | Equity vol | DD | Implied 1y PD |
|---|---|---|---|---|---|
| Jul 2017 | 1,841.8 | 83,988 | 30% | 3.99 | 0.0% |
| Sep 2017 | 350.0 | 79,800 | 28% | 4.23 | 0.0% |
| Aug 2018 | 373.2 | 86,023 | 28% | 4.07 | 0.0% |
| Sep 2018 | 183.7 | 42,331 | 48% | 2.20 | 1.4% |
| Jan 2019 | 219.6 | 50,618 | 58% | 1.75 | 4.0% |
| May 2019 | 141.2 | 32,547 | 75% | 1.17 | 12.1% |
| Sep 2019 | 68.5 | 15,869 | 88% | 0.77 | 22.0% |
| Jan 2020 | 47.1 | 10,904 | 98% | 0.56 | 28.8% |
| Mar 2020 | 16.1 | 3,739 | 128% | -0.04 | 51.5% |

The price falls fivefold Jul->Sep 2017 while market cap barely moves: that is
the split, correctly handled. The inflection is **September 2018**, when RBI
refused to extend the CEO's term — the model had no knowledge of that and
picked it up from price and volatility alone.

The moratorium was 5 March 2020. The accounts-based index only reached 69 on
FY2019 filings; the market was pricing a one-in-three chance of default four
months before the event. **This is the clearest evidence for keeping both
analyses** — and page 3 of the app is built around exactly that disagreement.

### Limitations specific to this analysis

- It only works for listed institutions with a liquid quote: 152 of 556.
- Weekly sampling means volatility reacts with up to a week's lag, and the
  52-week window smooths genuine regime changes.
- Merton assumes lognormal asset value, a single debt maturity, and no parent
  or sovereign support. For a bank, all three are strong assumptions, and the
  last is plainly false for public-sector banks.
- The archive reports total borrowings only, so the KMV convention of
  short-term debt plus half of long-term cannot be applied. The default point
  is total borrowings, adjustable in the app as a sensitivity.
- The implied probability is a **model output, not a forecast**. Ranking across
  institutions is far more trustworthy than the level.

## Reproducing

```bash
python3 build_panel.py && python3 score.py && python3 validate.py
python3 fetch_nse_prices.py && python3 resolve_splits.py && python3 merton.py
streamlit run app.py
```

## Pre-mortem: three experiments against our own failure modes

Run with `python3 premortem.py`.

**1. Unseen-event test.** Component selection redone using only the seven
events before 2018 and accounts to FY2016, then frozen and run on the four
later events. The kept set is **identical** to the shipped model (funding_stress
0.400 and growth_burst 0.266 dropped without seeing the later events), and the
frozen model caught **4 of 4** held-out events on a 64-name watchlist. This
rules out one specific failure — that the result is an artefact of selection —
and nothing more. Four events validates nothing, and the two halves are not
exchangeable (development is all PSU banks, held-out is all NBFCs).

**2. Alert-utility test.** Precision is the share of alert-years followed by an
event within 24 months.

| Rule | Caught | Precision | Alerts/yr | Material/yr | Persistence | Always-on |
|---|---|---|---|---|---|---|
| FDI >= 80 | 7/11 | 4.2% | 32 | 11 | 34% | 2 |
| FDI >= 70 | 10/11 | 2.7% | 82 | 34 | 42% | 11 |
| **FDI level or deterioration** | 8/11 | 2.7% | 53 | 14 | 27% | 2 |
| Borrowings/equity top decile | 10/11 | 4.3% | 49 | 45 | 61% | 26 |
| Equity/assets worst decile | 10/11 | 4.2% | 50 | 33 | 59% | 21 |
| **Merton DD worst decile** | 4/11 | **7.2%** | **9** | 4 | 23% | **0** |

Every precision figure is low single digits — with 11 events among ~500
institutions the base rate is ~0.2%, so these are only usable relative to each
other. Two things stand out: the single-ratio baselines keep 21 and 26
institutions permanently lit against 2 for the composite, and **the market
model has the best precision of anything tested on the smallest watchlist with
no always-on names**, while catching only 4 of 11. That is the division of
labour the two-analysis design predicts — Merton is blind to PSU banks whose
prices embed a state guarantee, and sharp where it can see.

**3. Coverage test.** Of 22 known Indian bank/NBFC distress events 2013–2023,
**11 are evaluable and 11 are missing** — and every missing one is a failure
(five merged PCA banks, Lakshmi Vilas, DHFL, SREI, IL&FS, PMC, Altico). The
archive retains survivors and deletes the hardest cases, so measured recall is
optimistic and the false-positive rate is flattered. Not repairable from this
archive; it needs statements sourced per institution from annual reports filed
before resolution. **This is the highest-value extension to the project.**
