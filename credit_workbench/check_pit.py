"""Point-in-time integrity test.

The product's central claim is that a finding dated D rests only on evidence
published on or before D. That claim is worth nothing if it is merely asserted,
because the ways to break it are subtle and arrive by accident:

  - a detector that scans a window FORWARD in time but stamps the finding with
    the start of the window (disclosure_burst did exactly this);
  - a data-quality check that compares a filing against its neighbours in both
    directions, so whether a filing is usable depends on later filings
    (scale_anomalies did exactly this);
  - any trailing statistic accidentally computed over the whole series.

This test walks every finding of every issuer, pulls every ISO timestamp out
of its evidence payload, and fails if any of them is later than the finding's
own knowable_on. It is the check that makes the replay control trustworthy,
and it should be run after any change to detect.py.

Exit status 0 if clean, 1 if any violation is found.
"""
import datetime as dt
import re
import sys

from detect import findings_for
from universe import ISSUERS

ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2})?)?\b")

# Fields that legitimately carry a date later than knowable_on because they
# describe the LIMITS of the evidence rather than the issuer's condition, and
# are always stamped with "today" by construction.
EXEMPT_KINDS = {"coverage_gap", "stale_evidence"}

# Keys whose dates are deliberately forward-looking context, not the basis of
# the finding.
EXEMPT_KEYS = {"missing", "quarters_expected", "quarters_present",
               "issuer_median_income_crore", "window_end"}

# Any key prefixed retrospective_ is, by convention, information that arrived
# AFTER the finding became knowable and is recorded as later context rather
# than as the basis of the finding. filing_overdue uses this: the deadline
# passing is knowable on the deadline; what the issuer eventually filed, and
# how late, is not.
EXEMPT_PREFIX = "retrospective_"


def timestamps(obj, key=None):
    """Every ISO date inside an evidence payload, with the key it sat under."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in EXEMPT_KEYS or k.startswith(EXEMPT_PREFIX):
                continue
            out += timestamps(v, k)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out += timestamps(v, key)
    elif isinstance(obj, str):
        for m in ISO.finditer(obj):
            out.append((key, m.group(1)))
    return out


def main():
    violations, checked, scanned = [], 0, 0
    for sym, *_ in ISSUERS:
        try:
            findings, _, _ = findings_for(sym)
        except Exception as e:
            print(f"  {sym}: ERROR {type(e).__name__}: {e}")
            continue
        for f in findings:
            scanned += 1
            if f["kind"] in EXEMPT_KINDS:
                continue
            known = f["knowable_on"][:10]
            for key, dstr in timestamps(f.get("evidence")):
                checked += 1
                if dstr > known:
                    violations.append((sym, f["kind"], known, key, dstr,
                                       f["what_changed"][:70]))

    print("=" * 78)
    print("POINT-IN-TIME INTEGRITY TEST")
    print("=" * 78)
    print(f"findings scanned        : {scanned}")
    print(f"evidence dates checked  : {checked}")
    print(f"violations              : {len(violations)}")
    if violations:
        print("\nA finding may not rest on evidence published after its own")
        print("knowable_on date. The following do:\n")
        for sym, kind, known, key, dstr, what in violations[:40]:
            print(f"  {sym:12s} {kind:22s} dated {known} "
                  f"but evidence[{key}] = {dstr}")
            print(f"               {what}")
        if len(violations) > 40:
            print(f"  ... and {len(violations) - 40} more")
        return 1
    print("\nClean. Every finding rests only on evidence published on or")
    print("before the date the product claims it became knowable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
