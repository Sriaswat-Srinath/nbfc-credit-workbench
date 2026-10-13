"""Read the attached document, not just the announcement title.

The gap this closes, stated precisely:

  Between 15 October and 30 December 2019, Reliance Capital filed 23
  announcements to the exchange. Every one carried the identical title -
  "Disclosure regarding payment of interest / principal on Non-Convertible
  Debentures" - and the detector, which matched distress language against the
  announcement SUMMARY, classified all 23 as timeline-only.

  Inside the attachments is this sentence:

      "It is expected that the debt servicing of the Company in relation to
       the accelerated amounts and otherwise will be delayed."

  The title is the same whether a company paid or did not. SEBI's disclosure
  obligation is to say which; the answer is in the PDF and nowhere else.

Corpus-wide there are 2,168 such announcements and the summary text promotes
only 14 of them. This module fetches the attachment, extracts its text, and
classifies the outcome, so a payment failure is detected on the day it was
disclosed rather than when a rating agency later confirms it.

Everything is cached. Re-running fetches only what is missing.

Run:  python3 attachments.py            all issuers
      python3 attachments.py RELCAPITAL one issuer
"""
import json
import os
import re
import subprocess
import sys
import time
import zipfile

from announcements import load_announcements
from universe import ISSUERS

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")

# Announcements whose TITLE concerns a payment obligation. Deliberately broad:
# the point is to decide which attachments are worth reading, and a false
# positive here costs one fetch.
PAYDISC = re.compile(
    r"(?i)(payment of (?:the )?interest|payment of interest|"
    r"interest\s*[/I]\s*principal|principal on non.?convertible|"
    r"debt servicing|servicing of (?:debt|NCD)|delay in payment|"
    r"default in payment|regulation 57|payment obligation)")

# Classification, evaluated in this order. Negative before positive, because a
# letter that says "we did not pay X, having paid Y" must classify as a
# failure. Each pattern is written to match the language these filings
# actually use, which is stilted and consistent.
# SEBI circular CIR/CFD/CMD/93/2017 prescribes a DEFAULT DISCLOSURE FORM with
# numbered fields - "Date of default", "Current default amount", "Gross
# principal amount on which the default above has occurred". A company files
# this form only when there is a default to report, so recognising the FORM is
# a far stronger signal than any phrase. DHFL's filing of 8 June 2019 is one,
# and keyword matching alone had scored it "unclear": it never uses a plain
# sentence saying the payment was missed, it fills in a template.
DEFAULT_FORM = re.compile(
    r"(?i)(date of default|current default amount|"
    r"default above has occurred|on date of default|"
    r"CIR\s*/\s*CFD\s*/\s*CMD\s*/\s*93\s*/\s*2017|"
    r"constitute an event of default|non[- ]?payment continues|"
    r"cure period of seven)")

NEGATIVE = [
    ("default_form", DEFAULT_FORM),
    ("not_paid", re.compile(
        r"(?i)(has not been (?:paid|serviced)|have not been (?:paid|serviced)|"
        r"could not (?:be paid|pay|service)|unable to (?:pay|service|meet)|"
        r"failed to (?:pay|service)|remains? (?:unpaid|outstanding and unpaid)|"
        r"non[- ]?payment of (?:the )?(?:interest|principal)|"
        r"defaulted (?:in|on)|has defaulted|in default of)")),
    ("delayed", re.compile(
        r"(?i)(will be delayed|has been delayed|have been delayed|"
        r"is (?:expected to be|likely to be) delayed|delay in (?:the )?"
        r"(?:servicing|payment|repayment)|servicing .{0,40} will be delayed|"
        r"beyond the due date|after the due date)")),
]
# DHFL's 141 Regulation 57(1) certificates all read "the Company has made
# timely payment of interest amount", which none of the first set of patterns
# matched - 214 of its disclosures came back "unclear". The classifier was
# right not to guess, but the phrasing is standard and belongs here.
POSITIVE = re.compile(
    r"(?i)(has been duly paid|have been duly paid|has been paid|have been paid|"
    r"duly (?:serviced|discharged|redeemed)|payment has been made|"
    r"payments? (?:has|have) been credited|paid on (?:the )?due date|"
    r"(?:made|making) timely payment|timely payment of|timely servicing|"
    r"paid on or before (?:the )?due date|"
    r"confirm and certify .{0,80} (?:has|have) made|"
    r"there (?:is|has been) no default|no (?:overdue|default|delay))")

ISIN = re.compile(r"\bINE[0-9A-Z]{9}\b")

# A phrase can appear without asserting anything. Three false positives on
# issuers that never missed a payment forced these guards:
#
#   IIFL 2010      "no grounds on which the Company could be found UNABLE TO
#                   PAY its debts" - a solvency declaration in a buyback
#                   document, matched as insolvency.
#   Manappuram 2018 "Details of any letter or comments regarding payment/
#                   NON-PAYMENT OF INTEREST, principal on due dates" - a
#                   form-field label.
#   Sammaan 2026   "DELAY IN PAYMENT" as a column heading in a tabular NCD
#                   disclosure.
#
# A match is discarded when the 90 characters before it negate it, or when it
# sits inside a label that offers both outcomes.
NEGATED_BEFORE = re.compile(
    r"(?i)(\bno grounds\b|\bnot be found\b|\bcould be found\b|"
    r"\bshall not\b|\bwill not be\b|\bis not\b|\bare not\b|"
    r"\bwithout any\b|\bno instance\b|\bnor any\b)"
    r"[^.;]{0,90}$")
LABEL_LIKE = re.compile(
    r"(?i)(payment\s*/\s*non[- ]?payment|non[- ]?payment\s*/\s*payment|"
    r"paid\s*/\s*unpaid|details of any|comments regarding|"
    r"whether (?:there|any)|\(if any\)|particulars of|"
    r"reason for delay|column|"
    # the debenture trustee's half-yearly certificate is a numbered template
    # whose item 3 reads "Delay in payment of interest / principal amount for
    # a period of more than three months from the due date or default in
    # payment" - a heading, usually answered "Nil"
    r"for a period of more than three months|"
    r"or default in payment of)")

# A numbered list marker immediately before the phrase means it is the item's
# heading, not an assertion.
NUMBERED_ITEM = re.compile(r"(?:^|\s)\(?\d{1,2}[.)]\s*$")


def asserted(flat, m):
    """Is the matched phrase actually asserting the outcome, or is it part of
    a negation or a form label?"""
    before = flat[max(0, m.start() - 90):m.start()]
    around = flat[max(0, m.start() - 60):m.end() + 70]
    if NEGATED_BEFORE.search(before):
        return False
    if LABEL_LIKE.search(around):
        return False
    if NUMBERED_ITEM.search(before[-8:]):
        return False
    return True


def curl(url, out, timeout=70):
    cmd = ["curl", "-sL", "--max-time", str(timeout - 15), "-A", UA,
           "-H", "Referer: https://www.nseindia.com/", "-o", out, url]
    for _ in range(2):
        try:
            subprocess.run(cmd, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        if os.path.exists(out) and os.path.getsize(out) > 2000:
            return True
        time.sleep(1.5)
    return False


def pdf_text(path):
    """Text of a filing. NSE serves a minority of attachments as ZIP archives
    under a .pdf-looking URL - 73 of DHFL's 214, which pdftotext read as zero
    characters without complaining. The archive is opened and its largest PDF
    used instead. Same trap as the annual-report work.
    """
    target = path
    if zipfile.is_zipfile(path):
        d = path + ".x"
        os.makedirs(d, exist_ok=True)
        try:
            with zipfile.ZipFile(path) as z:
                names = [n for n in z.namelist() if n.lower().endswith(".pdf")]
                if not names:
                    return ""
                big = max(names, key=lambda n: z.getinfo(n).file_size)
                z.extract(big, d)
                target = os.path.join(d, big)
        except Exception:
            return ""
    try:
        return subprocess.run(["pdftotext", "-layout", target, "-"],
                              capture_output=True, timeout=90
                              ).stdout.decode("utf8", "replace")
    except Exception:
        return ""


def classify(text):
    """-> (status, matched phrase).

    status in {default_form, not_paid, delayed, paid, unclear}. `unclear` is
    a real answer
    and is NOT treated as either outcome - these letters sometimes only
    schedule a future obligation, and guessing would manufacture findings.
    """
    flat = " ".join(text.split())
    for status, rx in NEGATIVE:
        for m in rx.finditer(flat):
            if asserted(flat, m):
                return status, m.group(0)
    for m in POSITIVE.finditer(flat):
        if asserted(flat, m):
            return "paid", m.group(0)
    return "unclear", ""


def context(text, phrase, span=240):
    """The sentence around the matched phrase, for the evidence block."""
    flat = " ".join(text.split())
    if not phrase:
        return flat[:span]
    i = flat.lower().find(phrase.lower())
    if i < 0:
        return flat[:span]
    return flat[max(0, i - span // 2): i + span // 2].strip()


# Set when the classification rules change and stored verdicts must be redone
# from the cached PDFs. No network traffic: the attachments are already local.
RECLASSIFY = os.environ.get("RECLASSIFY") == "1"


def process(sym, limit=None, verbose=True):
    d = os.path.join(CACHE, sym, "attachments")
    os.makedirs(d, exist_ok=True)
    store = os.path.join(CACHE, sym, "payment_disclosures.json")
    done = {}
    if os.path.exists(store):
        try:
            done = {r["ts"]: r for r in json.load(open(store))}
        except Exception:
            done = {}

    todo = [a for a in load_announcements(sym)
            if PAYDISC.search(a["text"] or "")
            and (a["attachment"] or "").startswith("http")]
    if limit:
        todo = todo[-limit:]

    fetched = 0
    for a in todo:
        prev = done.get(a["ts"])
        if prev and prev.get("status") not in (None, "unfetched") \
                and not RECLASSIFY:
            continue
        url = a["attachment"]
        fn = os.path.join(d, re.sub(r"[^A-Za-z0-9_.-]", "",
                                    os.path.basename(url))[:120])
        if not (os.path.exists(fn) and os.path.getsize(fn) > 2000):
            if not curl(url, fn):
                done[a["ts"]] = {"ts": a["ts"], "url": url,
                                 "status": "unfetched", "phrase": "",
                                 "context": "", "isins": [], "chars": 0}
                continue
            fetched += 1
            time.sleep(0.25)
        txt = pdf_text(fn)
        status, phrase = classify(txt)
        done[a["ts"]] = {
            "ts": a["ts"], "url": url, "file": os.path.basename(fn),
            "status": status, "phrase": phrase,
            "context": context(txt, phrase),
            "isins": sorted(set(ISIN.findall(txt)))[:6],
            "chars": len(txt),
            "title": a["text"][:200],
        }

    rows = sorted(done.values(), key=lambda r: r["ts"])
    with open(store, "w") as fh:
        json.dump(rows, fh, indent=1)
    if verbose:
        import collections
        c = collections.Counter(r["status"] for r in rows)
        print(f"  {sym:12s} {len(rows):4d} disclosures  "
              f"({fetched} newly fetched)  " +
              "  ".join(f"{k}:{v}" for k, v in c.most_common()), flush=True)
    return rows


def load(sym):
    p = os.path.join(CACHE, sym, "payment_disclosures.json")
    if not os.path.exists(p):
        return []
    try:
        return json.load(open(p))
    except Exception:
        return []


def main(only=None):
    syms = [only] if only else [i[0] for i in ISSUERS]
    total = 0
    for s in syms:
        total += len(process(s))
    print(f"\n{total} payment disclosures classified")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
