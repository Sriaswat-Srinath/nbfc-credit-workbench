# NBFC Credit Workbench: Concepts Guide

This guide explains every idea you need to understand the workbench: the
finance background, the data it is built on, the design rules, how each part of
the pipeline works, and why the project ended up as an evidence tool rather than
a default-prediction model.

It is written for a reader who has not seen the project before. It does not
replace the other documents in this folder. It is the map you read first, and
the other documents are the detail you read next (see
[Where to go next](#16-where-to-go-next)).

Figures quoted here (16 issuers, 253 findings, and so on) describe the data
files committed in this repository at the time of writing. Where this guide
and an older `.txt` document disagree on a detail, this guide follows the code.

## Contents

1. [The problem and the claim](#1-the-problem-and-the-claim)
2. [Background: Indian non-bank lending](#2-background-indian-non-bank-lending)
3. [The evidence: where the data comes from](#3-the-evidence-where-the-data-comes-from)
4. [Core idea one: point-in-time discipline](#4-core-idea-one-point-in-time-discipline)
5. [Core idea two: contradiction by arithmetic](#5-core-idea-two-contradiction-by-arithmetic)
6. [Design principles](#6-design-principles)
7. [The pipeline, stage by stage](#7-the-pipeline-stage-by-stage)
8. [XBRL in depth](#8-xbrl-in-depth)
9. [The detectors](#9-the-detectors)
10. [Anatomy of a finding](#10-anatomy-of-a-finding)
11. [Reading the interface](#11-reading-the-interface)
12. [The research that shaped the product](#12-the-research-that-shaped-the-product)
13. [Honest limits](#13-honest-limits)
14. [Statistics and research-method terms](#14-statistics-and-research-method-terms)
15. [Glossary](#15-glossary)
16. [Where to go next](#16-where-to-go-next)

---

## 1. The problem and the claim

A credit analyst who covers Indian non-bank lenders has to keep deciding whether
an issuer they hold, or lend to, is getting worse. The evidence is public, but
it is scattered across quarterly results, annual reports, rating notices and ad
hoc stock-exchange disclosures, and it arrives at unpredictable times.

The workbench compresses the first half of that job: discovering, verifying and
investigating emerging risk. It deliberately does not attempt the second half,
which is judgement.

The claim is stated so that it can be shown false:

> Reduce the time an analyst spends discovering, verifying and investigating
> emerging risk in Indian NBFCs.

It is **not** a claim that the tool predicts defaults. That claim was tested
during the research phase and failed (see section 12). Everything about the
product follows from that result: there is no risk score, every statement is tied
to a source document, and every alert carries the innocent explanation next to
the suspicion.

Two ideas are genuinely differentiated, and the rest of the product supports them:

- **Point-in-time replay.** Every figure and finding is stamped with the moment
  it reached the exchange, so the whole file can be rebuilt as it read on any
  past date (section 4).
- **Contradiction by arithmetic.** Numbers that must add up are added up, across
  filings, and mismatches are surfaced with a likely innocent cause (section 5).

---

## 2. Background: Indian non-bank lending

You need a small amount of finance vocabulary to follow the rest.

### Who the issuers are

- **NBFC (non-banking financial company).** A lender regulated by the Reserve
  Bank of India (RBI) that makes loans but does not hold ordinary bank deposits.
  Examples in the data: Bajaj Finance, Muthoot Finance, Shriram Finance.
- **HFC (housing finance company).** An NBFC-like lender that mainly lends
  against homes, historically under the National Housing Bank (NHB) and later the
  RBI. Examples: DHFL, LIC Housing Finance, PNB Housing, Repco Home Finance.
  Housing lenders borrow short and lend for twenty years, so they look very
  different from gold-loan or vehicle lenders, and the workbench never compares
  indicators across types.
- **CIC (core investment company).** A holding company that owns equity in group
  companies and books few loans itself. Reliance Capital is the example. Its own
  accounts do not describe the lending businesses beneath it.
- **Listed entity vs. operating entity.** The company whose shares trade on the
  exchange is often not the company carrying the risk. SREI Infrastructure's
  standalone accounts showed zero advances because the loan book sat in an
  unlisted subsidiary. This mismatch recurs throughout the project.

### How they fund themselves

- **NCD (non-convertible debenture).** A bond the lender sells to investors. It
  pays interest on fixed dates and returns principal at maturity. Missing either
  is a payment default, and the issuer must tell the exchange.
- **Commercial paper (CP).** Short-term unsecured borrowing, usually under a year.
  It must be rolled over repeatedly, so when markets freeze it is the first thing
  that cannot be refinanced.
- **Asset-liability mismatch (ALM).** Lenders borrow for short periods and lend for
  long ones. The "gap" between money due in versus money due out over a given
  horizon is the ALM gap. The research phase tested whether this gap predicts
  failure (section 12).
- **Refinancing risk.** The risk that a lender cannot roll over maturing debt. This,
  not the existence of a gap, is what failed lenders actually suffered from.

### Regulators and rules

- **SEBI** is the securities regulator. **NSE** is the stock exchange whose public
  filings the workbench reads.
- **LODR Regulation 33.** The listing rules require quarterly results within 45
  days of quarter end and audited annual results within 60 days of year end.
  Missing these is observable and does not depend on anyone's accounts being honest.
- **Regulation 57.** Rules about disclosing debenture payments to the exchange.
- **SEBI default-disclosure form (circular CIR/CFD/CMD/93/2017).** A numbered
  template ("Date of default", "Current default amount") that an issuer files only
  when there is a default to report.
- **RBI superseding a board.** The regulator removes a lender's directors and takes
  control. In this project it is classed as an *intervention*, not a default.
- **IBC / NCLT.** The Insolvency and Bankruptcy Code and its tribunal, the formal
  route for resolving a failed company.

### Accounting vocabulary

- **Ind AS.** Indian Accounting Standards. NSE files use three tag sets
  ("taxonomies"): one for NBFCs under Ind AS, a generic Ind AS one, and a pre-2018
  non-Ind-AS one. Their line items are named differently.
- **Standalone vs. consolidated.** Standalone accounts describe the listed
  company alone. Consolidated accounts add its subsidiaries. The workbench
  **never mixes the two**.
- **Quarter, half-year, nine-month and year-to-date (YTD).** One filing can carry
  the quarter and also the cumulative period so far. A nine-month column should
  equal the sum of three quarters.
- **Impairment / credit cost.** The amount a lender sets aside because loans may
  not be repaid. It is the lender's own admission that its book is worth less.
  It is strongly seasonal (large in the fourth quarter), which affects how the
  workbench compares it.
- **Gross NPA.** The share of loans that have stopped paying. Mostly absent from
  the annual data used here (section 13).
- **Equity / total assets.** The buffer between losses and creditors. Plain
  equity/assets beat a complex index in the research phase, so the product shows
  it directly.
- **Leverage.** Total assets divided by equity. When equity is zero or negative the
  ratio inverts and becomes meaningless, so the workbench withholds it.
- **Currency units.** 1 lakh = 100,000 and 1 crore = 10,000,000 rupees. Source
  files hold absolute rupees; the interface divides by 10^7 to show crore.

---

## 3. The evidence: where the data comes from

The workbench uses five NSE endpoints and one local file. Nothing else feeds it.

| Source | What it gives | Used for |
|---|---|---|
| NSE `corporate-announcements` | The disclosure stream from 2004: category, summary text, link to a PDF, timestamp. 25,919 items across the 16 issuers. Available even for delisted issuers. | Timeline; rating actions; clarification requests; payment disclosures |
| NSE `corporates-financial-results` | The index of every results filing with its dissemination timestamp, standalone/consolidated flag, audited flag and XBRL link. | Filing dates and timeliness; basis |
| NSE XBRL instances | The tagged quarterly results behind each filing. 661 instances. No PDF parsing is needed. | Quarterly profit and loss figures; the statement viewer |
| NSE announcement attachments | The PDFs behind payment announcements, fetched and read. 2,450 fetched. | Classifying whether a payment was made |
| NSE `annual-reports` | Publication timestamps for annual reports. | Dating the annual layer |
| `credit_workbench/data/panel.csv` | The annual balance sheet from a supplied financials dataset. Not from NSE. | Capital and leverage view |

Practical points:

- The NSE endpoints are unauthenticated but reject requests without a browser
  user-agent and a `Referer` header. Python's `urllib` hangs on them, so every
  fetch shells out to `curl`.
- The raw cache (about 900 MB) is **not** in the repository. `ingest.py` and
  `attachments.py` rebuild it. The committed `workbench_data.json` / `.js`
  and `statements/` are the derived outputs.
- `panel.csv` is why DHFL has no Capital and leverage view (it was delisted before
  the dataset snapshot) and why gross NPA exists for only some issuers. A single
  rename is handled by an alias (`SAMMAANCAP` is stored as `IBULHSGFIN`).
- Structured quarterly results exist only from about 2019, when XBRL became
  mandatory. DHFL, for example, has 14 readable filings against 73 listed.

### The universe

`universe.py` lists 16 issuers, chosen to be mixed on purpose:

| Class | Count | Issuers |
|---|---|---|
| Failed (default or board superseded) | 4 | DHFL, RHFL, SREI Infrastructure, Reliance Capital |
| Severe stress or regulatory action, survived | 4 | Sammaan Capital, PNB Housing, IIFL, Edelweiss |
| No notable event | 8 | Bajaj, LIC Housing, Cholamandalam, Muthoot, Shriram, Can Fin, Repco, Manappuram |

The `outcome` field exists only to label the demo. **No detector reads it.**
That property is enforced by never importing it, and it is what makes the
findings blind to who failed.

`RELATED` records two hand-written parent/subsidiary pairs (Reliance Capital and
Reliance Home Finance; SREI Infrastructure and its unlisted equipment-finance
arm). The project has no general entity resolution, which is its largest
structural gap.

---

## 4. Core idea one: point-in-time discipline

### Three different dates

Every financial fact has at least three dates, and confusing them is the most
common way an analysis cheats without meaning to:

| Date | Meaning | Example |
|---|---|---|
| **Period end** | The date the figures describe | 31 March 2019 |
| **Filing / board date** | When the issuer's board approved or filed | May 2019 |
| **Dissemination date** | When it actually reached the exchange and became public | 23 July 2019 |

Only the dissemination date tells you what an analyst could have known. The
workbench keys everything on it and never on the period end.

### Why it matters: the DHFL example

DHFL's FY2019 annual report was published on 5 September 2019, three months
**after** its 4 June 2019 default. A screen that joins data by fiscal year would
read that report as "available" before the default and appear to predict it,
using a document that did not yet exist. Checking publication timestamps removed
three of five cases from the earlier research for exactly this reason.

### `knowable_on`

Each finding carries a `knowable_on` timestamp: the moment a diligent analyst
could first have seen it. Everything turns on this field: the as-of control, the
brief, and the integrity test.

Rules for setting it:

- A fact from a filing is `knowable_on` the filing's **dissemination** timestamp.
- A missed deadline is `knowable_on` the day the **deadline passed**, not the day
  the issuer finally filed. On the deadline an analyst can observe that nothing
  arrived; the eventual filing date is not yet known.
- A finding built from a window of items is dated at the **last** item, because
  that is when the cluster completed.
- An annual figure is `knowable_on` the annual report's publication timestamp,
  with a flagged estimate (year end plus about six months) when no report could be
  matched.

### Replay

The whole corpus is exported once, with every finding's `knowable_on`. The browser
then keeps only what satisfies:

```
visible(issuer) = findings where knowable_on[:10] <= as_of
```

That is a plain string comparison on ISO dates (`2019-05-31`). It needs no
server and no re-query, and the page moves instantly when the analyst changes
the date. The same filter applies to quarterly figures, annual rows, timeline
items, statements and the brief.

Two side effects are deliberate:

- The recorded outcome (default, intervention) is **withheld** until the as-of
  date passes it, so a replay cannot be read with hindsight.
- Setting the date to 31 May 2019 ranks Reliance Home Finance, Reliance Capital
  and DHFL first, second and third. All three failed within thirty months. This is
  a demonstration, not evidence: three cases chosen with hindsight in a universe of
  sixteen.

### The `retrospective_` convention

Some findings are partly known on their date and partly known only later. A
missed-deadline finding is the clearest case. On the deadline you know "nothing
was filed". You do not yet know "it was filed 114 days late".

The code separates the two halves:

- Plain evidence keys hold what was knowable on `knowable_on`.
- Keys prefixed `retrospective_` hold what arrived afterwards.

The interface shows the retrospective half only once the as-of date has passed
it. So the same card reads "as at 2019-05-31, one further day has passed with
nothing filed" before the filing arrives, and "it was eventually filed on
2019-07-23, 114 days after period end" afterwards.

### The integrity test: `check_pit.py`

Claiming point-in-time correctness is worthless if it is only asserted, because
the ways to break it are subtle and arrive by accident. `check_pit.py` walks every
finding, extracts every ISO date from its evidence, and fails if any date is
later than the finding's own `knowable_on`. It exempts `retrospective_*` keys,
a few forward-looking keys, and the two finding kinds that describe the limits of
the evidence (stamped "today" by construction).

It has caught three real look-ahead leaks in this codebase, each found by
writing the test rather than reading the code:

1. `disclosure_burst` scanned 30 days **forward** but stamped the finding with the
   first item, so it was visible before its evidence existed.
2. `scale_anomalies` compared each filing with neighbours on **both** sides, so
   whether a filing was usable depended on filings published later.
3. `check_payments` described a run of disclosures using its worst status and total
   length, dating a "did not pay" to a day whose letter said "will be delayed" and
   citing filings that had not happened yet.

It should be run after every change to `detect.py`, and it must report zero
violations.

---

## 5. Core idea two: contradiction by arithmetic

Some numbers must add up by definition. When they do not, something changed after
the first publication, and the tool can show that using nothing but arithmetic on
filed data.

**Year-to-date vs. quarters.** A nine-month figure must equal the sum of its three
quarters. Where it does not, a quarter was restated after it was first reported.
A worked example from the data: Shriram Finance's FY2023 nine-month total income
was filed as Rs 22,542 crore, while the three quarters inside it, as originally
filed, sum to Rs 18,310 crore. The tool flags the break and names the likely
innocent cause, a merger that restated comparatives. That pairing is the intended
behaviour: find the contradiction, offer the counter-explanation, send a human to
check.

**Within a single filing.** The statement viewer recomputes six relationships that
hold by definition of a profit and loss account (total income, total revenue,
profit before exceptional items, total tax, profit from continuing operations,
total comprehensive income). Each result is reported as holds, breaks, or not
evaluated. Across the 1,164 statement columns in the corpus the documented result
is no breaks, which is what makes a future break meaningful.

Why two other checks were abandoned: summing the expense lines of a statement to
compare with the stated total produced failure rates of 7.6% and 35.9%. Both
were the rule being wrong, not the filings, because the three taxonomies break
income and expense into differently named lines. A check wrong a third of the
time trains the reader to ignore every check, so the decomposition is left
unchecked and the interface says so.

---

## 6. Design principles

Each principle is a response to a specific failure found in the research phase.
They are constraints, not preferences.

**No composite score.** A nine-component weighted distress index did not beat plain
equity/assets on held-out data. Where a simple ratio beats a composite, show the
simple ratio. The tool ranks evidence and leaves weighting to the analyst.

**Publication date, never period end.** See section 4.

**Never mix reporting basis.** Standalone and consolidated are shown and tested
separately. The listed entity is often not the entity at risk.

**Never impute.** A missing figure produces a coverage finding, not a filled value.
A mis-scaled filing is excluded and reported, not rescaled by a guessed multiplier.

**Always state the innocent explanation.** Every detector carries a
`counterevidence` field. A detector that flags without explaining trains the user
to ignore it.

**Assume the figures may be false.** Reliance Capital reported the best one-year
liquidity cover in its peer group while Rs 5,103 crore of its debentures had already
been recalled by the trustee. So the tool leans on signals that do not depend on
the figures being true, above all whether the issuer filed on time and what it said
about payments.

**Thresholds are visible constants.** The numbers that decide whether something is
an alert sit at the top of `detect.py` so an analyst can read and disagree with
them. They are not hidden in a model.

**Floors in rupees as well as percentages.** A purely relative test fires on rounding
noise in small numbers. The first build reported a Rs 0.3 crore "restatement" three
times. Every numeric detector therefore needs both a relative test and an absolute
floor.

**Evidence over opinion.** Every figure links to the source XBRL file or PDF the
exchange published. Nothing in the tool is the final authority; the linked document
is.

---

## 7. The pipeline, stage by stage

```
universe -> ingest -> facts/normalize -> annual -> attachments
                              \             |           /
                               \-----> detect <--------/
                                         |
                                       brief -> build -> workbench_data.json/js -> workbench.html
```

`check_pit.py` sits to the side: nothing depends on it, but it must pass before
anything is published.

| Stage | File | Job |
|---|---|---|
| Issuers | `universe.py` | The 16 issuers, their type, group and outcome label |
| Ingest | `ingest.py` | Fetch announcements, the results index and XBRL instances. Resumable and skip-if-present. Stores raw bytes, not a re-serialised copy, so the evidence is preserved exactly |
| Announcements | `announcements.py` | Load and clean the announcement stream. Exists as its own module to break an import cycle between `detect` and `attachments` |
| Facts | `facts.py` | Parse XBRL into a table of 23 curated metrics per period and basis, with the filing's dissemination timestamp |
| Normalize | `normalize.py` | Render a whole XBRL instance as a readable profit and loss statement with the original tag beside every line, plus the six self-consistency checks |
| Annual | `annual.py` | Join the annual balance sheet to annual-report publication dates and derive ratios |
| Attachments | `attachments.py` | Fetch and read the PDFs behind payment announcements, then classify the outcome |
| Detect | `detect.py` | The finding engine: ten check functions, deduplication, severity ordering |
| Brief | `brief.py` | Assemble the point-in-time investigation brief and its text rendering |
| Build | `build.py` | Export everything the page needs into `workbench_data.json` |
| Export | `export_statements.py` | Write every filing out as a readable text file in `statements/` |
| UI | `workbench.html` | The single-page interface |

### Resumability and the cache

The cache is the evidence. Nothing downstream rewrites it, and every number the
interface shows names the file it came from. Each ingestion step skips what it
already has, so a killed run costs only the file in flight.

### The build output and the interned lexicon

`build.py` writes `workbench_data.json`, and a one-line wrapper turns it into
`workbench_data.js` (`window.WB = ...;`) so the page can load it as a sibling
script. Statements are the heaviest part: about 1,164 statement columns of roughly
35 lines each. Spelling every label, section name and tag out each time produced a
15.2 MB export. Instead, repeated strings are **interned** into one shared list
(the lexicon, about 520 entries) and each line stores integer indices:

```
line  = [labelIdx, sectionIdx, kindIdx, value, tagIdx]
check = [ruleIdx, stated, recomputed, difference, state, [missingIdx]]
state: 1 holds, 0 breaks, null not evaluated
```

That cut the export to roughly 6.7 MB. Values are rounded to two decimals of
rupees because the source carries no more precision.

### Adding an issuer

Append a row to `ISSUERS` in `universe.py`, run `ingest.py <SYMBOL>`, then run
`build.py`. The only per-issuer hard-coding elsewhere is the `RELATED` pairs and
the `panel.csv` alias map.

---

## 8. XBRL in depth

XBRL is a tagged format for financial reports. An *instance* is an XML file
containing *facts*, each of which names a concept (a tag such as `InterestEarned`),
a value and a *context* that says which period or date it belongs to.

### Why the workbench uses it

Tagged data removes any need to parse PDFs for quarterly results. Every figure the
tool shows for a quarter comes from a tag, which makes it checkable.

### Columns inside one file

One NSE instance carries several columns of the published results table: the
quarter, the year to date, sometimes comparatives. They are distinguished by a
context prefix (`One`, `Two`, ... `Six`). In the files read here, `One` is typically
the quarter and `Four` the year to date.

### The wrong-dates trap

The `xbrli:context` period dates in these files are **unreliable**. In a Bajaj
Q3 filing every context is stamped with the quarter's dates, including the
nine-month column. Reading them would silently merge quarterly and cumulative
figures and corrupt every detector.

The true period comes from the facts `DateOfStartOfReportingPeriod` and
`DateOfEndOfReportingPeriod` that belong to each prefix. `normalize.py` uses
three sources in order of preference: the tagged dates, then the declared context,
then the dates from the results index. Nine early filings reference a context
they never declare, and are readable only through the third source. The source
used is recorded as `period_source`.

### Span classification

A column's length in days decides what it is: up to 100 days is a quarter (`Q`),
up to 190 a half-year (`H`), up to 285 nine months (`9M`), anything longer a full
year (`FY`).

### Units

Values are **absolute rupees**, not the scale named in the tagged rounding field.
Bajaj tags "Crores" and files 132,773,300,000.00 for Rs 13,277 crore. The
rounding label describes the published PDF and is not a multiplier.

### Mis-scaled filings

A minority of instances are pre-scaled, and the rounding label does not predict
which. `scale_anomalies` finds them by comparing each quarter's total income with
the median of the previous six filed quarter columns (at least four are needed), and
flagging a ratio that lands within 45% of a clean scaling factor (1e-7, 1e-5, 1e-2,
1e2, 1e5 or 1e7).

Three refinements were each forced by a false positive:

- A local window rather than the issuer's whole history, because Reliance Capital
  genuinely collapsed to shell scale and a global median called 17 of its filings
  mis-tagged.
- Quarter columns only, because pooling year-to-date columns inflated the median
  and let a filing a hundred times too small pass.
- A trailing window only, because a forward window made usability depend on later
  filings (one of the look-ahead leaks).

A tagging error produces an exact factor and a real business collapse does not.
Flagged columns are **excluded** from every numeric detector and reported as a
finding. The exclusion is the finding.

### Dealing with the same period filed twice

When the same period appears in more than one filing, `quarter_series` keeps the
**earliest** dissemination, because that is when the figure first became knowable.
The later filing is what the additivity check compares against.

---

## 9. The detectors

`findings_for(symbol)` runs ten check functions and produces fifteen kinds of
finding. Fourteen of them appear in the current data (`basis_withdrawn` never fires,
because no issuer here stops filing consolidated accounts once it starts; it is kept
because sixteen issuers do not prove it cannot happen).

Current counts in the committed data: 253 findings in total, 158 high, 64 medium
and 31 low.

### Summary

| Kind | Check function | Trigger | Dated at |
|---|---|---|---|
| `filing_overdue` | `check_filing_timeliness` | Results not filed within the statutory window | The deadline |
| `additivity_break` | `check_additivity` | YTD differs from the sum of its quarters | The cumulative filing |
| `unit_anomaly` | `check_scale` | Filing on a different scale from the issuer's history | The filing |
| `basis_withdrawn` / `basis_unavailable` | `check_basis_availability` | Consolidated reporting stopped, or never filed | Year end |
| `audit_opinion` | `check_audit_flags` | Audit statement other than unmodified | The filing |
| `deterioration` | `check_earnings` | Swing into loss, or credit cost sharply up year on year | The filing |
| `capital_erosion` | `check_capital` | Equity/assets falls 25% or turns negative | Annual report publication |
| `payment_disclosure` | `check_payments` | Attached PDF says a payment was missed or will be late | The first letter |
| `rating_action`, `exchange_clarification`, `price_flag` | `check_announcements` | Watched announcement matching distress language | The announcement |
| `disclosure_burst` | `check_announcements` | Four matched announcements within 30 days | The last item |
| `coverage_gap`, `stale_evidence` | `check_coverage` | Missing quarters, unreadable attachments, no recent filing | Today |

### Detail

**Filing timeliness (`filing_overdue`).** Quarterly results are due 45 days after
quarter end, annual results 60. Two periods use relaxed limits because SEBI extended
the deadlines market-wide during COVID-19: year ended 2020-03-31 gets 122 days and the
quarter ended 2020-06-30 gets 77. Applying them in advance avoids falsely flagging
every issuer. Severity is high at 30 or more days over, medium at 10 or more, else
low. The finding records the issuer's own trailing median lag, since lateness against
the issuer's own habit matters more than lateness against the rule. This is the
strongest signal in the corpus: DHFL filed its audited FY2019 results 114 days after
period end and its first default fell inside that gap; RHFL filed 136 days late
against its own norm of about 50.

**Additivity (`additivity_break`).** For each non-quarter column the check chains the
quarters inside it and compares total income, profit before tax and profit after
tax. It fires when the difference exceeds the larger of 1% and Rs 5 crore, and only
where the cumulative figure is at least Rs 50 crore. Severity is high if the gap is
over 5% of the cumulative figure. Innocent causes: an Ind AS transition, a
discontinued operation, a business combination or a retrospective merger.

**Scale (`unit_anomaly`).** See section 8.

**Basis availability.** `basis_unavailable` fires when consolidated accounts were never
filed. It is a statement about coverage, not an accusation, and carries an explicit
counter-explanation: a lender with no subsidiaries has standalone accounts that *are*
the group.

**Audit opinion (`audit_opinion`).** Reads the tagged audit-qualification field and
fires when it is present and is not "unmodified", "unqualified" or "not applicable". A
modified opinion is the auditor declining to stand fully behind the figures.

**Earnings (`deterioration`).** Two deliberately narrow branches:

- *Profit reversal.* Fires only on an actual loss against a trailing four-quarter
  median profit. A *decline* in profit is not reported; the first build flagged 13
  "deteriorations" at Bajaj Finance, which grew throughout.
- *Credit cost year on year.* Compares impairment with the **same quarter** of the
  previous year, because lender provisioning is strongly seasonal and a trailing
  comparison mostly detects the fourth quarter. Fires at +50% or more, severity high
  at +150%.

Both need to clear a materiality floor that scales with the issuer: the larger of
Rs 5 crore and 2% of trailing four-quarter income. A Rs 5 crore move matters for a
small lender and is noise for a large one.

**Capital (`capital_erosion`).** Compares consecutive annual equity/assets values and
fires if the ratio turns negative (high) or falls 25% relative (medium). Leverage
(assets/equity) is withheld wherever equity is zero or negative, because the ratio
inverts. Reliance Capital's equity fell from -Rs 949 crore to -Rs 19,820 crore while
the printed ratio "improved" from -88.5x to -3.2x. The interface shows "n/m" with the
reason and places equity next to total assets so the ratio can be checked rather than
trusted.

**Payments (`payment_disclosure`).** The announcement title is identical whether a
company paid or did not, so this detector reads the attached document. Between
October and December 2019 Reliance Capital filed 23 announcements under one identical
title; inside them was the sentence that debt servicing "will be delayed". Corpus-wide
there are 2,168 such announcements and the title text alone promotes only 14.

Consecutive adverse disclosures within 45 days are collapsed into a **run**, because a
company in difficulty files one letter per ISIN, often several a week. The finding
describes only the first letter, in its own words, and everything about how the run
continued lives under `retrospective_`. If a run begins with "delayed" and later
reaches "not paid" or the default form, the **escalation** is its own finding, dated
when it happened.

**Announcements.** Three NSE categories are watched: credit rating, news verification
(the exchange asking an issuer to confirm a press report) and price movement. An
announcement becomes a finding only if its text matches a visible distress pattern
(default, downgrade, rating watch, moratorium, NCLT, forensic, going concern, auditor
resignation and so on). Otherwise it stays on the timeline. Without this gate the
first build emitted 133 findings for DHFL, one per routine rating notice. The matched
phrase is stored as `promoted_because_text_matched` so the promotion is auditable.
Price-movement notices are the exchange's boilerplate and contain no distress words,
so they are gated on direction instead (a significant *decrease*). `disclosure_burst`
fires on four or more matched items within 30 days.

**Coverage (`coverage_gap`, `stale_evidence`).** These describe the **evidence**, not the
issuer: quarters with no machine-readable filing, payment attachments that are scanned
images with no text layer, and a last filing more than 150 days old. They are listed
under their own heading in the interface. Silence from a document nobody can read is not
evidence of calm. SREI Infrastructure's lack of payment findings is because most of its
attachments are unreadable scans.

### Reading attachments

`attachments.py` extracts text with `pdftotext` and classifies each letter in a fixed
order, negatives before positives so that "we did not pay X, having paid Y" is a failure:

| Status | Meaning |
|---|---|
| `default_form` | The SEBI default template. Filing the *form* is a stronger signal than any phrase |
| `not_paid` | Payment not made or the issuer unable to pay |
| `delayed` | Payment will be or has been delayed |
| `paid` | Standard confirmation of timely payment |
| `unclear` | A real answer: trustee compliance letters that state no payment outcome |

A phrase can appear without asserting anything, so each match passes three guards: it
is discarded when negated in the preceding 90 characters (for example "no grounds on
which the Company could be found unable to pay"), when it sits inside a form label (for
example "payment/non-payment of interest"), or when it follows a list marker. The
guards were tuned so that Reliance Capital's 154 true positives survived unchanged; a
guard that removes false alarms by also removing real ones would be worthless. Some
attachments are ZIP archives served under a PDF-looking address (73 of DHFL's 214),
which `pdftotext` silently reads as empty; the archive is opened and its largest PDF
used.

### Deduplication

Two kinds of duplicate inflated the first build:

1. The exchange files one event twice (its own query and the issuer's reply). These
   collapse on a signature of `(kind, day, first 90 characters of the text)`.
2. An issuer whose consolidated figures match standalone generates the same finding
   under both bases. The basis words are stripped before the signature is taken, the
   findings are merged, and the survivor notes that the figure was filed on both bases,
   because agreement across bases is information and two identical cards are not.

Findings are then sorted by severity, then by `knowable_on`.

---

## 10. Anatomy of a finding

Every detector emits the same record:

| Field | Meaning |
|---|---|
| `symbol` | The issuer |
| `kind` | Which detector produced it |
| `severity` | `high`, `medium` or `low` |
| `knowable_on` | When a diligent analyst could first have seen it |
| `what_changed` | One sentence, with the figures |
| `why_it_matters` | The mechanism, stated as a hypothesis, not a conclusion |
| `evidence` | Source, file, link, timestamps, intermediate values used in the test |
| `investigate` | What the human should do next |
| `counterevidence` | The innocent explanation, or `null` |
| `metric`, `value` | A machine-readable payload |

In the interface each card shows the same five parts: WHAT, WHY, AGAINST, NEXT and
EVIDENCE. Read AGAINST before acting on WHAT. It is there because most findings have a
boring explanation and the tool cannot tell which.

**Severity** reflects the strength of the signal for that detector, not the probability
of failure. **Evidence-limit findings** (coverage and staleness) are separated from
substantive ones, because they say what cannot be known and not what has gone wrong.

---

## 11. Reading the interface

The page is a single HTML file with no framework and no build step. Its state is three
fields, `{ sym, asof, tab }`, and one `draw()` function re-renders everything. All
interpolated text passes through an escaping helper before it reaches `innerHTML`. Charts
are hand-drawn with `div` elements: a filing-lag bar with a tick at the statutory limit,
and a diverging equity/assets bar with a zero rule.

Serve it over HTTP, because the data loads as a sibling script and `file://` will not
work:

```bash
python3 -m http.server 8777 --directory credit_workbench
# then open http://localhost:8777/workbench.html
```

### The as-of control

The bar at the top reads "evidence as it stood on", with a date box, a slider and
presets. Moving it rebuilds the whole page as the file read on that date. Two uses:

- **Live monitoring.** Leave it at today and treat the issuer rail as a reading queue.
- **Process review.** Set it to the date you made a decision, read the file as it stood,
  then move forward and see what arrived.

A dashboard tells you what is true now. This tells you what was knowable then, which is
the only way to judge whether a monitoring process was adequate rather than whether a
failure looks obvious in hindsight.

### The issuer rail is a queue, not a ranking

Issuers are sorted by how many unexamined high-severity findings sit in their file. Read
it as "where should I spend this afternoon", never "which is riskiest". Repco Home
Finance, a conservative lender that never got into difficulty, carries 14 findings over
its history; Bajaj Finance carries 4. The gap reflects mostly how much each filed, not
how sound each is.

### The six tabs

| Tab | Use it when |
|---|---|
| **Findings** | Start here. Grouped high, medium, low, with the five-part card |
| **Capital & leverage** | You want annual equity/assets, leverage, borrowings/assets, ROA and gross NPA, each dated by annual-report publication. Rows marked "est" carry an estimated date, so treat their lead times as optimistic |
| **Reported figures** | You want quarterly income, PBT, PAT and impairment as filed, standalone and consolidated kept separate, with the filing-lag bar |
| **Filed statement** | You want to verify a number: any single filing rendered as its profit and loss account with the original tag beside every line and the six checks beneath |
| **Disclosure timeline** | You need the sequence of exchange announcements, with links to the original PDFs |
| **Investigation brief** | You need prose for a credit memo. It does not conclude; it ends with what it cannot tell you |

### Mistakes the tool makes easy

- **Reading the count as risk.** It is a reading queue.
- **Reading zero findings as safety.** Check the limits-of-evidence section first.
- **Trusting a figure without opening it.** Use the Filed statement tab.
- **Reading a lead time off an estimated date.**
- **Treating a confirmation as a warning.** DHFL's default form is dated four days
  *after* its default. It confirms; it does not predict.
- **Assuming the group is the issuer.** A finding on Reliance Home Finance is not a finding
  on Reliance Capital.

---

## 12. The research that shaped the product

The workbench is the survivor of earlier research that mostly failed, and its constraints
come from those failures.

### What was tried and what happened

- A **nine-component weighted distress index** did not beat plain equity/assets on held-out
  US bank data.
- A US model caught most bank failures by count but almost none by asset size, and missed
  Silicon Valley Bank, whose last report looked healthy on every measure.
- An **ALM maturity-gap screen** for Indian lenders was tested against matched cohorts and
  scored at or below chance.

### The ALM study, in outline

Hypothesis: a lender with a worse one-year liquidity cover (inflows due within a year
divided by outflows due within a year) is more likely to fail.

It was **pre-registered** in `OUTCOME_DEFINITION.txt` before the extracted figures were
inspected: the primary outcome (a documented missed payment within 12 months of the
observation date), the secondary outcomes (kept separate, never pooled), the baselines the
measure had to beat, and what would falsify the idea. The result is in `ALM_FINDINGS.txt`:

| Cohort | Result |
|---|---|
| Housing finance companies, reports published mid-2018 (7 firms) | AUC 0.400, below chance |
| Other NBFCs, reports published mid-2020 (5 firms) | AUC 0.500, exactly chance |

Two of the pre-registered falsification conditions fired, so the project stopped rather
than building a hundred-institution panel.

### Three mechanisms behind the failure

1. **The gap is the business model, not the pathology.** Every housing lender shows a
   negative one-year gap because borrowing short against twenty-year mortgages is what
   they do. What killed DHFL was losing the ability to roll the gap, not its existence.
2. **The disclosure is discretionary, and the failures used the discretion to flatter
   themselves.** Reliance Capital placed investments in subsidiaries in the one-month
   bucket and showed already-accelerated debt at its original maturity, producing the best
   cover in its cohort while already in default.
3. **The filing entity is often not the entity at risk.** SREI Infrastructure's standalone
   ladder shows zero advances; Reliance Capital is a holding company.

The shared lesson: accounts disclose what the filer is willing to admit. That is why the
product leans on timeliness, quoted disclosures and arithmetic across filings, and why it
treats reported figures as claims to be checked.

### A design fact worth more than the result

With only two failures against three survivors, the smallest p-value that exhaustive
enumeration could ever produce is 0.100 even with perfect separation. The study could not
have reached conventional significance whatever the data said. This was knowable from the
event count alone before any PDF was downloaded.

---

## 13. Honest limits

- **16 issuers.** India has over 9,000 registered NBFCs.
- **No rating level or history.** NSE's rating endpoint returns nothing. Rating *actions*
  appear only as free text in announcements. This is the largest functional gap.
- **No unlisted entity.** IL&FS Financial Services, which defaulted on commercial paper,
  was never listed and filed nothing to any exchange.
- **XBRL only from about 2019.** Earlier periods would need results PDFs.
- **No general entity resolution** beyond two hand-recorded pairs.
- **Thin asset quality.** Gross NPA exists for only some issuers and none of the failed
  ones; the interface omits an empty column and says so instead of showing placeholders.
- **Some annual dates are estimated.** Flagged "est" in the interface and in the evidence.
- **No predictive claim.** Eight recorded outcomes, four of them failures, in a universe
  chosen knowing how they ended. Demonstrations in the documents are demonstrations, not
  evidence.
- **The tool cannot tell you whether the reported figures are true.**

This is an academic project. It is not investment advice and not a credit rating.

---

## 14. Statistics and research-method terms

- **Look-ahead bias.** Using information in an analysis that was not yet available at the
  date being analysed. Point-in-time discipline exists to remove it.
- **Survivorship bias.** Studying only entities that still exist, which hides the failures.
  The universe deliberately includes four failures.
- **Hindsight bias.** Reading a past file knowing how it ended. The withheld outcome banner
  addresses it.
- **Pre-registration.** Writing down the hypothesis, outcome definitions and success
  criteria before looking at results, so they cannot be edited to fit.
- **Baseline.** A simpler measure the new method must beat to justify its complexity.
- **Censoring.** An observation that has not yet had enough time to show an outcome. It is
  dropped, not counted as a clean negative.
- **AUC (area under the ROC curve).** The probability that a randomly chosen failure is
  ranked riskier than a randomly chosen survivor. 1.0 is perfect separation, 0.5 is chance,
  and below 0.5 is worse than chance.
- **Held-out data.** Data not used to build the model, used to test whether it generalises.
- **Alert rate.** Findings per issuer-year. The tool prints its own noise rate so the analyst
  can judge it.
- **False positive.** An alert on something that was fine. Most of the heuristics in this
  project were tuned after a specific false positive was found, and each is documented at the
  point where it was fixed.

---

## 15. Glossary

| Term | Meaning |
|---|---|
| **As-of date** | The date the interface rebuilds the file for |
| **Basis** | Standalone or consolidated reporting |
| **Counterevidence** | The innocent explanation attached to a finding |
| **Crore / lakh** | 10,000,000 / 100,000 rupees |
| **Dissemination** | The moment a filing reached the exchange and became public |
| **Evidence limit** | A finding about what cannot be known, not about the issuer |
| **Finding** | One alert record with what, why, against, next and evidence |
| **Innocent explanation** | A benign reason a flagged pattern may have occurred |
| **Interned lexicon** | The shared string table that keeps the data export small |
| **`knowable_on`** | When a diligent analyst could first have seen the finding |
| **Period end** | The last day of the period a figure describes |
| **Point-in-time (PIT)** | Using only information public by a given date |
| **Rail** | The left-hand issuer list, ordered as a reading queue |
| **Retrospective key** | Evidence that arrived after the finding's date and is shown later |
| **Run** | A cluster of consecutive payment letters collapsed into one finding |
| **Statement column** | One period's figures from one filing, rendered as a statement |
| **Taxonomy** | The set of tag definitions an XBRL filing uses |
| **YTD** | Year to date: the cumulative figure for the fiscal year so far |

---

## 16. Where to go next

| File | For |
|---|---|
| `README.md` (repository root) | The short pitch, how to run, limits |
| `credit_workbench/USING_THE_WORKBENCH.txt` | How to use the interface, with a worked investigation of Reliance Capital |
| `credit_workbench/ARCHITECTURE.txt` | What the product is, the analyst workflow, the design constraints |
| `credit_workbench/LOW_LEVEL_DESIGN.txt` | Module-by-module implementation detail, every threshold |
| `credit_workbench/PRODUCT.txt` | What is built and not built, alert rates, how to test it with analysts |
| `credit_workbench/ALM_FINDINGS.txt` | The pre-registered negative result |
| `credit_workbench/OUTCOME_DEFINITION.txt` | The pre-registration the result was tested against |
| `credit_workbench/statements/` | Every filed statement as readable text, by issuer and by filing |

Useful commands, from inside `credit_workbench/` (the first three need the raw cache,
which is not in the repository):

```bash
python3 ingest.py               # fetch and cache filings, resumable
python3 attachments.py          # fetch and classify payment PDFs
python3 build.py                # export workbench_data.json
python3 check_pit.py            # point-in-time integrity test, must report 0 violations
python3 brief.py DHFL 2019-05-31   # text brief as it stood on a past date
```
