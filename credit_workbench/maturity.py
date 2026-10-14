"""What falls due when, and whether it was paid on the day it was promised.

The gap this closes:

  For a lender that funds short and lends long, the central credit question is
  the repayment schedule against the cash available to meet it. The workbench
  had nothing on it. The quarterly XBRL carries a profit and loss account and
  no maturity ladder; the annual accounts carry a ladder whose buckets the ALM
  study found too coarse to answer the question (ALM_FINDINGS.txt).

  But the issuers themselves publish an instrument-level schedule, continually,
  and nobody reads it. SEBI LODR Regulations 57, 60(2) and 50(1) require an
  issuer to intimate the exchange of each interest and principal payment on
  its listed debentures - by ISIN, with the date. 1,729 of the 2,120 letters
  already cached by attachments.py carry at least one ISIN.

Two different things come out of those letters, and the distinction matters:

  * A FORWARD schedule - "record date 05-05-2018, date of payment 10-05-2018"
    - filed before the payment. Collecting these gives a disclosed repayment
    calendar: on any past date, what the issuer had told the market was
    falling due, and when.

  * A BACKWARD confirmation - Regulation 57(1), "due date 01.02.2019, date of
    payment 01.02.2019" - filed after. Where the actual date is LATER than the
    due date, the issuer has disclosed a delay on a named instrument, with
    both dates. That is a measured fact rather than a phrase match, and it is
    a stronger signal than anything attachments.py can classify from language.

Three refusals, each of which cost yield:

  * ISINs are checksum-validated and discarded when they fail. A third of the
    older letters are scans put through poor OCR - "INE148IO7BV3" with a
    letter O where a zero belongs, "19.05.20L7" for a date. The check digit
    detects exactly this. Repairing the character would be inventing an
    instrument identifier, so a failing ISIN is dropped and counted.
  * A date is parsed or it is not. "r5.05.2017" yields nothing.
  * A date's ROLE - due, actual, record - is taken from the table header, and
    only when the number of date columns the header names equals the number of
    dates on the row. Otherwise the dates are recorded as unassigned and take
    no part in any finding. Column order varies between formats: DHFL's 2018
    letters put the payment date BEFORE the period end, Manappuram's put due
    before actual, and guessing from order alone silently inverts delays into
    early payments.

No network access. This reads attachments already on disk.

Run:  python3 maturity.py            all issuers
      python3 maturity.py DHFL       one issuer
"""
import collections
import datetime as dt
import json
import os
import re
import sys

from attachments import pdf_text
from universe import ISSUERS

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

ISIN_RE = re.compile(r"\b(INE[0-9A-Z]{9})\b")

# Numeric and alphabetic date forms. Both appear, sometimes in one letter.
_MON = ("jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec")
DATE_RE = re.compile(
    r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b"
    r"|\b(\d{1,2})[-\s]?(" + _MON + r")[a-z]*[-,\s]+(\d{2,4})\b"
    r"|\b(" + _MON + r")[a-z]*\s+(\d{1,2})\s*,?\s*(\d{4})\b", re.I)
MONTHS = {m: i + 1 for i, m in enumerate(_MON.split("|"))}

# Amounts. "(in INR lacs)" and "Rs. in crore" both occur, so the unit is read
# from the header rather than assumed; an unlabelled figure is left unscaled
# and flagged, never guessed into crore.
AMT_RE = re.compile(r"\b(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+\.\d+)\b")
UNIT_RE = re.compile(r"(?i)\(?\s*(?:rs\.?|inr|₹)?\s*in\s+(lacs?|lakhs?|crores?|"
                     r"millions?|thousands?)\s*\)?")
UNIT_MULT = {"lac": 1e5, "lacs": 1e5, "lakh": 1e5, "lakhs": 1e5,
             "crore": 1e7, "crores": 1e7, "million": 1e6, "millions": 1e6,
             "thousand": 1e3, "thousands": 1e3}

# What the payment is. "Redemption" and "maturity" are principal.
KIND_RE = re.compile(r"(?i)\b(interest|coupon|principal|redemption|maturity)\b")
KIND_OF = {"interest": "interest", "coupon": "interest",
           "principal": "principal", "redemption": "principal",
           "maturity": "principal"}

# The date columns a header may name, and the role each denotes. Order within
# this table is irrelevant; the ORDER THEY APPEAR IN THE HEADER is what is
# zipped against the row.
ROLE_PATTERNS = [
    ("record", re.compile(r"(?i)record\s*date")),
    ("due", re.compile(r"(?i)due\s*date(?:\s*for\s*(?:the\s*)?payment)?")),
    ("actual", re.compile(r"(?i)actual\s*date(?:\s*of\s*\w+){0,3}")),
    ("payment", re.compile(r"(?i)date\s*of\s*(?:interest\s*)?payment|"
                           r"(?:interest\s*)?payment\s*date")),
    ("redemption", re.compile(r"(?i)(?:date\s*of\s*redemption|redemption\s*"
                              r"date|maturity\s*date)")),
    ("last_paid", re.compile(r"(?i)date\s*of\s*last\s*(?:\w+\s*){0,2}payment")),
]
# A header phrase that names a period rather than a payment. Picked up as a
# date column it shifts every role one place to the left.
NOT_A_ROLE = re.compile(r"(?i)(period\s*end|for\s*the\s*(?:month|quarter|"
                        r"period|half)|interest\s*for|date\s*of\s*allotment|"
                        r"date\s*of\s*issue|deemed\s*date)")


def _ck(isin):
    """ISIN check digit, so OCR damage is detected rather than repaired.

    Letters map A=10..Z=35, the digits are concatenated, and the Luhn check
    runs from the right. "INE148I07BV3" passes; the scanned "INE148IO7BV3",
    with a capital O for a zero, does not.
    """
    if len(isin) != 12:
        return False
    digits = ""
    for ch in isin[:11]:
        digits += str(ord(ch) - 55) if ch.isalpha() else ch
    total, dbl = 0, True
    for ch in reversed(digits):
        d = int(ch)
        if dbl:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        dbl = not dbl
    try:
        return (10 - total % 10) % 10 == int(isin[11])
    except ValueError:
        return False


def _date(m):
    """One regex match -> an ISO date, or None if it is not a real date."""
    g = m.groups()
    try:
        if g[0]:
            d, mo, y = int(g[0]), int(g[1]), int(g[2])
        elif g[3]:
            d, mo, y = int(g[3]), MONTHS[g[4][:3].lower()], int(g[5])
        else:
            mo, d, y = MONTHS[g[6][:3].lower()], int(g[7]), int(g[8])
        if y < 100:
            y += 2000 if y < 70 else 1900
        if not (1990 <= y <= 2100):
            return None
        return dt.date(y, mo, d).isoformat()
    except (ValueError, KeyError, TypeError):
        return None


def dates_in(s):
    """-> ([iso dates], [(start, end) character spans]) in reading order."""
    out, spans = [], []
    for m in DATE_RE.finditer(s):
        iso = _date(m)
        if iso:
            out.append(iso)
            spans.append((m.start(), m.end()))
    return out, spans


WORD_RE = re.compile(r"\S+")

# Prose that happens to contain a role phrase. DHFL's intimation opens "the
# Company has fixed the following dates, as the record dates and payment
# dates for the purpose of payment of Interest", and reading a role out of
# that sentence assigned a payment date from narrative text.
PROSE = re.compile(r"(?i)\b(we hereby|this is to inform|pursuant to|dear sir|"
                   r"in terms of|please find|kindly|in respect of|"
                   r"the company has)\b")

# ------------------------------------------------------------ known formats
# One machine-generated format accounts for most of the corpus, and its
# columns are fixed. Recognising it by signature and applying a known date
# order is both safer and simpler than inferring the layout: its header wraps
# over as many as seven lines, and reading those lines in sequence puts
# "record date" (which wraps onto line 3) AFTER "Due date" and "Actual date"
# (which sit on line 1). That mis-ordering paired each instrument's last
# coupon against its next due date and reported 1,634 delays on Sammaan
# Capital, an issuer that has never missed one - the giveaway being that the
# "delays" clustered at 30, 31 and 365 days, which are payment frequencies.
# The signature is the pair "record date" + "actual date", which no other
# format in the corpus carries, plus one corroborating column. An earlier
# version also required "issue size" and matched only a third of the format's
# letters: that heading wraps as "Issue" / "Size" over two lines, so the two
# words are never adjacent in reading order and the test could not pass.
SEBI_NCD = re.compile(r"(?i)(?=.*record\s*date)(?=.*actual\s*date)"
                      r"(?=.*(?:frequency|reason|issue))", re.S)
# Verified against letters of 2022-08-05 and 2025-09-26: the four dates on a
# row are, left to right, the interest record date, the due date, the actual
# date of payment, and the date of the last payment.
SEBI_NCD_ORDER = {4: ["record", "due", "actual", "last_paid"]}

FORMATS = [("sebi_ncd_tabular", SEBI_NCD, SEBI_NCD_ORDER)]


def header_block(lines, first):
    """The column headings: the contiguous run of non-blank lines immediately
    above the first data row.

    The blank line is the boundary that separates the headings from the
    letter's prose, and using it rather than a fixed lookback is what stops
    narrative text being mined for column roles.
    """
    i, blk = first - 1, []
    while i >= 0 and lines[i].strip() and len(blk) < 8:
        blk.append(lines[i])
        i -= 1
    return list(reversed(blk))


def label_above(header, a, b, pad=2):
    """The header words sitting over the character span (a, b)."""
    out = []
    for l in header:
        for m in WORD_RE.finditer(l):
            if min(m.end(), b + pad) - max(m.start(), a - pad) > 0:
                out.append(m.group(0))
    return " ".join(out)


def role_of(label):
    """The single role a column heading denotes, or None.

    None when the heading names no role, when it names a period rather than a
    payment, or when it names MORE THAN ONE role - which happens where
    columns are narrow enough that one date sits under words from both its
    own heading and its neighbour's. An ambiguous heading is dropped rather
    than resolved by preference.
    """
    if not label or NOT_A_ROLE.search(label):
        return None
    hits = []
    for role, rx in ROLE_PATTERNS:
        m = rx.search(label)
        if m:
            hits.append((m.start(), role))
    roles = {r for _, r in hits}
    if len(roles) != 1:
        return None
    return hits[0][1]


def consistent(got):
    """Do the assigned roles satisfy the relations that hold by definition?

    A record date fixes who is paid on the due date, so it cannot fall after
    it; the last payment cannot fall after the one now being reported. Where
    an assignment violates either, the layout was read wrongly - and it is the
    DELAY arithmetic that pays for it, since a due date read one column out
    turns an early payment into a late one. One Sammaan row survived every
    other guard this way: it placed the record date three weeks after the due
    date, which no schedule does.
    """
    rec, due = got.get("record"), got.get("due")
    if rec and due and rec > due:
        return False
    last, act = got.get("last_paid"), got.get("actual") or got.get("payment")
    if last and act and last > act:
        return False
    return True


def assign_roles(header, line, isos, spans):
    """-> ({role: date}, [unassigned dates], how)."""
    flat = " ".join(" ".join(header).split())
    for name, sig, order in FORMATS:
        if sig.search(flat):
            roles = order.get(len(isos))
            if roles:
                got = dict(zip(roles, isos))
                if not consistent(got):
                    return {}, isos, name + " (inconsistent dates)"
                return got, [], name
            return {}, isos, name + " (unexpected column count)"
    if any(PROSE.search(l) and len(re.findall(r"\s{2,}", l)) < 2
           for l in header):
        return {}, isos, "prose, not a table header"
    got = {}
    for iso, (a, b) in zip(isos, spans):
        r = role_of(label_above(header, a, b))
        if r and r not in got:
            got[r] = iso
    left = [d for d in isos if d not in got.values()]
    return got, left, "column position" if got else "no heading matched"


def table_of(text):
    """-> ([header lines], [data lines]) for the first ISIN table."""
    lines = text.splitlines()
    first = next((i for i, l in enumerate(lines) if ISIN_RE.search(l)), None)
    if first is None:
        return [], []
    data = [l for l in lines[first:] if ISIN_RE.search(l)]
    return header_block(lines, first), data


def unit_of(header, body):
    m = UNIT_RE.search(header) or UNIT_RE.search(body[:1500])
    if not m:
        return None, None
    w = m.group(1).lower()
    return UNIT_MULT.get(w), w


def extract(text, letter_ts):
    """Every instrument-level payment row the letter discloses."""
    header, data = table_of(text)
    if not data:
        return [], collections.Counter()
    flat_head = " ".join(" ".join(header).split())
    mult, unit_word = unit_of(flat_head, " ".join(text.split()))
    subject_kind = None
    km = KIND_RE.search(" ".join(text.split())[:700])
    if km:
        subject_kind = KIND_OF[km.group(1).lower()]

    out = []
    stats = collections.Counter()
    for line in data:
        m = ISIN_RE.search(line)
        isin = m.group(1)
        stats["rows"] += 1
        if not _ck(isin):
            stats["bad_isin"] += 1
            continue
        ds, spans = dates_in(line)
        km = KIND_RE.search(line)
        kind = KIND_OF[km.group(1).lower()] if km else subject_kind
        assigned, unassigned, how = assign_roles(header, line, ds, spans)
        if unassigned and not assigned:
            stats["unassigned"] += 1
        stats["how:" + how] += 1
        amt = None
        if mult:
            # the amount column sits after the ISIN; take the first figure on
            # the row that is not part of a date
            masked = DATE_RE.sub(" ", line[m.end():])
            a = AMT_RE.search(masked)
            if a:
                try:
                    amt = float(a.group(1).replace(",", "")) * mult
                except ValueError:
                    amt = None
        out.append({"isin": isin, "kind": kind, "knowable_on": letter_ts,
                    **{f"{k}_date": v for k, v in assigned.items()},
                    "unassigned_dates": unassigned,
                    "roles_from": how,
                    "amount": amt, "amount_unit": unit_word})
    return out, stats


def build(sym, verbose=True):
    src = os.path.join(CACHE, sym, "payment_disclosures.json")
    if not os.path.exists(src):
        return []
    try:
        letters = json.load(open(src))
    except Exception:
        return []
    adir = os.path.join(CACHE, sym, "attachments")
    rows, stats = [], collections.Counter()
    for L in letters:
        fn = os.path.join(adir, L.get("file") or "")
        if not (L.get("file") and os.path.exists(fn)):
            continue
        got, st = extract(pdf_text(fn), L["ts"])
        for g in got:
            g["url"] = L["url"]
            g["letter_status"] = L.get("status")
            g["title"] = (L.get("title") or "")[:160]
        rows += got
        stats.update(st)
        stats["letters"] += 1
    rows.sort(key=lambda r: (r["knowable_on"], r["isin"]))
    out = os.path.join(CACHE, sym, "schedule.json")
    with open(out, "w") as fh:
        json.dump(rows, fh, indent=1)
    if verbose:
        dated = sum(1 for r in rows if r.get("due_date") or r.get("payment_date")
                    or r.get("actual_date") or r.get("redemption_date"))
        print(f"  {sym:12s} {stats['letters']:5d} letters -> {len(rows):5d} rows "
              f"({dated:5d} with a dated role, {stats['bad_isin']:4d} ISIN "
              f"checksum failures, {stats['unassigned']:4d} rows unassigned)",
              flush=True)
    return rows


def load(sym):
    p = os.path.join(CACHE, sym, "schedule.json")
    if not os.path.exists(p):
        return []
    try:
        return json.load(open(p))
    except Exception:
        return []


# Only a layout read from a RECOGNISED format may support a delay claim.
# Roles inferred from column position are good enough to date a payment event
# for the calendar, but the due-versus-actual subtraction is not forgiving: a
# layout read one column out turns an instrument paid two days early into one
# thirteen days late, and that is how Sammaan Capital - which has not missed a
# payment - acquired 21 spurious delays after the first fix removed 1,634.
TRUSTED_LAYOUTS = {"sebi_ncd_tabular"}


def delays(sym, min_days=1):
    """Instrument-level delays the issuer itself disclosed: an actual payment
    date later than the due date it had named, on the same row."""
    out = []
    for r in load(sym):
        if r.get("roles_from") not in TRUSTED_LAYOUTS:
            continue
        due = r.get("due_date")
        act = r.get("actual_date") or r.get("payment_date")
        if not (due and act):
            continue
        slip = (dt.date.fromisoformat(act) - dt.date.fromisoformat(due)).days
        if slip >= min_days:
            out.append({**r, "days_late": slip})
    return out


def calendar(sym, as_of=None):
    """The repayment calendar as it was disclosed on or before `as_of`.

    One entry per (ISIN, due date) the issuer had intimated by then, with the
    date the intimation became public. Forward-looking by construction: these
    are dates in the future relative to the letter that disclosed them.
    """
    as_of = as_of or dt.date.today().isoformat()
    seen = {}
    for r in load(sym):
        if r["knowable_on"][:10] > as_of[:10]:
            continue
        due = (r.get("due_date") or r.get("payment_date")
               or r.get("record_date") or r.get("redemption_date"))
        if not due:
            continue
        key = (r["isin"], due)
        if key not in seen or r["knowable_on"] < seen[key]["knowable_on"]:
            seen[key] = {"isin": r["isin"], "due": due, "kind": r["kind"],
                         "amount": r.get("amount"),
                         "knowable_on": r["knowable_on"], "url": r["url"]}
    return sorted(seen.values(), key=lambda x: x["due"])


def main(only=None):
    syms = [only] if only else [i[0] for i in ISSUERS]
    tot = 0
    for s in syms:
        rows = build(s)
        tot += len(rows)
    print(f"\n{tot} instrument-level payment rows")
    for s in syms:
        d = delays(s)
        if d:
            print(f"  {s:12s} {len(d):4d} disclosed delays, worst "
                  f"{max(x['days_late'] for x in d)} days")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
