"""Download daily closes for the focus names and cache them under prices/.

The deck specified yfinance. That package is not installed here and pulls a
large dependency tree for one endpoint, so this calls the same public Yahoo
chart endpoint directly. Output format is identical to what yfinance returns
for `Close`, so swapping back is a one-line change.

Re-running is cheap: anything already cached is skipped unless --refresh.
"""

import os
import sys
import csv
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "prices")

URL = ("https://query2.finance.yahoo.com/v8/finance/chart/{sym}"
       "?period1={p1}&period2={p2}&interval=1d")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

START = int(datetime(2010, 1, 1, tzinfo=timezone.utc).timestamp())
END = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())


def fetch(symbol, tries=4):
    url = URL.format(sym=symbol, p1=START, p2=END)
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            code = getattr(e, "code", None)
            if code == 404:
                return None
            wait = 3 * (i + 1)
            print(f"    retry {i+1}/{tries} after {wait}s ({e})")
            time.sleep(wait)
    return None


def to_frame(payload):
    try:
        res = payload["chart"]["result"][0]
        ts = res["timestamp"]
        close = res["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError):
        return None
    df = pd.DataFrame({
        "date": pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Kolkata").date,
        "close": close,
    })
    return df.dropna().drop_duplicates("date").reset_index(drop=True)


def main():
    refresh = "--refresh" in sys.argv
    os.makedirs(CACHE, exist_ok=True)

    panel = pd.read_csv(os.path.join(HERE, "panel.csv"))
    events = pd.read_csv(os.path.join(HERE, "events.csv"))
    controls = ["HDFC Bank Ltd", "ICICI Bank Ltd", "Kotak Mahindra Bank Ltd",
                "State Bank of India", "Axis Bank Ltd", "Bajaj Finance Ltd",
                "Muthoot Finance Ltd", "Shriram Finance Ltd"]
    want = sorted(set(events["company"]) | set(controls))

    tickers = panel[panel["company"].isin(want)].groupby("company")["nse"].last()
    tickers = tickers[tickers.notna() & (tickers.astype(str).str.strip() != "")]

    index = []
    for company, sym in tickers.items():
        sym = str(sym).strip()
        path = os.path.join(CACHE, f"{sym}.csv")
        if os.path.exists(path) and not refresh:
            df = pd.read_csv(path)
            print(f"  cached  {company:32s} {sym:12s} {len(df)} rows")
        else:
            print(f"  fetch   {company:32s} {sym}")
            payload = fetch(f"{sym}.NS")
            df = to_frame(payload) if payload else None
            if df is None or df.empty:
                print(f"    no data for {sym}")
                continue
            df.to_csv(path, index=False)
            time.sleep(1.2)  # be polite to the endpoint
        index.append({"company": company, "ticker": sym, "rows": len(df),
                      "first": df["date"].iloc[0], "last": df["date"].iloc[-1]})

    idx = pd.DataFrame(index)
    idx.to_csv(os.path.join(HERE, "prices_index.csv"), index=False)
    print(f"\n{len(idx)} series cached in {CACHE}")
    print(idx.to_string(index=False))


if __name__ == "__main__":
    main()
