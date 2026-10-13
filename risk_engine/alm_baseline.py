"""Compare the ladder-based gap against the pre-registered baselines, and
report exact p-values, because n is 2 failures per cohort.

Baseline B4 is the one that matters: the share of total borrowings falling due
within one year. It needs only the borrowings rows, not the full ten-bucket
ladder. If B4 does as well, parsing the ladder buys nothing.
"""
import itertools
from alm_result import R

# total borrowings (all buckets) per filing, transcribed from the Total column
TOTAL_BORROWINGS = {
    "DHFL": (1033949 + 4204894 + 3736226 + 296476),          # lakh
    "Reliance Home Fin": (5645.19 + 7512.17),                # crore
    "LIC Housing Fin": (678973 + 1435881 + 12418003),        # lakh
    "Can Fin Homes": (463573.61 + 208309.54 + 22830.41 + 697762.00),
    "PNB Housing Fin": (11586.20 + 8489.58 + 32725.00 + 1467.56),
    "Repco Home Fin": (6000.01 + 2137.00),
    "Indiabulls Housing": (40629.74 + 62784.30 + 440.66),
    "SREI Infrastructure": 48426,
    "Reliance Capital": (624 + 16821 + 1700),
    "Cholamandalam Inv": 5500543,
    "M&M Financial": (881213.98 + 4772943.67 + 292072.90),
    "Bajaj Finance": 108441,
}


def auc(pos, neg, higher_is_riskier):
    s = 1 if higher_is_riskier else -1
    w = sum(1.0 if s * p > s * n else 0.5 if p == n else 0.0
            for p, n in itertools.product(pos, neg))
    return w / (len(pos) * len(neg))


def exact_p(vals, labels, higher_is_riskier):
    """Exact permutation: how many label assignments give an AUC at least as
    extreme? With n this small every arrangement can be enumerated."""
    k = sum(labels)
    obs = auc([v for v, l in zip(vals, labels) if l],
              [v for v, l in zip(vals, labels) if not l], higher_is_riskier)
    idx = range(len(vals))
    arr = list(itertools.combinations(idx, k))
    ge = sum(1 for c in arr
             if auc([vals[i] for i in c],
                    [vals[i] for i in idx if i not in c],
                    higher_is_riskier) >= obs)
    return obs, ge / len(arr), len(arr)


for c, title in (("A", "COHORT A - HFCs, filed mid-2018"),
                 ("B", "COHORT B - NBFCs, filed mid-2020")):
    rows = [r for r in R if r["cohort"] == c]
    labels = [r["fail"] for r in rows]
    print("\n" + "=" * 92)
    print(f"{title}   ({sum(labels)} failures / {len(labels)-sum(labels)} survivors)")
    print("=" * 92)

    measures = [
        ("ALM cover (in/out <=1y)",
         [r["cover"] for r in rows], False),
        ("ALM gap / assets",
         [r["gap_pct"] for r in rows], False),
        ("B4 short-borrowings share",
         [100.0 * r["outflow"] / TOTAL_BORROWINGS[r["name"]] for r in rows], True),
        ("B3 outflow / assets (leverage proxy)",
         [100.0 * r["outflow"] / r["assets"] for r in rows], True),
    ]
    print(f"{'measure':38s} {'AUC':>6s} {'exact p':>9s}   failures vs survivors")
    print("-" * 92)
    for name, vals, hir in measures:
        a, p, n = exact_p(vals, labels, hir)
        pv = [f"{v:.2f}" for v, l in zip(vals, labels) if l]
        nv = [f"{v:.2f}" for v, l in zip(vals, labels) if not l]
        print(f"{name:38s} {a:6.3f} {p:9.3f}   [{', '.join(pv)}] vs "
              f"[{', '.join(nv)}]")
    print(f"  ({n} possible label assignments enumerated; "
          f"the smallest attainable p is {1/n:.3f})")
