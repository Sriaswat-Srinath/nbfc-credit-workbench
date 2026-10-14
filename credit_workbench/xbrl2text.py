"""Convert a single XBRL filing into a readable text file.

normalize.py parses an instance and export_statements.py renders every filing
already in the cache. Neither helps when you have one document in your hand -
a file someone sent you, a URL from an exchange listing, an archive you just
downloaded. This is that tool.

    python3 xbrl2text.py FILING.xml
    python3 xbrl2text.py https://nsearchives.nseindia.com/corporate/xbrl/X.xml
    python3 xbrl2text.py FILING.zip -o statement.txt
    python3 xbrl2text.py ./folder_of_filings/ -o ./out/

It accepts a path, a URL or a directory, unwraps ZIP archives, and writes one
aligned text file per reporting column in the document. Three columns
throughout - line item, figure in Rs crore, and the original XBRL tag - so any
number can be checked against the source.

Two things it will tell you rather than guess at:

  * If the instance declares no reporting period - nine of the 661 cached
    filings reference a context they never define, which is malformed XBRL -
    it says so and asks for --period, rather than inventing dates.
  * If a subtotal cannot be recomputed because an operand was not filed, the
    check reports "not evaluated" and names the missing line. A subtotal check
    with an absent operand is meaningless, not failed.

As a library:

    from xbrl2text import convert
    text = convert("FILING.xml")                 # -> str
    text = convert(url, period=("2024-10-01", "2024-12-31"))
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import zipfile

from normalize import SECTION_ORDER, normalize

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")

W_LABEL, W_VALUE = 62, 16
RULE = "-" * 132

# Subtotals, emboldened with a leading marker so the statement reads as one.
TOTALS = {
    "Income", "Revenue", "Expenses", "ProfitBeforeTax", "TaxExpense",
    "ProfitLossForPeriod", "ProfitLossForThePeriod", "RevenueFromOperations",
    "ComprehensiveIncomeForThePeriod", "ProfitBeforeExceptionalItemsAndTax",
}


class XBRLError(Exception):
    """Raised with a message meant for the person running the tool."""


# ------------------------------------------------------------------ input
def fetch(url, dest):
    """Download a filing. curl rather than urllib: urllib hangs on the NSE
    archive hosts, which is where most of these documents live."""
    cmd = ["curl", "-sL", "--max-time", "60", "-A", UA,
           "-H", "Referer: https://www.nseindia.com/", "-o", dest, url]
    try:
        subprocess.run(cmd, capture_output=True, timeout=75)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        raise XBRLError(f"could not download {url}: {e}")
    if not os.path.exists(dest) or os.path.getsize(dest) < 200:
        raise XBRLError(f"download produced nothing usable from {url}")
    return dest


def unwrap(path, workdir):
    """Return a path to an XML instance, opening a ZIP if that is what it is.

    NSE serves a minority of documents as ZIP archives under a URL that looks
    like a plain file, and the extension is no guide - the magic bytes are.
    """
    if not zipfile.is_zipfile(path):
        return path
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".xml")]
            if not names:
                raise XBRLError(f"{path} is a ZIP archive with no XML inside")
            pick = max(names, key=lambda n: z.getinfo(n).file_size)
            z.extract(pick, workdir)
            return os.path.join(workdir, pick)
    except zipfile.BadZipFile as e:
        raise XBRLError(f"{path} looks like a ZIP but will not open: {e}")


def resolve(src, workdir):
    """A URL or a file -> one local XML path. Directories are expanded by
    main(), which runs the batch file by file so that one malformed document
    cannot abort the rest - the first version lost a good filing because an
    unreadable one sat next to it."""
    if src.startswith(("http://", "https://")):
        name = os.path.basename(src.split("?")[0]) or "filing.xml"
        return unwrap(fetch(src, os.path.join(workdir, name)), workdir)
    if not os.path.exists(src):
        raise XBRLError(f"no such file: {src}")
    return unwrap(src, workdir)


def listing(src):
    """The filings inside a directory."""
    out = [os.path.join(src, fn) for fn in sorted(os.listdir(src))
           if fn.lower().endswith((".xml", ".zip"))]
    if not out:
        raise XBRLError(f"no .xml or .zip files in {src}")
    return out


# ----------------------------------------------------------------- output
def fmt(value, kind):
    if value is None:
        return "-"
    return f"{value / 1e7 if kind == 'money' else value:,.2f}"


def render(stmt, source):
    """One reporting column as aligned text."""
    meta = stmt["meta"]
    L = ["=" * 132]
    name = meta.get("company") or "(company not named in the instance)"
    L.append(name)
    L.append(f"{stmt['period_start'] or '?'} to {stmt['period_end']}"
             f"   [column {stmt['column']}]")
    L.append("=" * 132)
    for key, label in (("basis", "basis"), ("audited", "audited"),
                       ("board_approved", "approved by board"),
                       ("quarter_label", "reporting quarter"),
                       ("audit_opinion", "audit opinion")):
        if meta.get(key):
            L.append(f"  {label:20s} {meta[key]}")
    if meta.get("rounding"):
        L.append(f"  {'filer states units':20s} {meta['rounding']}  "
                 f"(the instance carries absolute rupees; converted below)")
    if stmt.get("period_source") and stmt["period_source"] != "tagged":
        L.append(f"  {'period taken from':20s} {stmt['period_source']}")
    L.append(f"  {'source':20s} {source}")
    L.append("")
    L.append(f"{'LINE ITEM':{W_LABEL}}{'Rs CRORE':>{W_VALUE}}  XBRL TAG")
    L.append(RULE)

    for sec in SECTION_ORDER:
        rows = [ln for ln in stmt["lines"] if ln["section"] == sec]
        if not rows:
            continue
        L.append("")
        L.append(sec.upper())
        for ln in rows:
            lab = ln["label"]
            if len(lab) > W_LABEL - 4:
                lab = lab[:W_LABEL - 6] + "..."
            mark = "* " if ln["tag"] in TOTALS else "  "
            unit = "" if ln["kind"] == "money" else f"  [{ln['kind']}]"
            L.append(f"{mark}{lab:{W_LABEL - 2}}"
                     f"{fmt(ln['value'], ln['kind']):>{W_VALUE}}  "
                     f"{ln['tag']}{unit}".rstrip())

    L += ["", RULE,
          "* marks a subtotal. Figures in Rs crore except lines marked",
          "  [per_share] or [ratio], which are printed exactly as filed.",
          "", "DOES THE STATEMENT ADD UP"]
    if not stmt["checks"]:
        L.append("  no subtotal in this filing could be recomputed from the "
                 "lines it contains")
    for c in stmt["checks"]:
        if c["ok"] is None:
            L.append(f"  [not checked] {c['rule']}")
            L.append(f"                {', '.join(c['missing'])} was not "
                     f"filed, so the relationship cannot be tested")
        elif c["ok"]:
            L.append(f"  [holds      ] {c['rule']}")
        else:
            L.append(f"  [BREAKS     ] {c['rule']}")
            L.append(f"                stated {c['stated']/1e7:,.2f} cr, "
                     f"recomputed {c['recomputed']/1e7:,.2f} cr, "
                     f"difference {c['difference']/1e7:,.2f} cr")
    L += ["",
          "  Only relationships that hold by definition of a profit and loss",
          "  account are tested. Decomposition - a total against the lines",
          "  beneath it - is NOT checked: the XBRL taxonomies in use name "
          "those",
          "  lines differently, and the rule failed on healthy filings.", ""]
    return "\n".join(L)


# -------------------------------------------------------------- the entry
def convert(src, period=None, workdir=None):
    """Convert one filing to text. Returns the text; raises XBRLError with a
    message worth showing the user."""
    own = workdir is None
    workdir = workdir or tempfile.mkdtemp(prefix="xbrl2text-")
    try:
        path = resolve(src, workdir)
        stmts = normalize(path, period)
        if not stmts:
            head = open(path, encoding="utf8", errors="replace").read(400)
            if "in-bse-fin" not in head and "xbrl" not in head.lower():
                raise XBRLError(
                    f"{os.path.basename(path)} does not look like an XBRL "
                    f"instance. This tool reads the NSE/BSE in-bse-fin "
                    f"taxonomy.")
            raise XBRLError(
                f"{os.path.basename(path)} declares no reporting period. "
                f"Nine of the 661 cached NSE filings do this - they reference "
                f"a context they never define, which is malformed XBRL. "
                f"Re-run with:\n    --period YYYY-MM-DD YYYY-MM-DD")
        return "\n\n".join(render(s, src) for s in stmts)
    finally:
        if own:
            subprocess.run(["rm", "-rf", workdir], capture_output=True)


def out_name(src, outdir=None):
    base = os.path.basename(src.split("?")[0]) or "statement"
    name = re.sub(r"\.(xml|zip)$", "", base, flags=re.I) + ".txt"
    return os.path.join(outdir, name) if outdir else name


def main():
    ap = argparse.ArgumentParser(
        description="Convert an XBRL filing into a readable text statement.")
    ap.add_argument("source", help="path, URL, or directory of filings")
    ap.add_argument("-o", "--out",
                    help="output file, or directory when SOURCE is one. "
                         "Default: alongside the input, with a .txt suffix")
    ap.add_argument("--period", nargs=2, metavar=("START", "END"),
                    help="reporting period, for instances that declare none")
    ap.add_argument("--stdout", action="store_true",
                    help="print instead of writing a file")
    a = ap.parse_args()
    period = tuple(a.period) if a.period else None

    # ---- directory: one output per filing, and a bad file is skipped
    if os.path.isdir(a.source):
        try:
            files = listing(a.source)
        except XBRLError as e:
            print(f"xbrl2text: {e}", file=sys.stderr)
            return 2
        outdir = a.out or a.source
        os.makedirs(outdir, exist_ok=True)
        ok, failed = 0, []
        for f in files:
            try:
                text = convert(f, period)
            except XBRLError as e:
                failed.append((os.path.basename(f), str(e).split("\n")[0]))
                continue
            dest = out_name(f, outdir)
            with open(dest, "w") as fh:
                fh.write(text)
            ok += 1
        print(f"converted {ok} of {len(files)} filings -> {outdir}")
        for name, why in failed:
            print(f"  skipped {name}: {why}", file=sys.stderr)
        return 0 if ok else 2

    # ---- single file or URL
    try:
        text = convert(a.source, period)
    except XBRLError as e:
        print(f"xbrl2text: {e}", file=sys.stderr)
        return 2

    if a.stdout:
        print(text)
        return 0
    out = a.out
    if not out or os.path.isdir(out):
        out = out_name(a.source, out if out else None)
    with open(out, "w") as fh:
        fh.write(text)
    cols = text.count("=" * 132) // 2
    print(f"wrote {out}  ({cols} reporting column"
          f"{'s' if cols != 1 else ''}, {len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
