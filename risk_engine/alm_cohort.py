"""Matched-cohort download: survivors from the SAME filing season as each failure.

Two cohorts, because housing finance companies and other NBFCs file on
DIFFERENT maturity ladders (NHB's schedule vs RBI's). Comparing an HFC's
buckets with an NBFC's is not valid in the short buckets. They do reconcile
at the one-year cumulative point, which is where the measure is taken, but
the cohorts are kept separate anyway.

  Cohort A  FY2017-18, published mid-2018   HFCs
            failures: DHFL, Reliance Home Finance
  Cohort B  FY2019-20, published mid-2020   NBFCs
            events:   SREI Infrastructure, Reliance Capital (both S4)
"""
import os, re, json, time, zipfile, subprocess, urllib.parse
import datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "alm")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")
API = "https://www.nseindia.com/api/annual-reports?index=equities&symbol={}"

COHORT = {
    "A_hfc_fy2018": ("2017", ["LICHSGFIN", "PNBHOUSING", "CANFINHOME",
                              "GICHSGFIN", "REPCOHOME", "IBULHSGFIN",
                              "SAMMAANCAP", "HUDCO"]),
    "B_nbfc_fy2020": ("2019", ["BAJFINANCE", "MUTHOOTFIN", "CHOLAFIN",
                               "SHRIRAMFIN", "SRTRANSFIN", "M&MFIN",
                               "LTFH", "MANAPPURAM", "PFC", "RECLTD"]),
}


def curl(url, out=None, timeout=300):
    cmd = ["curl", "-sL", "--max-time", str(timeout - 30), "-A", UA,
           "-H", "Referer: https://www.nseindia.com/"]
    if out:
        cmd += ["-o", out]
    cmd.append(url)
    for _ in range(2):
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


def pub_ts(fname, broadcast):
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
            pass
    return None


def to_pdf(tag, url):
    raw = os.path.join(CACHE, tag + ".bin")
    if not os.path.exists(raw) or os.path.getsize(raw) < 20000:
        if not curl(url, raw):
            return None
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


def main():
    os.makedirs(CACHE, exist_ok=True)
    out = []
    for cohort, (fy, syms) in COHORT.items():
        print(f"\n===== {cohort}  (fiscal from {fy}) =====")
        for sym in syms:
            raw = curl(API.format(urllib.parse.quote(sym)))
            try:
                data = json.loads(raw).get("data", [])
            except Exception:
                print(f"  {sym:12s} no index")
                continue
            hit = None
            for r in data:
                if str(r.get("fromYr")) == fy:
                    hit = r
                    break
            if not hit:
                yrs = sorted({str(r.get("fromYr")) for r in data})
                print(f"  {sym:12s} no FY{fy} report (has {','.join(yrs[-6:])})")
                continue
            ts = pub_ts(hit["fileName"], hit.get("broadcast_dttm"))
            tag = f"{re.sub(r'[^A-Za-z0-9]', '', sym)}_{fy}"
            p = to_pdf(tag, hit["fileName"])
            if not p:
                print(f"  {sym:12s} FY{fy} download failed")
                continue
            txt = subprocess.run(["pdftotext", "-layout", p, "-"],
                                 capture_output=True, timeout=400
                                 ).stdout.decode("utf8", "replace")
            tf = os.path.join(CACHE, tag + ".txt")
            with open(tf, "w") as fh:
                fh.write(txt)
            has = len(re.findall(r"(?i)maturity pattern", txt))
            print(f"  {sym:12s} FY{fy} pub {ts:%Y-%m-%d}  "
                  f"{len(txt):>9,} chars  'maturity pattern' x{has}")
            out.append({"cohort": cohort, "symbol": sym, "fiscal_from": fy,
                        "published": ts.isoformat() if ts else None,
                        "url": hit["fileName"], "txt": tf,
                        "mentions": has, "chars": len(txt)})
            time.sleep(1)
    with open(os.path.join(HERE, "alm_cohort.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"\n{len(out)} survivor reports fetched")


if __name__ == "__main__":
    main()
