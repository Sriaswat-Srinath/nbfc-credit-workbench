"""The analyst investigation brief, scoped to a point in time.

The `as_of` parameter is the feature the research phase argued for hardest.
Every finding knows the timestamp at which it became knowable, so a brief can
be regenerated as it would have read on any past date. That makes two things
possible which a conventional dashboard cannot do:

  * An analyst can test their own monitoring process: "on 31 May 2019, what
    did DHFL's file actually say?" - rather than reading today's file and
    concluding the failure was obvious.
  * Nothing in a brief can be contaminated by hindsight, because a finding
    dated after `as_of` is not merely hidden, it is not computed.

The brief states what changed, why it may matter, what contradicts it, and
what the analyst has to go and check. It does not conclude. The research phase
established that a composite score on this kind of data does not beat a single
ratio, so this tool deliberately produces questions rather than a number.
"""
import datetime as dt

from detect import SEV_RANK, findings_for, load_announcements, quarter_series
from facts import load_symbol
from universe import BY_SYMBOL, RELATED

KIND_LABEL = {
    "filing_overdue": "Missed filing deadline",
    "additivity_break": "Figures do not reconcile across filings",
    "basis_withdrawn": "Consolidated reporting withdrawn",
    "audit_opinion": "Auditor did not give a clean opinion",
    "deterioration": "Material deterioration",
    "rating_action": "Rating action",
    "exchange_clarification": "Exchange sought clarification",
    "price_flag": "Exchange flagged a price move",
    "disclosure_burst": "Cluster of external scrutiny",
    "coverage_gap": "Evidence gap",
    "stale_evidence": "Evidence is stale",
}

# Findings that describe the limits of the evidence rather than the issuer's
# condition. They belong in the brief, but under their own heading - mixing
# them with substantive findings is what makes dashboards feel like noise.
EVIDENCE_KINDS = {"coverage_gap", "stale_evidence"}


def build(sym, as_of=None):
    meta = dict(BY_SYMBOL[sym])
    findings, filings, anns = findings_for(sym)
    as_of = as_of or dt.date.today().isoformat()

    visible = [f for f in findings if f["knowable_on"][:10] <= as_of]
    substantive = [f for f in visible if f["kind"] not in EVIDENCE_KINDS]
    limits = [f for f in visible if f["kind"] in EVIDENCE_KINDS]

    # the filings an analyst could have read by as_of
    seen_filings = [f for f in filings
                    if f["disseminated"] and f["disseminated"][:10] <= as_of]
    seen_anns = [a for a in anns if a["ts"][:10] <= as_of]

    # the most recent reported figures, as filed, within each basis
    latest = {}
    for basis in ("Standalone", "Consolidated"):
        qs = [r for r in quarter_series(seen_filings, basis)
              if r["span_kind"] == "Q"]
        if qs:
            r = qs[-1]
            latest[basis] = {
                "period": f"{r['start']} to {r['end']}",
                "disseminated": r["disseminated"],
                "audited": r["audited"],
                "file": r["file"], "url": r["url"],
                "metrics_crore": {k: round(v / 1e7, 1)
                                  for k, v in sorted(r["metrics"].items())},
            }

    rel = [{"parent": p, "related": c, "note": n}
           for p, c, n in RELATED if sym in (p, c)]

    by_sev = {s: [f for f in substantive if f["severity"] == s]
              for s in ("high", "medium", "low")}

    # alert rate, so the analyst can judge the tool rather than trust it
    if seen_filings:
        first = min(f["disseminated"][:10] for f in seen_filings)
        years = max(0.25, (dt.date.fromisoformat(as_of)
                           - dt.date.fromisoformat(first)).days / 365.25)
    else:
        first, years = None, None

    return {
        "issuer": meta,
        "as_of": as_of,
        "coverage": {
            "filings_readable": len(seen_filings),
            "announcements": len(seen_anns),
            "earliest_filing": first,
            "bases_available": sorted({f["basis"] for f in seen_filings}),
            "alerts_per_year": round(len(substantive) / years, 1) if years else None,
        },
        "latest_reported": latest,
        "findings": sorted(substantive,
                           key=lambda f: (SEV_RANK[f["severity"]],
                                          f["knowable_on"]), reverse=False),
        "evidence_limits": limits,
        "counts": {k: len(v) for k, v in by_sev.items()},
        "related_entities": rel,
        "timeline": [
            {"ts": a["ts"], "category": a["category"],
             "text": a["text"][:300], "attachment": a["attachment"]}
            for a in seen_anns
            if a["category"] in ("Credit Rating", "News Verification",
                                 "Price movement", "Outcome of Board Meeting",
                                 "Financial Result Updates", "Press Release")
        ][-400:],
    }


def render_text(b):
    """Plain-text brief. The product's actual output is this, not a score."""
    i = b["issuer"]
    L = []
    L.append("=" * 78)
    L.append(f"INVESTIGATION BRIEF - {i['name']} ({i['symbol']})")
    L.append(f"Evidence as it stood on {b['as_of']}")
    L.append("=" * 78)
    c = b["coverage"]
    L.append(f"\n{i['lender_type']}"
             + (f", {i['group']} group" if i.get("group") else "")
             + f". {c['filings_readable']} machine-readable result "
             + ("filing" if c["filings_readable"] == 1 else "filings")
             + (f" from {c['earliest_filing']}" if c["earliest_filing"] else "")
             + f", {c['announcements']} exchange announcements.")
    L.append(f"Reporting bases available: "
             f"{', '.join(c['bases_available']) or 'none'}.")
    if c["alerts_per_year"] is not None:
        L.append(f"Alert rate: {c['alerts_per_year']} substantive findings per "
                 f"year of coverage.")

    cnt = b["counts"]
    L.append(f"\n{cnt['high']} high, {cnt['medium']} medium, {cnt['low']} low. "
             f"This is a count of things to look at, NOT a probability of "
             f"default.")

    if b["related_entities"]:
        L.append("\nRELATED LISTED ENTITIES")
        for r in b["related_entities"]:
            L.append(f"  - {r['note']}")
            if r["related"]:
                L.append(f"    Read {r['related']} alongside this issuer; the "
                         f"standalone accounts of one do not describe the other.")

    for sev in ("high", "medium", "low"):
        fs = [f for f in b["findings"] if f["severity"] == sev]
        if not fs:
            continue
        L.append("\n" + "-" * 78)
        L.append(f"{sev.upper()} ({len(fs)})")
        L.append("-" * 78)
        for n, f in enumerate(fs, 1):
            L.append(f"\n{n}. [{f['knowable_on'][:10]}] "
                     f"{KIND_LABEL.get(f['kind'], f['kind'])}")
            L.append(f"   WHAT      {f['what_changed']}")
            L.append(f"   WHY       {f['why_it_matters']}")
            if f.get("counterevidence"):
                L.append(f"   AGAINST   {f['counterevidence']}")
            L.append(f"   NEXT      {f['investigate']}")
            e = f["evidence"]
            src = e.get("source", "")
            bits = [x for x in (e.get("file"), e.get("url"),
                                e.get("attachment")) if x]
            L.append(f"   EVIDENCE  {src}")
            for x in bits:
                L.append(f"             {x}")

    if b["evidence_limits"]:
        L.append("\n" + "-" * 78)
        L.append("LIMITS OF THE EVIDENCE")
        L.append("-" * 78)
        for f in b["evidence_limits"]:
            L.append(f"  - {f['what_changed']}")
            L.append(f"    {f['investigate']}")

    qs, order = {}, []
    for f in b["findings"]:
        q = f.get("investigate")
        if not q:
            continue
        if q not in qs:
            qs[q] = 0
            order.append(q)
        qs[q] += 1
    if qs:
        L.append("\n" + "-" * 78)
        L.append("QUESTIONS FOR THE ANALYST")
        L.append("-" * 78)
        for n, q in enumerate(sorted(order, key=lambda x: -qs[x])[:6], 1):
            L.append(f"  {n}. {q}"
                     + (f" ({qs[q]} findings)" if qs[q] > 1 else ""))

    L.append("\n" + "-" * 78)
    L.append("WHAT THIS BRIEF CANNOT TELL YOU")
    L.append("-" * 78)
    L.append("  - Whether the reported figures are accurate. Every finding "
             "above is\n    derived from what the issuer chose to disclose.")
    L.append("  - Anything about unlisted group entities, which file nothing "
             "to the\n    exchange and are where lending risk is often held.")
    L.append("  - Rating agency liquidity commentary, which is not in this "
             "data set and\n    may already contain the same conclusion "
             "earlier.")
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "DHFL"
    as_of = sys.argv[2] if len(sys.argv) > 2 else None
    print(render_text(build(sym, as_of)))
