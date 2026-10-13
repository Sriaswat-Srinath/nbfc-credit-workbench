"""Build the small ALM panel: pre-event reports only, with provenance.

Week two. The rule that governs everything here: an observation may only be
used if its PUBLICATION timestamp precedes the event. The week-one write-up
assumed annual reports were usable; checking the timestamps showed that DHFL's
FY2019 report (5 Sep 2019) and IL&FS Transportation's FY2018 report (24 Sep
2018) were both published AFTER those groups had already defaulted. They are
excluded.

That leaves exactly one usable observation per failed institution in the
6-18 month window, which is the honest size of this test:

    DHFL        FY2018  published 2018-07-19   10.5 months before default
    ITNL        FY2017  published 2017-09-04   12.0 months before default
    RHFL        FY2018  published 2018-09-20   11.3 months before default
    SREI        FY2020  published 2020-08-28   13.2 months before resolution
    Reliance Capital FY2020 published 2020-06-01  17.9 months before resolution

Survivors are drawn from the same filing seasons so the comparison is
contemporaneous.

Every record carries: publication timestamp, source URL, reporting basis
(standalone/consolidated), maturity basis (contractual/behavioural), bucket
schema and an extraction-completeness flag. Nothing is imputed.
"""

import os
import re
import json
import time
import zipfile
import subprocess
import datetime as dt
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "alm")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")
NSE_AR = "https://www.nseindia.com/api/annual-reports?index=equities&symbol={sym}"

# symbol -> (event date or None for survivors, label)
UNIVERSE = {
    "DHFL":        ("2019-06-04", "failed: first NCD default"),
    "IL&FSTRANS":  ("2018-09-04", "failed: IL&FS group CP default"),
    "RHFL":        ("2019-09-01", "failed: default, rating D"),
    "SREINFRA":    ("2021-10-04", "failed: RBI superseded board"),
    "RELCAPITAL":  ("2021-11-29", "failed: RBI superseded board"),
    "BAJFINANCE":  (None, "survivor"),
    "MUTHOOTFIN":  (None, "survivor"),
    "LICHSGFIN":   (None, "survivor"),
    "CHOLAFIN":    (None, "survivor"),
    "SHRIRAMFIN":  (None, "survivor"),
    "IBULHSGFIN":  (None, "survivor, severe stress 2019"),
    "PNBHOUSING":  (None, "survivor"),
}

# window in which a pre-event report is operationally useful
MIN_LEAD_M, MAX_LEAD_M = 6, 18
SURVIVOR_YEARS = {"2017", "2018", "2019", "2020"}

ROWS = ["Deposits", "Public deposits", "Advances", "Investments",
        "Borrowings", "Foreign Currency Assets", "Foreign currency assets",
        "Foreign Currency Liabilities", "Foreign currency liabilities"]


def curl(url, out=None, tries=2, timeout=240):
    cmd = ["curl", "-sL", "--max-time", str(timeout - 20), "-A", UA,
           "-H", "Referer: https://www.nseindia.com/"]
    if out:
        cmd += ["-o", out]
    cmd.append(url)
    for i in range(tries):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        if out:
            if os.path.exists(out) and os.path.getsize(out) > 20000:
                return True
        elif r.stdout:
            return r.stdout
        time.sleep(2)
    return False if out else b""


def published(fname, broadcast):
    if broadcast and broadcast != "-":
        try:
            return dt.datetime.strptime(broadcast, "%d-%b-%Y %H:%M:%S")
        except ValueError:
            pass
    m = re.findall(r"_(\d{14})", fname)
    if m:
        try:
            return dt.datetime.strptime(m[0], "%d%m%Y%H%M%S")
        except ValueError:
            return None
    return None


def list_reports(sym):
    raw = curl(NSE_AR.format(sym=urllib.parse.quote(sym)))
    try:
        data = json.loads(raw).get("data", [])
    except Exception:
        return []
    out = []
    for r in data:
        t = published(r["fileName"], r.get("broadcast_dttm"))
        if t:
            out.append({"from": r.get("fromYr"), "to": r.get("toYr"),
                        "published": t, "url": r["fileName"]})
    return sorted(out, key=lambda x: x["published"], reverse=True)


def fetch_pdf(sym, rep):
    tag = f"{re.sub(r'[^A-Za-z0-9]', '', sym)}_{rep['from']}"
    raw = os.path.join(CACHE, tag + ".bin")
    if not os.path.exists(raw) or os.path.getsize(raw) < 20000:
        if not curl(rep["url"], raw):
            return None
    # NSE serves some reports as ZIP with a .pdf extension
    if zipfile.is_zipfile(raw):
        d = os.path.join(CACHE, tag)
        os.makedirs(d, exist_ok=True)
        try:
            with zipfile.ZipFile(raw) as z:
                names = [n for n in z.namelist() if n.lower().endswith(".pdf")]
                if not names:
                    return None
                big = max(names, key=lambda n: z.getinfo(n).file_size)
                z.extract(big, d)
                return os.path.join(d, big)
        except Exception:
            return None
    return raw


def pdf_text(path):
    try:
        return subprocess.run(["pdftotext", "-layout", path, "-"],
                              capture_output=True, timeout=400
                              ).stdout.decode("utf8", "replace")
    except Exception:
        return ""


def parse_table(txt):
    """Find a maturity-pattern table and record how it is constructed."""
    best = None
    for m in re.finditer(r"[Mm]aturity pattern", txt):
        i = m.start()
        seg = txt[i:i + 4000]
        if "Over 5 years" not in seg and "Over 1 year" not in seg \
                and "to 3 years" not in seg:
            continue
        ctx = txt[max(0, i - 6000):i + 1500]
        rows, n_full = {}, 0
        for ln in seg.split("\n"):
            s = " ".join(ln.split())
            for key in ROWS:
                if s.lower().startswith(key.lower()):
                    tail = s[len(key):]
                    vals = []
                    for tok in re.findall(r"\(?[\d,]+\.?\d*\)?|[-–]", tail):
                        if tok in ("-", "–"):
                            vals.append(0.0)
                        else:
                            neg = tok.startswith("(")
                            t2 = tok.strip("()").replace(",", "")
                            try:
                                v = float(t2)
                                vals.append(-v if neg else v)
                            except ValueError:
                                pass
                    if len(vals) >= 5:
                        rows[key] = vals
                        n_full += 1
                    break
        if not rows:
            continue
        rec = {
            "reporting_basis": "consolidated" if re.search(r"consolidat", ctx, re.I)
                               else "standalone",
            "maturity_basis": "behavioural" if re.search(r"behavio", seg + ctx, re.I)
                              else "contractual",
            "n_buckets": max(len(v) for v in rows.values()),
            "rows": rows,
            "rows_found": n_full,
            "completeness": round(n_full / 4.0, 2),   # deposits/advances/inv/borrowings
        }
        if best is None or rec["rows_found"] > best["rows_found"]:
            best = rec
    return best


def main():
    os.makedirs(CACHE, exist_ok=True)
    records = []
    for sym, (event, label) in UNIVERSE.items():
        print(f"\n{sym}  ({label})")
        reps = list_reports(sym)
        if not reps:
            print("   no reports listed")
            continue

        if event:
            evd = dt.datetime.fromisoformat(event)
            usable = []
            for r in reps:
                lead = (evd - r["published"]).days / 30.44
                if MIN_LEAD_M <= lead <= MAX_LEAD_M:
                    usable.append((lead, r))
            if not usable:
                print(f"   NO report published {MIN_LEAD_M}-{MAX_LEAD_M} months "
                      f"before {event}")
                continue
            usable.sort()
            picks = [(usable[0][1], usable[0][0])]
        else:
            picks = [(r, None) for r in reps if r["from"] in SURVIVOR_YEARS][:2]

        for rep, lead in picks:
            path = fetch_pdf(sym, rep)
            if not path:
                print(f"   FY{rep['from']}: download failed")
                continue
            txt = pdf_text(path)
            if len(txt) < 20000:
                print(f"   FY{rep['from']}: only {len(txt)} chars (scanned?)")
                continue
            tab = parse_table(txt)
            lead_s = f"{lead:.1f}m before" if lead else "survivor"
            if not tab:
                print(f"   FY{rep['from']} pub {rep['published']:%Y-%m-%d} "
                      f"({lead_s}): NO TABLE")
                continue
            print(f"   FY{rep['from']} pub {rep['published']:%Y-%m-%d} ({lead_s}): "
                  f"{tab['n_buckets']} buckets, {tab['maturity_basis']}, "
                  f"{tab['reporting_basis']}, completeness {tab['completeness']:.0%}")
            records.append({
                "symbol": sym, "label": label, "event_date": event,
                "fiscal_from": rep["from"], "fiscal_to": rep["to"],
                "publication_timestamp": rep["published"].isoformat(),
                "lead_months": round(lead, 1) if lead else None,
                "source_url": rep["url"], **tab})
        time.sleep(1)

    with open(os.path.join(HERE, "alm_panel.json"), "w") as fh:
        json.dump(records, fh, indent=1, default=str)
    print(f"\n{len(records)} observations with full provenance "
          f"-> alm_panel.json")


if __name__ == "__main__":
    main()
