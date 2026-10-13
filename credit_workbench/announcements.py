"""Loading and cleaning the exchange announcement stream.

Lifted out of detect.py so that detect (which needs announcements) and
attachments (which also needs them, and which detect in turn imports) do not
form an import cycle.
"""
import datetime as dt
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")


# NSE's own feed contains U+FFFD replacement characters where smart quotes and
# apostrophes were lost somewhere upstream of the exchange - "the Company<?><?>s
# operational parameters". The original character is unrecoverable, so a run
# between two word characters is rendered as an apostrophe (by far the most
# common case) and anything else is dropped. This is presentation only; the
# cached bytes on disk are never altered, and the linked source PDF is
# authoritative.
_FFFD_POSS = re.compile(r"(?<=\w)\ufffd+(?=\w)")
_FFFD_ANY = re.compile(r"\ufffd+")


def clean(s):
    if not s:
        return ""
    return _FFFD_ANY.sub("", _FFFD_POSS.sub("\u2019", s))


def load_announcements(sym):
    p = os.path.join(CACHE, sym, "announcements.json")
    if not os.path.exists(p):
        return []
    try:
        raw = json.load(open(p))
    except Exception:
        return []
    out = []
    for r in raw:
        t = None
        for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
            try:
                t = dt.datetime.strptime(r.get("an_dt", ""), fmt)
                break
            except (ValueError, TypeError):
                pass
        if not t:
            continue
        out.append({"ts": t.isoformat(),
                    "category": clean(r.get("desc") or ""),
                    "text": clean(" ".join(
                        (r.get("attchmntText") or "").split())),
                    "attachment": r.get("attchmntFile"),
                    "disseminated": r.get("exchdisstime")})
    out.sort(key=lambda x: x["ts"])
    return out


