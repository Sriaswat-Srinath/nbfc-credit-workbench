"""Emit the workbench data file consumed by the UI.

All findings are exported with their `knowable_on` timestamp so the as-of
control can filter client-side. That is what makes the point-in-time replay
instantaneous: the page is not re-querying, it is hiding what was not yet
knowable, which is the same operation the analysis performs.
"""
import json
import os
import re
import datetime as dt

from annual import series as annual_series
from brief import build as build_brief
from normalize import normalize
from claims import open_claims
from detect import findings_for, load_announcements
from facts import load_symbol
from maturity import calendar as repayment_calendar
from ratings import current as rating_current, levels as rating_levels
from universe import ISSUERS, RELATED

HERE = os.path.dirname(os.path.abspath(__file__))

TIMELINE_CATS = ("Credit Rating", "News Verification", "Price movement",
                 "Outcome of Board Meeting", "Financial Result Updates",
                 "Press Release", "Updates")

# Statements are exported compactly - lines as arrays rather than objects -
# because 1,164 statement-columns at ~35 lines each is 40,000 rows and the
# object form roughly triples the payload for no gain.
# Strings are INTERNED into a shared lexicon: the same ~90 labels, 9 section
# names and ~290 tags repeat across all 1,164 statement columns, and spelling
# them out each time produced a 15.2 MB export against 4.4 MB interned. Lines
# and checks therefore carry integer indices into data.lex.
#   line  = [labelIdx, sectionIdx, kindIdx, value, tagIdx]
#   check = [ruleIdx, stated, recomputed, difference, state, [missingIdx]]
#           state 1 ok / 0 fail / null unevaluated

LEX = []
_LEX_AT = {}


def _i(s):
    """Intern a string, return its index in the exported lexicon."""
    s = "" if s is None else str(s)
    if s not in _LEX_AT:
        _LEX_AT[s] = len(LEX)
        LEX.append(s)
    return _LEX_AT[s]


def _r(v):
    """Round to the paisa. The source carries 2 decimals of rupees; keeping
    float noise beyond that costs bytes and means nothing."""
    return None if v is None else round(v, 2)


def _iso(s):
    for f in ("%d-%b-%Y", "%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
        try:
            return dt.datetime.strptime(s, f).date().isoformat()
        except (ValueError, TypeError):
            pass
    return None


def statements_for(sym):
    """Every cached instance, rendered as readable statements."""
    base = os.path.join(HERE, "cache", sym)
    try:
        index = json.load(open(os.path.join(base, "results.json")))
    except Exception:
        return []
    idx = {os.path.basename(r["xbrl"]): r for r in index
           if (r.get("xbrl") or "").endswith(".xml")}
    xd = os.path.join(base, "xbrl")
    out = []
    for fn in sorted(os.listdir(xd)) if os.path.isdir(xd) else []:
        row = idx.get(fn)
        if not row:
            continue
        fb = (_iso(row.get("fromDate")), _iso(row.get("toDate")))
        try:
            stmts = normalize(os.path.join(xd, fn),
                              fb if all(fb) else None)
        except Exception:
            continue
        disseminated_on = _iso(row.get("broadCastDate")) or _iso(row.get("filingDate"))
        for s in stmts:
            out.append({
                "file": fn,
                "url": row.get("xbrl"),
                "disseminated": disseminated_on,
                "basis": ("Consolidated"
                          if row.get("consolidated") == "Consolidated"
                          else s["meta"].get("basis", "Standalone")),
                "audited": row.get("audited") or s["meta"].get("audited"),
                "column": s["column"],
                "start": s["period_start"],
                "end": s["period_end"],
                "period_source": s["period_source"],
                "board_approved": s["meta"].get("board_approved"),
                "rounding": s["meta"].get("rounding"),
                "lines": [[_i(l["label"]), _i(l["section"]), _i(l["kind"]),
                           _r(l["value"]), _i(l["tag"])] for l in s["lines"]],
                "checks": [[_i(c["rule"]), _r(c["stated"]), _r(c["recomputed"]),
                            _r(c["difference"]),
                            (1 if c["ok"] else 0) if c["ok"] is not None
                            else None,
                            [_i(m) for m in (c.get("missing") or [])]]
                           for c in s["checks"]],
            })
    return out


def main():
    out = {"generated": dt.datetime.now().isoformat(timespec="seconds"),
           "lex": LEX, "issuers": [], "related": [{"parent": p, "related": c, "note": n}
                                      for p, c, n in RELATED]}
    for sym, name, ltype, group, outcome, odate, oclass in ISSUERS:
        findings, filings, anns = findings_for(sym)
        qs = {}
        for f in filings:
            if not f["disseminated"]:
                continue
            for c in f["columns"]:
                if not (c["period_start"] and c["period_end"]):
                    continue
                span = (dt.date.fromisoformat(c["period_end"])
                        - dt.date.fromisoformat(c["period_start"])).days
                if span > 100:
                    continue
                key = (c["period_end"], f["basis"])
                rec = {"end": c["period_end"], "basis": f["basis"],
                       "disseminated": f["disseminated"],
                       "lag_days": (dt.date.fromisoformat(f["disseminated"][:10])
                                    - dt.date.fromisoformat(c["period_end"])).days,
                       "audited": f["audited"],
                       "pat": c["metrics"].get("Profit after tax"),
                       "income": c["metrics"].get("Total income"),
                       "impair": c["metrics"].get("Impairment / credit cost"),
                       "file": f["file"], "url": f["xbrl_url"]}
                if key not in qs or f["disseminated"] < qs[key]["disseminated"]:
                    qs[key] = rec
        series = sorted(qs.values(), key=lambda r: (r["basis"], r["end"]))

        tl = [{"ts": a["ts"], "cat": a["category"], "text": a["text"][:300],
               "att": a["attachment"] if (a["attachment"] or "").startswith("http")
                      else None}
              for a in anns if a["category"] in TIMELINE_CATS]

        # The rating level and its history - previously absent entirely: the
        # workbench knew a rating action had happened and not what it moved to.
        robs = [{"ts": o["ts"], "agency": o["agency"],
                 "weakest": o["weakest"], "strongest": o["strongest"],
                 "sole": o["sole_symbol"], "outlook": o["outlook"],
                 "watch": o["watch"], "url": o["url"],
                 "down": o["says_downgrade"], "up": o["says_upgrade"]}
                for o in rating_levels(sym)]
        rnow = {a: {"symbol": o["weakest"], "ts": o["ts"], "url": o["url"],
                    "outlook": o["outlook"], "watch": o["watch"]}
                for a, o in rating_current(sym).items()}

        # The disclosed repayment calendar, compactly: one row per instrument
        # payment the issuer intimated to the exchange, carrying the date the
        # intimation became public so the as-of control can filter it.
        cal = [[c["due"], c["isin"], _i(c["kind"] or ""),
                _r(c["amount"]), c["knowable_on"][:10]]
               for c in repayment_calendar(sym)]

        # Quantified promises with a deadline. Exported as a record, not as
        # findings: see the note in detect.findings_for.
        cl = [{"due": c["due"], "made_on": c["made_on"][:10],
               "subject": c["subject"], "claim": c["claim"][:300],
               "low": _r(c["amount_low"]), "high": _r(c["amount_high"]),
               "horizon": c["horizon"], "url": c["url"]}
              for c in open_claims(sym)]

        b = build_brief(sym)
        out["issuers"].append({
            "symbol": sym, "name": name, "lender_type": ltype,
            "group": group, "outcome": outcome, "outcome_date": odate,
            "outcome_class": oclass,
            "findings": findings,
            "quarters": series,
            "timeline": tl,
            "latest_reported": b["latest_reported"],
            "annual": annual_series(sym),
            "statements": statements_for(sym),
            "ratings": robs,
            "rating_now": rnow,
            "calendar": cal,
            "claims": cl,
            "announcement_total": len(anns),
            "filings_total": len(filings),
        })
        print(f"  {sym:12s} {len(findings):3d} findings  {len(series):3d} "
              f"quarter-rows  {len(tl):5d} timeline  "
              f"{len(out['issuers'][-1]['statements']):4d} statements  "
              f"{len(robs):3d} ratings  {len(cal):5d} calendar", flush=True)

    p = os.path.join(HERE, "workbench_data.json")
    with open(p, "w") as fh:
        json.dump(out, fh, separators=(",", ":"), default=str)
    # The UI loads the payload as a plain script tag, and a browser will
    # happily serve yesterday's copy from cache - which during a demo looks
    # exactly like the build having failed. Stamp the build time into the src
    # so each rebuild is a new URL.
    js = os.path.join(HERE, "workbench_data.js")
    with open(js, "w") as fh:
        fh.write("window.WB=")
        fh.write(open(p).read())
        fh.write(";\n")
    stamp = out["generated"].replace(":", "").replace("-", "")
    hp = os.path.join(HERE, "workbench.html")
    html = open(hp).read()
    html = re.sub(r'src="workbench_data\.js(?:\?v=[^"]*)?"',
                  'src="workbench_data.js?v=' + stamp + '"', html)
    open(hp, "w").write(html)
    print(f"\n{os.path.getsize(p)/1e6:.2f} MB -> {p}")
    print(f"{os.path.getsize(js)/1e6:.2f} MB -> {js}  (stamped v={stamp})")


if __name__ == "__main__":
    main()
