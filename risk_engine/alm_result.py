"""The ALM one-year gap, tested within matched cohorts.

Figures transcribed by hand from each filing's printed maturity table, after
automated extraction failed on 3 of 5 failure filings and on several survivor
filings. Source file and the units of the original table are recorded per row.

Cohort A: housing finance companies, FY2017-18 accounts, reports published
          mid-2018. NHB maturity schedule.
Cohort B: other NBFCs, FY2019-20 accounts, reports published mid-2020.
          RBI maturity schedule.

Within a cohort, every firm files on the same regulator's ladder and in the
same filing season, so the <=1 year cumulative point is comparable.

gap_pct = (inflows<=1y - outflows<=1y) / total assets disclosed in the table
cover   = inflows<=1y / outflows<=1y
"""
import itertools, json, os

R = []


def add(name, cohort, pub, fail, outcome, inflow, outflow, assets,
        basis, reporting, src, note=""):
    R.append(dict(name=name, cohort=cohort, pub=pub, fail=fail,
                  outcome=outcome, inflow=inflow, outflow=outflow,
                  assets=assets, basis=basis, reporting=reporting,
                  src=src, note=note,
                  gap=inflow - outflow,
                  gap_pct=100.0 * (inflow - outflow) / assets,
                  cover=inflow / outflow))


S = sum
# ======================= COHORT A : HFCs, reports published mid-2018 ========
# DHFL  AR 2017-18 note 38.14, Rs lakh. FAILED 2019-06-04 (PRIMARY)
add("DHFL", "A", "2018-07-19", 1, "PRIMARY default 10.5m later",
    S([170086, 45856, 46240, 141019, 291821]) + S([687908, 0, 0, 0, 17285]),
    S([10735, 29915, 66060, 137736, 223841])
    + S([249912, 36284, 79234, 154522, 310595])
    + S([19655, 414227, 205383, 125436, 137845]) + S([0, 0, 0, 14794, 14794]),
    9193232 + 807650, "not stated", "standalone", "note 38.14 (Rs lakh)")

# Reliance Home Finance AR 2017-18 note 9, Rs crore. FAILED 2019-09-01
add("Reliance Home Fin", "A", "2018-09-20", 1, "PRIMARY default 11.3m later",
    S([385.05, 263.50, 100.71, 503.51, 1341.90]) + S([.01, .01, .01, .02, .04]),
    S([567.62, 355.04, 0, 221.62, 883.49]) + S([10.00, 339.97, 143.78, 136.95, 6.25]),
    14595.29 + 97.07, "behavioural", "standalone", "note 9 (Rs crore)",
    "asset timing uses management foreclosure estimates")

# LIC Housing Finance AR 2017-18 note 28, Rs lakh. SURVIVOR (AAA today)
add("LIC Housing Fin", "A", "2018-08-20", 0, "survivor",
    S([183571, 181987, 182376, 593756, 1321040]) + 0,
    S([6261, 15743, 4028, 104826, 219171])
    + S([0, 1928, 10719, 41283, 363575])
    + S([204484, 357429, 501816, 552708, 1409599]),
    16511406 + 102968, "NHB-prescribed", "standalone", "note 28 (Rs lakh)")

# Can Fin Homes AR 2017-18 note 28g, Rs lakh. SURVIVOR
add("Can Fin Homes", "A", "2018-07-25", 0, "survivor",
    S([5693.74, 4457.41, 12493.50, 13346.82, 41155.53, 90973.71])
    + S([0, 0, 0, 20.00, 895.00, 661.47]),
    S([0, 0, 1071.00, 2236.00, 37301.00, 90344.19])
    + S([0, 0, 0, 0, 8648.95, 17294.90])
    + S([1106.32, 361.46, 1284.26, 1030.92, 2884.51, 4105.59])
    + S([0, 20000.00, 29774.00, 34663.00, 118174.00, 149951.00]),
    1574299.19 + 3273.61, "NHB-prescribed", "standalone", "note 28g (Rs lakh)")

# PNB Housing Finance AR 2017-18, Rs crore. SURVIVOR
add("PNB Housing Fin", "A", "2018-07-30", 0, "survivor",
    S([1309.58, 1175.44, 1148.21, 3288.09, 5928.95])
    + S([1027.10, 191.17, 0, 0.09, 0.10]),
    S([435.59, 240.46, 185.90, 597.94, 1941.05])
    + S([1720.44, 112.73, 675.00, 335.70, 421.37])
    + S([2175.00, 1700.00, 3700.00, 1375.00, 1980.00])
    + S([0, 0, 12.52, 12.52, 25.05]),
    57078.33 + 2380.11, "NHB-prescribed", "standalone", "ALM note (Rs crore)")

# Repco Home Finance AR 2017-18 note 25.4.6, Rs crore. SURVIVOR
add("Repco Home Fin", "A", "2018-10-04", 0, "survivor",
    S([94.01, 51.07, 51.46, 156.58, 323.36]) + 0,
    S([811.78, 10.42, 52.23, 320.22, 542.24])
    + S([0, 400.00, 500.00, 350.00, 60.00]),
    9856.78 + 15.60, "NHB-prescribed", "standalone", "note 25.4.6 (Rs crore)")

# Indiabulls Housing AR 2017-18 note iv, Rs crore. SURVIVOR, near-failure 2019
add("Indiabulls Housing", "A", "2018-09-27", 0, "survivor (funding run 2019)",
    S([2506.84, 1554.91, 2173.24, 4760.02, 9241.38])
    + S([353.18, 1734.14, 3909.00, 4228.34, 1862.80])
    + S([0, 0, 0.77, 1.06, 0]),
    S([22.92, 1273.19, 1708.58, 3964.56, 4445.94])
    + S([368.00, 1762.00, 4109.00, 3727.00, 5188.83])
    + S([0, 0, 0, 95.22, 14.38]),
    112742.63 + 16358.47 + 59.24, "not stated", "standalone",
    "note iv (Rs crore)")

# ======================= COHORT B : NBFCs, reports published mid-2020 =======
# SREI Infrastructure AR 2019-20, Rs lakh. S4 2021-10-04
add("SREI Infrastructure", "B", "2020-08-28", 1, "S4 board superseded 13.2m later",
    S([1425, 0, 0, 0, 0, 5496, 0]),
    S([2990, 0, 85, 24753, 8436, 7517, 4645]),
    355301, "contractual", "standalone", "ALM note (Rs lakh)",
    "ZERO advances: lending book sits in SREI Equipment Finance")

# Reliance Capital AR 2019-20 note i, Rs crore. S4 2021-11-29
add("Reliance Capital", "B", "2020-06-01", 1, "S4 board superseded 17.9m later",
    S([0, 0, 102, 778, 764]) + S([32, 0, 5914, 5078, 0])
    + S([33, 0, 617, 3, 0]) + 6 + 18 + 1,
    S([34, 5, 0, 105, 9]) + S([1590, 482, 50, 676, 460])
    + S([1058, 262, 18, 184, 172]),
    6369 + 15177 + 689 + 6 + 18 + 1, "behavioural", "standalone",
    "note i (Rs crore)",
    "all quoted investments placed in <=1m; Rs 5,103cr NCDs already recalled "
    "by trustee at BS date but laddered at ORIGINAL maturity")

# Cholamandalam AR 2019-20 note 51, Rs lakh. SURVIVOR
add("Cholamandalam Inv", "B", "2020-07-08", 0, "survivor",
    S([10229, 4506, 29448, 28751, 41202, 229955, 884512]) + 0,
    S([27178, 4780, 40245, 22412, 73890, 269063, 722468])
    + S([1202, 1254, 39416, 79621, 114958, 14050, 209589]),
    5540273 + 7306, "contractual", "standalone", "note 51 (Rs lakh)")

# M&M Financial Services AR 2019-20 note XIV, Rs lakh. SURVIVOR
add("M&M Financial", "B", "2020-07-18", 0, "survivor",
    S([540634.79, 42040.84, 236176.26, 589818.93, 1103255.45])
    + S([324812.99, 1187.38, 1306.39, 2686.68, 5115.37]),
    S([10480.14, 10738.50, 12923.85, 40811.75, 90484.34])
    + S([164054.50, 53999.64, 224886.33, 420435.91, 832285.21])
    + S([0, 0, 0, 0, 18294.06]),
    6499347.04 + 591096.62, "contractual", "standalone", "note XIV (Rs lakh)")

# Bajaj Finance AR 2019-20 MD&A table 5, Rs crore. SURVIVOR
add("Bajaj Finance", "B", "2020-06-29", 0, "survivor",
    69496.0, 44985.0, 150486.0, "behavioural", "consolidated",
    "MD&A table 5 (Rs crore)",
    "different construction: balance-sheet-total presentation, capital "
    "counted as a >5y outflow; NOT the RBI note format")


def auc(pos, neg):
    """Mann-Whitney. Lower score = more distressed, so a good measure gives
    failures LOWER cover and AUC>0.5 when we rank by -cover."""
    if not pos or not neg:
        return None
    w = S(1.0 if p < n else 0.5 if p == n else 0.0
          for p, n in itertools.product(pos, neg))
    return w / (len(pos) * len(neg))


if __name__ == "__main__":
    for c, title in (("A", "COHORT A - housing finance cos, filed mid-2018"),
                     ("B", "COHORT B - other NBFCs, filed mid-2020")):
        rows = sorted((r for r in R if r["cohort"] == c), key=lambda x: x["cover"])
        print("\n" + "=" * 98)
        print(title)
        print("=" * 98)
        print(f"{'institution':22s} {'published':>11s} {'cover':>6s} {'gap/A':>8s} "
              f"{'basis':16s} outcome")
        print("-" * 98)
        for r in rows:
            flag = "FAIL" if r["fail"] else "    "
            print(f"{flag} {r['name'][:17]:17s} {r['pub']:>11s} {r['cover']:6.3f} "
                  f"{r['gap_pct']:7.1f}% {r['basis']:16s} {r['outcome']}")
        pos = [r["cover"] for r in rows if r["fail"]]
        neg = [r["cover"] for r in rows if not r["fail"]]
        a = auc(pos, neg)
        print(f"\n  failures {len(pos)}   survivors {len(neg)}   "
              f"AUC (ranking by lower cover = riskier) = "
              f"{a:.3f}" if a is not None else "")
        if a is not None:
            print(f"  worst-covered firm in cohort: {rows[0]['name']} "
                  f"({'FAILED' if rows[0]['fail'] else 'SURVIVED'})")

    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "alm_result.json"), "w") as fh:
        json.dump(R, fh, indent=1)
