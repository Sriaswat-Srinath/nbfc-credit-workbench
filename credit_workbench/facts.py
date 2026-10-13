"""Parse cached XBRL instances into a tidy, provenance-carrying fact table.

One row per (symbol, period, basis, metric). Each row records the filing that
produced it and when that filing was disseminated, which is what makes
point-in-time questions answerable: not "what was the Q3 figure" but "what was
the Q3 figure *as it was reported on the day it became public*".

NSE's instances put several columns in one file - the quarter, the year to
date, sometimes the prior-year comparatives - distinguished by context prefix
(One, Two, Three, Four, Five, Six). The xbrli:context dates are unreliable
(every context in a Bajaj Q3 file is stamped with the quarter's dates even for
the year-to-date column), so the period is taken from the tagged
DateOfStartOfReportingPeriod / DateOfEndOfReportingPeriod facts belonging to
each prefix, which are correct.
"""
import json
import os
import re
import datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
PREFIX = ("One", "Two", "Three", "Four", "Five", "Six")

FACT = re.compile(
    r'<in-bse-fin:(\w+)\s+contextRef="(One|Two|Three|Four|Five|Six)([A-Za-z0-9]*)"'
    r'[^>]*>([^<]*)</in-bse-fin:\1>')

# the metrics the product actually uses, with the label an analyst recognises
METRICS = {
    "InterestEarned": "Interest income",
    "RevenueFromOperations": "Revenue from operations",
    "OtherIncome": "Other income",
    "Income": "Total income",
    "FinanceCost": "Finance cost",
    "EmployeeBenefitExpense": "Employee cost",
    "ImpairmentOnFinancialInstruments": "Impairment / credit cost",
    "ProvisionsOtherThanTaxExpenseAndContingencies": "Provisions & contingencies",
    "Expenses": "Total expenses",
    "ProfitBeforeExceptionalItemsAndTax": "PBT before exceptional items",
    "ProfitBeforeTax": "Profit before tax",
    "TaxExpense": "Tax expense",
    "ProfitLossForPeriod": "Profit after tax",
    "ComprehensiveIncomeForThePeriod": "Total comprehensive income",
    "PaidUpValueOfEquityShareCapital": "Paid-up equity capital",
    "ReservesExcludingRevaluationReserve": "Reserves",
    "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations": "EPS (basic)",
    "NetWorth": "Net worth",
    "DebtEquityRatio": "Debt / equity",
    "TotalDebtToTotalAssets": "Total debt / total assets",
    "GrossNonPerformingAssets": "Gross NPA",
    "NetNonPerformingAssets": "Net NPA",
    "CapitalAdequacyRatio": "Capital adequacy ratio",
}

META = {
    "NatureOfReportStandaloneConsolidated": "basis",
    "WhetherResultsAreAuditedOrUnaudited": "audited",
    "DateOfBoardMeetingWhenFinancialResultsWereApproved": "board_approved",
    "DeclarationOfUnmodifiedOpinionOrStatementOnImpactOfAuditQualification":
        "audit_opinion",
    "ReportingQuarter": "quarter_label",
    "LevelOfRoundingUsedInFinancialStatements": "rounding",
    "NameOfTheCompany": "company",
    "DateOfStartOfFinancialYear": "fy_start",
    "DateOfEndOfFinancialYear": "fy_end",
}


def parse_instance(path):
    """-> list of column records, each with its own period and metric dict."""
    t = open(path, encoding="utf8", errors="replace").read()
    byctx = {}
    for m in FACT.finditer(t):
        tag, pre, suf, val = m.group(1), m.group(2), m.group(3), m.group(4)
        if suf not in ("D", "I", ""):      # skip dimensional breakdowns
            continue
        byctx.setdefault(pre, {})[tag] = val.strip()

    out = []
    for pre, facts in byctx.items():
        start = facts.get("DateOfStartOfReportingPeriod")
        end = facts.get("DateOfEndOfReportingPeriod")
        if not end:
            continue
        rec = {"column": pre, "period_start": start, "period_end": end,
               "metrics": {}, "meta": {}}
        for tag, label in META.items():
            if tag in facts:
                rec["meta"][label] = facts[tag]
        for tag, label in METRICS.items():
            if tag in facts:
                try:
                    rec["metrics"][label] = float(facts[tag])
                except ValueError:
                    pass
        if rec["metrics"]:
            out.append(rec)
    return out


def _ts(s):
    for f in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
        try:
            return dt.datetime.strptime(s, f)
        except (ValueError, TypeError):
            pass
    return None


def load_symbol(sym):
    """Join the results index to the parsed instances, so every figure knows
    the timestamp at which it became public."""
    d = os.path.join(CACHE, sym)
    try:
        index = json.load(open(os.path.join(d, "results.json")))
    except Exception:
        return []
    byfile = {}
    for row in index:
        u = (row.get("xbrl") or "").strip()
        if u.lower().endswith(".xml"):
            byfile[os.path.basename(u)] = row

    filings = []
    xd = os.path.join(d, "xbrl")
    for fn in sorted(os.listdir(xd)) if os.path.isdir(xd) else []:
        row = byfile.get(fn)
        if not row:
            continue
        try:
            cols = parse_instance(os.path.join(xd, fn))
        except Exception:
            continue
        if not cols:
            continue
        disseminated = _ts(row.get("broadCastDate")) or _ts(row.get("filingDate"))
        meta = cols[0]["meta"]
        filings.append({
            "symbol": sym,
            "file": fn,
            "xbrl_url": row.get("xbrl"),
            "disseminated": disseminated.isoformat() if disseminated else None,
            "filing_date_raw": row.get("filingDate"),
            "basis": ("Consolidated"
                      if (row.get("consolidated") == "Consolidated"
                          or meta.get("basis") == "Consolidated")
                      else "Standalone"),
            "audited": row.get("audited") or meta.get("audited"),
            "board_approved": meta.get("board_approved"),
            "audit_opinion": meta.get("audit_opinion"),
            "rounding": meta.get("rounding"),
            "relating_to": row.get("relatingTo"),
            "index_from": row.get("fromDate"),
            "index_to": row.get("toDate"),
            "columns": cols,
        })
    filings.sort(key=lambda f: f["disseminated"] or "")
    return filings


if __name__ == "__main__":
    import sys
    from universe import ISSUERS
    syms = [sys.argv[1]] if len(sys.argv) > 1 else [i[0] for i in ISSUERS]
    for s in syms:
        fl = load_symbol(s)
        if not fl:
            print(f"{s:12s} nothing parsed")
            continue
        ncol = sum(len(f["columns"]) for f in fl)
        mets = set()
        for f in fl:
            for c in f["columns"]:
                mets |= set(c["metrics"])
        print(f"{s:12s} {len(fl):3d} filings  {ncol:4d} columns  "
              f"{len(mets):2d} metrics  "
              f"{fl[0]['disseminated'][:10] if fl[0]['disseminated'] else '?'}"
              f" .. {fl[-1]['disseminated'][:10] if fl[-1]['disseminated'] else '?'}")
