"""Build a company-year panel for every bank / NBFC in the Kaggle archive.

Reads the per-company CSV folders and emits one tidy table:
    panel.csv  -- one row per (company, fiscal_year) with balance-sheet,
                  P&L, cash-flow and ratio fields already aligned.

Nothing here needs the network. The archive is the only input.
"""

import os
import re
import csv
import sys
import math
import pandas as pd

ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Detailed-Financials-Data-Of-4456-NSE-And-BSE-Company-20231230T233228Z-001",
    "Detailed-Financials-Data-Of-4456-NSE-_-BSE-Company",
)
OUT = os.path.dirname(os.path.abspath(__file__))

# Institutions recovered from source because the archive dropped them after
# merger, amalgamation or resolution (see recover_missing.py). Same layout and
# same accounting definitions, so they are read as part of the panel. Every one
# of them is a distress case, and they exist to evaluate the FROZEN model.
RECOVERED = os.path.join(OUT, "recovered")

FINANCIAL_SECTORS = {"Banks", "Finance"}


def _year(col):
    """Column headers come as '2019-03-01' or 'Mar 2019'. Return the fiscal year."""
    col = col.strip()
    m = re.match(r"^(\d{4})-(\d{2})-01$", col)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        # Sep-2023 interim columns are partial; keep them out of the yearly panel.
        return y if mo == 3 else None
    m = re.match(r"^([A-Za-z]{3})\s+(\d{4})$", col)
    if m:
        return int(m.group(2)) if m.group(1).lower() == "mar" else None
    return None


def _num(v):
    if v is None:
        return float("nan")
    v = str(v).strip().replace(",", "").replace("%", "")
    if v in ("", "-", "nan", "NaN"):
        return float("nan")
    try:
        return float(v)
    except ValueError:
        return float("nan")


def read_matrix(path):
    """Read a row-labelled CSV into {row_label: {fiscal_year: value}}."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return {}
    header = rows[0]
    years = {i: _year(c) for i, c in enumerate(header) if i > 0 and _year(c)}
    out = {}
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        label = r[0].strip()
        out[label] = {
            y: _num(r[i]) for i, y in years.items() if i < len(r)
        }
    return out


def read_basic_info(folder, name):
    path = os.path.join(folder, f"{name}_Basic_Info.csv")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        rows = list(csv.DictReader(fh))
    return rows[0] if rows else {}


def latest_npa(folder):
    """Gross/Net NPA only exist on the quarterly P&L and only for recent quarters.

    Return the earliest and latest observation so we can see the direction of travel.
    """
    m = read_matrix(os.path.join(folder, "Quarterly_Profit_Loss.csv"))
    # quarterly columns are mostly non-March, so re-read raw to keep every quarter
    path = os.path.join(folder, "Quarterly_Profit_Loss.csv")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return {}
    header = rows[0][1:]
    out = {}
    for r in rows[1:]:
        if not r:
            continue
        if r[0].strip() in ("Gross NPA %", "Net NPA %"):
            vals = [(header[i], _num(v)) for i, v in enumerate(r[1:]) if i < len(header)]
            vals = [(q, v) for q, v in vals if not math.isnan(v)]
            if vals:
                key = "gnpa" if "Gross" in r[0] else "nnpa"
                out[f"{key}_first"] = vals[0][1]
                out[f"{key}_last"] = vals[-1][1]
                out[f"{key}_max"] = max(v for _, v in vals)
    return out


def collect(root, origin, records):
    """Append one row per (company, fiscal year) for every folder under `root`."""
    skipped = 0
    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        if not os.path.isdir(folder):
            continue
        info = read_basic_info(folder, name)
        sector = (info.get("Sector") or "").strip()
        if sector not in FINANCIAL_SECTORS:
            continue

        bs = read_matrix(os.path.join(folder, "Yearly_Balance_Sheet.csv"))
        pl = read_matrix(os.path.join(folder, "Yearly_Profit_Loss.csv"))
        cf = read_matrix(os.path.join(folder, "Yearly_Cash_flow.csv"))
        rt = read_matrix(os.path.join(folder, "Ratios.csv"))
        npa = latest_npa(folder)

        if not bs:
            skipped += 1
            continue

        years = sorted(set().union(*[set(d) for d in bs.values()]) if bs else set())
        for y in years:
            def g(mat, label):
                return mat.get(label, {}).get(y, float("nan"))

            def gfirst(mat, *labels):
                """Banks use Revenue/Financing Profit; other NBFCs use Sales/Operating Profit."""
                for lb in labels:
                    v = mat.get(lb, {}).get(y, float("nan"))
                    if v == v:
                        return v
                return float("nan")

            rec = {
                "company": name,
                "sector": sector,
                "source": origin,
                "nse": (info.get("NSE") or "").strip(),
                "face_value": _num(info.get("Face Value")),
                "fy": y,
                "equity_capital": g(bs, "Equity Capital"),
                "reserves": g(bs, "Reserves"),
                "borrowings": g(bs, "Borrowings"),
                "other_liabilities": g(bs, "Other Liabilities"),
                "total_assets": g(bs, "Total Assets"),
                "investments": g(bs, "Investments"),
                "fixed_assets": g(bs, "Fixed Assets"),
                "revenue": gfirst(pl, "Revenue", "Sales"),
                "interest_exp": g(pl, "Interest"),
                "expenses": g(pl, "Expenses"),
                "op_profit": gfirst(pl, "Financing Profit", "Operating Profit"),
                "op_margin": gfirst(pl, "Financing Margin %", "OPM %"),
                "other_income": g(pl, "Other Income"),
                "pbt": g(pl, "Profit before tax"),
                "net_profit": g(pl, "Net Profit"),
                "eps": g(pl, "EPS in Rs"),
                "cfo": g(cf, "Cash from Operating Activity"),
                "cff": g(cf, "Cash from Financing Activity"),
                "roe_pct": g(rt, "ROE %"),
                "roce_pct": g(rt, "ROCE %"),
            }
            rec.update(npa)
            records.append(rec)
    return skipped


def main():
    if not os.path.isdir(ROOT):
        sys.exit(f"archive not found at {ROOT}")

    sources = [(ROOT, "archive")]
    if os.path.isdir(RECOVERED):
        sources.append((RECOVERED, "recovered"))

    records = []
    skipped = 0
    for root, origin in sources:
        skipped += collect(root, origin, records)

    df = pd.DataFrame(records)
    df = df.sort_values(["company", "fy"]).reset_index(drop=True)
    path = os.path.join(OUT, "panel.csv")
    df.to_csv(path, index=False)
    print(f"companies: {df['company'].nunique()}  rows: {len(df)}  skipped(no BS): {skipped}")
    print(f"fy range: {int(df['fy'].min())}-{int(df['fy'].max())}")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
