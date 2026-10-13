"""Pull FDIC bank failures and quarterly call-report financials.

Why this exists
---------------
The Indian study is limited by events, not rows: 6,223 company-years but only 18
labelled distress events, 13 of them the same kind. No amount of additional
Indian financial data fixes that, because the event population is itself about
twenty institutions.

The FDIC publishes, free and without authentication:
  * every US bank failure since 1934, dated, with a CERT identifier
  * quarterly call-report financials for every insured institution

They join on CERT. That gives thousands of events, quarterly rather than annual
frequency, a real non-performing-assets series, and -- crucially -- no
survivorship bias, because failed banks remain in the data with the call reports
they filed before failing.

The purpose is to test whether the *methodology* generalises, on a sample large
enough to say so. The Indian system remains the application; this is its
validation.
"""

import os
import json
import time
import subprocess
import urllib.parse

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "fdic")
API = "https://api.fdic.gov/banks/{ep}?{q}"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

# Window spans two distinct failure regimes: the 2008-2012 wave (488 failures)
# and the post-crisis tail including the 2023 regional bank failures (76). That
# split is what makes a genuine temporal holdout possible.
START_YEAR, END_YEAR = 2003, 2023

FIN_FIELDS = ["CERT", "REPDTE", "ASSET", "EQ", "DEP", "NETINC",
              "ROA", "INTINC", "EINTEXP", "NPERFV", "LNATRES"]
DELAY = 0.6
PAGE = 10000


def get(ep, params, tries=3):
    """Fetch via curl.

    urllib hangs against this endpoint even though curl returns immediately,
    so the transport is shelled out rather than fought with.
    """
    url = API.format(ep=ep, q=urllib.parse.urlencode(params))
    cmd = ["curl", "-sL", "--max-time", "45", "-A", UA, url]
    for i in range(tries):
        try:
            out = subprocess.run(cmd, capture_output=True, timeout=60).stdout
            if out:
                return json.loads(out)
        except Exception:
            pass
        time.sleep(2 * (i + 1))
    return None


def quarters(y0, y1):
    for y in range(y0, y1 + 1):
        for md in ("0331", "0630", "0930", "1231"):
            yield f"{y}{md}"


def fetch_failures():
    path = os.path.join(CACHE, "failures.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    rows, offset = [], 0
    while True:
        d = get("failures", {"fields": "CERT,NAME,FAILDATE,FAILYR,QBFASSET,QBFDEP,RESTYPE",
                             "limit": PAGE, "offset": offset, "format": "json"})
        if not d or not d.get("data"):
            break
        rows += [r["data"] for r in d["data"]]
        offset += PAGE
        if offset >= d["meta"]["total"]:
            break
        time.sleep(DELAY)
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    print(f"  failures: {len(df):,} records, {df['FAILYR'].min()}-{df['FAILYR'].max()}")
    return df


def fetch_quarter(rep):
    path = os.path.join(CACHE, f"fin_{rep}.csv")
    if os.path.exists(path):
        return
    d = get("financials", {"filters": f"REPDTE:{rep}",
                           "fields": ",".join(FIN_FIELDS),
                           "limit": PAGE, "format": "json"})
    if not d or not d.get("data"):
        open(path, "w").write("")
        return
    df = pd.DataFrame([r["data"] for r in d["data"]])
    df.to_csv(path, index=False)
    return len(df)


def main():
    os.makedirs(CACHE, exist_ok=True)
    print("fetching failures...")
    fail = fetch_failures()

    qs = list(quarters(START_YEAR, END_YEAR))
    print(f"fetching {len(qs)} quarters of call reports ({START_YEAR}-{END_YEAR})...")
    for i, rep in enumerate(qs, 1):
        n = fetch_quarter(rep)
        if n:
            time.sleep(DELAY)
        if i % 8 == 0 or i == len(qs):
            print(f"  {i}/{len(qs)} quarters")

    frames = []
    for rep in qs:
        p = os.path.join(CACHE, f"fin_{rep}.csv")
        if os.path.exists(p) and os.path.getsize(p):
            frames.append(pd.read_csv(p))
    fin = pd.concat(frames, ignore_index=True)
    fin.to_csv(os.path.join(HERE, "fdic_panel.csv"), index=False)

    print(f"\npanel: {len(fin):,} bank-quarters, {fin['CERT'].nunique():,} institutions, "
          f"{fin['REPDTE'].nunique()} quarters")
    fl = fail.copy()
    fl["FAILDATE"] = pd.to_datetime(fl["FAILDATE"], errors="coerce")
    inwin = fl[(fl["FAILDATE"] >= f"{START_YEAR}-01-01") &
               (fl["FAILDATE"] <= f"{END_YEAR}-12-31")]
    print(f"failures inside the window: {len(inwin):,}")
    print(f"of those, matched to a call report: "
          f"{inwin['CERT'].isin(set(fin['CERT'])).sum():,}")


if __name__ == "__main__":
    main()
