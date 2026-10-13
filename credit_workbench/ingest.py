"""Fetch and cache the primary evidence for each issuer.

Three sources, all from NSE, all carrying a real dissemination timestamp:

  1. corporate-announcements      categorised disclosure stream, 2004 onwards,
                                  with the attachment PDF URL
  2. corporates-financial-results index of every quarterly/annual result
                                  filing, with the standalone/consolidated
                                  flag, the audited flag, and a link to XBRL
  3. the XBRL instance per filing  tagged figures, so no PDF parsing

Everything is cached on disk and the script is resumable: re-running only
fetches what is missing. Nothing is imputed and nothing is rewritten; the
cache is the evidence, and every figure the product later shows points back
to a file here.
"""
import json
import os
import subprocess
import sys
import time

from universe import ISSUERS

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")
BASE = "https://www.nseindia.com/api"
MAX_XBRL = 90          # per issuer; DHFL's full history is 73 filings


def curl(url, timeout=60):
    cmd = ["curl", "-sL", "--max-time", str(timeout - 10), "-A", UA,
           "-H", "Referer: https://www.nseindia.com/", url]
    for _ in range(3):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            time.sleep(3)
            continue
        if r.stdout:
            return r.stdout
        time.sleep(3)
    return b""


def cached_json(path, url, force=False):
    if not force and os.path.exists(path) and os.path.getsize(path) > 3:
        try:
            return json.load(open(path))
        except Exception:
            pass
    raw = curl(url)
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except Exception:
        return None
    with open(path, "wb") as fh:
        fh.write(raw)
    return d


def main(only=None):
    os.makedirs(CACHE, exist_ok=True)
    summary = []
    for sym, name, *_ in ISSUERS:
        if only and sym != only:
            continue
        d = os.path.join(CACHE, sym)
        os.makedirs(os.path.join(d, "xbrl"), exist_ok=True)

        ann = cached_json(os.path.join(d, "announcements.json"),
                          f"{BASE}/corporate-announcements"
                          f"?index=equities&symbol={sym}")
        res = cached_json(os.path.join(d, "results.json"),
                          f"{BASE}/corporates-financial-results"
                          f"?index=equities&symbol={sym}&period=Quarterly")
        ann = ann or []
        res = res or []

        # XBRL instances, newest first, capped
        got, miss = 0, 0
        for row in res[:MAX_XBRL]:
            u = (row.get("xbrl") or "").strip()
            if not u.lower().endswith(".xml"):
                miss += 1
                continue
            fn = os.path.join(d, "xbrl", os.path.basename(u))
            if os.path.exists(fn) and os.path.getsize(fn) > 500:
                got += 1
                continue
            raw = curl(u)
            if raw and raw.lstrip()[:5] == b"<?xml":
                with open(fn, "wb") as fh:
                    fh.write(raw)
                got += 1
                time.sleep(0.3)
            else:
                miss += 1
        print(f"{sym:12s} announcements {len(ann):5d}  results {len(res):4d}  "
              f"xbrl {got:3d} cached, {miss:3d} unavailable", flush=True)
        summary.append({"symbol": sym, "name": name, "announcements": len(ann),
                        "results": len(res), "xbrl": got, "xbrl_missing": miss})

    with open(os.path.join(CACHE, "ingest_summary.json"), "w") as fh:
        json.dump(summary, fh, indent=1)
    print(f"\n{sum(s['xbrl'] for s in summary)} XBRL instances, "
          f"{sum(s['announcements'] for s in summary)} announcements cached")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
