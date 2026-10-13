"""Recover the distressed institutions that are missing from the archive.

The coverage test found that 11 of 22 known distress events could not be
evaluated, and that every missing name was a failure - the archive keeps
survivors and drops the hardest cases. That is the project's worst bias and it
cannot be fixed by modelling.

Most of those institutions are still published at source. The archive's schema
(Equity Capital / Reserves / Borrowings / CWIP / ...) is screener.in's balance
sheet layout, so the same statements can be pulled in identical definitions and
dropped straight into the panel - no reconciliation, no re-derivation.

Writes per-company folders under recovered/ in exactly the archive's layout, so
build_panel.py picks them up with no special cases.

IMPORTANT: these institutions are for evaluating the FROZEN model. Nothing here
may be used to re-select components, re-derive thresholds or re-fit weights.
"""

import os
import re
import csv
import sys
import time
import html
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "recovered")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")
BASE = "https://www.screener.in/company/{sym}/"
DELAY = 2.0

# symbol -> (archive-style company name, sector, NSE code)
TARGETS = {
    "ALBK": ("Allahabad Bank", "Banks", "ALBK"),
    "CORPBANK": ("Corporation Bank", "Banks", "CORPBANK"),
    "DENABANK": ("Dena Bank", "Banks", "DENABANK"),
    "ORIENTBANK": ("Oriental Bank of Commerce", "Banks", "ORIENTBANK"),
    "UNITEDBNK": ("United Bank of India", "Banks", "UNITEDBNK"),
    "LAKSHVILAS": ("Lakshmi Vilas Bank Ltd", "Banks", "LAKSHVILAS"),
    "SREINFRA": ("SREI Infrastructure Finance Ltd", "Finance", "SREINFRA"),
}

SECTIONS = {
    "profit-loss": "Yearly_Profit_Loss.csv",
    "balance-sheet": "Yearly_Balance_Sheet.csv",
    "cash-flow": "Yearly_Cash_flow.csv",
    "ratios": "Ratios.csv",
}


def fetch(sym, tries=3):
    req = urllib.request.Request(BASE.format(sym=sym), headers={"User-Agent": UA})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(3 * (i + 1))
        except Exception:
            time.sleep(3 * (i + 1))
    return None


def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def parse_section(page, section_id):
    """Return (headers, [(label, [values...])]) for one screener card."""
    m = re.search(rf'id="{section_id}"\s+class="card.*?</table>', page, re.S)
    if not m:
        return None, []
    block = m.group()

    head = re.search(r"<thead>.*?</thead>", block, re.S)
    headers = []
    if head:
        headers = [strip_tags(h) for h in re.findall(r"<th[^>]*>(.*?)</th>",
                                                     head.group(), re.S)]
        headers = headers[1:]            # first cell is the row-label column

    body = re.search(r"<tbody>.*?</tbody>", block, re.S)
    rows = []
    if body:
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(), re.S):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if not cells:
                continue
            label = strip_tags(cells[0]).rstrip("+").strip()
            vals = [strip_tags(c).replace(",", "").replace("%", "") for c in cells[1:]]
            if label:
                rows.append((label, vals))
    return headers, rows


def top_ratio(page, name):
    m = re.search(rf"{re.escape(name)}\s*</span>.*?</span>", page, re.S)
    if not m:
        m = re.search(rf"{re.escape(name)}.{{0,220}}", page, re.S)
    if not m:
        return ""
    txt = strip_tags(m.group())
    num = re.search(r"-?[\d,]+\.?\d*", txt.split(name)[-1])
    return num.group().replace(",", "") if num else ""


def write_company(sym, page):
    name, sector, nse = TARGETS[sym]
    folder = os.path.join(OUT, name)
    os.makedirs(folder, exist_ok=True)

    wrote = []
    for section_id, fname in SECTIONS.items():
        headers, rows = parse_section(page, section_id)
        if not rows:
            continue
        with open(os.path.join(folder, fname), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow([""] + headers)
            for label, vals in rows:
                w.writerow([label] + vals[:len(headers)])
        wrote.append(f"{fname.replace('.csv','')}({len(rows)}r x {len(headers)}c)")

    fv = top_ratio(page, "Face Value") or "10"
    with open(os.path.join(folder, f"{name}_Basic_Info.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["", "Company_name", "Sector", "BSE", "NSE", "Market Cap",
                    "Current Price", "Face Value"])
        w.writerow(["0", name, sector, "", nse,
                    top_ratio(page, "Market Cap"), top_ratio(page, "Current Price"), fv])
    return wrote


def main():
    os.makedirs(OUT, exist_ok=True)
    ok, failed = [], []
    for sym in TARGETS:
        name = TARGETS[sym][0]
        page = fetch(sym)
        time.sleep(DELAY)
        if not page:
            print(f"  MISS  {name:34s} ({sym}) - not published")
            failed.append(name)
            continue
        wrote = write_company(sym, page)
        if not wrote:
            print(f"  EMPTY {name:34s} ({sym}) - no tables parsed")
            failed.append(name)
            continue
        print(f"  ok    {name:34s} {', '.join(wrote)}")
        ok.append(name)

    print(f"\nrecovered {len(ok)} institutions into {OUT}")
    if failed:
        print(f"still missing: {', '.join(failed)}")
    print("\nDHFL, IL&FS, Punjab & Maharashtra Co-op and Altico remain unavailable:")
    print("  DHFL was delisted and its page withdrawn; IL&FS and Altico were never")
    print("  listed; PMC was a co-operative outside the listed universe.")


if __name__ == "__main__":
    main()
