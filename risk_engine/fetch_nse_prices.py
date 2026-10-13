"""Build a daily price panel for the listed institutions, from NSE's own archive.

Why not yfinance / Yahoo
------------------------
The project brief suggests yfinance. Yahoo's endpoint IP-throttled this machine
(HTTP 429 on every attempt) and the usual fallback gates behind a bot
challenge. NSE publishes its daily bhavcopy as plain static ZIPs, which is the
primary source Yahoo itself derives from, so this reads that directly.

One bhavcopy holds every symbol traded that day, so a single request covers all
~180 listed institutions in the panel at once. Each file is cached under
bhavcopy/, and days with no file (market holidays) are negative-cached so they
are never retried.

A note on PREVCLOSE
------------------
An earlier version of this pipeline sampled weekly and assumed bhavcopy's
PREVCLOSE was adjusted for corporate actions. It is not: on Yes Bank's split
day the file reports CLOSE 377.05 against PREVCLOSE 1880.10, the raw drop.
Split detection therefore works off single-day ratios on the full daily series
instead -- see resolve_splits.py.
"""

import io
import os
import sys
import csv
import time
import zipfile
import datetime as dt
import urllib.error
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "bhavcopy")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")
URL = ("https://nsearchives.nseindia.com/content/historical/EQUITIES/"
       "{y}/{M}/cm{d:02d}{M}{y}bhav.csv.zip")
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

START = dt.date(2013, 1, 1)
END = dt.date(2023, 12, 31)
DELAY = 0.35


def url_for(day):
    return URL.format(y=day.year, M=MONTHS[day.month - 1], d=day.day)


def fetch_day(day, tries=2):
    """Bhavcopy CSV text for `day`, or None if NSE has no file (holiday)."""
    req = urllib.request.Request(url_for(day), headers={
        "User-Agent": UA, "Accept": "*/*",
        "Referer": "https://www.nseindia.com/",
    })
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                return z.read(z.namelist()[0]).decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
            time.sleep(2 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, zipfile.BadZipFile, OSError):
            time.sleep(2 * (attempt + 1))
    return None


def wanted_symbols():
    panel = pd.read_csv(os.path.join(HERE, "panel.csv"))
    s = panel["nse"].dropna().astype(str).str.strip()
    return set(s[s != ""])


def day_file(day):
    return os.path.join(CACHE, f"{day:%Y-%m-%d}.csv")


def ensure_day(day, syms):
    """Fetch and cache one day's rows for the tracked symbols. Returns rows or None."""
    path = day_file(day)
    if os.path.exists(path):
        return None if os.path.getsize(path) == 0 else pd.read_csv(path)

    text = fetch_day(day)
    time.sleep(DELAY)
    if not text:
        open(path, "w").write("")          # holiday / no file: never retry
        return None

    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        sym = (r.get("SYMBOL") or "").strip()
        if sym in syms and (r.get("SERIES") or "").strip() == "EQ":
            rows.append({"date": day.isoformat(), "symbol": sym,
                         "close": r.get("CLOSE"), "prevclose": r.get("PREVCLOSE")})
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    return df


def consolidate():
    frames = []
    for f in sorted(os.listdir(CACHE)):
        p = os.path.join(CACHE, f)
        if not f.endswith(".csv") or os.path.getsize(p) == 0:
            continue
        frames.append(pd.read_csv(p))
    if not frames:
        sys.exit("no bhavcopy data collected")

    px = pd.concat(frames, ignore_index=True)
    px["date"] = pd.to_datetime(px["date"])
    for c in ("close", "prevclose"):
        px[c] = pd.to_numeric(px[c], errors="coerce")
    px = (px.dropna(subset=["close"])
            .sort_values(["symbol", "date"])
            .drop_duplicates(["symbol", "date"]))
    out = os.path.join(HERE, "prices_daily.csv")
    px.to_csv(out, index=False)
    print(f"wrote {out}: {len(px):,} rows, {px['symbol'].nunique()} symbols, "
          f"{px['date'].min():%Y-%m-%d} .. {px['date'].max():%Y-%m-%d}, "
          f"{px['date'].nunique():,} trading days")
    return px


def main():
    os.makedirs(CACHE, exist_ok=True)
    syms = wanted_symbols()
    print(f"tracking {len(syms)} NSE symbols from the panel")

    days = [d.date() for d in pd.bdate_range(START, END)]
    missing = [d for d in days if not os.path.exists(day_file(d))]
    print(f"{len(days)} weekdays in range, {len(missing)} not yet cached")

    for i, d in enumerate(missing, 1):
        ensure_day(d, syms)
        if i % 50 == 0 or i == len(missing):
            print(f"  filled {i}/{len(missing)}")

    consolidate()


if __name__ == "__main__":
    main()
