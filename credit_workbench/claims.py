"""Quantified promises management made, and the date each one came due.

The gap this closes:

  On 1 March 2019 Reliance Capital told the market it expected Rs 10,000-12,000
  crore from asset sales "within the next three to four months". The sales did
  not happen; the company was referred to resolution in November 2021. The
  claim was public, dated, specific and falsifiable, and no credit file
  anywhere recorded it as an open commitment with a deadline.

  That is the asymmetry this module attacks. An issuer under pressure makes
  forward statements continually - a disposal, a capital raise, a deleveraging
  target - and the market reads them when they are made and never again. The
  statement that matters is the one whose deadline passed in silence.

So: find quantified forward-looking statements with a horizon, compute the date
each falls due, and keep them as an open book. A claim whose deadline has
passed is a question for the analyst - "this was promised by then; was it
delivered?" - which is a different kind of finding from the rest of the
workbench, and deliberately so. It asserts nothing about the outcome.

Three limits, stated because they bound what this can be used for:

  * A claim is extracted only when BOTH a figure and a horizon are present.
    "We expect to deleverage significantly" has no deadline and no amount, and
    is not a claim this module can test. Across 25,919 announcements the
    exchange summary alone yields 6 such claims; the rest are in the
    attachment, which is why this module fetches them.
  * The horizon is read literally. "Within three to four months" becomes the
    later bound, four months, because the earlier bound is not the promise.
  * Delivery is NOT inferred from the figures. A fall in total assets after a
    disposal claim is consistent with the disposal and also with a write-down,
    and the workbench does not guess between them. Where an annual balance
    sheet published after the deadline lets the direction be checked, that
    comparison is attached to the finding as context, labelled as such.

Everything is cached under cache/<SYM>/claims.json.

Run:  python3 claims.py            all issuers
      python3 claims.py RELCAPITAL one issuer
      RECLASSIFY=1 python3 claims.py     re-extract from cached PDFs
"""
import collections
import datetime as dt
import json
import os
import re
import sys
import time

from announcements import load_announcements
from attachments import curl, pdf_text
from universe import ISSUERS

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

# Where management speaks in its own voice. Board outcomes and record-date
# notices are procedural and carry no forward statements worth testing.
CATEGORIES = {"Press Release", "Investor Presentation", "Media Release",
              "Press Release / Media Release"}

NUM_WORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
            "twelve": 12, "eighteen": 18, "twenty": 20, "twentyfour": 24,
            "a": 1, "an": 1, "couple": 2, "few": 3}

# A forward-looking commitment, not a report of what happened. "We have sold"
# is history; "we expect to sell" is a claim.
INTENT = (r"expect\w*|anticipat\w*|target\w*|intend\w*|plan\w*|aim\w*|"
          r"propose\w*|envisag\w*|project\w*|likely to|on track to|"
          r"confident of|committed to|will (?:be )?(?:raise|reduce|sell|"
          r"complete|monetis\w+|monetiz\w+)|guidance of|expects? to")

AMOUNT = (r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*"
          r"(?:(?:to|-|–|and)\s*([\d,]+(?:\.\d+)?)\s*)?"
          r"(crore|cr\b|lakh|lac|billion|bn|million|mn)")

# Both bounds of a range may be written as words - "three to four months" is
# how Reliance Capital's March 2019 statement is phrased, and an earlier
# version accepted only digits for the second bound, so the one claim this
# module exists to catch was the one it missed.
_NUM = r"\d{1,2}|" + "|".join(sorted(NUM_WORD, key=len, reverse=True))
HORIZON = (r"(?:with ?in|by|over|during|in)\s+(?:the\s+)?(?:next\s+)?"
           r"(?:(" + _NUM + r")\s*"
           r"(?:to|-|–|or)?\s*(" + _NUM + r")?\s*"
           r"(month|months|quarter|quarters|year|years|week|weeks|day|days|"
           r"fortnight)"
           r"|(?:end of\s+)?(?:FY\s?'?(\d{2,4})|Q([1-4])\s*FY\s?'?(\d{2,4})|"
           r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*"
           r"'?(\d{2,4})?))")

# The three claim types that bear on credit, named so a finding can say which.
SUBJECT = [
    ("asset_sale", re.compile(r"(?i)\b(asset sale|sale of asset|divest\w*|"
                              r"monetis\w+|monetiz\w+|stake sale|sell(?:ing)? "
                              r"(?:our|its|the) |disposal|exit from)")),
    ("capital_raise", re.compile(r"(?i)\b(capital raise|raise (?:of )?(?:up "
                                 r"to )?(?:rs|inr|₹|equity|capital|funds)|"
                                 r"fund rais\w+|rights issue|QIP|preferential "
                                 r"allot\w+|infus\w+)")),
    ("debt_reduction", re.compile(r"(?i)\b(reduce (?:our |its |the )?(?:debt|"
                                  r"borrowings|leverage)|deleverag\w+|debt "
                                  r"reduction|repay\w* (?:of )?(?:debt|"
                                  r"borrowings)|bring down (?:our |its )?debt)")),
    ("growth_target", re.compile(r"(?i)\b(loan book|AUM|disbursement\w*|"
                                 r"book size|balance sheet) (?:of|to|will)")),
]

UNIT = {"crore": 1e7, "cr": 1e7, "lakh": 1e5, "lac": 1e5,
        "billion": 1e9, "bn": 1e9, "million": 1e6, "mn": 1e6}

SENT = re.compile(r"(?<=[.;!?])\s+")
RECLASSIFY = os.environ.get("RECLASSIFY") == "1"

CLAIM_RE = re.compile(r"(?i)(?=.*(?:" + INTENT + r"))"
                      r"(?=.*" + AMOUNT + r")"
                      r"(?=.*" + HORIZON + r")", re.S)
AMOUNT_RE = re.compile("(?i)" + AMOUNT)
HORIZON_RE = re.compile("(?i)" + HORIZON)
INTENT_RE = re.compile("(?i)" + INTENT)


def _n(tok):
    if tok is None:
        return None
    tok = tok.strip().lower()
    if tok.isdigit():
        return int(tok)
    return NUM_WORD.get(tok)


def due_from(horizon_match, base):
    """The date a horizon resolves to, relative to the statement's own date.

    A range takes its LATER bound: "three to four months" is a promise by four
    months, not by three.
    """
    g = horizon_match.groups()
    a, b, unit, fy, q, qfy, mon, mony = g[0], g[1], g[2], g[3], g[4], g[5], g[6], g[7]
    if unit:
        n = _n(b) or _n(a)
        if n is None:
            return None, None
        days = {"day": 1, "days": 1, "week": 7, "weeks": 7, "fortnight": 14,
                "month": 30, "months": 30, "quarter": 91, "quarters": 91,
                "year": 365, "years": 365}[unit.lower()]
        return (base + dt.timedelta(days=n * days)).isoformat(), \
            f"{n} {unit.lower()}"
    if fy:
        y = int(fy)
        y += 2000 if y < 70 else (1900 if y < 100 else 0)
        # an Indian fiscal year labelled FY20 ends 31 March 2020
        return dt.date(y, 3, 31).isoformat(), f"FY{fy}"
    if q and qfy:
        y = int(qfy)
        y += 2000 if y < 70 else (1900 if y < 100 else 0)
        qend = {1: (6, 30), 2: (9, 30), 3: (12, 31), 4: (3, 31)}[int(q)]
        yy = y if int(q) != 4 else y
        return dt.date(yy if int(q) != 4 else y, *qend).isoformat(), \
            f"Q{q} FY{qfy}"
    if mon:
        mi = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
              "oct", "nov", "dec"].index(mon.lower()[:3]) + 1
        y = int(mony) if mony else base.year
        if y < 100:
            y += 2000
        # a month named without a year means the next occurrence
        d = dt.date(y, mi, 28)
        if not mony and d < base:
            d = dt.date(y + 1, mi, 28)
        return d.isoformat(), f"{mon.title()} {y}"
    return None, None


def subject_of(s):
    for name, rx in SUBJECT:
        if rx.search(s):
            return name
    return None


def amount_of(s):
    m = AMOUNT_RE.search(s)
    if not m:
        return None, None, None
    mult = UNIT[m.group(3).lower().rstrip(".")]
    try:
        lo = float(m.group(1).replace(",", "")) * mult
        hi = float(m.group(2).replace(",", "")) * mult if m.group(2) else None
    except ValueError:
        return None, None, None
    return lo, hi, m.group(0)


# Scanned faxes. DHFL's press releases up to 2015 arrive as images put
# through OCR that renders "The Manager" as "l'he Manager" and loses every
# figure. Reporting "no claims" for such a document would be wrong in the way
# that matters - it is not that the issuer made none, it is that the document
# cannot be read - so the quality is measured and recorded.
def legible(flat):
    if len(flat) < 120:
        return False, "document contains almost no extractable text"
    words = flat.split()
    good = sum(1 for w in words if w.isalpha() and 2 <= len(w) <= 14)
    if good < 0.45 * len(words):
        return False, "text is mostly unreadable, probably a scan"
    return True, None


def windows(sents, span=3, cap=700):
    """Runs of up to `span` consecutive sentences, shortest first.

    A press release rarely puts the intent, the figure and the deadline in one
    sentence - "The Company has approved a plan to divest its stake. Proceeds
    of around Rs 2,000 crore are expected within six months." Requiring all
    three in a single sentence found 0 claims in 162 real documents while
    passing every unit test, which is how the constraint survived to here.
    The window is reported on each claim so a wide one can be discounted.
    """
    for n in range(1, span + 1):
        for i in range(len(sents) - n + 1):
            w = " ".join(sents[i:i + n])
            if 40 <= len(w) <= cap:
                yield w, n


def extract(text, base_date):
    """Every dated, quantified forward statement in the document."""
    flat = " ".join((text or "").split())
    ok, _why = legible(flat)
    if not ok:
        return []
    out = []
    taken = {}
    for s, span in windows(SENT.split(flat)):
        if not (INTENT_RE.search(s) and AMOUNT_RE.search(s)):
            continue
        hm = HORIZON_RE.search(s)
        if not hm:
            continue
        due, horizon = due_from(hm, base_date)
        if not due or due <= base_date.isoformat():
            continue
        lo, hi, amt_text = amount_of(s)
        if lo is None:
            continue
        # One promise, not one per window that happens to contain it. The
        # same figure and deadline reached by a narrower window that missed
        # the subject must not survive alongside the wider one that found it.
        key = (due, lo)
        subj = subject_of(s)
        prev = taken.get(key)
        if prev is not None and (prev["subject"] or not subj):
            continue
        if prev is not None:
            out.remove(prev)
        out.append({"claim": s[:450], "subject": subj,
                    "amount_low": lo, "amount_high": hi,
                    "amount_text": amt_text, "horizon": horizon,
                    "due": due, "sentences_spanned": span})
        taken[key] = out[-1]
    # one claim per (subject, due, amount) - a press release repeats itself
    seen, uniq = set(), []
    for c in out:
        k = (c["subject"], c["due"], c["amount_low"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    return uniq


def process(sym, verbose=True):
    d = os.path.join(CACHE, sym, "attachments")
    os.makedirs(d, exist_ok=True)
    store = os.path.join(CACHE, sym, "claims.json")
    done = {}
    if os.path.exists(store):
        try:
            done = {r["ts"]: r for r in json.load(open(store))}
        except Exception:
            done = {}

    todo = [a for a in load_announcements(sym)
            if a["category"] in CATEGORIES
            and (a["attachment"] or "").startswith("http")]

    fetched = 0
    for a in todo:
        if a["ts"] in done and done[a["ts"]].get("state") != "unfetched" \
                and not RECLASSIFY:
            continue
        url = a["attachment"]
        fn = os.path.join(d, re.sub(r"[^A-Za-z0-9_.-]", "",
                                    os.path.basename(url))[:120])
        if not (os.path.exists(fn) and os.path.getsize(fn) > 2000):
            if not curl(url, fn):
                done[a["ts"]] = {"ts": a["ts"], "url": url,
                                 "state": "unfetched", "claims": []}
                continue
            fetched += 1
            time.sleep(0.25)
        base = dt.date.fromisoformat(a["ts"][:10])
        text = pdf_text(fn)
        ok, why = legible(" ".join((text or "").split()))
        cl = extract(text, base)
        # the summary is a second source for the same document
        cl += [c for c in extract(a["text"] or "", base)
               if (c["subject"], c["due"], c["amount_low"])
               not in {(x["subject"], x["due"], x["amount_low"]) for x in cl}]
        done[a["ts"]] = {"ts": a["ts"], "url": url,
                         "file": os.path.basename(fn),
                         "state": "read" if ok else "illegible",
                         "illegible_because": why,
                         "category": a["category"],
                         "chars": len(text), "claims": cl}

    rows = sorted(done.values(), key=lambda r: r["ts"])
    with open(store, "w") as fh:
        json.dump(rows, fh, indent=1)
    if verbose:
        n = sum(len(r["claims"]) for r in rows)
        bad = sum(1 for r in rows if r.get("state") == "illegible")
        print(f"  {sym:12s} {len(rows):4d} documents  ({fetched} newly "
              f"fetched)  {n:4d} dated quantified claims"
              + (f"   [{bad} unreadable]" if bad else ""), flush=True)
    return rows


def load(sym):
    p = os.path.join(CACHE, sym, "claims.json")
    if not os.path.exists(p):
        return []
    try:
        return json.load(open(p))
    except Exception:
        return []


def open_claims(sym, as_of=None):
    """Claims whose deadline had passed as at `as_of`.

    Point-in-time by construction: the claim is knowable on the date it was
    made, and it becomes a question on the date it fell due - which is the
    date the finding is stamped with, never the date the answer arrived.
    """
    as_of = as_of or dt.date.today().isoformat()
    out = []
    for r in load(sym):
        for c in r["claims"]:
            if c["due"] <= as_of[:10]:
                out.append({**c, "made_on": r["ts"], "url": r["url"],
                            "category": r.get("category")})
    return sorted(out, key=lambda x: x["due"])


def main(only=None):
    syms = [only] if only else [i[0] for i in ISSUERS]
    tot = collections.Counter()
    for s in syms:
        rows = process(s)
        tot["docs"] += len(rows)
        tot["claims"] += sum(len(r["claims"]) for r in rows)
    print(f"\n{tot['claims']} dated quantified claims from {tot['docs']} "
          f"documents")
    for s in syms:
        oc = open_claims(s)
        if oc:
            by = collections.Counter(c["subject"] for c in oc)
            print(f"  {s:12s} {len(oc):3d} matured   " +
                  "  ".join(f"{k}:{v}" for k, v in by.most_common()))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
