"""Write every cached XBRL filing out as a readable, column-aligned text file.

A browser shows an XBRL instance as an unformatted wall of numbers, because
there is no stylesheet attached and the markup carries the meaning. Opening
the evidence link therefore proves nothing to a reader - which defeats the
point of linking to it.

This writes the same filings as plain text:

    statements/INDEX.txt          every filing, one line each, with its period,
                                  basis, filing date and the file holding it
    statements/<SYMBOL>.txt       all of that issuer's filings, newest first
    statements/by-filing/<...>.txt one file per filing, for direct linking

Three columns throughout: the line item, the figure, and the original XBRL tag
the figure was read from. Figures are Rs crore except per-share amounts and
ratios, which are printed as filed.

Run:  python3 export_statements.py
"""
import datetime as dt
import glob
import json
import os
import re

from normalize import SECTION_ORDER, normalize
from universe import BY_SYMBOL, ISSUERS

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
OUT = os.path.join(HERE, "statements")

W_LABEL, W_VALUE, W_TAG = 62, 16, 60
RULE = "-" * (W_LABEL + W_VALUE + W_TAG + 2)

TOTAL_TAGS = {
    "Income", "Revenue", "Expenses", "ProfitBeforeTax", "TaxExpense",
    "ProfitLossForPeriod", "ProfitLossForThePeriod", "RevenueFromOperations",
    "ComprehensiveIncomeForThePeriod", "ProfitBeforeExceptionalItemsAndTax",
}


def _iso(s):
    for f in ("%d-%b-%Y", "%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
        try:
            return dt.datetime.strptime(s, f).date().isoformat()
        except (ValueError, TypeError):
            pass
    return None


def span_name(start, end):
    if not (start and end):
        return "period"
    d = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days
    return ("quarter" if d <= 100 else "half year" if d <= 190
            else "nine months" if d <= 285 else "full year")


def fmt(value, kind):
    if value is None:
        return "-"
    v = value / 1e7 if kind == "money" else value
    return f"{v:,.2f}"


def render(stmt, row, sym):
    """One statement column as aligned text."""
    meta = stmt["meta"]
    L = []
    name = BY_SYMBOL.get(sym, {}).get("name", sym)
    L.append("=" * len(RULE))
    L.append(f"{name}  ({sym})")
    L.append(f"{stmt['period_start']} to {stmt['period_end']}"
             f"   [{span_name(stmt['period_start'], stmt['period_end'])}]")
    L.append("=" * len(RULE))
    disseminated = _iso(row.get("broadCastDate")) or _iso(row.get("filingDate"))
    L.append(f"  basis                {row.get('consolidated') or meta.get('basis','?')}")
    L.append(f"  audited              {row.get('audited') or meta.get('audited','?')}")
    if meta.get("board_approved"):
        L.append(f"  approved by board    {meta['board_approved']}")
    L.append(f"  disseminated by NSE  {disseminated or '?'}")
    if meta.get("rounding"):
        L.append(f"  filer states units   {meta['rounding']}  "
                 f"(the instance itself carries absolute rupees; converted "
                 f"below)")
    if stmt.get("period_source") and stmt["period_source"] != "tagged":
        L.append(f"  period taken from    {stmt['period_source']}")
    L.append(f"  source               {row.get('xbrl','')}")
    L.append("")
    L.append(f"{'LINE ITEM':{W_LABEL}}{'Rs CRORE':>{W_VALUE}}  XBRL TAG")
    L.append(RULE)

    for sec in SECTION_ORDER:
        rows = [ln for ln in stmt["lines"] if ln["section"] == sec]
        if not rows:
            continue
        L.append("")
        L.append(sec.upper())
        for ln in rows:
            lab = ln["label"]
            if len(lab) > W_LABEL - 4:
                lab = lab[:W_LABEL - 6] + "..."
            mark = "* " if ln["tag"] in TOTAL_TAGS else "  "
            unit = "" if ln["kind"] == "money" else f"  [{ln['kind']}]"
            L.append(f"{mark}{lab:{W_LABEL - 2}}"
                     f"{fmt(ln['value'], ln['kind']):>{W_VALUE}}  "
                     f"{ln['tag']}{unit}".rstrip())

    L.append("")
    L.append(RULE)
    L.append("* marks a subtotal.  Figures in Rs crore except lines marked")
    L.append("  [per_share] or [ratio], which are printed exactly as filed.")
    L.append("")
    L.append("DOES THE STATEMENT ADD UP")
    if not stmt["checks"]:
        L.append("  no subtotal in this filing could be recomputed from the "
                 "lines it contains")
    for c in stmt["checks"]:
        if c["ok"] is None:
            L.append(f"  [not checked] {c['rule']}")
            L.append(f"                {', '.join(c['missing'])} was not "
                     f"filed, so the relationship cannot be tested")
        elif c["ok"]:
            L.append(f"  [holds      ] {c['rule']}")
        else:
            L.append(f"  [BREAKS     ] {c['rule']}")
            L.append(f"                stated {c['stated']/1e7:,.2f} cr, "
                     f"recomputed {c['recomputed']/1e7:,.2f} cr, "
                     f"difference {c['difference']/1e7:,.2f} cr")
    L.append("")
    L.append("  Only relationships that hold by definition of a profit and "
             "loss account")
    L.append("  are tested. Decomposition - a total against the lines beneath "
             "it - is NOT")
    L.append("  checked: the three XBRL taxonomies in use name those lines "
             "differently and")
    L.append("  the rule failed on healthy filings, so it was removed rather "
             "than shipped.")
    L.append("")
    return "\n".join(L)


def main():
    os.makedirs(os.path.join(OUT, "by-filing"), exist_ok=True)
    index = []
    for sym, name, *_ in ISSUERS:
        base = os.path.join(CACHE, sym)
        try:
            rows = json.load(open(os.path.join(base, "results.json")))
        except Exception:
            continue
        idx = {os.path.basename(r["xbrl"]): r for r in rows
               if (r.get("xbrl") or "").endswith(".xml")}
        xd = os.path.join(base, "xbrl")
        if not os.path.isdir(xd):
            continue

        blocks = []
        for fn in sorted(os.listdir(xd)):
            row = idx.get(fn)
            if not row:
                continue
            fb = (_iso(row.get("fromDate")), _iso(row.get("toDate")))
            try:
                stmts = normalize(os.path.join(xd, fn),
                                  fb if all(fb) else None)
            except Exception:
                continue
            disseminated = (_iso(row.get("broadCastDate"))
                            or _iso(row.get("filingDate")) or "")
            for s in stmts:
                text = render(s, row, sym)
                basis = (row.get("consolidated")
                         or s["meta"].get("basis", "Standalone"))
                basis = "cons" if basis.startswith("Cons") else "std"
                stub = (f"{sym}_{s['period_start']}_{s['period_end']}"
                        f"_{basis}_{s['column']}.txt")
                stub = re.sub(r"[^A-Za-z0-9_.-]", "", stub)
                with open(os.path.join(OUT, "by-filing", stub), "w") as fh:
                    fh.write(text)
                blocks.append((disseminated, s["period_end"], s["column"], text))
                index.append((sym, s["period_start"], s["period_end"],
                              span_name(s["period_start"], s["period_end"]),
                              basis, row.get("audited", ""), disseminated,
                              len(s["lines"]), stub))

        blocks.sort(reverse=True)
        with open(os.path.join(OUT, f"{sym}.txt"), "w") as fh:
            fh.write(f"{name} ({sym}) - every machine-readable filing, "
                     f"newest first\n")
            fh.write(f"Generated {dt.date.today()} from the cached NSE XBRL "
                     f"instances.\n\n")
            fh.write("\n\n".join(b[3] for b in blocks))
        print(f"  {sym:12s} {len(blocks):4d} statements", flush=True)

    index.sort(key=lambda r: (r[0], r[2]), reverse=True)
    with open(os.path.join(OUT, "INDEX.txt"), "w") as fh:
        fh.write("EVERY MACHINE-READABLE FILING IN THE CACHE\n")
        fh.write(f"Generated {dt.date.today()}.  "
                 f"{len(index)} statement columns from "
                 f"{len({r[8].rsplit('_',1)[0] for r in index})} filings.\n\n")
        fh.write(f"{'ISSUER':12} {'FROM':11} {'TO':11} {'SPAN':12} "
                 f"{'BASIS':6} {'AUDITED':10} {'FILED':11} {'LINES':>5}  FILE\n")
        fh.write("-" * 130 + "\n")
        for r in index:
            fh.write(f"{r[0]:12} {str(r[1]):11} {r[2]:11} {r[3]:12} "
                     f"{r[4]:6} {str(r[5])[:10]:10} {r[6]:11} {r[7]:5d}  "
                     f"by-filing/{r[8]}\n")
    print(f"\n{len(index)} statement columns -> {OUT}/")


if __name__ == "__main__":
    main()
