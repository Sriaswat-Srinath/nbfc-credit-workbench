"""Generate the US-only methodology report as PDF.

A standalone document about the US bank-failure system: no Indian material.
Every figure comes from fdic_model.py and the FDIC call-report panel.
"""

import os
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle, PageBreak)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "US_Bank_Failure_Early_Warning.pdf")

INK = colors.HexColor("#15181D")
NAVY = colors.HexColor("#18304A")
STEEL = colors.HexColor("#2E6B8A")
GREY = colors.HexColor("#5A6069")
RULE = colors.HexColor("#D5DCE2")
SOFT = colors.HexColor("#EFF4F7")
RED = colors.HexColor("#9D3528")

S = getSampleStyleSheet()


def style(name, **kw):
    kw.setdefault("parent", S["Normal"])
    return ParagraphStyle(name, **kw)


BODY = style("Body", fontName="Times-Roman", fontSize=10, leading=14.5, textColor=INK,
             alignment=TA_JUSTIFY, spaceAfter=7)
LEAD = style("Lead", parent=BODY, fontSize=11, leading=16, textColor=colors.HexColor("#2C333C"))
H1 = style("H1", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=NAVY,
           spaceBefore=4, spaceAfter=3)
H2 = style("H2", fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=NAVY,
           spaceBefore=15, spaceAfter=5)
BUL = style("Bul", parent=BODY, leftIndent=13, bulletIndent=3, spaceAfter=4)
CAP = style("Cap", fontName="Helvetica", fontSize=8, leading=11, textColor=GREY, spaceAfter=9)
EYE = style("Eye", fontName="Helvetica-Bold", fontSize=7.5, leading=11, textColor=STEEL)
CODE = style("Code", fontName="Courier", fontSize=8.2, leading=12,
             textColor=colors.HexColor("#22272E"))
TCELL = style("TCell", fontName="Times-Roman", fontSize=8.6, leading=11.5, textColor=INK)
THEAD = style("THead", fontName="Helvetica-Bold", fontSize=7.4, leading=10,
              textColor=colors.white)


def P(t, s=BODY):
    return Paragraph(t, s)


def bullets(items, s=BUL):
    return [Paragraph(t, s, bulletText="•") for t in items]


def code(lines):
    body = "<br/>".join(re.sub(r"  +", lambda m: "&nbsp;" * len(m.group()), ln)
                        for ln in lines)
    t = Table([[Paragraph(body, CODE)]], colWidths=[165 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SOFT),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return [t, Spacer(1, 8)]


def table(header, rows, widths, aligns=None, highlight=(), font=8.6):
    data = [[Paragraph(h, THEAD) for h in header]]
    for r in rows:
        data.append([Paragraph(str(v), ParagraphStyle("c", parent=TCELL, fontSize=font,
                                                      leading=font * 1.32)) for v in r])
    t = Table(data, colWidths=widths, repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), NAVY),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
          ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
          ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT])]
    for i, a in enumerate(aligns or []):
        if a != "L":
            st.append(("ALIGN", (i, 0), (i, -1), "RIGHT" if a == "R" else "CENTER"))
    for r in highlight:
        st.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#FBE9E7")))
    t.setStyle(TableStyle(st))
    return [t, Spacer(1, 10)]


def rule_bar(c=STEEL, w=28 * mm, th=1.6):
    t = Table([[""]], colWidths=[w], rowHeights=[th])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), c)]))
    return [Spacer(1, 3), t, Spacer(1, 9)]


def part(n, title, blurb):
    return [PageBreak(), P(f"PART {n}", EYE), P(title, H1)] + rule_bar() + \
           [P(blurb, LEAD), Spacer(1, 4)]


def on_page(canv, doc):
    canv.saveState()
    canv.setFont("Helvetica", 7.5)
    canv.setFillColor(GREY)
    canv.drawString(22 * mm, 13 * mm, "US Bank Failure Early-Warning System")
    canv.drawRightString(188 * mm, 13 * mm, str(canv.getPageNumber()))
    canv.setStrokeColor(RULE)
    canv.setLineWidth(0.4)
    canv.line(22 * mm, 16 * mm, 188 * mm, 16 * mm)
    canv.restoreState()


def build():
    doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
                          topMargin=20 * mm, bottomMargin=22 * mm,
                          title="US Bank Failure Early-Warning System",
                          author="Team B-15")
    doc.addPageTemplates([PageTemplate(id="m", frames=[Frame(
        doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")], onPage=on_page)])
    f = []

    # ---------------- cover ----------------
    f += [Spacer(1, 36 * mm), P("METHODOLOGY REPORT", EYE),
          P("An Early-Warning System for US Bank Failure", H1)]
    f += rule_bar(STEEL, 42 * mm, 2.2)
    f += [P("A distress screen built entirely from FDIC call reports, developed on the "
            "2008-12 failure wave and tested on 2013-2023 &mdash; including the failures "
            "it could not see.", LEAD), Spacer(1, 10)]
    f += table(["", ""], [
        ["Panel", "588,177 bank-quarters, 10,459 institutions, 2003-2023, quarterly"],
        ["Events", "563 dated bank failures matched to pre-failure call reports"],
        ["Development", "529 failures before 2013 &mdash; the 2008-12 wave"],
        ["Held-out test", "63 failures 2013-2023, a different regime"],
        ["Headline", "54 of 63 caught (86%), median lead 15.8 months, 24.8x precision lift"],
        ["Counter-headline", "<b>4% of failed-bank assets</b>, and no better than a one-line benchmark"],
    ], [32 * mm, 133 * mm], ["L", "L"], highlight=(6,))
    f += [Spacer(1, 6), P("Academic work on public data. Not investment advice, not a "
                          "supervisory tool.", CAP)]

    # ---------------- contents ----------------
    f += [PageBreak(), P("CONTENTS", EYE), P("What is in this report", H1)] + rule_bar()
    f += table(["Part", "Contents"], [
        ["I &mdash; Problem and data", "Why bank failure is predictable in principle, and what "
         "the FDIC publishes."],
        ["II &mdash; Method", "Nine ratios, peer-relative percentiles, a weighted index, and an "
         "alert rule with two legs."],
        ["III &mdash; Development", "Component and threshold selection on the 2008-12 wave, "
         "including a flaw in the selection rule."],
        ["IV &mdash; Held-out results", "Performance on 2013-2023, a regime the model never saw."],
        ["V &mdash; What the model cannot see", "The 2023 failures, and why a credit model is "
         "blind to a duration run."],
        ["VI &mdash; Limitations", "What the evidence does not support."],
    ], [45 * mm, 120 * mm], ["L", "L"])

    # ================= PART I =================
    f += part("I", "Problem and Data",
              "A bank fails on one day. The condition that causes it develops over years and "
              "is filed quarterly with the regulator.")

    f += [P("1. Why this is a tractable problem", H2)]
    f += [P("US banks file a Consolidated Report of Condition and Income &mdash; the call "
            "report &mdash; every quarter. Capital, earnings, loan quality and funding are all "
            "reported on a common schedule and a common definition, for every insured "
            "institution. Separately, the FDIC publishes every failure since 1934 with its "
            "date. The two join on a single identifier.")]
    f += [P("This makes bank failure one of the few credit problems with a genuinely large, "
            "clean, dated event set: <b>563 failures with pre-failure financials</b> inside "
            "this window. Most corporate-distress work has to make do with dozens.")]
    f += [P("Cole and White [5] find that the 2008-09 failures were explained well by "
            "ordinary call-report ratios &mdash; commercial real-estate concentration and thin "
            "capital. That is the hypothesis this system operationalises and tests out of "
            "sample.")]

    f += [P("2. The data", H2)]
    f += table(["Source", "Content", "Scale"], [
        ["FDIC <i>financials</i> endpoint", "Quarterly call reports: assets, equity, deposits, "
         "net income, interest income and expense, non-performing assets, loss reserves",
         "588,177 bank-quarters"],
        ["FDIC <i>failures</i> endpoint", "Every failure with date, resolution type and "
         "assets at failure", "4,117 records; 563 in window"],
    ], [42 * mm, 93 * mm, 30 * mm], ["L", "L", "L"])
    f += [P("Both are free and require no authentication. Nothing else is used &mdash; no "
            "market prices, no ratings, no supervisory data.", CAP)]
    f += [P("<b>No survivorship bias.</b> Failed banks remain in the panel with the call "
            "reports they filed before failing. This is the defect that makes most "
            "commercial financial databases unusable for this question: they drop "
            "institutions once those institutions cease to exist, which removes precisely "
            "the observations the exercise needs.")]
    f += [P("<b>Point-in-time.</b> A call report for a quarter end is treated as public 45 "
            "days later. No result uses information that was unavailable on the date the "
            "prediction is attributed to.")]

    # ================= PART II =================
    f += part("II", "Method",
              "Nine ratios, each converted to a rank against comparable banks in the same "
              "quarter, combined into one index, with an alert rule that fires on level or "
              "on movement.")

    f += [P("3. Components", H2)]
    f += table(["Family", "Component", "Definition", "Weight"], [
        ["Capital", "Capital buffer", "equity / assets", "0.20"],
        ["", "Capital erosion", "8-quarter change in equity, scaled by assets", "0.14"],
        ["", "Leverage", "(assets &minus; equity) / equity", "0.08"],
        ["Asset quality", "Non-performing ratio", "non-performing assets / assets", "0.18"],
        ["", "Reserve shortfall", "non-performing assets not covered by loss reserves", "0.08"],
        ["Earnings", "Profitability", "return on assets", "0.14"],
        ["", "Earnings trend", "12-quarter change in ROA", "0.06"],
        ["Funding", "Deposit contraction", "4-quarter fall in deposits", "0.06"],
        ["", "Interest burden", "interest expense / interest income", "0.06"],
    ], [26 * mm, 36 * mm, 80 * mm, 23 * mm], ["L", "L", "L", "C"])
    f += [P("Weights are set by economic reasoning, not fitted. With 529 development events "
            "they could be fitted; they are not, so that the held-out result measures the "
            "design rather than the fitting.", CAP)]

    f += [P("4. From ratio to score", H2)]
    f += code([
        "1. orient    every ratio so that a larger value means more risk",
        "2. rank      within (quarter x size tercile), as a percentile 0-100",
        "3. anchor    capital components also ranked against all banks that quarter,",
        "             and the two ranks averaged",
        "4. override  equity <= 0 forces the capital components to 100",
        "5. weight    index = sum(percentile x weight) / sum(weight available)",
        "             null if fewer than 60% of components are available",
    ])
    f += [P("Ranking rather than thresholding makes the index self-calibrating: in a quarter "
            "when every bank's capital is falling, the ranking still identifies who is "
            "weakest. Size terciles keep a community bank from being judged against a money "
            "centre. The second, whole-population anchor on capital exists because a tercile "
            "that is uniformly thin would otherwise look safe by its own standards.")]

    f += [P("5. Alert rule", H2)]
    f += code([
        "alert  =  index >= 85",
        "       OR ( index >= 65  AND  index - median(own last 12 quarters) >= +20 )",
    ])
    f += [P("Two legs, because they answer different questions. A high level identifies "
            "<i>which</i> banks are weak; a sharp move against a bank's own history "
            "identifies <i>when</i> something changed. A bank that has scored badly for five "
            "years is a standing concern, not a warning. Thresholds are derived in Part III "
            "and never adjusted afterwards.")]

    # ================= PART III =================
    f += part("III", "Development",
              "Components and thresholds are chosen using only failures before 2013, then "
              "frozen. The held-out period is a different regime, not merely later dates.")

    f += [P("6. Component selection", H2)]
    f += [P("Each candidate is scored by its ability to separate pre-failure bank-quarters "
            "from the rest, on development data alone. All nine clear a coin flip, so none "
            "is dropped.")]
    f += table(["Component", "AUC, development data"], [
        ["<b>Non-performing ratio</b>", "<b>0.875</b>"],
        ["<b>Reserve shortfall</b>", "<b>0.856</b>"],
        ["Profitability", "0.830"],
        ["Leverage", "0.815"],
        ["Capital buffer", "0.814"],
        ["Earnings trend", "0.783"],
        ["Interest burden", "0.779"],
        ["Capital erosion", "0.768"],
        ["Deposit contraction", "0.580"],
    ], [95 * mm, 60 * mm], ["L", "R"], highlight=(1, 2))
    f += [P("Asset quality dominates, which is what a credit-driven failure wave should look "
            "like. <b>Deposit contraction is the weakest of the nine.</b> Part V shows why "
            "that ordering, learned from 2008-12, is the system's central weakness.")]

    f += [P("7. A flaw in the threshold rule, caught and corrected", H2)]
    f += [P("Thresholds were first chosen by maximising development recall, with watchlist "
            "size only as a tie-break. With 529 events that rule simply loosens the threshold "
            "until nearly everything is flagged. It selected a watchlist of <b>18% of the "
            "banking system</b> &mdash; a list no analyst would read, and the exact failure "
            "this kind of model is usually criticised for.")]
    f += [P("The rule was replaced, before re-running, with: <b>maximise recall subject to a "
            "watchlist no larger than 5% of banks</b>. The capacity of the person reading the "
            "list is a modelling constraint and belongs in the objective, not in the "
            "commentary afterwards.")]
    f += table(["Selection rule", "Thresholds", "Held-out watchlist", "Held-out precision"], [
        ["Maximise recall", "70 / 50 / +10", "18% of banks", "0.74%  (4.7x lift)"],
        ["<b>Recall subject to 5% cap</b>", "<b>85 / 65 / +20</b>", "<b>2.8% of banks</b>",
         "<b>3.93%  (24.8x lift)</b>"],
    ], [52 * mm, 35 * mm, 38 * mm, 40 * mm], ["L", "C", "R", "R"], highlight=(2,))
    f += [P("On development data the chosen rule catches 504 of 529 failures with 381 banks "
            "on the list per quarter.")]

    # ================= PART IV =================
    f += part("IV", "Held-Out Results",
              "2013-2023: the post-crisis tail. The model was developed on a credit wave and "
              "is tested on a period that contains almost none.")

    f += [P("8. Headline", H2)]
    f += table(["Measure", "Value"], [
        ["Failures alerted within 24 months", "<b>54 of 63   (86%)</b>"],
        ["Median lead time", "15.8 months  (quartiles 8.2 / 22.2)"],
        ["Watchlist", "159 of 5,675 banks per quarter  (2.8%)"],
        ["Precision", "3.93% against a 0.16% base rate &mdash; <b>24.8x lift</b>"],
        ["Permutation test", "observed 55, null mean 4.6, <b>p &lt; 0.001</b>"],
    ], [72 * mm, 93 * mm], ["L", "L"], highlight=(1,))
    f += [P("The permutation null preserves failure dates and size terciles and permutes only "
            "<i>which</i> bank failed, over 1,000 draws. Chance would have caught about five.")]

    f += [P("9. By year", H2)]
    f += table(["Year", "Failures", "Alerted"],
               [["2013", "24", "24"], ["2014", "18", "16"], ["2015", "8", "8"],
                ["2016", "5", "5"], ["2017", "8", "7"], ["2019", "4", "3"],
                ["2020", "4", "4"], ["<b>2023</b>", "<b>5</b>", "<b>1</b>"]],
               [40 * mm, 40 * mm, 40 * mm], ["L", "R", "R"], highlight=(8,))
    f += [P("Seven consecutive years at or near complete recall, then a collapse. The "
            "remainder of this report is about that last row.", CAP)]

    f += [P("10. What the asset-quality components contributed", H2)]
    f += table(["Model", "Caught", "Median lead", "Precision", "AUC"], [
        ["Six components (capital, earnings, interest)", "55 / 68", "14.4 months", "2.04%", "0.895"],
        ["<b>Nine, adding asset quality and funding</b>", "<b>55 / 68</b>", "14.5 months",
         "<b>3.93%</b>", "0.894"],
    ], [68 * mm, 22 * mm, 28 * mm, 24 * mm, 23 * mm], ["L", "C", "R", "R", "R"],
        highlight=(2,))
    f += [P("Identical recall, lead and AUC &mdash; and half the false alarms. Asset quality "
            "is the strongest standalone signal in the system, yet it changes nothing about "
            "<i>which</i> banks are caught, because capital and earnings already identify "
            "them. What it adds is discrimination among the many banks that look weak, which "
            "halves the list needed to catch the same failures.")]

    # ================= PART V =================
    f += part("V", "What the Model Cannot See",
              "In March 2023 three of the four largest bank failures in US history occurred "
              "inside the held-out window. The model flagged none of them.")

    f += [P("11. Recall by count and by assets", H2)]
    f += table(["Period", "Failures caught", "Failed assets caught"], [
        ["2013-2022", "53 of 58  (91%)", "<b>$20.1bn of $20.4bn  (99%)</b>"],
        ["<b>2023</b>", "<b>1 of 5</b>", "<b>$0.1bn of $532.2bn  (0.02%)</b>"],
        ["Full held-out period", "54 of 63  (86%)", "<b>4%</b>"],
    ], [38 * mm, 50 * mm, 77 * mm], ["L", "C", "R"], highlight=(2, 3))
    f += [P("<b>By count the system looks strong. By assets it caught 4% of what failed.</b> "
            "Those two numbers describe the same model on the same data, and the gap between "
            "them is the most important result in this report.")]

    f += [P("12. What Silicon Valley Bank's last call report said", H2)]
    f += [P("SVB filed for the quarter ending 31 December 2022, public in February 2023. It "
            "failed on 10 March 2023. The figures, in $ thousands:")]
    f += code([
        "assets              209,026,000       equity / assets      7.39%",
        "equity               15,456,000       return on assets     0.96%",
        "deposits            175,378,000       non-performing      0.066%",
        "                 (191,431,000 a year earlier,  -8.4%)",
    ])
    f += [P("On every measure this system reads, SVB was a well-capitalised, profitable bank "
            "with almost no bad loans. Its non-performing ratio sat in the best quartile of "
            "its peer group. The index scored it <b>59.0</b> against an alert threshold of "
            "85, or 65 with a sharp move.")]
    f += table(["Bank", "Last index", "Capital", "Non-performing", "Profitability",
                "Deposit contraction"], [
        ["Silicon Valley Bank", "59.0", "75", "25", "70", "<b>94</b>"],
        ["Signature Bank", "61.9", "77", "53", "51", "<b>98</b>"],
        ["First Republic Bank", "48.6", "63", "21", "78", "19"],
    ], [42 * mm, 24 * mm, 22 * mm, 28 * mm, 26 * mm, 33 * mm],
        ["L", "R", "R", "R", "R", "R"])
    f += [P("Component percentiles against peers, on the last call report published before "
            "failure. 100 is worst in the peer group.", CAP)]
    f += [P("<b>One component did fire.</b> Deposit contraction put SVB at the 94th "
            "percentile and Signature at the 98th &mdash; the deposit flight was visible in "
            "the filings. But deposit contraction was the weakest component in development "
            "(AUC 0.580, Part III) and carries a 6% weight, so it could not move a composite "
            "dominated by capital and asset quality.")]

    f += [P("13. It does not beat a one-line benchmark", H2)]
    f += [P("The Texas Ratio &mdash; non-performing assets divided by tangible equity plus "
            "loss reserves &mdash; is the standard bank-distress screen, computable in one "
            "line. Any claim that a nine-component index is worth building has to survive "
            "comparison with it. At a matched 2.8% watchlist rate on the held-out period:")]
    f += table(["Signal", "AUC", "Failures caught", "Precision"], [
        ["Nine-component index", "0.894", "56 of 63", "3.98%"],
        ["Texas Ratio", "0.869", "56 of 63", "4.02%"],
        ["<b>Equity / assets alone</b>", "<b>0.913</b>", "<b>56 of 63</b>", "3.57%"],
    ], [55 * mm, 25 * mm, 45 * mm, 30 * mm], ["L", "R", "C", "R"], highlight=(3,))
    f += [P("<b>All three catch the same 56 failures.</b> The composite adds no recall over "
            "a single ratio, and on this period a bare capital ratio has the higher AUC. "
            "What the composite provides is a decomposable score with an explicit reason "
            "attached to each alert &mdash; interpretability, not accuracy.")]
    f += [P("This also qualifies a claim made elsewhere in this project. Over the full "
            "2003-2023 period the composite does beat a leverage ratio (0.861 against "
            "0.837). On the held-out period the ranking reverses. The advantage is not "
            "robust to the period chosen, and should not be presented as though it were.")]

    f += [P("14. Why a credit model is blind to a duration run", H2)]
    f += [P("The 2008-12 failures, on which this model was built, were credit events: banks "
            "made bad loans, the loans went bad, reserves and then capital absorbed the "
            "losses, and the bank closed. Every stage of that sequence is visible in the "
            "ratios above, which is why the model achieves 99% asset recall in 2013-2022.")]
    f += [P("The 2023 failures were not credit events. Jiang and co-authors [6] describe the "
            "mechanism: banks held long-dated securities bought at low rates, rate rises cut "
            "their market value, and the resulting unrealised losses were large relative to "
            "equity but were <b>not recognised in the reported figures</b> for securities "
            "held to maturity. A concentrated, uninsured depositor base then withdrew faster "
            "than the bank could sell assets without crystallising those losses.")]
    f += [P("None of that appears in the nine components. The fields that would capture it "
            "are available in call reports and were simply not pulled here:")]
    f += bullets([
        "<b>Unrealised securities losses</b> (accumulated other comprehensive income, and the "
        "amortised-cost versus fair-value gap on held-to-maturity portfolios).",
        "<b>Held-to-maturity share of assets</b> &mdash; how much of the balance sheet is "
        "carried at a value the market no longer agrees with.",
        "<b>Uninsured deposit share</b> &mdash; how much of the funding can leave in a day.",
        "<b>Securities duration</b> &mdash; how much value a given rate move destroys.",
    ])
    f += [P("<b>These were not added and the model was not re-run.</b> Adding features after "
            "seeing which failures were missed, and then reporting improved recall on those "
            "same failures, would be fitting to the test set. The honest statement is that "
            "this system detects credit-driven failure and is structurally blind to "
            "interest-rate-driven runs, and that the fix is specified above but untested.")]
    f += [P("The general lesson is not about banks. A model trained on one failure mechanism "
            "measures that mechanism. It will score well on a held-out sample drawn from the "
            "same mechanism &mdash; seven straight years here &mdash; and fail completely the "
            "first time the mechanism changes. Out-of-sample testing does not protect against "
            "this, because the new regime is not in any sample yet.")]

    # ================= PART VI =================
    f += part("VI", "Limitations",
              "Read this before quoting any figure above.")

    f += [P("15. Scope of the claim", H2)]
    f += bullets([
        "<b>The 4% asset-recall figure is the headline, not the 86%.</b> The system is "
        "demonstrated on small and mid-sized credit-driven failures. It has no demonstrated "
        "ability on large institutions, and one clear demonstration of failure on them.",
        "<b>The held-out period is thin.</b> 63 failures, and 2014-2022 contributes fewer "
        "than 35. Seven years of near-complete recall rests on a small annual count.",
        "<b>Development is one crisis.</b> 529 of the events come from a single 2008-12 wave "
        "with a common cause. The model learned that cause well.",
        "<b>The index is a rank, not a probability.</b> A score of 85 means worse than 85% of "
        "comparable banks that quarter. It is not a probability of failure, and most banks "
        "above the threshold do not fail: precision is 3.93%.",
    ])

    f += [P("16. Data and construction", H2)]
    f += bullets([
        "<b>Call-report figures are as filed.</b> Reported non-performing assets depend on a "
        "bank's own classification decisions, and the 2017 failure missed here (Washington "
        "Federal Bank for Savings) was a fraud case in which the filings were false.",
        "<b>Securities and interest-rate risk are entirely absent</b> from the feature set, "
        "as Part V describes.",
        "<b>Failures after 2023 cannot be evaluated</b> because the call-report panel ends at "
        "2023Q4, so the four failures in 2025-2026 are excluded rather than counted as misses.",
        "<b>Size terciles are recomputed each quarter</b>, so a growing bank can change peer "
        "group, and therefore score, without changing itself.",
        "<b>Weights are judgement.</b> They were not fitted, which protects the held-out "
        "test, but it also means no claim is made that they are optimal.",
    ])

    f += [P("17. Reproducing this", H2)]
    f += code([
        "pip install pandas numpy",
        "",
        "python3 fdic_fetch.py      # FDIC failures + call reports -> fdic_panel.csv",
        "python3 fdic_model.py      # components, thresholds, held-out test",
        "",
        "# roughly 90 API calls, no authentication, about 15 minutes",
    ])
    f += [P("Every figure in this report is produced by those two scripts.", CAP)]

    # ---------------- references ----------------
    f += [PageBreak(), P("REFERENCES", EYE), P("References", H1)] + rule_bar()
    refs = [
        "R. C. Merton, &ldquo;On the pricing of corporate debt: The risk structure of "
        "interest rates,&rdquo; <i>J. Finance</i>, vol. 29, no. 2, pp. 449&ndash;470, 1974.",
        "E. I. Altman, &ldquo;Financial ratios, discriminant analysis and the prediction of "
        "corporate bankruptcy,&rdquo; <i>J. Finance</i>, vol. 23, no. 4, pp. 589&ndash;609, 1968.",
        "Federal Deposit Insurance Corporation, &ldquo;BankFind Suite: API for developers,&rdquo; "
        "FDIC. [Online]. Available: https://api.fdic.gov",
        "Federal Financial Institutions Examination Council, &ldquo;Consolidated Reports of "
        "Condition and Income (Call Reports),&rdquo; FFIEC.",
        "R. A. Cole and L. J. White, &ldquo;D&eacute;j&agrave; vu all over again: The causes of "
        "U.S. commercial bank failures this time around,&rdquo; <i>J. Financial Services "
        "Research</i>, vol. 42, pp. 5&ndash;29, 2012.",
        "E. X. Jiang, G. Matvos, T. Piskorski and A. Seru, &ldquo;Monetary tightening and "
        "U.S. bank fragility in 2023: Mark-to-market losses and uninsured depositor "
        "runs?&rdquo; NBER Working Paper 31048, 2023.",
    ]
    for i, r in enumerate(refs, 1):
        f.append(Paragraph(f"[{i}]&nbsp;&nbsp;{r}",
                           ParagraphStyle("r", parent=BODY, fontSize=10, leading=15,
                                          spaceAfter=9)))

    doc.build(f)
    print(f"wrote {OUT} ({os.path.getsize(OUT)/1024:.0f} KB)")


if __name__ == "__main__":
    build()
