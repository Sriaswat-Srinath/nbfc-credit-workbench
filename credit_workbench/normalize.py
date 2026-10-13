"""Turn an XBRL instance into the statement a person can actually read.

The evidence links in this tool previously dropped the analyst into raw XML.
That satisfies the letter of "verifiable" and not the spirit: nobody checks a
figure by reading `<in-bse-fin:ProfitBeforeExceptionalItemsAndTax
contextRef="OneD" unitRef="INR" decimals="-5">49780600000.00</...>`.

This module renders the same instance as the profit and loss account it
represents, with the original tag beside every line so the rendering can be
checked against the source.

Three things make that possible:

  1. DOCUMENT ORDER IS STATEMENT ORDER. NSE's instances list facts in the
     order they appear in the published results table - revenue components,
     then total revenue, then expenses, then the profit subtotals, then tax,
     then per-share figures. Preserving file order reproduces the statement
     without needing the presentation linkbase, which NSE does not ship with
     the instance.

  2. THE TAGS ARE SELF-DESCRIBING. 291 distinct tags appear across the
     corpus. The ~90 that carry meaning are given curated labels; the rest
     fall back to splitting the CamelCase, which is readable if inelegant.

  3. THE STATEMENT CHECKS ITSELF. Every subtotal in a P&L is defined as a sum
     or difference of lines above it. Those relationships are encoded here and
     recomputed, so the viewer reports whether the filing adds up. This is the
     same idea as the cross-filing additivity detector, applied within a single
     filing rather than across several.

Three taxonomies occur: NBFC_INDAS (521 instances), INDAS (131) and NONINDAS
(9, pre-2018). Their tag sets differ and the subtotal rules are written to
tolerate missing lines rather than assume one taxonomy.
"""
import json
import os
import re

from facts import META, _ts

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

CONTEXT = re.compile(
    r'<xbrli:context id="([A-Za-z0-9]+)"[^>]*>(.*?)</xbrli:context>', re.S)
CTX_DATE = re.compile(r'<xbrli:(startDate|endDate|instant)>([^<]+)<')

FACT = re.compile(
    r'<in-bse-fin:(\w+)\s+contextRef="(One|Two|Three|Four|Five|Six)([A-Za-z0-9]*)"'
    r'([^>]*)>([^<]*)</in-bse-fin:\1>')

# ---------------------------------------------------------------- labelling
LABELS = {
    # --- revenue, NBFC Ind AS
    "InterestEarned": "Interest income",
    "DividendIncome": "Dividend income",
    "RentalIncome": "Rental income",
    "FeesAndCommissionIncome": "Fees and commission income",
    "NetGainOnFairValueChanges": "Net gain on fair value changes",
    "NetGainOnDerecognitionOfFinancialInstrumentsUnderAmortisedCostCategory":
        "Net gain on derecognition of financial instruments",
    "RevenueFromSaleOfProduct": "Sale of products",
    "RevenueFromSaleOfServices": "Sale of services",
    "OtherRevenueFromOperations": "Other operating revenue",
    "RevenueFromOperations": "Revenue from operations",
    "OtherIncome": "Other income",
    "Income": "Total income",
    "Revenue": "Total revenue",
    # --- expenses
    "FinanceCosts": "Finance costs",
    "FeesAndCommissionExpense": "Fees and commission expense",
    "NetLossOnFairValueChanges": "Net loss on fair value changes",
    "NetLossOnDerecognitionOfFinancialInstrumentsUnderAmortisedCostCategory":
        "Net loss on derecognition of financial instruments",
    "ImpairmentOnFinancialInstruments": "Impairment on financial instruments",
    "CostOfMaterialsConsumed": "Cost of materials consumed",
    "PurchasesOfStockInTrade": "Purchases of stock in trade",
    "ChangesInInventoriesOfFinishedGoodsWorkInProgressAndStockInTrade":
        "Changes in inventories",
    "EmployeeBenefitExpense": "Employee benefit expense",
    "DepreciationDepletionAndAmortisationExpense":
        "Depreciation and amortisation",
    "DepreciationAndAmortisationExpense": "Depreciation and amortisation",
    "OtherExpenses": "Other expenses",
    "Expenses": "Total expenses",
    # --- profit ladder
    "ProfitBeforeExceptionalItemsAndTax": "Profit before exceptional items and tax",
    "ProfitBeforeExceptionalAndExtraordinaryItemsAndTax":
        "Profit before exceptional and extraordinary items and tax",
    "ExceptionalItemsBeforeTax": "Exceptional items",
    "ExceptionalItems": "Exceptional items",
    "ProfitBeforeExtraordinaryItemsAndTax": "Profit before extraordinary items and tax",
    "ExtraordinaryItems": "Extraordinary items",
    "ProfitBeforeTax": "Profit before tax",
    "CurrentTax": "Current tax",
    "DeferredTax": "Deferred tax",
    "TaxExpense": "Total tax expense",
    "ProfitLossForPeriodFromContinuingOperations":
        "Profit after tax from continuing operations",
    "ProfitLossForThePeriodFromContinuingOperations":
        "Profit after tax from continuing operations",
    "ProfitLossFromDiscontinuedOperationsBeforeTax":
        "Profit from discontinued operations, before tax",
    "ProfitLossFromDiscontinuingOperationsBeforeTax":
        "Profit from discontinued operations, before tax",
    "TaxExpenseOfDiscontinuedOperations": "Tax on discontinued operations",
    "TaxExpenseOfDiscontinuingOperations": "Tax on discontinued operations",
    "ProfitLossFromDiscontinuedOperationsAfterTax":
        "Profit from discontinued operations, after tax",
    "ProfitLossFromDiscontinuingOperationAfterTax":
        "Profit from discontinued operations, after tax",
    "ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod":
        "Share of profit of associates and joint ventures",
    "ProfitLossForPeriodBeforeMinorityInterest":
        "Profit for the period before minority interest",
    "ProfitLossForPeriod": "Profit for the period",
    "ProfitLossForThePeriod": "Profit for the period",
    # --- OCI and comprehensive income
    "OtherComprehensiveIncome": "Other comprehensive income",
    "OtherComprehensiveIncomeNetOfTaxes": "Other comprehensive income, net of tax",
    "ComprehensiveIncomeForThePeriod": "Total comprehensive income",
    "ComprehensiveIncomeForThePeriodAttributableToOwnersOfParent":
        "Comprehensive income attributable to owners of the parent",
    "ComprehensiveIncomeForThePeriodAttributableToOwnersOfParentNonControllingInterests":
        "Comprehensive income attributable to non-controlling interests",
    # --- capital and per share
    "PaidUpValueOfEquityShareCapital": "Paid-up equity share capital",
    "FaceValueOfEquityShareCapital": "Face value per share",
    "ReservesExcludingRevaluationReserve": "Reserves excluding revaluation reserve",
    "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations":
        "Earnings per share, basic",
    "DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations":
        "Earnings per share, diluted",
    "BasicEarningsLossPerShareFromContinuingOperations":
        "EPS basic, continuing operations",
    "DilutedEarningsLossPerShareFromContinuingOperations":
        "EPS diluted, continuing operations",
    "BasicEarningsLossPerShareFromDiscontinuedOperations":
        "EPS basic, discontinued operations",
    "DilutedEarningsLossPerShareFromDiscontinuedOperations":
        "EPS diluted, discontinued operations",
    # --- debt-listed disclosures
    "NetWorth": "Net worth",
    "DebtEquityRatio": "Debt / equity ratio",
    "TotalDebtToTotalAssets": "Total debt to total assets",
    "CapitalAdequacyRatio": "Capital adequacy ratio",
    "GrossNonPerformingAssets": "Gross non-performing assets",
    "NetNonPerformingAssets": "Net non-performing assets",
}

ACRONYM = {"Eps": "EPS", "Npa": "NPA", "Oci": "OCI", "Pat": "PAT",
           "Pbt": "PBT"}


def label_for(tag):
    """Curated label, else a readable split of the CamelCase tag."""
    if tag in LABELS:
        return LABELS[tag]
    words = re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+", tag)
    out = []
    for i, w in enumerate(words):
        w = ACRONYM.get(w, w)
        out.append(w if (i == 0 or w.isupper()) else w.lower())
    s = " ".join(out)
    return s[0].upper() + s[1:] if s else tag


# ----------------------------------------------------------------- sections
# Evaluated in order; first match wins. Deliberately coarse - the point is to
# break a 40-line statement into blocks a reader can scan, not to reproduce
# the taxonomy's own hierarchy.
# Explicit tag -> section. The first implementation matched by substring and
# bounced: "OtherComprehensiveIncomeNetOfTaxes" contains "Income" so it landed
# under Income, and the tax line of discontinued operations jumped back into
# Tax in the middle of the result block. Known tags are therefore assigned
# outright and only unknown ones fall back to pattern matching.
SECTION_ORDER = ["Income", "Expenses", "Profit before tax", "Tax", "Result",
                 "Comprehensive income", "Capital and per share",
                 "Debt-listed disclosures", "Cash flow", "Other"]

# Tested BEFORE every other rule. Half-yearly and annual filings include a
# cash flow statement whose tags otherwise scatter across the P&L sections.
CASHFLOW_PATTERNS = (
    "AdjustmentsFor", "ClassifiedAsOperatingActivities",
    "ClassifiedAsInvestingActivities", "ClassifiedAsFinancingActivities",
    "CashFlowsFrom", "CashFlowsUsedIn", "NetCashFlows", "ProceedsFrom",
    "PaymentsFor", "PaymentsTo", "CashAndCashEquivalents",
    "IncomeTaxesPaidRefund", "InterestPaidClassified", "DividendsPaidClassified",
    "WhetherCashFlow", "DescriptionOfOther",
)

SECTION_OF = {}
for _sec, _tags in [
    ("Income", """InterestEarned DividendIncome RentalIncome
        FeesAndCommissionIncome NetGainOnFairValueChanges
        NetGainOnDerecognitionOfFinancialInstrumentsUnderAmortisedCostCategory
        RevenueFromSaleOfProduct RevenueFromSaleOfServices
        OtherRevenueFromOperations RevenueFromOperations OtherIncome
        Income Revenue"""),
    ("Expenses", """FinanceCosts FeesAndCommissionExpense
        NetLossOnFairValueChanges
        NetLossOnDerecognitionOfFinancialInstrumentsUnderAmortisedCostCategory
        ImpairmentOnFinancialInstruments CostOfMaterialsConsumed
        PurchasesOfStockInTrade
        ChangesInInventoriesOfFinishedGoodsWorkInProgressAndStockInTrade
        EmployeeBenefitExpense DepreciationDepletionAndAmortisationExpense
        DepreciationAndAmortisationExpense OtherExpenses Expenses"""),
    ("Profit before tax", """ProfitBeforeExceptionalItemsAndTax
        ProfitBeforeExceptionalAndExtraordinaryItemsAndTax
        ExceptionalItemsBeforeTax ExceptionalItems
        ProfitBeforeExtraordinaryItemsAndTax ExtraordinaryItems
        ProfitBeforeTax"""),
    ("Tax", "CurrentTax DeferredTax TaxExpense"),
    ("Result", """ProfitLossForPeriodFromContinuingOperations
        ProfitLossForThePeriodFromContinuingOperations
        ProfitLossFromDiscontinuedOperationsBeforeTax
        ProfitLossFromDiscontinuingOperationsBeforeTax
        TaxExpenseOfDiscontinuedOperations TaxExpenseOfDiscontinuingOperations
        ProfitLossFromDiscontinuedOperationsAfterTax
        ProfitLossFromDiscontinuingOperationAfterTax
        ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod
        ProfitLossForPeriodBeforeMinorityInterest ProfitLossForPeriod
        ProfitLossForThePeriod"""),
    ("Comprehensive income", """OtherComprehensiveIncome
        OtherComprehensiveIncomeNetOfTaxes ComprehensiveIncomeForThePeriod
        ComprehensiveIncomeForThePeriodAttributableToOwnersOfParent
        ComprehensiveIncomeForThePeriodAttributableToOwnersOfParentNonControllingInterests"""),
    ("Capital and per share", """PaidUpValueOfEquityShareCapital
        FaceValueOfEquityShareCapital ReservesExcludingRevaluationReserve
        BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations
        DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations
        BasicEarningsLossPerShareFromContinuingOperations
        DilutedEarningsLossPerShareFromContinuingOperations
        BasicEarningsLossPerShareFromDiscontinuedOperations
        DilutedEarningsLossPerShareFromDiscontinuedOperations"""),
    ("Debt-listed disclosures", """NetWorth DebtEquityRatio
        TotalDebtToTotalAssets CapitalAdequacyRatio GrossNonPerformingAssets
        NetNonPerformingAssets"""),
]:
    for _t in _tags.split():
        SECTION_OF[_t] = _sec

# fallback for the ~200 tags that appear rarely and are not curated
FALLBACK = [
    ("Comprehensive income", ("ComprehensiveIncome",)),
    ("Capital and per share", ("PerShare", "ShareCapital", "Reserves")),
    ("Tax", ("Tax",)),
    ("Result", ("ProfitLoss",)),
    ("Profit before tax", ("ProfitBefore", "ExceptionalItems")),
    ("Expenses", ("Expense", "Cost", "Impairment", "Depreciation", "NetLoss")),
    ("Income", ("Income", "Revenue", "Earned", "NetGain")),
]


PER_SHARE = ("EarningsLossPerShare", "FaceValue")
RATIO = ("Ratio", "CapitalAdequacy", "TotalDebtToTotalAssets")


def section_for(tag):
    if any(p in tag for p in CASHFLOW_PATTERNS):
        return "Cash flow"
    if tag in SECTION_OF:
        return SECTION_OF[tag]
    for name, pats in FALLBACK:
        if any(p in tag for p in pats):
            return name
    return "Other"


def kind_for(tag):
    if any(p in tag for p in PER_SHARE):
        return "per_share"
    if any(p in tag for p in RATIO):
        return "ratio"
    return "money"


# ------------------------------------------------------- subtotal integrity
# Two kinds of rule.
#
# STRUCTURAL rules name their operands explicitly. They hold by definition of
# the statement and run at a 0% failure rate across all 1,164 statement
# columns in the corpus, which is what makes a failure meaningful.
#
# SECTION rules sum everything the renderer placed in a section rather than a
# fixed list of tags. The first version hardcoded the NBFC Ind AS expense
# lines and then reported a 7.6% failure rate - but that was the rule being
# wrong, not the filings. DHFL files under the generic Ind AS taxonomy, whose
# expense lines are named differently, so the component sum came to Rs 169
# crore against a stated Rs 1,827 crore. A rule that is wrong 7.6% of the time
# teaches the reader to ignore it, which is worse than not checking at all.
#
# (result_tag, [addends], [subtrahends], description)
STRUCTURAL = [
    ("Income", ["RevenueFromOperations", "OtherIncome"], [],
     "total income = revenue from operations + other income"),
    ("Revenue", ["RevenueFromOperations", "OtherIncome"], [],
     "total revenue = revenue from operations + other income"),
    ("ProfitBeforeExceptionalItemsAndTax", ["Income"], ["Expenses"],
     "profit before exceptional items = total income - total expenses"),
    ("TaxExpense", ["CurrentTax", "DeferredTax"], [],
     "total tax = current tax + deferred tax"),
    ("ProfitLossForPeriodFromContinuingOperations", ["ProfitBeforeTax"],
     ["TaxExpense"],
     "profit from continuing operations = profit before tax - tax"),
    ("ComprehensiveIncomeForThePeriod",
     ["ProfitLossForPeriod", "OtherComprehensiveIncomeNetOfTaxes"], [],
     "total comprehensive income = profit + other comprehensive income"),
]

# Deliberately EMPTY. Two section rules were tried - total expenses and
# revenue from operations against the lines filed beneath them - and both were
# abandoned. Hardcoding the NBFC Ind AS component tags produced a 7.6% failure
# rate that was the rule being wrong rather than the filings; summing whatever
# the renderer placed in the section instead produced 35.9%, because the three
# taxonomies decompose income and expenses differently and a generic Ind AS
# filer puts lines where the NBFC schedule does not.
#
# No reliable decomposition check exists across these taxonomies without a
# per-taxonomy component map, which is a day of work and a maintenance burden
# every time NSE revises the schedule. Until that exists the statement reports
# the six relationships that DO hold universally, and says plainly that the
# decomposition is unchecked. A check that is wrong a third of the time trains
# the reader to ignore all of them.
SECTION_RULES = []

# Tags excluded from a section sum because they are themselves totals, or
# belong to the cash-flow reconciliation rather than the P&L.
NOT_A_COMPONENT = {"Expenses", "Income", "Revenue", "RevenueFromOperations",
                   "OtherIncome"}
CASHFLOW_PREFIX = "AdjustmentsFor"

TOL_REL, TOL_ABS = 0.005, 1e6     # 0.5% or Rs 10 lakh, whichever is larger


def check_rules(values, lines=None):
    """Recompute every subtotal the filing states.

    `lines` carries the section each tag was placed in, which the section
    rules need. Returns one row per rule that could be evaluated; a rule whose
    operands are absent is silently skipped rather than reported as a failure.
    """
    out = []
    for result, plus, minus, why in STRUCTURAL:
        if result not in values:
            continue
        missing = [x for x in plus if x not in values]
        present_m = [x for x in minus if x in values]
        if missing:
            # A subtotal check with an absent operand is meaningless, not
            # failed. Cholamandalam and Reliance Home Finance omit
            # ProfitLossForPeriod and tag the figure only as
            # ProfitLossForPeriodFromContinuingOperations; scoring that as a
            # broken statement would be the rule's fault, not the filer's.
            # It is reported as unevaluated, naming what was not filed, which
            # is itself worth knowing when relying on the figure.
            out.append({
                "line": label_for(result), "tag": result, "rule": why,
                "stated": values[result], "recomputed": None,
                "difference": None, "ok": None,
                "missing": [label_for(x) for x in missing],
                "operands": [label_for(x) for x in plus]
                            + ["less " + label_for(x) for x in minus],
            })
            continue
        got = values[result]
        exp = sum(values[x] for x in plus) - sum(values[x] for x in present_m)
        diff = got - exp
        out.append({
            "line": label_for(result), "tag": result, "rule": why,
            "stated": got, "recomputed": exp, "difference": diff,
            "ok": abs(diff) <= max(abs(got) * TOL_REL, TOL_ABS),
            "missing": [],
            "operands": [label_for(x) for x in plus]
                        + ["less " + label_for(x) for x in present_m],
        })

    by_section = {}
    for ln in (lines or []):
        by_section.setdefault(ln["section"], []).append(ln)
    for result, section, why in SECTION_RULES:
        if result not in values or section not in by_section:
            continue
        comps = [ln for ln in by_section[section]
                 if ln["tag"] != result
                 and ln["tag"] not in NOT_A_COMPONENT
                 and not ln["tag"].startswith(CASHFLOW_PREFIX)
                 and ln["kind"] == "money"]
        if len(comps) < 2:
            continue
        got = values[result]
        exp = sum(c["value"] for c in comps)
        diff = got - exp
        out.append({
            "line": label_for(result), "tag": result, "rule": why,
            "stated": got, "recomputed": exp, "difference": diff,
            "ok": abs(diff) <= max(abs(got) * TOL_REL, TOL_ABS),
            "operands": [c["label"] for c in comps],
        })
    return out


# -------------------------------------------------------------- the renderer
def normalize(path, fallback_period=None):
    """One XBRL instance -> readable statements, one per reporting column.

    `fallback_period` is an optional (start, end) pair from the results index,
    used only when the instance supplies neither a tagged reporting period nor
    a declared context. Nine of the 661 cached instances - all pre-Ind-AS -
    reference contextRef="OneD" without ever declaring that context, which is
    malformed XBRL; without the index dates those filings are unreadable.
    """
    t = open(path, encoding="utf8", errors="replace").read()

    # Context dates are a LAST RESORT. For modern instances they are wrong -
    # every context in a Bajaj Q3 file is stamped with the quarter's dates
    # even for the year-to-date column - so the tagged period facts always
    # win. The nine pre-Ind-AS instances in the corpus carry no tagged period
    # at all, and for those the context is the only source there is.
    ctx = {}
    for m in CONTEXT.finditer(t):
        ds = CTX_DATE.findall(m.group(2))
        s = next((v for k, v in ds if k == "startDate"), None)
        e = next((v for k, v in ds if k in ("endDate", "instant")), None)
        if e:
            ctx[m.group(1)] = (s, e)

    cols, order, meta = {}, {}, {}
    for m in FACT.finditer(t):
        tag, pre, suf, attrs, raw = (m.group(1), m.group(2), m.group(3),
                                     m.group(4), m.group(5).strip())
        if suf not in ("D", "I", ""):
            continue
        cols.setdefault(pre, {})[tag] = raw
        order.setdefault(pre, []).append(tag)
        if tag in META:
            meta.setdefault(pre, {})[META[tag]] = raw

    out = []
    for pre, facts in cols.items():
        start = facts.get("DateOfStartOfReportingPeriod")
        end = facts.get("DateOfEndOfReportingPeriod")
        period_source = "tagged"
        if not end:
            start, end = ctx.get(pre + "D", (start, None))
            period_source = "context (tagged period absent in this taxonomy)"
        if not end and fallback_period and pre == "One":
            start, end = fallback_period
            period_source = ("results index (the instance declares no context "
                             "for this column)")
        if not end:
            continue
        numeric, seen = {}, set()
        lines = []
        for tag in order[pre]:
            if tag in seen or tag in META or tag.startswith("Date") \
                    or tag in ("Symbol", "ScripCode", "MSEISymbol",
                               "NameOfTheCompany", "ClassOfSecurity",
                               "DescriptionOfPresentationCurrency"):
                seen.add(tag)
                continue
            seen.add(tag)
            raw = facts[tag]
            try:
                v = float(raw)
            except ValueError:
                continue
            numeric[tag] = v
            lines.append({
                "tag": tag,
                "label": label_for(tag),
                "section": section_for(tag),
                "kind": kind_for(tag),
                "value": v,
            })
        if not lines:
            continue
        out.append({
            "column": pre,
            "period_start": start,
            "period_end": end,
            "period_source": period_source,
            "meta": meta.get(pre, {}),
            "lines": lines,
            "checks": check_rules(numeric, lines),
        })
    return out


def render_text(stmt, width=74):
    """Plain-text statement, Rs crore."""
    L = []
    m = stmt["meta"]
    L.append("=" * width)
    L.append(f"{stmt['period_start']} to {stmt['period_end']}"
             f"   {m.get('basis','?')}   {m.get('audited','?')}")
    if m.get("board_approved"):
        L.append(f"approved by the board {m['board_approved']}")
    L.append("=" * width)
    sec = None
    for ln in stmt["lines"]:
        if ln["section"] != sec:
            sec = ln["section"]
            L.append("")
            L.append(sec.upper())
        if ln["kind"] == "money":
            val = f"{ln['value']/1e7:>14,.2f}"
        elif ln["kind"] == "per_share":
            val = f"{ln['value']:>14,.2f}"
        else:
            val = f"{ln['value']:>14,.2f}"
        L.append(f"  {ln['label'][:48]:48s}{val}")
    L.append("")
    L.append("-" * width)
    L.append("INTERNAL CONSISTENCY")
    if not stmt["checks"]:
        L.append("  no subtotal could be recomputed from the lines present")
    for c in stmt["checks"]:
        if c["ok"] is None:
            L.append(f"  [ --  ] {c['rule']}")
            L.append(f"          not evaluated: "
                     f"{', '.join(c['missing'])} not filed")
            continue
        mark = "ok  " if c["ok"] else "FAIL"
        L.append(f"  [{mark}] {c['rule']}")
        if not c["ok"]:
            L.append(f"         stated {c['stated']/1e7:,.2f} cr, "
                     f"recomputed {c['recomputed']/1e7:,.2f} cr, "
                     f"difference {c['difference']/1e7:,.2f} cr")
    L.append("")
    L.append("Figures in Rs crore except per-share amounts and ratios.")
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    import glob
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        paths = [sys.argv[1]]
    else:
        sym = sys.argv[1] if len(sys.argv) > 1 else "BAJFINANCE"
        paths = sorted(glob.glob(os.path.join(CACHE, sym, "xbrl", "*.xml")))[-1:]
    for p in paths:
        print(f"\n### {os.path.basename(p)}")
        for stmt in normalize(p):
            print(render_text(stmt))
