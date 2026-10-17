# NBFC Credit Workbench

An evidence-first monitoring tool for Indian non-bank lenders (NBFCs and
housing finance companies), built on NSE primary filings.

It is **not** a default-prediction model. That framing was tested and
abandoned — see `credit_workbench/ALM_FINDINGS.txt` for the negative result
that led here. The workbench helps a credit analyst discover, verify and
investigate emerging risk, and leaves the judgement to them.

## What it does

Tracks 16 issuers across three primary sources, all carrying real exchange
dissemination timestamps:

- **25,919 corporate announcements** (2004 onwards), categorised, with links
  to the original PDFs
- **661 XBRL instances** behind every quarterly result filing — tagged, so no
  PDF parsing
- **2,450 announcement attachments** fetched and classified, because the
  announcement *title* is identical whether a company paid its debenture
  interest or did not

From these it raises **253 findings** across thirteen detectors, each stating
what changed, why it may matter, **the innocent explanation**, the source
document, and what to check next.

## The two things that are actually differentiated

**Point-in-time replay.** Every figure and finding is stamped with when it
reached the exchange, never the period it describes. A date control rebuilds
the entire file as it read on any past date — so you can ask what your own
process should have caught, rather than reading today's file and concluding a
failure was obvious. `check_pit.py` enforces this and has caught three real
look-ahead leaks in this codebase.

**Contradiction by arithmetic.** Year-to-date figures must equal the sum of
their quarters. Where they do not, something was restated after it was first
published. The tool does that arithmetic across filings and names the likely
innocent cause.

## Running it

```bash
python3 -m http.server 8777 --directory credit_workbench
# then http://localhost:8777/workbench.html
```

`file://` will not work — the data loads as a sibling script.

To rebuild from source, see `credit_workbench/USING_THE_WORKBENCH.txt` §9.
The NSE cache is not in this repository (902 MB); `ingest.py` and
`attachments.py` rebuild it.

## Sources

Five NSE endpoints and one local file. Nothing else feeds the workbench.

| Source | Supplies |
|---|---|
| NSE `corporate-announcements` | the disclosure timeline, rating actions, clarification requests |
| NSE XBRL instances | quarterly P&L, reporting basis, audit flags, the filed statements |
| NSE `corporates-financial-results` | the filing index — dissemination timestamps and flags |
| NSE announcement attachments | payment-disclosure classification, read from the PDFs |
| NSE `annual-reports` | publication timestamps for the annual layer |
| `credit_workbench/data/panel.csv` | the annual balance sheet |

`panel.csv` is the only input not from NSE. It derives from a supplied
financials dataset, which is why DHFL has no Capital & leverage view and gross
NPA exists for only 6 of 15 issuers.

## Documentation

| File | For |
|---|---|
| `credit_workbench/CONCEPTS.md` | start here: every concept explained, from the finance background to the detectors |
| `credit_workbench/USING_THE_WORKBENCH.txt` | how to use it, with a worked investigation |
| `credit_workbench/ARCHITECTURE.txt` | what it is, the workflow, and the design constraints |
| `credit_workbench/LOW_LEVEL_DESIGN.txt` | implementation detail, every detector and threshold |
| `credit_workbench/PRODUCT.txt` | what is built, what is not, alert rates, and the limits |
| `credit_workbench/ALM_FINDINGS.txt` | the pre-registered negative result that led here |
| `credit_workbench/OUTCOME_DEFINITION.txt` | the pre-registration it was tested against |

## Honest limits

- 16 issuers. India has over 9,000 registered NBFCs.
- No rating level or history — NSE's rating endpoint returns nothing.
- No unlisted entity. IL&FS Financial Services, which defaulted on the
  commercial paper, filed nothing to any exchange.
- Structured quarterly results exist only from about 2019.
- No entity resolution beyond two hand-recorded parent/subsidiary pairs. This
  is the largest structural gap.
- Nothing here establishes predictive value. Eight recorded outcomes, four of
  them real, in a universe chosen knowing how they ended.

Academic project. Not investment advice and not a credit rating.
