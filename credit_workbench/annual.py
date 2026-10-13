"""The annual balance-sheet layer, dated by actual publication.

Quarterly XBRL carries only the profit and loss account, so leverage,
equity/assets and asset quality - the measures the research phase found most
durable - are not in it. They come from annual accounts instead.

The discipline that matters here is the publication date. An annual balance
sheet for the year ended 31 March is not knowable on 31 March; the report
reaches the exchange three to six months later, and the research phase found
that difference large enough to invalidate three of five test cases. So each
annual observation is stamped with the dissemination timestamp of the annual
report that carried it, taken from NSE's annual-reports index. Where no report
can be matched the observation is stamped with a conservative fallback and
flagged as estimated, never silently dated to the fiscal year end.
"""
import csv
import datetime as dt
import json
import os
import re
import subprocess
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
PANEL = os.path.join(os.path.dirname(HERE), "risk_engine", "panel.csv")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")
API = "https://www.nseindia.com/api/annual-reports?index=equities&symbol={}"

# panel.csv predates two renames
ALIAS = {"SAMMAANCAP": "IBULHSGFIN"}


def curl(url, timeout=60):
    cmd = ["curl", "-sL", "--max-time", str(timeout - 10), "-A", UA,
           "-H", "Referer: https://www.nseindia.com/", url]
    for _ in range(2):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        if r.stdout:
            return r.stdout
        time.sleep(2)
    return b""


def pub_ts(fname, broadcast):
    if broadcast and broadcast != "-":
        try:
            return dt.datetime.strptime(broadcast, "%d-%b-%Y %H:%M:%S")
        except ValueError:
            pass
    m = re.findall(r"_(\d{14})", fname or "")
    if m:
        try:
            return dt.datetime.strptime(m[0], "%d%m%Y%H%M%S")
        except ValueError:
            pass
    return None


def report_dates(sym):
    """fiscal start year -> (publication timestamp, source url)."""
    p = os.path.join(CACHE, sym, "annual_reports.json")
    if os.path.exists(p) and os.path.getsize(p) > 3:
        data = json.load(open(p))
    else:
        raw = curl(API.format(urllib.parse.quote(sym)))
        try:
            data = json.loads(raw).get("data", [])
        except Exception:
            data = []
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(data, open(p, "w"))
    out = {}
    for r in data:
        t = pub_ts(r.get("fileName"), r.get("broadcast_dttm"))
        if t and r.get("fromYr"):
            out[str(r["fromYr"])] = (t.isoformat(), r.get("fileName"))
    return out


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def series(sym):
    """Annual ratios for one issuer, each stamped with when it became public."""
    key = ALIAS.get(sym, sym)
    rows = [r for r in csv.DictReader(open(PANEL)) if r.get("nse") == key]
    if not rows:
        return []
    pub = report_dates(sym)
    out = []
    for r in sorted(rows, key=lambda x: x["fy"]):
        fy = r["fy"]                     # fiscal year ENDING, e.g. 2018
        ta, ec, rs = f(r["total_assets"]), f(r["equity_capital"]), f(r["reserves"])
        if not ta or ec is None or rs is None:
            continue
        eq = ec + rs
        bo, np_, rev = f(r["borrowings"]), f(r["net_profit"]), f(r["revenue"])
        # the annual report for FY ending 2018 is indexed under fromYr 2017
        k = str(int(fy) - 1)
        if k in pub:
            knowable, src, est = pub[k][0], pub[k][1], False
        else:
            knowable = f"{fy}-09-30T00:00:00"   # conservative: 6 months after
            src, est = None, True
        # Leverage is assets/equity, and with equity at or below zero the
        # ratio is not a leverage measure at all - it inverts. Reliance
        # Capital's equity fell from -Rs 949 crore (FY2019) to -Rs 19,820
        # crore (FY2022) while the printed ratio moved from -88.5x to -3.2x,
        # so the number improved monotonically as the balance sheet was
        # destroyed. An analyst skimming the column would read that backwards.
        # The ratio is withheld and the reason recorded.
        lev = round(ta / eq, 2) if eq > 0 else None
        lev_note = None if eq > 0 else (
            "not meaningful: reported equity is " +
            ("negative" if eq < 0 else "zero") +
            ", so assets/equity does not measure leverage. Read total "
            "borrowings and the obligations falling due instead.")
        out.append({
            "fy_ending": fy,
            "knowable_on": knowable,
            "knowable_estimated": est,
            "source_report": src,
            "total_assets_cr": round(ta, 1),
            "equity_cr": round(eq, 1),
            "equity_assets_pct": round(100.0 * eq / ta, 2),
            "leverage_x": lev,
            "leverage_note": lev_note,
            "borrowings_assets_pct": round(100.0 * bo / ta, 2) if bo else None,
            "roa_pct": round(100.0 * np_ / ta, 2) if np_ is not None else None,
            "gnpa_pct": f(r["gnpa_last"]),
            "revenue_cr": round(rev, 1) if rev else None,
        })
    return out


if __name__ == "__main__":
    from universe import ISSUERS
    allout = {}
    for sym, *_ in ISSUERS:
        s = series(sym)
        allout[sym] = s
        est = sum(1 for x in s if x["knowable_estimated"])
        if s:
            print(f"{sym:12s} {len(s):2d} years {s[0]['fy_ending']}.."
                  f"{s[-1]['fy_ending']}  equity/assets "
                  f"{s[0]['equity_assets_pct']:5.1f}% -> "
                  f"{s[-1]['equity_assets_pct']:5.1f}%  "
                  f"({est} dates estimated)")
        else:
            print(f"{sym:12s} no annual balance sheet in the archive")
        time.sleep(.4)
    json.dump(allout, open(os.path.join(HERE, "annual.json"), "w"), indent=0)
    print("\n-> annual.json")
