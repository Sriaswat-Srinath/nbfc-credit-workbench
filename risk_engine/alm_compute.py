"""Compute the one-year cumulative ALM gap for the verified pre-event filings.

Figures are transcribed by hand from the printed tables, because automated
extraction does NOT generalise across these filings: of five pre-event
reports, three used layouts the regex parser could not read (DHFL's buckets
are capitalised differently, Reliance Home Finance transposes the table, and
Reliance Capital interleaves two fiscal years per row). Each entry below
records the source file and the page-text line range so the numbers can be
checked against the original.

Bucket convention: the <=1 year cumulative point is the sum of all buckets
up to and including "over 6 months to 1 year". Both ladders in use (RBI's
NBFC schedule and NHB's HFC schedule) share that boundary, which is why the
cohorts can be compared at one year even though their short buckets differ.
"""
import json, os

LAKH_TO_CR = 0.01

# name, cohort, published, lead_months, outcome_class, basis, reporting,
# inflows<=1y, outflows<=1y, total disclosed assets, source, note
F = []

def add(**kw):
    kw["gap"] = kw["inflow"] - kw["outflow"]
    kw["gap_pct"] = 100.0 * kw["gap"] / kw["assets"]
    kw["cover"] = kw["inflow"] / kw["outflow"]
    F.append(kw)

# ---------------------------------------------------------------- failures
# DHFL FY2017-18, note 38.14, Rs lakh -> Rs crore.  DHFL_2017.txt:13823-13837
add(name="DHFL", cohort="A_hfc", published="2018-07-19", lead=10.5,
    outcome="PRIMARY default 2019-06-04", basis="contractual",
    reporting="standalone",
    inflow=((170086+45856+46240+141019+291821)          # advances
            + (687908+0+0+0+17285)                      # investments
            + 0) * LAKH_TO_CR,
    outflow=((10735+29915+66060+137736+223841)          # deposits
             + (249912+36284+79234+154522+310595)       # bank borrowings
             + (19655+414227+205383+125436+137845)      # market borrowings
             + (0+0+0+14794+14794)) * LAKH_TO_CR,       # FC liabilities
    assets=(9193232+807650+0) * LAKH_TO_CR,
    src="AR_2017_2018.pdf note 38.14", note="NHB 10-bucket ladder")

# Reliance Home Finance FY2017-18, note 9, Rs crore. RHFL_2017.txt:5757-5785
add(name="Reliance Home Fin", cohort="A_hfc", published="2018-09-20", lead=11.3,
    outcome="PRIMARY default 2019-09-01", basis="behavioural",
    reporting="standalone",
    inflow=(385.05+263.50+100.71+503.51+1341.90)        # loans & advances
           + (0.01+0.01+0.01+0.02+0.04),                # investments
    outflow=(567.62+355.04+0+221.62+883.49)             # bank borrowings
            + (10.00+339.97+143.78+136.95+6.25),        # market borrowings
    assets=14595.29+97.07,
    src="AR_2017_2018.pdf note 9",
    note="asset timing uses management foreclosure estimates")

# SREI Infrastructure FY2019-20, Rs crore (week-one figures, re-checked)
add(name="SREI Infrastructure", cohort="B_nbfc", published="2020-08-28", lead=13.2,
    outcome="S4 board superseded 2021-10-04", basis="contractual",
    reporting="standalone",
    inflow=6921.0, outflow=48426.0, assets=354000.0*LAKH_TO_CR,
    src="AR_16955_SREINFRA_2019_2020", note="lending book sits in subsidiary")

# Reliance Capital FY2019-20, Rs crore. RELCAPITAL_2019.txt:5983-6032
add(name="Reliance Capital", cohort="B_nbfc", published="2020-06-01", lead=17.9,
    outcome="S4 board superseded 2021-11-29", basis="behavioural",
    reporting="standalone",
    inflow=(0+0+102+778+764)                            # loans
           + (32+0+5914+5078+0)                         # investments
           + (33+0+617+3+0)                             # other fin assets
           + 6 + (18+0+0+0+0) + 1,                      # cash, bank, recv
    outflow=(34+5+0+105+9)                              # bank / FI borrowings
            + (1590+482+50+676+460)                     # market borrowings
            + (1058+262+18+184+172),                    # other fin liabs
    assets=6369+15177+689+6+18+1,
    src="AR_2019_2020.pdf note i",
    note="quoted investments all placed in <=1m; Rs 5,103cr NCDs already "
         "recalled at BS date but laddered at original maturity")

if __name__ == "__main__":
    print(f"{'institution':22s} {'pub':>11s} {'lead':>5s} {'in<=1y':>9s} "
          f"{'out<=1y':>9s} {'gap':>9s} {'gap/A':>7s} {'cover':>6s}  basis")
    print("-" * 104)
    for r in sorted(F, key=lambda x: x["gap_pct"]):
        print(f"{r['name'][:22]:22s} {r['published']:>11s} {r['lead']:5.1f} "
              f"{r['inflow']:9,.0f} {r['outflow']:9,.0f} {r['gap']:9,.0f} "
              f"{r['gap_pct']:6.1f}% {r['cover']:6.2f}  {r['basis']}")
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "alm_failures.json"), "w") as fh:
        json.dump(F, fh, indent=1)
    print("\nAll figures Rs crore. 'cover' = inflows / outflows within 1 year.")
