"""Week-one go/no-go: can ALM maturity data be recovered at all?

This is a DATA FEASIBILITY TEST, not a model. It answers three questions and
nothing else:

  1. Can annual reports be located for failed and surviving NBFCs, with a
     verifiable publication date?
  2. Does the RBI maturity-bucket table appear in them, in a parseable form?
  3. Is the format consistent enough across institutions and years to build a
     panel, or does every filer do it differently?

A negative answer to any of these ends the ALM hypothesis cheaply, which is the
point of running it first.

Known trap, already observed on SREI: the listed entity's STANDALONE table can
be nearly empty if the lending book sits in a subsidiary. Standalone and
consolidated are not interchangeable and the script records which it found.
"""

import os
import re
import json
import time
import subprocess
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "alm")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")

# Failed institutions and survivors from the same period, so the comparison is
# not purely between firms that died and firms that never existed in stress.
TARGETS = [
    ("SREINFRA", "SREI Infrastructure Finance", "failed 2021-10"),
    ("RELCAPITAL", "Reliance Capital", "failed 2021-11"),
    ("RHFL", "Reliance Home Finance", "failed 2019-09"),
    ("IBULHSGFIN", "Indiabulls Housing Finance", "survived, severe stress 2019"),
    ("BAJFINANCE", "Bajaj Finance", "survivor"),
    ("MUTHOOTFIN", "Muthoot Finance", "survivor"),
    ("LICHSGFIN", "LIC Housing Finance", "survivor"),
    ("CHOLAFIN", "Cholamandalam Investment", "survivor"),
]

# RBI's standard maturity ladder. A filer that uses these headings is parseable.
BUCKETS = ["1 day to 7 days", "8 days to 14 days", "15 days to 30/31 days",
           "Over 1 month upto 2 months", "Over 2 months upto 3 months",
           "Over 3 months upto 6 months", "Over 6 months upto 1 year",
           "Over 1 year upto 3 years", "Over 3 years upto 5 years",
           "Over 5 years"]
ROWS = ["Deposits", "Advances", "Investments", "Borrowings",
        "Foreign Currency Assets", "Foreign Currency Liabilities"]


def curl(url, out=None, tries=2):
    cmd = ["curl", "-sL", "--max-time", "90", "-A", UA,
           "-H", "Referer: https://www.bseindia.com/"]
    if out:
        cmd += ["-o", out]
    cmd.append(url)
    for i in range(tries):
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if out and os.path.exists(out) and os.path.getsize(out) > 5000:
            return True
        if not out and r.stdout:
            return r.stdout
        time.sleep(2)
    return False if out else b""


def annual_reports(symbol):
    """Annual-report PDF links and their stated year, from the company page."""
    h = curl(f"https://www.screener.in/company/{symbol}/").decode("utf8", "replace")
    m = re.search(r'id="documents".{0,6000}', h, re.S)
    if not m:
        return []
    out = []
    for url, label in re.findall(r'href="([^"]+)"[^>]*>\s*([^<]{0,60})', m.group()):
        label = " ".join(label.split())
        if label.lower().startswith("annual report") and ".pdf" in url.lower():
            yr = re.search(r"(20\d\d)", label)
            out.append((int(yr.group(1)) if yr else None,
                        url.replace("&amp;", "&"), label))
    return sorted(out, reverse=True)


def pdf_text(path):
    try:
        return subprocess.run(["pdftotext", "-layout", path, "-"],
                              capture_output=True, timeout=300
                              ).stdout.decode("utf8", "replace")
    except Exception:
        return ""


def find_table(txt):
    """Locate the maturity-pattern table and parse its rows."""
    hits = [m.start() for m in re.finditer(r"[Mm]aturity pattern", txt)]
    for i in hits:
        seg = txt[i:i + 3500]
        if "Over 5 years" not in seg and "Over 1 year" not in seg:
            continue
        basis = "consolidated" if re.search(
            r"consolidat", txt[max(0, i - 4000):i], re.I) else "standalone"
        asof = re.search(r"as at\s+(\d{1,2}(?:st|nd|rd|th)?\s+\w+,?\s+20\d\d)", seg)
        rows = {}
        for ln in seg.split("\n"):
            s = " ".join(ln.split())
            for key in ROWS:
                if s.startswith(key):
                    nums = re.findall(r"[\d,]+(?:\.\d+)?|-", s[len(key):])
                    vals = []
                    for n in nums:
                        if n == "-":
                            vals.append(0.0)
                        else:
                            try:
                                vals.append(float(n.replace(",", "")))
                            except ValueError:
                                pass
                    if len(vals) >= 6:
                        rows[key] = vals
        if rows:
            return {"basis": basis, "as_at": asof.group(1) if asof else None,
                    "rows": rows, "n_rows": len(rows)}
    return None


def main():
    os.makedirs(CACHE, exist_ok=True)
    results = []
    for sym, name, status in TARGETS:
        print(f"\n{name}  ({sym}) - {status}")
        reports = annual_reports(sym)
        if not reports:
            print("   no annual-report links found")
            results.append({"symbol": sym, "name": name, "status": status,
                            "reports": 0, "parsed": False})
            continue
        print(f"   {len(reports)} annual reports listed: "
              f"{', '.join(str(y) for y, _, _ in reports[:6])}")

        parsed = None
        for yr, url, label in reports:
            if yr is None or yr > 2021:
                continue
            path = os.path.join(CACHE, f"{sym}_{yr}.pdf")
            if not os.path.exists(path) or os.path.getsize(path) < 5000:
                if not curl(url, path):
                    print(f"   {yr}: download failed")
                    continue
            txt = pdf_text(path)
            if len(txt) < 20000:
                print(f"   {yr}: {os.path.getsize(path)//1024}KB but only "
                      f"{len(txt)} chars of text (likely scanned)")
                continue
            tab = find_table(txt)
            if tab:
                print(f"   {yr}: FOUND  basis={tab['basis']}  as_at={tab['as_at']}  "
                      f"rows={tab['n_rows']}")
                parsed = {"year": yr, **tab}
                break
            print(f"   {yr}: no maturity table located ({len(txt):,} chars)")
        results.append({"symbol": sym, "name": name, "status": status,
                        "reports": len(reports), "parsed": bool(parsed),
                        "detail": parsed})
        time.sleep(1)

    with open(os.path.join(HERE, "alm_feasibility.json"), "w") as fh:
        json.dump(results, fh, indent=1, default=str)

    print("\n" + "=" * 74)
    print("GO / NO-GO SUMMARY")
    print("=" * 74)
    ok = [r for r in results if r["parsed"]]
    print(f"  institutions attempted            : {len(results)}")
    print(f"  annual reports located            : "
          f"{sum(1 for r in results if r['reports'])}")
    print(f"  maturity table parsed             : {len(ok)}")
    for r in results:
        d = r.get("detail") or {}
        print(f"    {r['name'][:34]:34s} {'OK ' if r['parsed'] else '-- '} "
              f"{d.get('year','')} {d.get('basis','')}")


if __name__ == "__main__":
    main()
