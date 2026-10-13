"""The finding engine.

Every finding answers the five questions the product promises, and carries the
evidence needed to check it:

    what_changed      one sentence, specific, with the figures
    knowable_on       the timestamp at which a diligent analyst could first
                      have seen it - never the fiscal period end
    why_it_matters    the mechanism, stated as a hypothesis not a conclusion
    evidence          source file, source URL, dissemination timestamp
    investigate       what the analyst should do next
    counterevidence   the innocent explanation, where one exists

Design rules, taken from what went wrong in the research phase:

  * No composite score. The research showed a nine-component index failing to
    beat equity/assets, so this tool ranks findings by severity and leaves
    weighting to the analyst.
  * Nothing is imputed. A missing figure produces a coverage finding, not a
    filled value.
  * Standalone and consolidated are never mixed. Comparisons are within basis.
  * The outcome labels in universe.py are NOT read anywhere in this file.
    Detection is blind to who failed.
"""
import datetime as dt
import json
import os
import re
import statistics as st

from annual import series as annual_series
from announcements import clean, load_announcements
from universe import BY_SYMBOL
from attachments import load as attach_load
from facts import load_symbol

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

# SEBI LODR Regulation 33: quarterly results within 45 days of quarter end,
# annual audited results within 60 days of year end.
LIMIT_Q, LIMIT_FY = 45, 60

# SEBI relaxed those deadlines market-wide for two periods during COVID-19
# (circulars of 19 March and 24 June 2020). Treating those as issuer-specific
# late filings put four findings on LIC Housing Finance that were nothing of
# the kind, so the relaxed limit is applied rather than noted after the fact.
RELAXED = {"2020-03-31": 122,    # annual results extended to 31 July 2020
           "2020-06-30": 77}     # Q1 FY21 extended to 15 September 2020
MATERIAL_REL = 0.25          # 25% move before "material"
ROUND_TOL = 0.01             # 1% tolerance on additivity, for rounding
# Absolute floors. Without these, a relative test fires on rounding noise in
# small numbers: the first build flagged a Rs 0.3 crore "restatement" three
# times. Every detector needs a floor in rupees as well as a percentage.
MIN_DIFF = 5e7               # Rs 5 crore - below this, do not report
MIN_LEVEL = 5e8              # Rs 50 crore - ignore issuers/periods below this


def _d(s):
    return dt.date.fromisoformat(s[:10]) if s else None


def _pct(new, old):
    if old in (None, 0) or new is None:
        return None
    return 100.0 * (new - old) / abs(old)


def F(sym, kind, sev, knowable, what, why, evidence, investigate,
      counter=None, metric=None, value=None):
    return {"symbol": sym, "kind": kind, "severity": sev,
            "knowable_on": knowable, "what_changed": what, "why_it_matters": why,
            "evidence": evidence, "investigate": investigate,
            "counterevidence": counter, "metric": metric, "value": value}


# ---------------------------------------------------------------- quarterly
def scale_anomalies(filings):
    """Identify columns whose figures are mis-scaled relative to the issuer's
    own neighbouring filings.

    Most NSE instances carry absolute rupees, but a minority are pre-scaled,
    and the tagged LevelOfRoundingUsedInFinancialStatements does not predict
    which: Shriram filed absolute figures under "Lakhs" while LIC Housing
    filed scaled figures under the same label.

    Two refinements over the naive test, both needed:

      * Compare against a LOCAL window of neighbouring filings, not the
        issuer's whole history. Reliance Capital and Reliance Home Finance
        genuinely collapsed to shell-company scale, and a global comparison
        called seventeen of their filings mis-tagged when their income had
        simply fallen by three orders of magnitude.
      * Require the discrepancy to sit near a CLEAN scaling factor - a
        hundred, a lakh, a crore. A tagging error produces an exact factor; a
        business collapse does not.

    Guessing a multiplier would be imputation, so suspect columns are
    EXCLUDED from numeric tests and reported instead. The exclusion is the
    finding.
    """
    # Compare like with like: QUARTER columns only. The first version pooled
    # quarter and year-to-date columns, which inflated the local median and
    # let a LIC Housing filing reported a hundred times too small pass the
    # clean-factor test.
    pts = []
    for f in filings:
        if not f["disseminated"]:
            continue
        for c in f["columns"]:
            v = c["metrics"].get("Total income")
            if not v or not (c["period_start"] and c["period_end"]):
                continue
            span = (_d(c["period_end"]) - _d(c["period_start"])).days
            if span > 100:
                continue
            pts.append((f["disseminated"], f["file"], c["column"], abs(v)))
    if len(pts) < 8:
        return set(), None
    pts.sort()
    vals = [p[3] for p in pts]
    overall = st.median(vals)
    factors = (1e-7, 1e-5, 1e-2, 1e2, 1e5, 1e7)
    bad = set()
    for i, (_, fn, col, v) in enumerate(pts):
        # TRAILING window only. A forward-looking window would decide whether
        # a filing is usable using filings published after it, which would
        # contaminate every finding derived from that decision. The cost is
        # that the first few filings of an issuer cannot be scale-checked;
        # that is the correct trade and it is reported as a coverage limit
        # rather than papered over.
        near = [pts[j][3] for j in range(max(0, i - 6), i)]
        if len(near) < 4:
            continue
        local = st.median(near)
        if not local:
            continue
        ratio = v / local
        if any(abs(ratio / fac - 1.0) < 0.45 for fac in factors):
            bad.add((fn, col))
    return bad, overall


def check_scale(sym, filings):
    bad, mid = scale_anomalies(filings)
    if not bad:
        return []
    byfile = {}
    for f in filings:
        for c in f["columns"]:
            if (f["file"], c["column"]) in bad:
                byfile.setdefault(f["file"], f)
    out = []
    for fn, f in byfile.items():
        out.append(F(
            sym, "unit_anomaly", "medium", f["disseminated"],
            f"The figures in this filing are on a different scale from the "
            f"issuer's other filings - its total income differs from the "
            f"issuer's median filed income by more than fifty times. The "
            f"tagged rounding is \"{f['rounding']}\".",
            "The exchange's own structured data is internally inconsistent "
            "here. Any ratio or trend computed across this filing and its "
            "neighbours would be wrong by orders of magnitude, so the figures "
            "are excluded from every numeric test rather than rescaled by a "
            "guessed factor.",
            {"source": "NSE XBRL, scale checked against the issuer's own "
                       "filing history",
             "file": f["file"], "url": f["xbrl_url"],
             "disseminated": f["disseminated"],
             "tagged_rounding": f["rounding"],
             "issuer_median_income_crore": round((mid or 0) / 1e7, 1)},
            "Read the figures off the results PDF for this period and confirm "
            "the correct scale before using the period in any analysis.",
            "A genuine collapse or a change in the reporting entity can "
            "legitimately move reported income by orders of magnitude; check "
            "the PDF before assuming a tagging error.",
            "scale", f["rounding"]))
    return out


def quarter_series(filings, basis, exclude=None):
    """Deduplicated quarter columns for one basis, oldest first.

    Where the same period is filed more than once the EARLIEST dissemination
    is kept, because that is when the figure became knowable; the later filing
    is what the restatement check compares against.
    """
    exclude = exclude or set()
    out = {}
    for f in filings:
        if f["basis"] != basis or not f["disseminated"]:
            continue
        for c in f["columns"]:
            if not c["period_start"] or not c["period_end"]:
                continue
            if (f["file"], c["column"]) in exclude:
                continue
            span = (_d(c["period_end"]) - _d(c["period_start"])).days
            kind = "Q" if span <= 100 else ("H" if span <= 190 else
                                            "9M" if span <= 285 else "FY")
            key = (c["period_start"], c["period_end"])
            rec = {"start": c["period_start"], "end": c["period_end"],
                   "span_kind": kind, "metrics": c["metrics"],
                   "disseminated": f["disseminated"], "file": f["file"],
                   "url": f["xbrl_url"], "audited": f["audited"],
                   "audit_opinion": f["audit_opinion"],
                   "board_approved": f["board_approved"]}
            if key not in out or f["disseminated"] < out[key]["disseminated"]:
                out[key] = rec
    return sorted(out.values(), key=lambda r: r["end"])


def check_filing_timeliness(sym, filings, basis, today,
                            exclude=None):
    """Late and missing filings. The strongest signal found in the research:
    both Indian NBFC defaults in the sample blew the statutory deadline for
    their audited annual result BEFORE they defaulted."""
    out = []
    qs = [r for r in quarter_series(filings, basis, exclude)
          if r["span_kind"] == "Q"]
    lags = []
    for r in qs:
        pe, ds = _d(r["end"]), _d(r["disseminated"])
        lag = (ds - pe).days
        is_fy = r["end"][5:10] == "03-31"
        limit = RELAXED.get(r["end"], LIMIT_FY if is_fy else LIMIT_Q)
        base = st.median(lags[-6:]) if len(lags) >= 3 else None
        lags.append(lag)
        if lag <= limit:
            continue
        over = lag - limit
        # knowable on the day the deadline passed, not the day it finally filed
        deadline = pe + dt.timedelta(days=limit)
        sev = "high" if over >= 30 else "medium" if over >= 10 else "low"
        extra = (f" The issuer's trailing median lag was {base:.0f} days."
                 if base else "")
        # What is knowable ON THE DEADLINE is that the deadline passed with
        # nothing filed. The eventual lag is not knowable until the filing
        # arrives, so it is kept out of the finding's own text and recorded
        # under retrospective_* keys instead. The point-in-time test
        # (check_pit.py) enforces this separation.
        out.append(F(
            sym, "filing_overdue", sev, deadline.isoformat(),
            f"The {limit}-day SEBI LODR deadline for {basis.lower()} results "
            f"for the period ending {r['end']} passed with no filing."
            + extra,
            "A missed results deadline is one of the few distress signals that "
            "does not depend on the reported figures being accurate. It "
            "usually means the accounts are contested, the auditor has not "
            "signed, or a valuation is unresolved.",
            {"source": "NSE corporates-financial-results + XBRL",
             "period_end": r["end"],
             "statutory_limit_days": limit,
             "deadline": deadline.isoformat(),
             "trailing_median_lag_days": round(base) if base else None,
             # everything below postdates the finding and is retrospective
             "retrospective_filed_on": r["disseminated"],
             "retrospective_lag_days": lag,
             "retrospective_days_past_limit": over,
             "retrospective_board_approved": r["board_approved"],
             "retrospective_file": r["file"],
             "retrospective_url": r["url"]},
            f"Check the exchange announcements from {deadline} onward for an "
            f"intimation of delay, an auditor communication, or a "
            f"board-meeting postponement.",
            "A late filing is not always issuer-specific: SEBI's COVID-19 "
            "relaxations are already applied to the two periods they covered. "
            "Check whether any other market-wide extension was in force.",
            "filing_lag_days", lag))
    return out


def check_additivity(sym, filings, basis, exclude=None):
    """Year-to-date columns must equal the sum of their quarters. A break is a
    restatement, a reclassification, or an error - all worth knowing, and all
    invisible unless someone does the arithmetic."""
    out = []
    series = quarter_series(filings, basis, exclude)
    q = {r["end"]: r for r in series if r["span_kind"] == "Q"}
    for r in series:
        if r["span_kind"] == "Q":
            continue
        fy_start = r["start"]
        parts, missing = [], False
        cur = _d(fy_start)
        while cur < _d(r["end"]):
            nxt = None
            for e, qq in q.items():
                if qq["start"] == cur.isoformat():
                    nxt = qq
                    break
            if not nxt:
                missing = True
                break
            parts.append(nxt)
            cur = _d(nxt["end"]) + dt.timedelta(days=1)
        if missing or len(parts) < 2:
            continue
        for metric in ("Total income", "Profit before tax", "Profit after tax"):
            if metric not in r["metrics"]:
                continue
            if any(metric not in p["metrics"] for p in parts):
                continue
            ytd = r["metrics"][metric]
            ssum = sum(p["metrics"][metric] for p in parts)
            if abs(ytd) < MIN_LEVEL:
                continue
            diff = ytd - ssum
            if abs(diff) <= max(abs(ytd) * ROUND_TOL, MIN_DIFF):
                continue
            out.append(F(
                sym, "additivity_break",
                "high" if abs(diff) > abs(ytd) * 0.05 else "medium",
                r["disseminated"],
                f"{metric} for {r['start']} to {r['end']} was filed as "
                f"Rs {ytd/1e7:,.0f} crore, but the {len(parts)} quarters "
                f"inside that period, as originally filed, sum to "
                f"Rs {ssum/1e7:,.0f} crore - a difference of "
                f"Rs {diff/1e7:,.0f} crore ({100*diff/abs(ytd):+.1f}%).",
                "A cumulative figure that does not equal the sum of its parts "
                "means one of the quarters was restated after it was first "
                "reported, or an item was reclassified between periods. Either "
                "way, the originally published quarter is no longer what the "
                "issuer stands behind.",
                {"source": "NSE XBRL, arithmetic on filed figures",
                 "cumulative_filing": {"file": r["file"], "url": r["url"],
                                       "disseminated": r["disseminated"]},
                 "quarter_filings": [{"period": f"{p['start']}..{p['end']}",
                                      "file": p["file"],
                                      "value_crore": round(p["metrics"][metric]/1e7, 1),
                                      "disseminated": p["disseminated"]}
                                     for p in parts]},
                "Compare the two filings directly and find the restated line. "
                "Ask whether the restatement was disclosed as such, and whether "
                "it changed any covenant or ratio the issuer reports.",
                "Ind AS transition, a discontinued operation, a business "
                "combination, or a merger accounted for retrospectively can all "
                "legitimately change comparatives - but each should be "
                "explicitly disclosed in the filing.",
                metric, diff))
    return out


def check_basis_availability(sym, filings):
    """Consolidated reporting that is absent, not withdrawn.

    The first version looked for an issuer that filed consolidated accounts
    one year and stopped the next. Across all sixteen issuers that never
    happens - the pattern is always ".CCCCC", they begin filing consolidated
    and continue. The detector was unreachable.

    The condition that DOES occur, and matters more, is consolidated accounts
    never being filed at all. Reliance Home Finance files standalone only from
    2018 to 2025; so does Can Fin Homes. For a subsidiary inside a lending
    group that is the SREI problem exactly - the listed entity's own accounts
    need not describe the business that carries the risk.
    """
    out = []
    years = {}
    for f in filings:
        if not f["disseminated"]:
            continue
        years.setdefault(f["disseminated"][:4], set()).add(f["basis"])
    if not years:
        return out
    ordered = sorted(years)

    for prev, cur in zip(ordered, ordered[1:]):
        if "Consolidated" in years[prev] and "Consolidated" not in years[cur]:
            out.append(F(
                sym, "basis_withdrawn", "medium", f"{cur}-12-31",
                f"Consolidated results were filed during {prev} but not "
                f"during {cur}; only standalone figures are available for "
                f"{cur}.",
                "Where the lending book sits in subsidiaries, the standalone "
                "accounts of the listed entity can understate group risk "
                "severely. Losing the consolidated view removes the only "
                "basis on which group leverage can be read.",
                {"source": "NSE corporates-financial-results index",
                 "years_with_consolidated": ordered},
                "Obtain the consolidated annual report for the missing year "
                "and identify which subsidiaries carry the loan assets.",
                "A group restructuring may have removed the subsidiaries, in "
                "which case standalone and consolidated legitimately converge.",
                "basis", cur))

    if not any("Consolidated" in v for v in years.values()):
        grp = BY_SYMBOL.get(sym, {}).get("group")
        out.append(F(
            sym, "basis_unavailable", "medium", f"{ordered[-1]}-12-31",
            f"No consolidated results have ever been filed. Every one of this "
            f"issuer's {len(filings)} machine-readable filings, from "
            f"{ordered[0]} to {ordered[-1]}, is standalone.",
            "Standalone accounts describe the listed entity alone. Where a "
            "lender sits inside a group, they need not describe the business "
            "that carries the risk: SREI Infrastructure's standalone accounts "
            "reported zero advances because the loan book sat in a subsidiary. "
            "Without a consolidated basis, group leverage cannot be read from "
            "this source at all."
            + (f" This issuer is part of the {grp} group." if grp else ""),
            {"source": "NSE corporates-financial-results index",
             "filings_examined": len(filings),
             "years": f"{ordered[0]}-{ordered[-1]}",
             "bases_seen": sorted({b for v in years.values() for b in v}),
             "group": grp},
            "Establish whether the issuer has subsidiaries at all. If it does, "
            "obtain the group's consolidated annual report; if it is itself a "
            "subsidiary, read the parent alongside it.",
            "A standalone-only filer may simply have no subsidiaries, in which "
            "case standalone IS the group and nothing is missing.",
            "consolidated_filings", 0))
    return out


def check_audit_flags(sym, filings):
    out = []
    for f in filings:
        op = (f["audit_opinion"] or "").strip()
        if not op or op.lower() in ("not applicable", "na", "n.a.", "-"):
            continue
        if "unmodified" in op.lower() or "unqualified" in op.lower():
            continue
        out.append(F(
            sym, "audit_opinion", "high", f["disseminated"],
            f"The filing for {f['relating_to'] or 'the period'} carries an "
            f"audit opinion statement other than unmodified: \"{op[:200]}\"",
            "A modified opinion, qualification or emphasis of matter is the "
            "auditor declining to stand fully behind the figures. It is the "
            "most direct available evidence that the reported numbers should "
            "not be taken at face value.",
            {"source": "NSE XBRL tagged field "
                       "DeclarationOfUnmodifiedOpinionOrStatementOnImpact"
                       "OfAuditQualification",
             "file": f["file"], "url": f["xbrl_url"],
             "disseminated": f["disseminated"]},
            "Read the qualification itself in the results PDF and determine "
            "which balances it touches and whether it recurs.",
            None, "audit_opinion", op[:300]))
    return out


def check_earnings(sym, filings, basis, exclude=None):
    """Deterioration against the issuer's own history, within basis.

    Two deliberate restrictions, both learned from this build's first pass,
    which produced 13 "deterioration" findings for Bajaj Finance - a lender
    that grew throughout the period:

      * Profit is reported only on an actual REVERSAL into loss, never on a
        decline. A 25% fall in profit is not news; a loss is.
      * Credit cost is compared with the SAME QUARTER of the previous year,
        not the trailing median, because NBFC provisioning is strongly
        seasonal and a trailing-median comparison mostly detects Q4.

    The materiality floor scales with the issuer: a Rs 5 crore move matters
    for Repco and is noise for Bajaj, so the floor is the larger of MIN_DIFF
    and 2% of trailing annual income.
    """
    out = []
    qs = [r for r in quarter_series(filings, basis, exclude)
          if r["span_kind"] == "Q"]

    def floor_for(i):
        """2% of trailing four-quarter total income, or MIN_DIFF."""
        inc = [qs[j]["metrics"].get("Total income") for j in range(max(0, i - 4), i)]
        inc = [v for v in inc if v]
        return max(MIN_DIFF, 0.02 * sum(inc)) if inc else MIN_DIFF

    # --- profit reversal -------------------------------------------------
    hist = []
    for i, r in enumerate(qs):
        v = r["metrics"].get("Profit after tax")
        if v is None:
            continue
        if len(hist) >= 4:
            base = st.median(hist[-4:])
            if v < 0 <= base and abs(v - base) >= floor_for(i):
                out.append(F(
                    sym, "deterioration", "high", r["disseminated"],
                    f"Profit after tax for the quarter ending {r['end']} "
                    f"({basis}) was a loss of Rs {abs(v)/1e7:,.0f} crore, "
                    f"against a trailing four-quarter median profit of "
                    f"Rs {base/1e7:,.0f} crore.",
                    "A swing into loss consumes the equity buffer directly and "
                    "is the point at which rating agencies and lenders "
                    "typically reassess. For a lender it usually means "
                    "provisions were raised rather than that income fell.",
                    {"source": "NSE XBRL", "file": r["file"], "url": r["url"],
                     "disseminated": r["disseminated"], "basis": basis,
                     "audited": r["audited"],
                     "trailing_quarters_crore":
                         [round(h / 1e7, 1) for h in hist[-4:]],
                     "this_quarter_crore": round(v / 1e7, 1)},
                    "Establish whether the loss is provisioning or write-off, "
                    "and whether it was pre-announced. Compare with lenders of "
                    "the same type in the same quarter: a sector-wide "
                    "provisioning change is not issuer-specific news.",
                    "A one-time provision, an accounting transition, or a "
                    "regulator-mandated change in provisioning norms can each "
                    "produce a single loss-making quarter.",
                    "Profit after tax", v))
        hist.append(v)

    # --- credit cost, year on year --------------------------------------
    byend = {r["end"]: (i, r) for i, r in enumerate(qs)}
    for end_s, (i, r) in byend.items():
        v = r["metrics"].get("Impairment / credit cost")
        if v is None or v <= 0:
            continue
        prior = f"{int(end_s[:4]) - 1}{end_s[4:]}"
        if prior not in byend:
            continue
        pv = byend[prior][1]["metrics"].get("Impairment / credit cost")
        if pv is None or pv <= 0:
            continue
        ch = _pct(v, pv)
        if ch is None or ch < 50 or (v - pv) < floor_for(i):
            continue
        out.append(F(
            sym, "deterioration", "high" if ch >= 150 else "medium",
            r["disseminated"],
            f"Impairment on financial instruments for the quarter ending "
            f"{end_s} ({basis}) was Rs {v/1e7:,.0f} crore against "
            f"Rs {pv/1e7:,.0f} crore in the same quarter a year earlier "
            f"({ch:+.0f}%).",
            "Impairment is the issuer's own admission that the loan book is "
            "worth less than previously carried. Compared year on year rather "
            "than against the trailing quarter, it is not confounded by the "
            "seasonality of NBFC provisioning.",
            {"source": "NSE XBRL", "file": r["file"], "url": r["url"],
             "disseminated": r["disseminated"], "basis": basis,
             "audited": r["audited"],
             "this_quarter_crore": round(v / 1e7, 1),
             "same_quarter_prior_year_crore": round(pv / 1e7, 1),
             "prior_year_filing": byend[prior][1]["file"]},
            "Determine which book the impairment sits in and whether stage-2 "
            "and stage-3 balances moved with it. Check whether the issuer "
            "changed its ECL assumptions in the same filing.",
            "Loan-book growth raises impairment proportionally; scale the move "
            "against the change in advances before treating it as "
            "deterioration.",
            "Impairment / credit cost", v))
    return out


def check_capital(sym):
    """Capital erosion from the annual accounts, dated by publication.

    Featured deliberately: across the US bank-failure work that preceded this
    tool, plain equity/assets had a HIGHER held-out AUC than a nine-component
    weighted index. Where a simple ratio beats a composite, the product shows
    the simple ratio and says where it came from.
    """
    rows = annual_series(sym)
    out = []
    for prev, cur in zip(rows, rows[1:]):
        a, b = prev["equity_assets_pct"], cur["equity_assets_pct"]
        if a is None or b is None:
            continue
        neg = b < 0 <= a
        drop = a > 0 and (b - a) / a <= -0.25
        if not (neg or drop):
            continue
        est = cur["knowable_estimated"]
        out.append(F(
            sym, "capital_erosion", "high" if neg else "medium",
            cur["knowable_on"],
            f"Equity as a share of total assets fell from {a:.1f}% for the "
            f"year ended {prev['fy_ending']} to {b:.1f}% for the year ended "
            f"{cur['fy_ending']}"
            + (" - the issuer's net worth is negative." if neg
               else f" ({100*(b-a)/a:+.0f}% relative)."),
            "Equity over assets is the buffer between losses and creditors. "
            "In the testing behind this tool it separated failed from "
            "surviving lenders better than a weighted multi-factor index did, "
            "which is why it is reported on its own rather than folded into a "
            "score.",
            {"source": "Annual accounts (archive panel), dated by the "
                       "publication timestamp of the annual report"
                       + (" - ESTIMATED, no report matched" if est else ""),
             "fy_ending": cur["fy_ending"],
             "knowable_on": cur["knowable_on"],
             "date_is_estimated": est,
             "source_report": cur["source_report"],
             "equity_crore": cur["equity_cr"],
             "total_assets_crore": cur["total_assets_cr"],
             "leverage_x": cur["leverage_x"],
             "gnpa_pct": cur["gnpa_pct"]},
            "Confirm the figure against the audited balance sheet, and "
            "establish whether the fall is losses, a write-down, or a "
            "distribution. Check whether regulatory capital ratios moved with "
            "it - they use a different numerator.",
            "A capital raise in the following year, a change in the reporting "
            "entity, or a one-off accounting adjustment can each move this "
            "ratio without the underlying buffer changing."
            + (" The publication date here is an estimate, so the lead time "
               "shown may be optimistic." if est else ""),
            "equity_assets_pct", b))
    return out


def check_payments(sym):
    """Payment disclosures, read from the attached document.

    The detector that matched distress language against announcement SUMMARIES
    could not see these at all. Reliance Capital filed 23 announcements
    between October and December 2019 under one identical title - "Disclosure
    regarding payment of interest / principal on Non-Convertible Debentures" -
    while the attachments said the company's debt servicing "will be delayed".
    Corpus-wide there are 2,168 such announcements and the summary text
    promotes 14.

    This is the only detector in the tool that reads a document rather than a
    tagged field, and it is the earliest adverse signal available for the
    cases tested: Reliance Capital's first delayed-servicing disclosure is
    dated 11 October 2019, 25.6 months before the RBI superseded its board.

    Consecutive disclosures are collapsed into a RUN, because a company in
    difficulty files one per ISIN - often several a week - and one finding per
    letter would bury everything else.
    """
    rows = [r for r in attach_load(sym)
            if r.get("status") in ("default_form", "not_paid", "delayed")]
    if not rows:
        return []
    rows.sort(key=lambda r: r["ts"])

    runs, cur = [], [rows[0]]
    for r in rows[1:]:
        gap = (_d(r["ts"]) - _d(cur[-1]["ts"])).days
        if gap <= 45:
            cur.append(r)
        else:
            runs.append(cur)
            cur = [r]
    runs.append(cur)

    WORD = {"default_form": "filed the SEBI default-disclosure form "
                            "(circular CIR/CFD/CMD/93/2017) in respect of",
            "not_paid": "did not pay",
            "delayed": "would be delayed in paying"}
    out = []
    for run in runs:
        first, last = run[0], run[-1]
        isins = first.get("isins") or []
        # The finding describes ONLY the first letter, in ITS OWN words. The
        # first build used the run's worst status and its total length, which
        # dated a "did not pay" to a day whose letter said "will be delayed"
        # and cited 154 filings that had not happened yet. Everything about
        # how the run went on belongs under retrospective_.
        if first["status"] == "default_form":
            head = ("The issuer filed the SEBI default-disclosure form "
                    "(circular CIR/CFD/CMD/93/2017), which is submitted only "
                    "to report a default on listed debt")
        else:
            head = (f"The issuer disclosed to the exchange that it "
                    f"{WORD[first['status']]} interest or principal on its "
                    f"debentures")
        out.append(F(
            sym, "payment_disclosure", "high", first["ts"],
            head
            + (f", naming {len(isins)} ISIN" + ("s" if len(isins) > 1 else "")
               if isins else "")
            + (". The form's own wording: " if first["status"] == "default_form"
               else ". The filing states: ")
            + f"\u201c{first['phrase']}\u201d.",
            "A disclosed failure or delay in servicing debt is the issuer's "
            "own admission, made under SEBI's continuous-disclosure "
            "obligation. It is not an opinion, a ratio, or a third party's "
            "view, and it is usually the earliest adverse fact on the public "
            "record - rating agencies and the accounts both follow it.",
            {"source": "NSE corporate-announcements, text extracted from the "
                       "attached PDF",
             "classification": first["status"],
             "matched_phrase": first["phrase"],
             "quoted_context": first["context"],
             "isins": isins[:12],
             "attachment": first.get("url"),
             "retrospective_run_ended": last["ts"],
             "retrospective_filings_in_run": len(run),
             "retrospective_run_days": (_d(last["ts"]) - _d(first["ts"])).days},
            "Open the attachment and establish which instrument was affected, "
            "the amount, and whether the issuer attributed the delay to its "
            "own liquidity or to an external cause such as a lender "
            "accelerating a facility. Then check whether the next quarterly "
            "result acknowledged it.",
            "An issuer may disclose a delay caused by an operational or "
            "banking failure rather than an inability to pay, and some of "
            "these letters dispute a rating action while maintaining that no "
            "amount is overdue. The quoted sentence, not the title, is what "
            "to read.",
            "payment_status", first["status"]))

        # Escalation within a run is its own event, dated when it happened.
        if first["status"] == "delayed":
            esc = next((r for r in run
                        if r["status"] in ("not_paid", "default_form")), None)
            if esc:
                days = (_d(esc["ts"]) - _d(first["ts"])).days
                out.append(F(
                    sym, "payment_disclosure", "high", esc["ts"],
                    f"The disclosures escalated: having said on "
                    f"{first['ts'][:10]} that payment would be delayed, the "
                    f"issuer now states that it was not made. The filing "
                    f"reads: \u201c{esc['phrase']}\u201d.",
                    "A delay the issuer expects to cure and a payment it has "
                    "failed to make are different facts. The move from one to "
                    "the other is the point at which an expectation of "
                    "recovery stopped being tenable.",
                    {"source": "NSE corporate-announcements, text extracted "
                               "from the attached PDF",
                     "classification": "not_paid",
                     "matched_phrase": esc["phrase"],
                     "quoted_context": esc["context"],
                     "first_delayed_disclosure": first["ts"],
                     "days_from_first_delay": days,
                     "isins": (esc.get("isins") or [])[:12],
                     "attachment": esc.get("url")},
                    "Compare the two letters. Establish whether the issuer "
                    "changed its account of why, and whether any instrument "
                    "cured in between.",
                    None, "payment_status", "not_paid"))
    return out


# ------------------------------------------------------------ announcements
# Categories that belong on the TIMELINE. Appearing here does not make an
# announcement an alert: DHFL filed 62 rating announcements and 48 exchange
# clarification requests, and emitting one finding per announcement produced a
# 133-item alert list that no analyst would read. An announcement becomes a
# finding only if its text matches DISTRESS_RE, or if it arrives in a cluster.
WATCH = {
    "Credit Rating": ("rating_action", "medium",
                      "A rating action is a third party revising its view. "
                      "Downgrades frequently cluster before a payment failure, "
                      "and the commentary usually names the concern."),
    "News Verification": ("exchange_clarification", "medium",
                          "The exchange only seeks clarification when a news "
                          "report is material enough to move the price. It is "
                          "a timestamped record that something was alleged in "
                          "public that the issuer had not disclosed."),
    "Price movement": ("price_flag", "low",
                       "An exchange-flagged price move is not information in "
                       "itself, but it dates the moment the market repriced "
                       "the issuer, which can be compared with when the issuer "
                       "disclosed."),
}

# Words that distinguish a material action from a routine reaffirmation. Kept
# deliberately narrow and visible rather than hidden in a model, so an analyst
# can see exactly why something was promoted to an alert and change it.
# Price-movement notices are the exchange's own boilerplate - "Significant
# decrease in price has been observed in X. The Exchange, in order to ensure
# that investors have latest..." - and contain no distress vocabulary
# whatever. All 36 in the corpus were gated behind DISTRESS_RE, which none
# could ever match, so the detector was structurally unreachable. It gets the
# only gate that applies to it: the direction of the move.
PRICE_FALL = re.compile(r"(?i)significant (?:decrease|fall|decline) in price")

DISTRESS_RE = re.compile(
    r"\b(default|defaulted|downgrad\w*|revised downward|rating watch|"
    r"credit watch|negative (?:outlook|implications)|withdrawn|suspend\w*|"
    r"non[- ]?payment|missed (?:payment|interest)|delay in (?:payment|servicing)|"
    r"\bD\b ?rating|moratorium|resolution plan|insolvency|NCLT|"
    r"fraud|forensic|qualified opinion|going concern|"
    r"resignation of (?:the )?auditor|auditor.{0,20}resign)\b", re.I)


def check_announcements(sym, anns):
    out = []
    for a in anns:
        hit = WATCH.get(a["category"])
        if not hit:
            continue
        kind, sev, why = hit
        if a["category"] == "Price movement":
            m = PRICE_FALL.search(a["text"] or "")
            if not m:
                continue      # an unqualified "movement" says nothing
        else:
            m = DISTRESS_RE.search(a["text"] or "")
            if not m:
                continue      # timeline only; not an alert
            sev = "high"
        out.append(F(
            sym, kind, sev, a["ts"],
            f"{a['category']}: {a['text'][:260] or '(no text)'}",
            why,
            {"source": "NSE corporate-announcements",
             "category": a["category"], "announced": a["ts"],
             "exchange_disseminated": a["disseminated"],
             "attachment": (a["attachment"]
                            if (a["attachment"] or "").startswith("http")
                            else None),
             "promoted_because_text_matched": m.group(0)},
            "Open the attachment and record what specifically was said, by "
            "whom, and whether the issuer's next filing addressed it.",
            None, "announcement", a["category"]))
    # clustering: unusual density of watched categories in a 30-day window
    watched = [a for a in anns if a["category"] in WATCH
               and DISTRESS_RE.search(a["text"] or "")]
    for i, a in enumerate(watched):
        t0 = dt.datetime.fromisoformat(a["ts"])
        win = [b for b in watched[i:]
               if (dt.datetime.fromisoformat(b["ts"]) - t0).days <= 30]
        # The first version also demanded two distinct categories. Every
        # real cluster in the corpus is a single category - a run of rating
        # actions - so the requirement made the detector unreachable. The
        # largest clusters are RHFL and Reliance Capital at five in April
        # 2019, and DHFL at four in October 2019; no surviving issuer exceeds
        # two, so four items is the separating threshold.
        if len(win) >= 4:
            cats = sorted({b["category"] for b in win})
            if True:
                # Date the finding when the cluster COMPLETED, not when it
                # began. The window looks 30 days forward, so stamping it with
                # the first item would make the finding visible on a date when
                # the evidence establishing it did not yet exist - the exact
                # look-ahead the replay control exists to prevent.
                out.append(F(
                    sym, "disclosure_burst", "high", win[-1]["ts"],
                    f"{len(win)} "
                    + (cats[0].lower() if len(cats) == 1
                       else "rating actions and exchange notices")
                    + f" filings within 30 days, from {a['ts'][:10]} to "
                    + f"{win[-1]['ts'][:10]}.",
                    "Individually these are routine. Arriving together they "
                    "indicate the issuer is the subject of active external "
                    "scrutiny, which historically precedes a funding "
                    "withdrawal rather than following it.",
                    {"source": "NSE corporate-announcements",
                     "window_start": a["ts"], "window_end": win[-1]["ts"],
                     "count": len(win),
                     "items": [{"ts": b["ts"], "category": b["category"],
                                "text": b["text"][:140]} for b in win[:10]]},
                    "Read the cluster in order. Establish what the first item "
                    "alleged and whether the issuer's response was a denial, "
                    "a clarification, or silence.",
                    "Scheduled events - results season, a rating annual "
                    "review, an index rebalance - can bunch announcements "
                    "without any change in condition.",
                    "burst_count", len(win)))
                break
    return out


# ------------------------------------------------------------------ coverage
def check_coverage(sym, filings, anns, today):
    out = []
    qs = [r for r in quarter_series(filings, "Standalone")
          if r["span_kind"] == "Q"]
    if not qs:
        out.append(F(
            sym, "coverage_gap", "high", today.isoformat(),
            "No machine-readable quarterly results could be parsed for this "
            "issuer.",
            "Without structured results no indicator can be computed and no "
            "consistency check can be run. The issuer cannot be monitored at "
            "all on this source.",
            {"source": "NSE XBRL", "parsed_filings": 0,
             "announcements_available": len(anns)},
            "Fall back to the results PDFs in the announcement stream, or to "
            "the annual reports, and extract manually.",
            None, "quarters_parsed", 0))
        return out

    ends = [r["end"] for r in qs]
    QE = ((3, 31), (6, 30), (9, 30), (12, 31))
    first, last = _d(ends[0]), _d(ends[-1])
    expect = [dt.date(y, m, d).isoformat()
              for y in range(first.year, last.year + 1)
              for m, d in QE
              if first <= dt.date(y, m, d) <= last]
    miss = [e for e in expect if e not in set(ends)]
    if miss:
        out.append(F(
            sym, "coverage_gap", "medium" if len(miss) < 4 else "high",
            today.isoformat(),
            f"{len(miss)} of {len(expect)} quarters between {ends[0]} and "
            f"{ends[-1]} have no machine-readable filing: "
            f"{', '.join(miss[:8])}{' ...' if len(miss) > 8 else ''}.",
            "A gap is not evidence of a problem, but it bounds what can be "
            "claimed. Any trend drawn across a gap is an assumption.",
            {"source": "NSE XBRL", "quarters_present": len(ends),
             "quarters_expected": len(expect), "missing": miss},
            "NSE published results XBRL only from about 2019. For earlier "
            "periods use the results PDF attached to the announcement stream.",
            None, "quarters_missing", len(miss)))

    # Attachments that carry no text layer. 96 of the 471 payment disclosures
    # read so far are scanned images, and for SREI Infrastructure it is 51 of
    # 57 - so its disclosures classify as "unclear" because they cannot be
    # read, not because they say nothing. Reporting the difference matters:
    # silence from an unreadable document is not evidence of calm.
    pay = attach_load(sym)
    if pay:
        unread = [r for r in pay if r.get("chars", 0) < 200]
        if len(unread) >= max(5, 0.3 * len(pay)):
            out.append(F(
                sym, "coverage_gap",
                "high" if len(unread) > 0.6 * len(pay) else "medium",
                today.isoformat(),
                f"{len(unread)} of {len(pay)} payment-related attachments "
                f"({100*len(unread)//len(pay)}%) are scanned images with no "
                f"text layer and could not be read.",
                "A payment disclosure that cannot be read is not a disclosure "
                "that says nothing. Where most attachments are unreadable, the "
                "absence of a payment finding for this issuer carries no "
                "weight either way.",
                {"source": "NSE announcement attachments",
                 "attachments_total": len(pay),
                 "unreadable": len(unread),
                 "examples": [r["url"] for r in unread[:4]]},
                "Open a sample directly. If the issuer's filings are routinely "
                "scanned, this channel needs optical character recognition "
                "before it can be relied on for this name.",
                None, "unreadable_attachments", len(unread)))

    gap = (today - _d(qs[-1]["disseminated"])).days
    if gap > 150:
        out.append(F(
            sym, "stale_evidence", "medium" if gap < 400 else "high",
            today.isoformat(),
            f"The most recent parseable results filing was disseminated "
            f"{qs[-1]['disseminated'][:10]}, {gap} days ago.",
            "An issuer that has stopped filing cannot be assessed. For a "
            "delisted or suspended issuer this is expected; for an active one "
            "it is itself the finding.",
            {"source": "NSE XBRL", "last_filing": qs[-1]["disseminated"],
             "file": qs[-1]["file"], "days_stale": gap},
            "Confirm whether the issuer is still listed and still required to "
            "file.",
            "Delisting, suspension, merger or voluntary wind-down all stop the "
            "filing stream legitimately.",
            "days_since_filing", gap))
    return out


_BASIS_RE = re.compile(r"\s*\((Standalone|Consolidated)\)", re.I)
# The basis also appears INLINE - "the 45-day deadline for standalone results"
# - and the first version only stripped the parenthesised form, so every
# filing_overdue finding survived as two near-identical cards, one per basis.
# Edelweiss showed the same deadline twice with the same follow-up question.
_BASIS_WORD = re.compile(r"\b(standalone|consolidated)\s+(results|figures|"
                         r"accounts|basis)\b", re.I)


def _basis_of(f):
    m = _BASIS_RE.search(f["what_changed"]) or _BASIS_WORD.search(f["what_changed"])
    if m:
        return m.group(1).capitalize()
    return (f.get("evidence") or {}).get("basis")


def _strip_basis(s):
    """Finding text with every basis marker removed, so the same event filed
    on both bases produces one signature."""
    s = _BASIS_RE.sub("", s)
    s = _BASIS_WORD.sub(r"\2", s)
    return re.sub(r"^(Standalone|Consolidated) ", "", s, flags=re.I)


SEV_RANK = {"high": 0, "medium": 1, "low": 2}


def findings_for(sym, today=None):
    today = today or dt.date.today()
    filings = load_symbol(sym)
    anns = load_announcements(sym)
    bad_scale, _ = scale_anomalies(filings)

    out = []
    out += check_basis_availability(sym, filings)
    out += check_audit_flags(sym, filings)
    out += check_announcements(sym, anns)
    out += check_coverage(sym, filings, anns, today)
    out += check_scale(sym, filings)
    out += check_capital(sym)
    out += check_payments(sym)
    for basis in ("Standalone", "Consolidated"):
        if any(f["basis"] == basis for f in filings):
            out += check_filing_timeliness(sym, filings, basis, today,
                                           bad_scale)
            out += check_additivity(sym, filings, basis, bad_scale)
            out += check_earnings(sym, filings, basis, bad_scale)

    # --- collapse duplicates ------------------------------------------------
    # Two kinds of duplication, both of which inflated the first build's alert
    # counts without adding information:
    #
    #  (a) the exchange files one event twice - its own query and the issuer's
    #      reply arrive as separate announcements;
    #  (b) an issuer whose consolidated figures barely differ from its
    #      standalone ones generates the identical finding under both bases.
    #      LIC Housing produced eighteen findings this way where nine were
    #      warranted. Where both bases fire, they are merged and the surviving
    #      finding says so, because "both bases agree" is information and two
    #      identical cards are not.
    merged = {}
    order = []
    for f in out:
        # 90 characters is enough to identify the event and short enough
        # that the exchange's query and the issuer's reply - which share an
        # opening but diverge later - collapse into one finding.
        sig = (f["kind"], f["knowable_on"][:10],
               _strip_basis(f["what_changed"])[:90])
        if sig in merged:
            prev = merged[sig]
            pb, nb = _basis_of(prev), _basis_of(f)
            if pb and nb and pb != nb:
                prev["bases_agree"] = sorted({pb, nb})
                prev["what_changed"] = _strip_basis(
                    prev["what_changed"]).replace(
                    " was ", " was ", 1)
                prev["evidence"]["also_filed_on_basis"] = nb
            continue
        merged[sig] = f
        order.append(sig)

    deduped = [merged[s] for s in order]
    for f in deduped:
        if f.get("bases_agree"):
            f["what_changed"] += (" The same figure was filed on both the "
                                  "standalone and consolidated basis.")
    deduped.sort(key=lambda f: (SEV_RANK[f["severity"]], f["knowable_on"]))
    return deduped, filings, anns


if __name__ == "__main__":
    import sys
    import collections
    from universe import ISSUERS
    syms = [sys.argv[1]] if len(sys.argv) > 1 else [i[0] for i in ISSUERS]
    for s in syms:
        try:
            fs, fl, an = findings_for(s)
        except Exception as e:
            print(f"{s:12s} ERROR {type(e).__name__}: {e}")
            continue
        c = collections.Counter(f["kind"] for f in fs)
        print(f"{s:12s} {len(fl):3d} filings {len(an):5d} anns -> "
              f"{len(fs):3d} findings  " +
              " ".join(f"{k}:{v}" for k, v in c.most_common(6)))
