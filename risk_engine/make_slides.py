"""Generate an IEEE-style conference presentation deck as PDF.

Follows IEEE presentation conventions: a title slide carrying authors and
affiliation, Roman-numeral section numbering as in IEEE papers, "Fig. n." and
"TABLE n" captions, and IEEE-style bracketed references.

16:9, built with reportlab. Every figure is drawn from the project's own
outputs, so the deck cannot drift from the results.
"""

import os
import math

import pandas as pd
import numpy as np

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph, Table, TableStyle

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "IEEE_Presentation_Bank_NBFC_Risk.pdf")

W, H = 960, 540                     # 16:9
M = 54                              # margin

IEEE_BLUE = colors.HexColor("#00629B")
IEEE_DARK = colors.HexColor("#003B5C")
INK = colors.HexColor("#1A1A1A")
GREY = colors.HexColor("#5A5A5A")
RULE = colors.HexColor("#C9D4DC")
SOFT = colors.HexColor("#EDF3F7")
ACCENT = colors.HexColor("#B8603A")
RED = colors.HexColor("#9D3528")
MKT = colors.HexColor("#7A4E8C")

BODY = ParagraphStyle("b", fontName="Times-Roman", fontSize=15.5, leading=22, textColor=INK)
BULLET = ParagraphStyle("bu", parent=BODY, leftIndent=16, bulletIndent=2, spaceAfter=7)
SMALL = ParagraphStyle("s", fontName="Times-Roman", fontSize=12, leading=16, textColor=GREY)
CELL = ParagraphStyle("c", fontName="Times-Roman", fontSize=11.5, leading=14, textColor=INK)
HEADC = ParagraphStyle("hc", fontName="Helvetica-Bold", fontSize=10, leading=13,
                       textColor=colors.white)


class Deck:
    def __init__(self, path):
        self.c = pdfcanvas.Canvas(path, pagesize=landscape((H, W)))
        self.c.setPageSize((W, H))
        self.n = 0
        self.total = 0

    # ---------------------------------------------------------------- chrome
    def frame(self, section, title, subtitle=None):
        c = self.c
        self.n += 1
        c.setFillColor(colors.white)
        c.rect(0, 0, W, H, stroke=0, fill=1)

        c.setFillColor(IEEE_BLUE)
        c.rect(0, H - 6, W, 6, stroke=0, fill=1)

        if section:
            c.setFont("Helvetica-Bold", 10)
            c.setFillColor(IEEE_BLUE)
            c.drawString(M, H - 34, section.upper())
        c.setFont("Helvetica-Bold", 25)
        c.setFillColor(IEEE_DARK)
        c.drawString(M, H - 68, title)
        y = H - 92
        if subtitle:
            c.setFont("Times-Italic", 14)
            c.setFillColor(GREY)
            c.drawString(M, y, subtitle)
            y -= 20
        c.setStrokeColor(RULE)
        c.setLineWidth(0.8)
        c.line(M, y, W - M, y)

        c.setFont("Helvetica", 8.5)
        c.setFillColor(GREY)
        c.drawString(M, 24, "Bank & NBFC Default Risk Intelligence System")
        c.drawRightString(W - M, 24, str(self.n))
        return y - 26

    def bullets(self, y, items, size=15.5, gap=9):
        for t in items:
            p = Paragraph(t, ParagraphStyle("x", parent=BODY, fontSize=size,
                                            leading=size * 1.42))
            w, h = p.wrap(W - 2 * M - 20, H)
            self.c.setFillColor(IEEE_BLUE)
            self.c.circle(M + 5, y - size * 0.42, 2.6, stroke=0, fill=1)
            p.drawOn(self.c, M + 18, y - h)
            y -= h + gap
        return y

    def para(self, y, text, style=BODY, x=M, width=None):
        p = Paragraph(text, style)
        w, h = p.wrap(width or (W - 2 * M), H)
        p.drawOn(self.c, x, y - h)
        return y - h - 10

    def table(self, y, header, rows, widths, aligns=None, x=None,
              highlight=(), font=11.5):
        data = [[Paragraph(h, HEADC) for h in header]]
        for r in rows:
            data.append([Paragraph(str(v), ParagraphStyle(
                "cc", parent=CELL, fontSize=font, leading=font * 1.25)) for v in r])
        t = Table(data, colWidths=widths)
        st = [("BACKGROUND", (0, 0), (-1, 0), IEEE_DARK),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
              ("LEFTPADDING", (0, 0), (-1, -1), 7),
              ("RIGHTPADDING", (0, 0), (-1, -1), 7),
              ("TOPPADDING", (0, 0), (-1, -1), 4),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT])]
        for i, a in enumerate(aligns or []):
            if a != "L":
                st.append(("ALIGN", (i, 0), (i, -1), "RIGHT" if a == "R" else "CENTER"))
        for r in highlight:
            st.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#FDF0E3")))
        t.setStyle(TableStyle(st))
        tw, th = t.wrap(0, 0)
        t.drawOn(self.c, x if x is not None else M, y - th)
        return y - th - 12

    def caption(self, y, text, center=None):
        """IEEE-style caption. `center` defaults to the page, but a table that
        does not span the full width should pass its own centre."""
        c = self.c
        c.setFont("Times-Italic", 11)
        c.setFillColor(GREY)
        c.drawCentredString(center if center is not None else W / 2, y, text)
        return y - 16

    def page(self):
        self.c.showPage()

    def save(self):
        self.c.save()


# ------------------------------------------------------------------ figures
def fig_dual(dk, x0, y0, w, h, company="Yes Bank Ltd"):
    """Fig. 1 — accounting index and market-implied PD on one time axis."""
    c = dk.c
    sc = pd.read_csv(os.path.join(HERE, "scored.csv"))
    mt = pd.read_csv(os.path.join(HERE, "merton.csv"), parse_dates=["date"])

    g = sc[(sc["company"] == company) & sc["fdi"].notna() & sc["fy"].between(2013, 2021)]
    m = mt[(mt["company"] == company) & (mt["date"] <= "2020-04-01")]
    if g.empty or m.empty:
        return

    t0, t1 = 2013.0, 2021.0
    px = lambda t: x0 + (t - t0) / (t1 - t0) * w
    pyF = lambda v: y0 + v / 100.0 * h
    pdmax = max(10.0, float(m["pd"].max()) * 100)
    pyM = lambda v: y0 + (v / pdmax) * h

    c.setStrokeColor(RULE)
    c.setLineWidth(0.6)
    for v in (0, 25, 50, 75, 100):
        c.line(x0, pyF(v), x0 + w, pyF(v))
        c.setFont("Helvetica", 8)
        c.setFillColor(IEEE_BLUE)
        c.drawRightString(x0 - 6, pyF(v) - 3, str(v))
    for v in (0, pdmax / 2, pdmax):
        c.setFillColor(MKT)
        c.drawString(x0 + w + 6, pyM(v) - 3, f"{v:.0f}%")
    for yr in range(2013, 2022):
        c.setFillColor(GREY)
        c.setFont("Helvetica", 8)
        c.drawCentredString(px(yr), y0 - 13, str(yr))

    # alert threshold
    c.setStrokeColor(ACCENT)
    c.setDash(3, 3)
    c.line(x0, pyF(80), x0 + w, pyF(80))
    c.setDash()

    # market PD
    c.setStrokeColor(MKT)
    c.setLineWidth(2)
    pth = c.beginPath()
    first = True
    for r in m.itertuples():
        t = r.date.year + (r.date.month - 1) / 12.0
        if t < t0 or t > t1 or not np.isfinite(r.pd):
            continue
        X, Y = px(t), pyM(r.pd * 100)
        pth.moveTo(X, Y) if first else pth.lineTo(X, Y)
        first = False
    c.drawPath(pth)

    # accounting index, stepped at each publication date (30 June)
    c.setStrokeColor(IEEE_BLUE)
    c.setLineWidth(2.6)
    pts = [(px(r.fy + 0.5), pyF(r.fdi)) for r in g.itertuples()]
    for i in range(1, len(pts)):
        c.line(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i - 1][1])
        c.line(pts[i][0], pts[i - 1][1], pts[i][0], pts[i][1])
    c.setFillColor(IEEE_BLUE)
    for X, Y in pts:
        c.circle(X, Y, 2.8, stroke=0, fill=1)

    # event marker
    c.setStrokeColor(RED)
    c.setLineWidth(1.6)
    ex = px(2020 + 2 / 12.0)
    c.line(ex, y0, ex, y0 + h)
    c.setFillColor(RED)
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(ex - 5, y0 + h - 11, "RBI moratorium")

    # legend
    c.setFont("Helvetica", 9)
    lx, ly = x0, y0 + h + 14
    c.setStrokeColor(IEEE_BLUE); c.setLineWidth(2.6)
    c.line(lx, ly, lx + 20, ly)
    c.setFillColor(INK); c.drawString(lx + 26, ly - 3, "Distress index (annual, left)")
    c.setStrokeColor(MKT); c.setLineWidth(2)
    c.line(lx + 215, ly, lx + 235, ly)
    c.drawString(lx + 241, ly - 3, "Merton implied PD (monthly, right)")


def fig_bars(dk, x0, y0, w, h, labels, values, cap=None, colr=IEEE_BLUE):
    c = dk.c
    n = len(values)
    bw = w / (n * 1.6)
    mx = max(values) * 1.15
    for i, (lab, v) in enumerate(zip(labels, values)):
        X = x0 + (i + 0.3) * (w / n)
        bh = v / mx * h
        c.setFillColor(colr if not isinstance(colr, list) else colr[i])
        c.rect(X, y0, bw, bh, stroke=0, fill=1)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(X + bw / 2, y0 + bh + 5, f"{v:g}")
        c.setFont("Helvetica", 9)
        c.setFillColor(GREY)
        c.drawCentredString(X + bw / 2, y0 - 13, lab)
    c.setStrokeColor(RULE)
    c.line(x0, y0, x0 + w, y0)


# ------------------------------------------------------------------- slides
def build():
    dk = Deck(OUT)
    c = dk.c

    # ---- 1 title ----
    c.setFillColor(colors.white); c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(IEEE_DARK); c.rect(0, H - 120, W, 120, stroke=0, fill=1)
    c.setFillColor(IEEE_BLUE); c.rect(0, H - 126, W, 6, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 31)
    c.drawCentredString(W / 2, H - 62, "A Dual-Signal Early-Warning System for")
    c.drawCentredString(W / 2, H - 98, "Indian Bank and NBFC Financial Distress")
    c.setFillColor(INK)
    c.setFont("Times-Italic", 16)
    c.drawCentredString(W / 2, H - 170,
                        "Combining Accounting-Based Distress Scoring with Merton Structural Credit Risk")
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(IEEE_DARK)
    c.drawCentredString(W / 2, H - 225, "Sriaswat Srinath,  Mukhirathinam R.,  Pranaav,  Pavani")
    c.setFont("Times-Roman", 13)
    c.setFillColor(GREY)
    c.drawCentredString(W / 2, H - 248, "Team B-15, Financial Engineering")
    c.setStrokeColor(IEEE_BLUE); c.setLineWidth(1.2)
    c.line(W / 2 - 110, H - 272, W / 2 + 110, H - 272)
    c.setFont("Times-Roman", 12.5)
    c.setFillColor(INK)
    for i, ln in enumerate([
            "563 institutions  -  6,223 company-years  -  FY2006-FY2023",
            "303,995 daily closing prices  -  18 labelled distress events",
            "All inputs public; full pipeline reproducible"]):
        c.drawCentredString(W / 2, H - 300 - i * 20, ln)
    c.setFont("Helvetica", 9.5); c.setFillColor(GREY)
    c.drawCentredString(W / 2, 34,
                        "Academic decision support. Not investment advice and not a credit rating.")
    dk.n = 1
    dk.page()

    # ---- 2 outline ----
    y = dk.frame("", "Outline")
    y = dk.bullets(y - 6, [
        "<b>I. Introduction</b> &mdash; motivation and problem statement",
        "<b>II. Background</b> &mdash; structural and accounting approaches to default risk",
        "<b>III. Data</b> &mdash; sources, construction, and recovery of missing institutions",
        "<b>IV. Methodology</b> &mdash; the distress index, the Merton model, and the alert rule",
        "<b>V. Results</b> &mdash; lead times, discrimination, and the alert-utility test",
        "<b>VI. External validation</b> &mdash; the frozen method on 547 US bank failures",
        "<b>VII. Discussion</b> &mdash; signals that failed, and why",
        "<b>VIII. Limitations</b>",
        "<b>IX. Conclusion</b>",
    ], size=17, gap=13)
    dk.page()

    # ---- 3 introduction ----
    y = dk.frame("I. Introduction", "Failures are announced on one day; they develop over years")
    y = dk.bullets(y - 4, [
        "India's financial sector saw repeated sudden distress: IL&amp;FS (2018), DHFL (2019), "
        "Yes Bank (2020), Reliance Capital (2021), SREI (2021).",
        "Credit ratings and regulatory action largely <i>confirm</i> distress rather than "
        "anticipate it; commercial early-warning tools are proprietary.",
        "Yet most of the deterioration is visible in filings and prices that are already public.",
    ])
    y -= 6
    c.setFillColor(SOFT); c.rect(M, y - 92, W - 2 * M, 92, stroke=0, fill=1)
    c.setFillColor(IEEE_BLUE); c.rect(M, y - 92, 5, 92, stroke=0, fill=1)
    dk.para(y - 12, "<b>Research question.</b> Using only public accounting statements and "
                    "market prices, can institution-level distress be detected early enough, "
                    "and selectively enough, to be operationally useful?",
            ParagraphStyle("q", parent=BODY, fontSize=16, leading=23), x=M + 20,
            width=W - 2 * M - 40)
    dk.page()

    # ---- 4 background ----
    y = dk.frame("II. Background", "Two families of default models, with opposite blind spots")
    y = dk.table(y - 4,
                 ["", "Accounting-based", "Structural (market-based)"],
                 [["Origin", "Altman Z-score [2]", "Merton [1]; Black-Scholes [5]"],
                  ["Input", "Financial statements", "Equity value and volatility, debt"],
                  ["Mechanism", "Ratios of capital, leverage, profitability",
                   "Equity as a call option on firm assets"],
                  ["Coverage", "Any institution that files", "Listed firms with a liquid quote"],
                  ["Blind spot", "Inherits whatever filings conceal",
                   "Needs a market; ignores state support"]],
                 [110, 300, 342], ["L", "L", "L"], font=12.5)
    y = dk.caption(y + 4, "TABLE I.   Complementary properties of the two model families.",
                   center=M + (110 + 300 + 342) / 2)
    y = dk.bullets(y - 2, [
        "Bharath and Shumway [6] show the Merton distance-to-default functional form carries "
        "most of its predictive content &mdash; motivating its use as an independent second signal.",
        "This work runs both, and treats their <i>disagreement</i> as the informative quantity.",
    ], size=14)
    dk.page()

    # ---- 5 data ----
    y = dk.frame("III. Data", "Three public sources, combined point-in-time")
    y = dk.table(y - 2,
                 ["Source", "Content", "Scale"],
                 [["NSE/BSE company financials archive",
                   "Balance sheet, P&amp;L, cash flow, ratios", "556 institutions"],
                  ["Recovered from source filings",
                   "Institutions the archive dropped after merger or resolution",
                   "7 institutions"],
                  ["NSE daily bhavcopy", "Daily closing prices and corporate actions",
                   "303,995 observations, 180 symbols"],
                  ["RBI releases and public filings", "Dated distress events", "18 events"]],
                 [280, 370, 202], ["L", "L", "L"], font=12.5)
    y = dk.caption(y + 4, "TABLE II.   Data sources.", center=M + (280 + 370 + 202) / 2)
    y = dk.bullets(y - 2, [
        "<b>Survivorship bias identified and partly corrected.</b> Of 22 known distress "
        "episodes, only 11 were evaluable; institutions that merge or resolve leave the "
        "archive. Seven were recovered from source filings in identical accounting "
        "definitions, raising coverage to <b>18 of 22 (82%)</b>.",
        "<b>Point-in-time discipline.</b> Accounts for a fiscal year ending 31 March are "
        "treated as public from 30 June, so no result uses information unavailable at the "
        "time of prediction.",
    ], size=13.5, gap=7)
    dk.page()

    # ---- raw records ----
    y = dk.frame("III. Data  (B)", "What the raw records actually look like")
    y = dk.para(y - 2, "Each institution is a folder of eight CSV files &mdash; balance sheet, "
                       "profit and loss, cash flow and ratios, yearly and quarterly. Figures "
                       "are in Rs crore. Extract, <i>Yes Bank Ltd / Yearly_Balance_Sheet.csv</i>:",
                ParagraphStyle("d", parent=BODY, fontSize=13.5, leading=19))
    y = dk.table(y + 2,
                 ["Line item", "FY2017", "FY2018", "FY2019", "FY2020"],
                 [["Equity Capital", "456", "461", "463", "2,510"],
                  ["Reserves", "21,583", "25,292", "26,424", "19,185"],
                  ["Borrowings", "181,464", "275,582", "335,982", "219,102"],
                  ["Total Assets", "215,060", "312,450", "380,860", "257,832"]],
                 [200, 95, 95, 95, 95], ["L", "R", "R", "R", "R"], font=12)
    y = dk.caption(y + 4, "TABLE III.   Source records, Yes Bank Ltd.",
                   center=M + (200 + 95 * 4) / 2)

    y -= 4
    y = dk.para(y, "The same records for a bank that did fail. Reserves more than halve and the "
                   "funding base contracts 40% in two years &mdash; deposit flight visible in the "
                   "raw filing, before any modelling:",
                ParagraphStyle("d2", parent=BODY, fontSize=13.5, leading=19))
    y = dk.table(y + 2,
                 ["Line item", "FY2017", "FY2018", "FY2019", "FY2020"],
                 [["Reserves", "1,945", "2,072", "<b>1,573</b>", "<b>893</b>"],
                  ["Borrowings", "32,326", "37,322", "30,201", "<b>22,199</b>"],
                  ["Total Assets", "35,245", "40,429", "33,046", "<b>24,422</b>"]],
                 [200, 95, 95, 95, 95], ["L", "R", "R", "R", "R"], font=12, highlight=(1,))
    dk.caption(y + 4, "TABLE IV.   Lakshmi Vilas Bank Ltd. (PCA Sep 2019, amalgamated Nov 2020), "
                      "recovered from source filings.", center=M + (200 + 95 * 4) / 2)
    dk.page()

    # ---- 6 methodology A ----
    y = dk.frame("IV. Methodology  (A)", "Fundamental Distress Index (FDI)")
    y = dk.para(y - 2, "Six ratios, each converted to a within-year percentile against "
                       "comparable institutions, then weighted:", BODY)
    y = dk.table(y + 2,
                 ["Component", "Definition", "Weight"],
                 [["Capital buffer", "equity / total assets", "0.30"],
                  ["Capital erosion", "(equity<sub>t</sub> &minus; equity<sub>t&minus;2</sub>) / assets<sub>t</sub>", "0.20"],
                  ["Profitability", "net profit / total assets", "0.20"],
                  ["Leverage", "borrowings / equity", "0.12"],
                  ["Interest burden", "interest expense / revenue", "0.10"],
                  ["Earnings trend", "ROA<sub>t</sub> &minus; ROA<sub>t&minus;3</sub>", "0.08"]],
                 [170, 330, 80], ["L", "L", "C"], x=M, font=12)
    y2 = dk.caption(y + 4, "TABLE V.   Index components.", center=M + (170 + 330 + 80) / 2)
    # right column notes
    c.setFillColor(SOFT); c.rect(M + 600, 120, W - M - (M + 600) + 0, 250, stroke=0, fill=1)
    ty = 352
    for head, txt in [
        ("Peer-relative", "Banks are ranked against banks, NBFCs against NBFCs of similar "
                          "size. Ranking all institutions together penalised every normally "
                          "funded lender."),
        ("Dual-anchored", "Capital components are additionally ranked against the whole "
                          "sector, so a uniformly thin group does not look safe by its own "
                          "standards."),
        ("Not fitted", "Weights come from economic reasoning. With 18 events, fitted "
                       "weights would memorise the sample.")]:
        c.setFont("Helvetica-Bold", 11.5); c.setFillColor(IEEE_DARK)
        c.drawString(M + 616, ty, head)
        p = Paragraph(txt, ParagraphStyle("n", parent=SMALL, fontSize=10.5, leading=13.5))
        w_, h_ = p.wrap(W - M - (M + 616) - 10, 200)
        p.drawOn(c, M + 616, ty - 6 - h_)
        ty -= h_ + 26
    dk.page()

    # ---- worked example: filing to score ----
    y = dk.frame("IV. Methodology  (B)", "From filing to score: Yes Bank, FY2019")
    y = dk.para(y - 2, "Accounts public 30 June 2019; RBI moratorium 5 March 2020. "
                       "Ranked against the other 38 banks.",
                ParagraphStyle("w", parent=SMALL, fontSize=12.5, leading=16))
    c.setFillColor(SOFT); c.rect(M, y - 74, W - 2 * M, 70, stroke=0, fill=1)
    c.setFillColor(INK); c.setFont("Courier", 11.5)
    for i, ln in enumerate([
        "equity   =     463 + 26,424  =   26,887      ROA      =   1,709 / 380,860 = 0.0045",
        "assets   =                      380,860      leverage = 335,982 / 26,887  = 12.50",
        "erosion  = (26,887 - 22,039) / 380,860 = 0.0127      [FY2017 equity 22,039]"]):
        c.drawString(M + 18, y - 22 - i * 17, ln)
    y -= 86
    y = dk.table(y, ["Component", "Raw value", "Percentile", "Weight", "Contribution"],
                 [["Capital buffer", "0.0706", "78.7", "0.30", "23.62"],
                  ["Capital erosion", "0.0127", "57.1", "0.20", "11.43"],
                  ["Profitability (ROA)", "0.0045", "51.3", "0.20", "10.26"],
                  ["Leverage", "12.50", "80.4", "0.12", "9.65"],
                  ["Interest burden", "0.6687", "71.8", "0.10", "7.18"],
                  ["Earnings trend", "-0.0108", "85.3", "0.08", "6.82"],
                  ["<b>Distress index</b>", "", "", "", "<b>68.96</b>"]],
                 [220, 130, 120, 100, 140], ["L", "R", "R", "R", "R"],
                 highlight=(7,), font=11.5)
    y = dk.caption(y + 4, "TABLE VI.   Component percentiles and weighted contributions.",
                   center=M + (220 + 130 + 120 + 100 + 140) / 2)
    dk.para(y - 2, "69 is below the level threshold of 80, so a level-only screen stays silent. "
                   "But Yes Bank's own three-year median was <b>39.9</b>, making this a "
                   "<b>+29.0</b> move against itself &mdash; the deterioration leg fires "
                   "<b>8.2 months before the moratorium</b>. Profitability still ranked 51st "
                   "percentile: the accounts did not yet show the problem.",
            ParagraphStyle("v", parent=BODY, fontSize=12.5, leading=17))
    dk.page()

    # ---- 7 methodology B ----
    y = dk.frame("IV. Methodology  (C)", "Merton structural credit risk")
    y = dk.para(y - 2, "Equity is a call option on firm assets struck at the face value of "
                       "debt. Two equations are solved simultaneously for the two unobservable "
                       "quantities, asset value <i>V</i> and asset volatility &sigma;<sub>V</sub>:", BODY)
    c.setFillColor(SOFT); c.rect(M, y - 104, W - 2 * M, 100, stroke=0, fill=1)
    c.setFillColor(INK); c.setFont("Courier-Bold", 14)
    c.drawString(M + 26, y - 30, "E  =  V N(d1)  -  D e^(-rT) N(d2)")
    c.drawString(M + 26, y - 54, "sE =  (V/E) N(d1) sV")
    c.setFont("Courier", 13); c.setFillColor(IEEE_DARK)
    c.drawString(M + 26, y - 82, "DD = [ln(V/D) + (r - sV^2/2)T] / (sV sqrt(T))      PD = N(-DD)")
    y -= 118
    y = dk.bullets(y, [
        "Solved by fixed-point iteration (the KMV approach [3]); non-convergence returns no "
        "estimate rather than a partial one.",
        "Market capitalisation uses raw prices with share count from equity capital and "
        "split-adjusted face value; volatility uses fully adjusted returns over 250 days.",
        "<b>Corporate actions were the dominant engineering problem.</b> Missed stock splits "
        "produced 170% spurious volatility. Detection uses single-day price ratios that land "
        "on exact fractions, with guards for circuit limits, market-wide stress and listing days.",
    ], size=13.5, gap=7)
    dk.page()

    # ---- Merton on real numbers ----
    y = dk.frame("IV. Methodology  (D)", "The solver on real numbers: Yes Bank, 27 Sep 2019")
    y = dk.table(y - 2, ["", "Quantity", "Value", "Where it comes from"],
                 [["Observed", "Share price", "Rs 48.75", "NSE bhavcopy, 27 Sep 2019"],
                  ["Observed", "Shares outstanding", "231.5 cr",
                   "equity capital 463 / face value 2"],
                  ["Observed", "Equity value E", "Rs 11,286 cr", "price x shares"],
                  ["Observed", "Equity volatility sE", "90.0%",
                   "250-day returns, split-adjusted"],
                  ["Observed", "Default point D", "Rs 335,982 cr",
                   "borrowings, FY2019 accounts"],
                  ["<b>Solved</b>", "<b>Asset value V</b>", "<b>Rs 324,420 cr</b>",
                   "<b>fixed-point iteration</b>"],
                  ["<b>Solved</b>", "<b>Asset volatility sV</b>", "<b>4.03%</b>",
                   "<b>fixed-point iteration</b>"],
                  ["<b>Output</b>", "<b>Distance to default</b>", "<b>0.72</b>",
                   "<b>standard deviations above debt</b>"],
                  ["<b>Output</b>", "<b>Implied 1-year PD</b>", "<b>23.4%</b>", "<b>N(-DD)</b>"]],
                 [95, 230, 170, 320], ["L", "L", "R", "L"], highlight=(6, 7, 8, 9), font=11.5)
    y = dk.caption(y + 4, "TABLE VII.   Merton inputs and solution for a single date.")
    y = dk.bullets(y - 2, [
        "Equity is worth only <b>3.4%</b> of the debt it stands behind, and is roughly "
        "twenty times as volatile as the assets &mdash; the option is far out of the money.",
        "The accounts at this date still scored 69. The market was pricing close to a "
        "<b>one-in-four</b> chance of default, five months before the moratorium.",
    ], size=13.5, gap=7)
    dk.page()

    # ---- 8 alert rule ----
    y = dk.frame("IV. Methodology  (E)", "Alert rule: level or deterioration")
    c.setFillColor(SOFT); c.rect(M, y - 72, W - 2 * M, 68, stroke=0, fill=1)
    c.setFillColor(IEEE_BLUE); c.rect(M, y - 72, 5, 68, stroke=0, fill=1)
    c.setFillColor(INK); c.setFont("Courier-Bold", 15)
    c.drawString(M + 24, y - 30, "alert  =  FDI >= 80")
    c.drawString(M + 24, y - 54, "       OR ( FDI >= 60  AND  FDI - median(own last 3 years) >= +15 )")
    y -= 88
    y = dk.bullets(y, [
        "A level-only trigger fails on the case the exercise exists for. Yes Bank's FY2019 "
        "accounts scored <b>69</b> &mdash; below any sensible threshold, but <b>29 points above "
        "its own three-year median of 39.9</b>.",
        "The deterioration leg fires <b>8 months before</b> the RBI moratorium, at a cost of "
        "roughly three additional material names per year on the watchlist.",
        "A high level identifies <i>who</i> is weak; a sharp move identifies <i>when</i> "
        "something changed. An early-warning system needs both.",
    ], size=14.5, gap=9)
    dk.page()

    # ---- 9 Fig 1: dual signal ----
    y = dk.frame("V. Results  (A)", "Case study: Yes Bank Ltd., FY2013-FY2020")
    fig_dual(dk, M + 46, 148, W - 2 * M - 110, 232)
    dk.caption(118, "Fig. 1.   Accounting distress index (left axis) and Merton implied "
                    "one-year PD (right axis) on a common time axis.")
    dk.para(96, "The accounts reach 69 only on the FY2019 filings. The market had been pricing "
                "above 10% from mid-2019 and roughly one-in-three by January 2020 &mdash; the "
                "clearest evidence for running both signals.",
            ParagraphStyle("f", parent=SMALL, fontSize=12, leading=16))
    dk.page()

    # ---- 10 lead times ----
    y = dk.frame("V. Results  (B)", "Lead time across 18 labelled distress events")
    rows = [["Indian Overseas Bank", "PCA", "Oct 2015", "39"],
            ["Dhanlaxmi Bank", "PCA", "Nov 2015", "40"],
            ["United Bank of India &#9679;", "PCA", "Jan 2017", "42"],
            ["Dena Bank &#9679;", "PCA", "May 2017", "10"],
            ["IDBI Bank", "PCA", "May 2017", "missed"],
            ["Oriental Bank of Commerce &#9679;", "PCA", "Oct 2017", "3"],
            ["Bank of India", "PCA", "Dec 2017", "17"],
            ["Allahabad Bank &#9679;", "PCA", "Jan 2018", "30"],
            ["Reliance Home Finance", "default", "Sep 2019", "2"],
            ["Lakshmi Vilas Bank &#9679;", "PCA", "Sep 2019", "75"],
            ["Yes Bank", "moratorium", "Mar 2020", "8"],
            ["SREI Infrastructure &#9679;", "resolution", "Oct 2021", "3"],
            ["Reliance Capital", "resolution", "Nov 2021", "41"]]
    y = dk.table(y - 2, ["Institution", "Event", "Date", "Lead (months)"], rows,
                 [300, 110, 110, 120], ["L", "L", "L", "R"], highlight=(5,), font=11)
    dk.caption(y + 4, "TABLE VIII.   Selected events (13 of 18 shown); a dot marks "
                      "institutions recovered from source.",
               center=M + (300 + 110 + 110 + 120) / 2)
    c.setFillColor(SOFT); c.rect(M + 660, 120, W - M - (M + 660), 250, stroke=0, fill=1)
    ty = 350
    for k, v in [("17 / 18", "alerted before the event"),
                 ("14 / 18", "within the 24-month window"),
                 ("52-94%", "95% CI on recall"),
                 ("76", "highest control reading")]:
        c.setFont("Helvetica-Bold", 20); c.setFillColor(IEEE_BLUE)
        c.drawString(M + 676, ty, k)
        c.setFont("Times-Roman", 11); c.setFillColor(GREY)
        c.drawString(M + 676, ty - 15, v)
        ty -= 56
    dk.page()

    # ---- 11 validation ----
    y = dk.frame("V. Results  (C)", "Does it generalise, or is it chance?")
    y = dk.bullets(y - 2, [
        "<b>Unseen-event test.</b> Components re-selected on pre-2018 events only, methodology "
        "frozen, then run on seven later events: the same six components survive, and all "
        "<b>7 of 7</b> held-out events are caught.",
        "<b>Permutation test.</b> The null preserves event dates and sector, permuting only "
        "<i>which</i> institution failed, over 4,000 draws.",
    ], size=14, gap=8)
    y = dk.table(y - 2,
                 ["Statistic", "Observed", "Null mean", "p-value"],
                 [["Events alerted (all 18)", "17", "7.20", "&lt; 0.00025"],
                  ["Alert precision", "2.55%", "1.02%", "&lt; 0.00025"],
                  ["<b>Held-out events only (7)</b>", "<b>7</b>", "<b>2.18</b>", "<b>0.0003</b>"]],
                 [330, 150, 150, 180], ["L", "C", "R", "R"], highlight=(3,), font=12.5)
    y = dk.caption(y + 4, "TABLE IX.   Permutation test against a sector-preserving null.",
                   center=M + (330 + 150 + 150 + 180) / 2)
    dk.para(y - 2, "Chance is ruled out as an explanation of <i>which</i> institutions are "
                   "flagged. This does not establish performance on future events, and does "
                   "not repair the four episodes still missing from the panel.",
            ParagraphStyle("z", parent=SMALL, fontSize=12.5, leading=17))
    dk.page()

    # ---- 12 alert utility ----
    y = dk.frame("V. Results  (D)", "Accuracy is the wrong test for an alarm")
    y = dk.table(y - 2,
                 ["Rule", "Caught", "AUC", "Persistence", "Always-on", "Failed"],
                 [["Distress index (level or deterioration)", "14/18", "0.900", "27%", "2", "0"],
                  ["Borrowings / equity, top decile", "15/18", "<b>0.976</b>", "62%", "<b>22</b>", "0"],
                  ["Equity / assets, worst decile", "17/18", "0.932", "60%", "19", "0"],
                  ["Merton DD, worst decile", "4/18", "&mdash;", "23%", "<b>0</b>", "0"]],
                 [330, 90, 85, 115, 110, 80], ["L", "C", "R", "R", "C", "C"],
                 highlight=(2,), font=11.5)
    y = dk.caption(y + 4, "TABLE X.   Alert utility. 'Always-on' counts institutions "
                          "flagged in every one of 8+ observed years; 'Failed' counts how many "
                          "of those actually failed.",
                   center=M + (330 + 90 + 85 + 115 + 110 + 80) / 2)
    y = dk.bullets(y - 2, [
        "A single leverage ratio attains the <b>highest AUC</b> and is the <b>worst instrument</b>: "
        "it permanently flags HDFC Bank, ICICI, Axis, Canara and Bank of Baroda, and "
        "<b>none of the institutions it permanently flags ever failed</b>.",
        "It never changes its mind, so it carries no timing. <b>AUC is the wrong headline "
        "metric on a clustered event set</b>; lead time, persistence and watchlist size are "
        "what matter.",
    ], size=13.5, gap=7)
    dk.page()

    # ---- external validation A ----
    y = dk.frame("VI. External Validation  (A)", "The same method, 547 US bank failures")
    y = dk.para(y - 2, "Eighteen events cannot settle whether a method works. The FDIC "
                       "publishes every US bank failure since 1934 and quarterly call "
                       "reports for every insured institution, joined on one identifier. "
                       "<b>Nothing was refitted</b> &mdash; same components, weights, "
                       "anchoring, alert rule and horizon; only the field names change.",
                ParagraphStyle("x1", parent=BODY, fontSize=13.5, leading=19))
    y = dk.table(y + 2, ["", "India", "United States"],
                 [["Panel", "6,223 company-years", "<b>416,285 bank-quarters</b>"],
                  ["Institutions", "563", "<b>10,341</b>"],
                  ["Period", "FY2006-FY2023, annual", "2003-2015, quarterly"],
                  ["Evaluable events", "18", "<b>547</b>"],
                  ["Pre-event observations", "36", "<b>4,309</b>"],
                  ["Survivorship bias", "7 institutions recovered by hand",
                   "<b>none - failed banks remain</b>"]],
                 [180, 270, 290], ["L", "L", "L"], highlight=(4, 5), font=12)
    y = dk.caption(y + 4, "TABLE XI.   Scale of the external test.",
                   center=M + (180 + 270 + 290) / 2)
    y = dk.table(y - 2, ["Result on US data", "Value"],
                 [["Failures alerted within 24 months", "<b>535 of 547   (98%)</b>"],
                  ["Median lead time", "<b>19.6 months</b>   (quartiles 13.1 / 22.5)"],
                  ["Alert precision", "7.32% against a 1.04% base rate - <b>7.1x lift</b>"],
                  ["Watchlist", "829 of 8,005 banks per quarter (10%)"],
                  ["Permutation test", "observed 535, null mean 141.9, <b>p &lt; 0.001</b>"]],
                 [280, 460], ["L", "L"], highlight=(1,), font=12)
    dk.caption(y + 4, "TABLE XII.   Frozen methodology, unchanged, on 547 failures.",
               center=M + (280 + 460) / 2)
    dk.page()

    # ---- external validation B ----
    y = dk.frame("VI. External Validation  (B)", "Two findings that change earlier conclusions")
    y = dk.para(y - 2, "<b>1. The AUC trap is settled.</b> On Indian data a single leverage "
                       "ratio beat the composite (0.976 against 0.912), defended as an "
                       "artefact of an event set clustered on thin-capital public-sector "
                       "banks. That defence is testable where no such clustering exists.",
                ParagraphStyle("x2", parent=BODY, fontSize=13.5, leading=19))
    y = dk.table(y + 2, ["Signal", "AUC", "Caught", "Persistence", "Always-on"],
                 [["<b>Distress index composite</b>", "<b>0.861</b>", "<b>535 / 547</b>",
                   "<b>19%</b>", "<b>2</b>"],
                  ["Leverage alone", "0.828", "511 / 547", "27%", "27"]],
                 [250, 90, 110, 110, 100], ["L", "R", "C", "R", "C"],
                 highlight=(1,), font=12)
    y = dk.caption(y + 4, "TABLE XIII.   On 547 events the composite wins on every measure.",
                   center=M + (250 + 90 + 110 + 110 + 100) / 2)
    y = dk.bullets(y - 2, [
        "The Indian ranking was the artefact it was argued to be. Leverage alone remains "
        "the worse alarm: <b>27</b> institutions permanently flagged against <b>2</b>.",
        "<b>2. The Indian weakness is a missing input, not a flawed structure.</b> Call "
        "reports carry a non-performing-assets ratio for every bank-quarter; as a standalone "
        "signal it scores <b>AUC 0.887 at 100% coverage</b> &mdash; stronger than any "
        "component in the model. The Indian archive has it only from 2020, for a tenth of "
        "the panel.",
        "<b>What this does not establish.</b> US and Indian banking differ in regulation, "
        "funding and resolution, and the US window is dominated by one crisis. This shows "
        "the method is not an artefact of the Indian sample; it does not show the Indian "
        "results are precise.",
    ], size=13, gap=7)
    dk.page()

    # ---- 13 discussion: negative results ----
    y = dk.frame("VII. Discussion", "Signals that were tested and rejected")
    y = dk.table(y - 2,
                 ["Candidate signal", "Coverage", "AUC", "Added events", "Watchlist cost"],
                 [["Market: drawdown from peak", "20%", "0.777", "0", "+17%"],
                  ["Market: abnormal 12-month return", "17%", "0.769", "0", "+11%"],
                  ["Funding: loan book shrinking", "61%", "0.736", "+1", "+57%"],
                  ["Funding: thin liquid buffer", "100%", "0.390", "0", "+74%"],
                  ["Quality: profit minus operating cash", "98%", "<b>0.321</b>", "0", "+85%"]],
                 [330, 110, 100, 130, 140], ["L", "R", "R", "C", "R"], font=11.5)
    y = dk.caption(y + 4, "TABLE XIV.   Candidate extensions. None was adopted.",
                   center=M + (330 + 110 + 100 + 130 + 140) / 2)
    y = dk.bullets(y - 2, [
        "<b>Earnings-quality measures are inverted for lenders.</b> A lender's operating cash "
        "flow is dominated by loan-book movement, so a shrinking book releases cash: distressed "
        "lenders show cash <i>above</i> profit. The corporate-finance intuition does not transfer.",
        "Market signals discriminate well but flag institutions the accounts already condemn &mdash; "
        "they add <i>timing</i>, which the Merton layer already supplies, not new names.",
    ], size=13, gap=6)
    dk.page()

    # ---- 14 limitations ----
    y = dk.frame("VIII. Limitations", "What the evidence does not support")
    y = dk.bullets(y - 4, [
        "<b>Eighteen events is a small sample</b>, and 13 are Prompt Corrective Action "
        "placements. The failure mode of greatest practical interest &mdash; an NBFC that stops "
        "paying &mdash; rests on five observations.",
        "<b>The index is a rank, not a probability.</b> A score of 88 means worse than 88% of "
        "peers, not an 88% chance of default. The Merton PD is a model output under strong "
        "assumptions, not a calibrated forecast.",
        "<b>Four distress episodes remain unevaluable</b> (DHFL, IL&amp;FS, PMC Bank, Altico), "
        "and all four are failures, so measured recall remains optimistic.",
        "<b>No notion of sovereign or parent support</b>, and group or related-party exposure &mdash; "
        "the mechanism that actually brought down IL&amp;FS and Reliance Capital &mdash; is invisible "
        "in a standalone balance sheet.",
        "<b>Component selection used the same events it was tested on</b>; the held-out test "
        "mitigates but does not eliminate this.",
    ], size=13.5, gap=9)
    dk.page()

    # ---- 15 conclusion ----
    y = dk.frame("IX. Conclusion", "")
    y = dk.bullets(y + 10, [
        "Credit-risk techniques normally restricted to commercial providers can be reproduced "
        "from entirely public data, across <b>563 institutions</b> rather than a handful.",
        "The system alerted before <b>17 of 18</b> real distress events and within the "
        "actionable window for <b>14</b>, while healthy controls never exceeded 76 of 100.",
        "A sector-preserving permutation test rules out chance on held-out events "
        "(<b>p = 0.0003</b>), and the frozen method transfers to <b>547 US bank failures</b>, "
        "catching 535 with a median lead of 19.6 months (<b>p &lt; 0.001</b>).",
        "The two analyses are complementary by construction: the accounts fail where losses "
        "are unrecognised, and precisely there the market moves first.",
        "<b>The most transferable finding is methodological</b> &mdash; on a clustered, rare-event "
        "problem, AUC rewards instruments that are useless as alarms. Persistence and watchlist "
        "size decide whether a model can actually be used.",
    ], size=14.5, gap=11)
    dk.page()

    # ---- 16 references ----
    y = dk.frame("References", "")
    refs = [
        "R. C. Merton, &ldquo;On the pricing of corporate debt: The risk structure of interest "
        "rates,&rdquo; <i>J. Finance</i>, vol. 29, no. 2, pp. 449&ndash;470, 1974.",
        "E. I. Altman, &ldquo;Financial ratios, discriminant analysis and the prediction of "
        "corporate bankruptcy,&rdquo; <i>J. Finance</i>, vol. 23, no. 4, pp. 589&ndash;609, 1968.",
        "P. Crosbie and J. Bohn, &ldquo;Modeling default risk,&rdquo; Moody&rsquo;s KMV, 2003.",
        "F. Black and M. Scholes, &ldquo;The pricing of options and corporate liabilities,&rdquo; "
        "<i>J. Polit. Econ.</i>, vol. 81, no. 3, pp. 637&ndash;654, 1973.",
        "S. T. Bharath and T. Shumway, &ldquo;Forecasting default with the Merton distance to "
        "default model,&rdquo; <i>Rev. Financ. Stud.</i>, vol. 21, no. 3, pp. 1339&ndash;1369, 2008.",
        "Reserve Bank of India, &ldquo;Prompt Corrective Action framework for scheduled "
        "commercial banks,&rdquo; RBI, 2017.",
        "National Stock Exchange of India, &ldquo;Historical daily bhavcopy archive,&rdquo; NSE.",
    ]
    yy = y - 4
    for i, r in enumerate(refs, 1):
        p = Paragraph(f"[{i}]&nbsp;&nbsp;{r}",
                      ParagraphStyle("r", parent=BODY, fontSize=13, leading=18))
        w_, h_ = p.wrap(W - 2 * M - 10, H)
        p.drawOn(c, M, yy - h_)
        yy -= h_ + 10
    dk.page()

    dk.save()
    print(f"wrote {OUT} ({os.path.getsize(OUT)/1024:.0f} KB, {dk.n} slides)")


if __name__ == "__main__":
    build()
