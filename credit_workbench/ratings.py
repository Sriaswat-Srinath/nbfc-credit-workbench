"""The rating level and its path, read from the agency letter.

What was missing, stated precisely:

  detect.py already notices a rating announcement. It notices it as an EVENT -
  "Credit Rating: the company has informed the exchange..." - promoted to an
  alert only when the summary text happens to contain a distress word. What it
  never recorded was the RATING: the notch, the agency, the direction, the
  outlook.

  That is the single most informative public series on a borrower, and the
  reason it was absent is the same reason payment status was absent before
  attachments.py: the exchange summary does not carry it. Across the 16
  issuers there are 533 rating announcements and the summary text contains a
  rating symbol in 93 of them. The other 440 say only that a rating was
  communicated; the symbol is in the agency letter.

  Without the level, a downgrade from AAA to AA+ and a downgrade from BB- to D
  are the same finding. With it, they are not remotely the same finding.

So this module fetches the letter, extracts every (agency, symbol) pair it
asserts, maps the symbol onto a common notch scale, and reconstructs each
issuer's rating path agency by agency. Direction comes from the path and from
the letter's own "revised from X to Y" phrasing - not from keyword guessing.

Three things it refuses to do:

  * Invent a level. A letter that names no symbol is recorded as `unparsed`
    and takes no part in the path. 93 of 533 is the floor the summary gave;
    whatever this module reaches, the remainder is reported, not filled.
  * Mix scales. Long-term (AAA..D) and short-term (A1+..A4) are different
    scales and are tracked separately. A move from A1+ to A2 is not
    comparable to a move from AAA to AA.
  * Compare across agencies. CARE's AA and ICRA's AA are a coincidence of
    notation, not an observation. A path is per agency per scale.

Everything is cached under cache/<SYM>/ratings.json. Re-running fetches only
what is missing.

Run:  python3 ratings.py            all issuers
      python3 ratings.py DHFL       one issuer
      RECLASSIFY=1 python3 ratings.py    re-parse cached letters, no network
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

# ---------------------------------------------------------------- the scales
# The Indian long-term scale, best to worst. Notch numbers are positions in
# this list, so "two notches down" is arithmetic rather than interpretation.
LONG = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-",
        "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
        "B+", "B", "B-", "C+", "C", "C-", "D"]
# Short-term, a separate and much shorter scale.
SHORT = ["A1+", "A1", "A2+", "A2", "A3+", "A3", "A4+", "A4", "D"]

LONG_IX = {s: i for i, s in enumerate(LONG)}
SHORT_IX = {s: i for i, s in enumerate(SHORT)}

# BBB- is the lowest investment grade. BB+ and below is speculative, and the
# crossing is the single most consequential move on the scale: mandates,
# bank risk weights and repo eligibility are written against it.
SPECULATIVE_FROM = LONG_IX["BB+"]
DEFAULT_GRADE = {LONG_IX["C+"], LONG_IX["C"], LONG_IX["C-"], LONG_IX["D"]}

AGENCIES = {
    "CRISIL": "CRISIL", "ICRA": "ICRA", "CARE": "CARE",
    "IND": "India Ratings", "INDIA RATINGS": "India Ratings",
    "FITCH": "India Ratings",
    "BWR": "Brickwork", "BRICKWORK": "Brickwork",
    "ACUITE": "Acuite", "SMERA": "Acuite",
    "INFOMERICS": "Infomerics",
}

# Longest alternative first: regex alternation takes the leftmost that
# matches, so "A1+" must precede "A1" and "AA+" must precede "AA", or every
# AA+ in the corpus is read as AA.
_SYMS = ("AAA", r"AA\+", "AA-", "AA",
         r"A1\+", "A1", r"A2\+", "A2", r"A3\+", "A3", r"A4\+", "A4",
         r"A\+", "A-", "A",
         r"BBB\+", "BBB-", "BBB", r"BB\+", "BB-", "BB",
         r"B\+", "B-", "B", r"C\+", "C-", "C", "D")
_SYM_RE = "|".join(_SYMS)
_AG_RE = "|".join(sorted(AGENCIES, key=len, reverse=True)).replace(" ", r"\s+")

# "CRISIL AAA/Stable", "[ICRA]AA+(Negative)", "CARE AA+ (Double A Plus)",
# "IND AA-/RWN". The bracket forms are ICRA's house style.
RATED = re.compile(r"(?i)\[?\s*(" + _AG_RE + r")\s*\]?\s*[\s:\-]?\s*"
                   r"(" + _SYM_RE + r")(?![A-Za-z0-9+])")

# The letter's own statement of direction, which is more reliable than any
# verb: "revised the rating from CARE AA to CARE AA-".
FROM_TO = re.compile(r"(?i)\bfrom\s+\[?\s*(?:" + _AG_RE + r")?\s*\]?\s*"
                     r"(" + _SYM_RE + r")(?![A-Za-z0-9+])"
                     r"[^.]{0,80}?\bto\s+\[?\s*(?:" + _AG_RE + r")?\s*\]?\s*"
                     r"(" + _SYM_RE + r")(?![A-Za-z0-9+])")

# "CARE Ratings has revised rating by one notch to AA for the Company's
# long-term debt programme" - the symbol carries no agency prefix, which is
# how a third of the summaries are written. Attributed only when the body
# names exactly ONE agency, and only when the symbol sits immediately after an
# action verb, so the scale legend at the foot of a letter cannot be mined
# this way.
BARE = re.compile(r"(?i)\b(?:revis\w+|downgrad\w+|upgrad\w+|assign\w+|"
                  r"reaffirm\w+|reiterat\w+|maintain\w+|rated|"
                  r"continues? to be|placed)\b[^.]{0,70}?"
                  r"\b(?:to|at|as|of)\s+"
                  r"(" + _SYM_RE + r")(?![A-Za-z0-9+])")
AGENCY_ANY = re.compile(r"(?i)\b(" + _AG_RE + r")\b")

OUTLOOK = re.compile(r"(?i)\b(stable|positive|negative|developing)\s*"
                     r"(?:outlook)?\b")
# The direction must be captured when present, so the lazy quantifier cannot
# be allowed to satisfy an optional group with nothing: "Rating Watch with
# Negative Implications" read as watch=unspecified, discarding the only part
# of the phrase that carries information.
WATCH_DIR = re.compile(r"(?i)(?:rating|credit)\s*watch\b[^.]{0,60}?"
                       r"\b(negative|developing|positive)\b")
WATCH_ANY = re.compile(r"(?i)((?:rating|credit)\s*watch|on watch|\bRWN\b)")
WITHDRAWN = re.compile(r"(?i)\b(withdraw\w*|suspend\w*)\b")

# A rating symbol can appear without being asserted of this issuer. Same
# failure mode the payment classifier hit: the scale legend printed at the
# foot of every CARE letter lists every symbol from AAA to D, and a naive
# reader takes the whole alphabet as the issuer's rating.
LEGEND = re.compile(r"(?i)(rating\s+scale|scale\s+for|definition[s]?\s+of|"
                    r"instruments? with this rating are considered|"
                    r"highest degree of safety|lowest degree of safety|"
                    r"annexure|disclaimer|press release archive|"
                    r"about (?:crisil|icra|care|brickwork|acuite)|"
                    r"historical rating|rating history)")
# A long-term rating is often quoted beside its short-term sibling. Which
# scale a symbol belongs to is decided by the symbol itself, never by context.
LT_HINT = re.compile(r"(?i)\b(long[- ]term|long term|lt\b|non[- ]convertible|"
                     r"NCD|debenture|subordinat\w+|perpetual|term loan|"
                     r"bank facilit\w+|fixed deposit|bond)")
ST_HINT = re.compile(r"(?i)\b(short[- ]term|commercial paper|\bCP\b|"
                     r"working capital demand loan)")

RECLASSIFY = os.environ.get("RECLASSIFY") == "1"


def scale_of(sym):
    if sym in SHORT_IX and sym != "D":
        return "short"
    if sym in LONG_IX:
        return "long"
    return None


def parse(text):
    """-> dict with the symbols the letter asserts, and how.

    Returns {"long": [...], "short": [...], "from_to": (a,b) or None,
             "outlook": str|None, "watch": str|None, "withdrawn": bool}
    """
    flat = " ".join((text or "").split())
    # Cut the letter at its scale legend / disclaimer. Everything after it is
    # boilerplate that names every symbol on the scale.
    cut = len(flat)
    for m in LEGEND.finditer(flat):
        # ignore a legend reference in the first 400 chars - that is a subject
        # line, not the appendix
        if m.start() > 400:
            cut = m.start()
            break
    body = flat[:cut]

    longs, shorts = [], []
    for m in RATED.finditer(body):
        agency = AGENCIES[re.sub(r"\s+", " ", m.group(1).upper())]
        sym = m.group(2).upper().replace(" ", "")
        sc = scale_of(sym)
        if sc is None:
            continue
        near = body[max(0, m.start() - 120):m.end() + 60]
        # "D" is on both scales; let the surrounding instrument decide, and
        # default to long-term, which is what a default is reported against.
        if sym == "D":
            sc = "short" if (ST_HINT.search(near)
                             and not LT_HINT.search(near)) else "long"
        (longs if sc == "long" else shorts).append((agency, sym))

    if not (longs or shorts):
        named = {AGENCIES[re.sub(r"\s+", " ", a.upper())]
                 for a in AGENCY_ANY.findall(body)}
        if len(named) == 1:
            agency = named.pop()
            for m in BARE.finditer(body):
                s = m.group(1).upper()
                sc = scale_of(s)
                if sc == "long":
                    longs.append((agency, s))
                elif sc == "short":
                    shorts.append((agency, s))

    ft = None
    m = FROM_TO.search(body)
    if m:
        a, b = m.group(1).upper(), m.group(2).upper()
        if scale_of(a) == scale_of(b) and scale_of(a) is not None:
            ft = (a, b)

    wd = WATCH_DIR.search(body)
    watch = (wd.group(1).lower() if wd
             else "negative" if re.search(r"\bRWN\b", body)
             else "unspecified" if WATCH_ANY.search(body) else None)
    return {
        "long": sorted(set(longs)),
        "short": sorted(set(shorts)),
        "from_to": ft,
        "outlook": (OUTLOOK.search(body).group(1).lower()
                    if OUTLOOK.search(body) else None),
        "watch": watch,
        "withdrawn": bool(WITHDRAWN.search(body)),
        "chars": len(flat),
    }


def worst(pairs, ix):
    """The weakest rating the letter asserts, per agency.

    An issuer's letter typically covers several instruments. The weakest is
    the one that matters for refinancing - a AAA on a secured bond does not
    help an NCD rated BB - and taking the best would systematically flatter
    every issuer in the file.
    """
    out = {}
    for agency, sym in pairs:
        n = ix[sym]
        if agency not in out or n > out[agency][1]:
            out[agency] = (sym, n)
    return out


def process(sym, verbose=True):
    d = os.path.join(CACHE, sym, "attachments")
    os.makedirs(d, exist_ok=True)
    store = os.path.join(CACHE, sym, "ratings.json")
    done = {}
    if os.path.exists(store):
        try:
            done = {r["ts"]: r for r in json.load(open(store))}
        except Exception:
            done = {}

    todo = [a for a in load_announcements(sym)
            if a["category"] == "Credit Rating"
            and (a["attachment"] or "").startswith("http")]

    fetched = 0
    for a in todo:
        prev = done.get(a["ts"])
        if prev and prev.get("state") not in (None, "unfetched") \
                and not RECLASSIFY:
            continue
        url = a["attachment"]
        fn = os.path.join(d, re.sub(r"[^A-Za-z0-9_.-]", "",
                                    os.path.basename(url))[:120])
        if not (os.path.exists(fn) and os.path.getsize(fn) > 2000):
            if not curl(url, fn):
                done[a["ts"]] = {"ts": a["ts"], "url": url,
                                 "state": "unfetched", "long": [],
                                 "short": [], "title": a["text"][:200]}
                continue
            fetched += 1
            time.sleep(0.25)
        p = parse(pdf_text(fn))
        # the summary sometimes carries the symbol even when the attachment
        # will not open; it is a legitimate second source for the same event
        if not (p["long"] or p["short"]):
            p = parse(a["text"] or "")
            src = "announcement summary"
        else:
            src = "agency letter"
        done[a["ts"]] = {
            "ts": a["ts"], "url": url, "file": os.path.basename(fn),
            "state": "parsed" if (p["long"] or p["short"]) else "unparsed",
            "read_from": src,
            "long": [list(x) for x in p["long"]],
            "short": [list(x) for x in p["short"]],
            "from_to": list(p["from_to"]) if p["from_to"] else None,
            "outlook": p["outlook"], "watch": p["watch"],
            "withdrawn": p["withdrawn"], "chars": p["chars"],
            "title": a["text"][:300],
        }

    rows = sorted(done.values(), key=lambda r: r["ts"])
    with open(store, "w") as fh:
        json.dump(rows, fh, indent=1)
    if verbose:
        c = collections.Counter(r["state"] for r in rows)
        print(f"  {sym:12s} {len(rows):4d} rating letters  "
              f"({fetched} newly fetched)  " +
              "  ".join(f"{k}:{v}" for k, v in c.most_common()), flush=True)
    return rows


def load(sym):
    p = os.path.join(CACHE, sym, "ratings.json")
    if not os.path.exists(p):
        return []
    try:
        return json.load(open(p))
    except Exception:
        return []


# Letters cover different INSTRUMENTS, and that defeats notch arithmetic
# across letters. 103 of the 341 parsed letters assert more than one long-term
# symbol - an issuer's senior NCD at AAA, its subordinated debt at AA+, its
# perpetual at AA - and which instruments a given letter covers varies. Taking
# the weakest symbol in each letter and differencing produced impossible
# round-trips: DHFL read as CARE AAA -> A in May 2018 and A -> AA ten weeks
# later, Shriram as AA+ -> A and back to AAA in six. Neither was a rating
# action; each was a letter about a different instrument.
#
# The letters' own statement of direction would settle it, but "revised from X
# to Y" appears in 5 of 341.
#
# So no finding in this module rests on a cross-letter notch difference. What
# a letter asserts ON ITS OWN DATE - the level, the outlook, the watch status -
# is recorded and used; the comparison between letters is presented as a
# history for the analyst to read, with each observation marked for whether it
# was unambiguous.
DOWNGRADE_WORD = re.compile(r"(?i)\bdowngrad\w*|revised downward|"
                            r"lowered the rating|rating.{0,20}revised downward")
UPGRADE_WORD = re.compile(r"(?i)\bupgrad\w*|revised upward|raised the rating")


def levels(sym, scale="long"):
    """Every level observation, one per (letter, agency).

    Each carries the date the issuer told the exchange - not the date printed
    on the agency's letter, which is earlier and was never actionable.

    `sole_symbol` is True when the letter asserts exactly one symbol on this
    scale, so the observation is unambiguous about which instrument it
    describes. Observations where it is False name the weakest and the
    strongest symbol the letter carries and should not be differenced against
    a neighbour.
    """
    ix = LONG_IX if scale == "long" else SHORT_IX
    out = []
    for r in load(sym):
        if r["state"] != "parsed":
            continue
        pairs = [tuple(x) for x in r[scale]]
        if not pairs:
            continue
        syms = {s for _, s in pairs}
        for agency, (symb, notch) in worst(pairs, ix).items():
            best = min((ix[s] for a, s in pairs if a == agency), default=notch)
            out.append({
                "ts": r["ts"], "agency": agency, "scale": scale,
                "weakest": symb, "weakest_notch": notch,
                "strongest": (LONG if scale == "long" else SHORT)[best],
                "sole_symbol": len(syms) == 1,
                "symbols_in_letter": sorted(syms),
                "outlook": r["outlook"], "watch": r["watch"],
                "withdrawn": r["withdrawn"],
                "says_downgrade": bool(DOWNGRADE_WORD.search(r["title"] or "")),
                "says_upgrade": bool(UPGRADE_WORD.search(r["title"] or "")),
                "read_from": r["read_from"], "url": r["url"],
                "title": r["title"],
            })
    out.sort(key=lambda x: x["ts"])
    return out


def first_crossings(sym):
    """The dates at which the rating file first showed each condition.

    All three are properties of a SINGLE letter, so none depends on comparing
    letters that may cover different instruments.
    """
    spec = dflt = wneg = None
    for o in levels(sym):
        n = o["weakest_notch"]
        if n >= SPECULATIVE_FROM and not spec:
            spec = o
        if n in DEFAULT_GRADE and not dflt:
            dflt = o
        if o["watch"] == "negative" and not wneg:
            wneg = o
    return {"speculative": spec, "default_grade": dflt,
            "watch_negative": wneg}


def current(sym, as_of=None):
    """The weakest long-term rating on record from each agency, as it stood on
    `as_of` - the rating LEVEL the workbench previously had no way to show."""
    as_of = as_of or dt.date.today().isoformat()
    held = {}
    for o in levels(sym):
        if o["ts"][:10] > as_of[:10]:
            continue
        held[o["agency"]] = o
    return held


def main(only=None):
    syms = [only] if only else [i[0] for i in ISSUERS]
    tot = collections.Counter()
    for s in syms:
        rows = process(s)
        tot["letters"] += len(rows)
        tot["parsed"] += sum(1 for r in rows if r["state"] == "parsed")
    print(f"\n{tot['parsed']} of {tot['letters']} rating letters yielded a "
          f"level")
    for s in syms:
        obs = levels(s)
        if not obs:
            continue
        lo = max(obs, key=lambda x: x["weakest_notch"])
        cx = first_crossings(s)
        bits = [f"{k}={v['ts'][:10]}" for k, v in cx.items() if v]
        print(f"  {s:12s} {len(obs):3d} level observations   weakest "
              f"{lo['weakest']:4s} ({lo['agency']}) on {lo['ts'][:10]}"
              + ("   " + "  ".join(bits) if bits else ""))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
