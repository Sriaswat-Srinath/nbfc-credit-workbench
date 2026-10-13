"""Dump each filing's maturity-table region for transcription.

No parsing. The layouts differ too much for one regex, so this locates the
table and prints it for a human to read off. That limitation is itself the
answer to feasibility question Q3.
"""
import json, re, sys

CAND = re.compile(r"(?i)maturity pattern")
BUCKET = re.compile(r"(?i)(over 6 month|upto 1 year|up to 1 year|to 1 year|"
                    r"over 1 year)")

rows = json.load(open("alm_cohort.json"))
want = sys.argv[1] if len(sys.argv) > 1 else None

for r in rows:
    if want and r["symbol"] != want:
        continue
    txt = open(r["txt"]).read()
    lines = txt.split("\n")
    best, bi = -1, None
    for i, ln in enumerate(lines):
        if not CAND.search(ln):
            continue
        win = "\n".join(lines[i:i + 30])
        # score: does it look like an actual ladder, not prose?
        sc = len(BUCKET.findall(win)) + 3 * len(re.findall(
            r"(?i)^\s*(deposits|advances|investments|borrowings|loans)\b",
            win, re.M))
        if sc > best:
            best, bi = sc, i
    print("=" * 100)
    print(f"{r['symbol']}  FY{r['fiscal_from']}  pub {r['published'][:10]}  "
          f"cohort {r['cohort']}  score {best}")
    print("=" * 100)
    if bi is None:
        print("   no candidate region")
        continue
    for ln in lines[max(0, bi - 2):bi + 62]:
        print("  " + ln[:190].rstrip())
    print()
