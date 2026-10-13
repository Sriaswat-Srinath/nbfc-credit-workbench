"""Generate the methodology report PDF (high-level + low-level)."""

import os
import re
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle, PageBreak, KeepTogether)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "Default_Risk_System_Methodology.pdf")

INK = colors.HexColor("#15181D")
NAVY = colors.HexColor("#16314F")
TEAL = colors.HexColor("#2C7A7B")
GREY = colors.HexColor("#5A6069")
RULE = colors.HexColor("#D8D8D0")
SOFT = colors.HexColor("#F4F4F0")
RED = colors.HexColor("#9D3528")

S = getSampleStyleSheet()


def style(name, **kw):
    kw.setdefault("parent", S["Normal"])
    return ParagraphStyle(name, **kw)


BODY = style("Body", fontName="Times-Roman", fontSize=10, leading=14.5,
             textColor=INK, alignment=TA_JUSTIFY, spaceAfter=7)
LEAD = style("Lead", parent=BODY, fontSize=11, leading=16, textColor=colors.HexColor("#2C333C"))
H1 = style("H1", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=NAVY,
           spaceBefore=4, spaceAfter=3)
H2 = style("H2", fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=NAVY,
           spaceBefore=15, spaceAfter=5)
H3 = style("H3", fontName="Helvetica-Bold", fontSize=10, leading=13.5, textColor=INK,
           spaceBefore=10, spaceAfter=3)
BUL = style("Bul", parent=BODY, leftIndent=13, bulletIndent=3, spaceAfter=4)
CAP = style("Cap", fontName="Helvetica", fontSize=8, leading=11, textColor=GREY, spaceAfter=9)
EYE = style("Eye", fontName="Helvetica-Bold", fontSize=7.5, leading=11, textColor=TEAL)
CODE = style("Code", fontName="Courier", fontSize=8.2, leading=12, textColor=colors.HexColor("#22272E"))
TCELL = style("TCell", fontName="Times-Roman", fontSize=8.6, leading=11.5, textColor=INK)
THEAD = style("THead", fontName="Helvetica-Bold", fontSize=7.4, leading=10,
              textColor=colors.white)


def P(t, s=BODY):
    return Paragraph(t, s)


def bullets(items, s=BUL):
    return [Paragraph(t, s, bulletText="•") for t in items]


def code(lines):
    """Monospaced block on a tinted panel.

    Paragraph collapses runs of whitespace, which destroys the column alignment
    these blocks rely on, so leading and internal runs become non-breaking.
    """
    body = "<br/>".join(
        re.sub(r"  +", lambda m: "&nbsp;" * len(m.group()), ln) for ln in lines
    )
    t = Table([[Paragraph(body, CODE)]], colWidths=[165 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SOFT),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return [t, Spacer(1, 8)]


def table(header, rows, widths, aligns=None, highlight=None):
    data = [[Paragraph(h, THEAD) for h in header]]
    for r in rows:
        data.append([Paragraph(str(c), TCELL) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1)
    st = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT]),
    ]
    for i, a in enumerate(aligns or []):
        if a != "L":
            st.append(("ALIGN", (i, 0), (i, -1), "RIGHT" if a == "R" else "CENTER"))
    for r in (highlight or []):
        st.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#FDF3E3")))
    t.setStyle(TableStyle(st))
    return [t, Spacer(1, 10)]


def rule(c=TEAL, w=28 * mm, th=1.6):
    t = Table([[""]], colWidths=[w], rowHeights=[th])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), c)]))
    return [Spacer(1, 3), t, Spacer(1, 9)]


def part(n, title, blurb):
    return [PageBreak(), P(f"PART {n}", EYE), P(title, H1)] + rule() + [P(blurb, LEAD), Spacer(1, 4)]


def on_page(canv, doc):
    canv.saveState()
    canv.setFont("Helvetica", 7.5)
    canv.setFillColor(GREY)
    canv.drawString(22 * mm, 13 * mm, "Bank & NBFC Default Risk Intelligence System")
    canv.drawRightString(188 * mm, 13 * mm, str(canv.getPageNumber()))
    canv.setStrokeColor(RULE)
    canv.setLineWidth(0.4)
    canv.line(22 * mm, 16 * mm, 188 * mm, 16 * mm)
    canv.restoreState()


def build():
    doc = BaseDocTemplate(OUT, pagesize=A4,
                          leftMargin=22 * mm, rightMargin=22 * mm,
                          topMargin=20 * mm, bottomMargin=22 * mm,
                          title="Bank & NBFC Risk Workbench - Methodology",
                          author="Team B-15")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=on_page)])

    f = []

    # ---------------- cover ----------------
    f += [Spacer(1, 34 * mm), P("METHODOLOGY REPORT", EYE),
          P("Bank &amp; NBFC Risk Workbench", H1)]
    f += rule(TEAL, 42 * mm, 2.2)
    f += [P("A comparative financial distress and structural credit-risk system for "
            "Indian banks and NBFCs. How both analyses are built, how they were tested "
            "against real RBI actions and defaults, and what they cannot tell you.", LEAD),
          Spacer(1, 10)]
    f += table(["", ""], [
        ["Universe", "556 Indian banks and NBFCs (39 banks, 517 finance companies)"],
        ["Panel", "6,223 company-years, 563 institutions, FY2006-FY2023 (dense from FY2012)"],
        ["Accounts", "Detailed Financials of 4,456 NSE &amp; BSE companies (public archive)"],
        ["Prices", "303,995 daily closes, 180 symbols, 2,713 trading days, from NSE's own archive"],
        ["Analysis 1", "Fundamental Distress Index - reads the published accounts"],
        ["Analysis 2", "Merton / KMV distance-to-default - reads the equity market"],
        ["Validation", "18 labelled distress events, each with a public source"],
        ["Headline", "7 of 7 held-out events caught by a rule that never saw them, p = 0.0003"],
        ["Coverage", "18 of 22 known distress events now evaluable, after recovering 7 from source"],
    ], [30 * mm, 135 * mm], ["L", "L"])
    f += [Spacer(1, 6),
          P("Academic decision support. Not investment advice and not a credit rating.", CAP)]

    # ---------------- contents ----------------
    f += [PageBreak(), P("CONTENTS", EYE), P("What is in this report", H1)] + rule()
    f += table(["Part", "Contents", "For"], [
        ["I - High level", "What the tool does and why each design choice was made, in "
         "plain language. No formulas.", "Anyone"],
        ["II - Low level: Analysis 1", "Exact definitions, transforms, thresholds and "
         "edge cases for the Fundamental Distress Index, with two worked examples.",
         "Reproducing it"],
        ["III - Low level: Analysis 2", "The Merton solver, the price pipeline, and the "
         "corporate-action problem that had to be solved exactly.", "Reproducing it"],
        ["IV - Validation", "Event set, evaluation mechanics, results, and why the "
         "headline accuracy metric is misleading.", "Defending it"],
        ["V - Pre-mortem", "Three experiments run against the system's own most likely "
         "failure modes: overfitting, unusable alerts, and missing cases.", "Stress-testing it"],
        ["VI - External validation", "The frozen methodology re-run on 547 US bank failures, "
         "to test whether it generalises or was fitted to India.", "Trusting it"],
        ["VII - Limitations", "What the evidence does not support.", "Before quoting it"],
    ], [38 * mm, 101 * mm, 26 * mm], ["L", "L", "L"])

    # ================= PART I =================
    f += part("I", "High-Level Explanation",
              "The tool reads published accounts and market prices and produces a ranked "
              "view of which lenders look fragile. It is not forecasting a date; it is "
              "answering comparative questions, and showing where two independent ways of "
              "asking disagree.")

    f += [P("1. The problem", H2)]
    f += [P("When a bank or NBFC fails, the failure is announced on a single day - a "
            "moratorium, a default, a regulator superseding the board. But the "
            "deterioration that caused it took years, and most of it sat in public filings "
            "the whole time. Credit ratings and regulatory action tend to confirm distress "
            "rather than anticipate it. The question asked each year, for each lender, is: "
            "<b>compared with institutions like it, how bad does this look, and is it "
            "getting worse?</b>")]

    f += [P("2. Two analyses, deliberately different", H2)]
    f += [P("The tool runs two analyses that read different evidence. That is the point of "
            "the design, not a convenience:")]
    f += table(["", "Analysis 1 - Fundamental", "Analysis 2 - Structural (Merton)"], [
        ["Reads", "Published annual accounts", "Daily equity prices and debt"],
        ["Technique", "Financial statement analysis", "Option pricing (Black-Scholes)"],
        ["Output", "Distress index, 0-100", "Distance to default, implied PD"],
        ["Covers", "All 556 institutions", "152 listed with a liquid quote"],
        ["Strength", "Works for unlisted firms; "
                     "directly interpretable", "Moves daily; prices in what "
                     "investors suspect but accounts do not yet show"],
        ["Weakness", "Inherits whatever the "
                     "accounts conceal", "Needs a market; assumes no parent "
                     "or state support"],
    ], [24 * mm, 70 * mm, 71 * mm], ["L", "L", "L"])
    f += [P("The weakness of the first is exactly the strength of the second. Yes Bank's "
            "reported profitability ranked mid-pack right up to the end, because the bad "
            "loans had not been recognised. The share price had already collapsed. A third "
            "page in the tool is built on the gap between the two.")]

    f += [P("3. The data", H2)]
    f += [P("The accounting archive holds 4,492 listed Indian companies, each a folder of "
            "eight CSV files covering balance sheet, profit and loss, cash flow, ratios and "
            "shareholding. The 556 institutions whose sector is Banks or Finance are kept, "
            "giving 6,139 company-years from 2006 to 2023, dense from about 2012.")]
    f += [P("Two inconsistencies had to be resolved first. The files use two date formats in "
            "their column headers. More importantly, lenders file their profit and loss in "
            "two different shapes: 75 report <i>Revenue</i> and <i>Financing Profit</i>, the "
            "other 481 report <i>Sales</i> and <i>Operating Profit</i>. These are the same "
            "concepts under different labels; without unifying them 87% of the panel would "
            "carry a blank revenue column.")]
    f += [P("Prices come from NSE's own daily bhavcopy archive rather than yfinance, which "
            "is covered in Part III.")]

    f += [P("4. What Analysis 1 measures", H2)]
    f += [P("Six readings per institution per year, each a different route into trouble:")]
    f += bullets([
        "<b>How thick the cushion is.</b> Equity as a share of total assets - the money "
        "that absorbs losses before depositors and lenders start losing theirs.",
        "<b>Whether the cushion is shrinking.</b> The two-year change in equity. This is the "
        "reading that caught Reliance Capital: reserves fell from Rs 15,081 crore in FY2017 "
        "to Rs 760 crore in FY2018, then turned negative. The collapse came in late 2021.",
        "<b>Whether it earns money.</b> Return on assets. A lender that cannot earn its way "
        "out of a problem must shrink or raise capital, and distressed firms can rarely do "
        "either.",
        "<b>How much it borrows against that cushion.</b> Borrowings divided by equity.",
        "<b>How much income interest consumes.</b> A lender paying most of its revenue to "
        "its own creditors has little margin for error.",
        "<b>Whether earnings are trending down.</b> Return on assets against three years "
        "ago, which catches slow bleeds a single snapshot makes look acceptable.",
    ])

    f += [P("5. Comparing like with like", H2)]
    f += [P("A raw ratio means nothing in isolation. Seven percent equity-to-assets is "
            "ordinary for a bank and alarming for a finance company. So every reading "
            "becomes a rank - where this institution sits among comparable ones that year - "
            "on a 0 to 100 scale where 100 is always worst. Ranking self-calibrates to the "
            "cycle: in a bad year absolute numbers worsen but the ranking still identifies "
            "who is weakest, with no fixed thresholds to go stale.")]
    f += [P("<b>The first attempt was wrong, and the error is instructive.</b> Ranking all "
            "556 institutions together put HDFC Bank at 66 against a sector median of 50 - "
            "the model was calling one of the safest banks in the country above-average "
            "risky. Most of the 517-company Finance sector are not lenders at all but small "
            "investment and holding companies carrying almost no borrowings. Against that "
            "crowd, any institution funding itself normally - the whole business model of "
            "banking - looks dangerously leveraged.")]
    f += [P("Comparison sets were narrowed: banks against the other 38 banks, NBFCs against "
            "NBFCs of similar size. HDFC Bank fell to the 30s and stayed there.")]
    f += [P("<b>That fix created the opposite problem.</b> If an entire group is uniformly "
            "thin on capital, ranking inside the group makes them all look fine by their own "
            "standards - precisely the gap separating the weak public-sector banks from the "
            "private ones, which sat at 5-6% equity against 10-14%. So the two capital "
            "readings are scored twice, once against peers and once against the whole "
            "sector, and averaged. Measured on the eleven events available at the time, "
            "this moved accuracy from 0.859 to 0.912 and took the model from catching "
            "6 of those 11 to 9.")]

    f += [P("6. Why the alert has two triggers", H2)]
    f += [P("The obvious rule is to alert when the score is high. That rule fails on the "
            "most important case in the dataset. Yes Bank's FY2019 accounts, public June "
            "2019 and nine months before the moratorium, scored <b>69</b> - not low, but not "
            "high enough to flag. Yet 69 was wildly out of character: its own scores over "
            "the preceding years were 44, 40, 40, 45, and its three-year median was 39.9. "
            "FY2019 was a <b>29-point jump against itself</b>.")]
    f += [P("The rule became: alert if the score is 80 or above, <b>or</b> if it is above 60 "
            "and has risen 15 or more points above the institution's own recent median. A "
            "high score tells you <i>who</i> is weak; a rising score tells you <i>when</i> "
            "something changed.")]

    f += [P("7. What Analysis 2 measures", H2)]
    f += [P("Merton's insight is that owning equity in a leveraged firm is the same payoff "
            "as owning a call option on its assets, struck at the face value of its debt. If "
            "assets end above the debt, shareholders keep the difference; if below, they get "
            "nothing and the option expires worthless. That makes the Black-Scholes "
            "machinery from the derivatives part of the course directly applicable to credit "
            "risk.")]
    f += [P("Asset value and asset volatility are not observable, but equity value and "
            "equity volatility are. Two equations - the option price and its volatility "
            "relationship - are solved for the two unknowns. The result is "
            "<b>distance to default</b>: how many standard deviations of asset value sit "
            "between the firm and its debt. Feeding that through the normal distribution "
            "gives a model-implied probability of default.")]
    f += [P("The number this produces is an output of the model's assumptions, not an "
            "observed default rate. Its value is comparative and directional: that Yes "
            "Bank's implied probability rose from 1.5% to 36% over fifteen months is far "
            "more meaningful than the 36% itself.")]

    f += [P("8. The tool", H2)]
    f += [P("A Streamlit application with a menu of five pages:")]
    f += table(["Page", "What the user does"], [
        ["Data Explorer", "Filter by sector, peer group, year range and institution, then "
         "compute descriptive statistics on that selection - mean, median, standard "
         "deviation, quartiles, IQR, skew, correlation matrix, year-on-year changes, "
         "distribution and data coverage. Nothing is precomputed; results download as CSV."],
        ["1 - Fundamental Distress", "Pick an institution and year. See the six components "
         "with raw values, percentiles and weighted contributions, the trajectory against "
         "the peer median, the alert status and the full peer ranking."],
        ["2 - Structural Credit Risk", "Pick a listed institution. See distance to default "
         "and implied PD over time, plus the model inputs. Risk-free rate, horizon and "
         "default point are sliders, so the user can test how far the result depends on the "
         "assumptions."],
        ["3 - Comparative Assessment", "Both analyses on common percentile axes for a chosen "
         "year, with the institutions where they disagree most listed in both directions."],
        ["Backtest &amp; Validation", "Lead times against the real events, distressed names "
         "against healthy controls, and why accuracy alone is the wrong test."],
    ], [38 * mm, 127 * mm], ["L", "L"])

    f += [P("9. The finding worth arguing about", H2)]
    f += [P("On the standard accuracy measure, <b>a single leverage ratio beats the entire "
            "fundamental model</b> - 0.976 against 0.900. Taken at face value that makes the "
            "project pointless. It is not, for two reasons. First, seven of the eleven "
            "events are thinly capitalised public-sector banks put under Prompt Corrective "
            "Action in 2015-17, so any ratio that effectively detects “is this a PSU "
            "bank” scores brilliantly without predicting anything. Second, and more "
            "damning, <b>leverage alone never changes its mind</b>: at a matched alert rate "
            "it flags 22 institutions continuously for eight years or more - HDFC Bank, "
            "ICICI, Axis, Canara and Bank of Baroda among them - and not one of the "
            "institutions it permanently flags ever failed. A smoke detector that is always "
            "sounding has perfect recall and no value.")]

    # ================= PART II =================
    f += part("II", "Low Level: Fundamental Distress Index",
              "Exact definitions, transforms, thresholds and edge cases, in pipeline order. "
              "Implemented in build_panel.py and score.py; reruns from the archive with no "
              "network access.")

    f += [P("10. Data ingestion", H2)]
    f += bullets([
        "<b>Sector filter.</b> Keep folders whose Basic_Info sector is <font face='Courier' "
        "size='8.5'>Banks</font> or <font face='Courier' size='8.5'>Finance</font>: 39 and "
        "517 respectively.",
        "<b>Column parsing.</b> Headers appear as <font face='Courier' size='8.5'>"
        "2019-03-01</font> or <font face='Courier' size='8.5'>Mar 2019</font>. Only March "
        "columns are retained, so the September 2023 interim column is dropped as a partial "
        "period.",
        "<b>Schema unification.</b> <font face='Courier' size='8.5'>revenue</font> takes "
        "Revenue or Sales; <font face='Courier' size='8.5'>op_profit</font> takes Financing "
        "Profit or Operating Profit. First non-null wins.",
        "<b>Share count inputs.</b> Face value is carried from Basic_Info so share counts "
        "can be derived per year rather than from a present-day snapshot. Part III uses this.",
        "<b>Asset quality.</b> Gross and Net NPA exist only on the quarterly P&amp;L and only "
        "for recent quarters. They are carried as current context and never used in the "
        "backtest.",
    ])

    f += [P("11. Feature definitions", H2)]
    f += code([
        "equity            = Equity Capital + Reserves",
        "",
        "f_capital_buffer  = equity / total_assets",
        "f_capital_erosion = (equity[t] - equity[t-2]) / total_assets[t]",
        "f_leverage        = borrowings / equity          (equity &gt; 0 only)",
        "f_roa             = net_profit / total_assets",
        "f_earnings_trend  = f_roa[t] - f_roa[t-3]",
        "f_interest_burden = interest_exp / revenue",
    ])
    f += [P("Lags are taken within company after sorting by fiscal year, so a gap in a "
            "company's history shifts the lag rather than silently comparing non-adjacent "
            "years. Total assets or revenue of zero become null rather than infinity.")]

    f += [P("12. Peer-group construction", H2)]
    f += code([
        "if sector == 'Banks':   group = 'Banks'                   (39 institutions)",
        "else:                   group = 'NBFC-' + size_tercile",
        "",
        "size_tercile = qcut( rank(total_assets) , 3 ) within each fiscal year",
        "               -&gt; Small | Mid | Large",
    ])
    f += [P("Group sizes in FY2019: Banks 39, NBFC-Small 168, NBFC-Mid 167, NBFC-Large 167. "
            "Terciles are recomputed annually, so a growing NBFC can change group.", CAP)]

    f += [P("13. Percentile transform", H2)]
    f += [P("Each feature is first oriented so a larger number always means more risk "
            "(capital buffer, capital erosion, ROA and earnings trend are negated), then "
            "ranked within its (fiscal year x peer group) cell:")]
    f += code([
        "s_&lt;component&gt; = rank(oriented_value, pct=True) * 100     -&gt; 0 .. 100",
        "",
        "nulls stay null (not imputed, and they do not take a rank)",
        "cells with fewer than MIN_PEERS = 20 institutions are left unscored",
    ])

    f += [P("14. Dual anchoring on capital", H2)]
    f += code([
        "DUAL_ANCHOR = { capital_buffer , leverage }",
        "",
        "s_component = mean( rank within (fy, peer_group) ,",
        "                    rank within (fy)             )",
    ])

    f += [P("15. Edge cases", H2)]
    f += bullets([
        "<b>Negative or zero equity.</b> The firm is balance-sheet insolvent and no "
        "percentile is meaningful. Both capital components are forced to 100 and the "
        "leverage ratio is left undefined rather than reported as a negative multiple.",
        "<b>Missing components.</b> The weighted mean is renormalised over whichever "
        "components are present.",
        "<b>Insufficient coverage.</b> Rows with under 60% of components available are left "
        "unscored. 103 of 6,139 rows fall out this way.",
    ])

    f += [P("16. Aggregation and alert rule", H2)]
    f += code([
        "WEIGHTS = { capital_buffer  : 0.30 ,  leverage        : 0.12 ,",
        "            capital_erosion : 0.20 ,  interest_burden : 0.10 ,",
        "            profitability   : 0.20 ,  earnings_trend  : 0.08 }",
        "",
        "FDI = sum( s_c * w_c for available c ) / sum( w_c for available c )",
        "FDI = null  if coverage &lt; 0.60",
        "band: Low &lt; 60 | Watch 60-80 | Elevated 80-90 | High &ge; 90",
        "",
        "fdi_base3 = median of the previous 3 fiscal years' FDI",
        "            ( shift(1) then rolling(3, min_periods=2).median() )",
        "alert = ( FDI &ge; 80 ) OR ( FDI &ge; 60 AND FDI - fdi_base3 &ge; +15 )",
    ])
    f += [P("The baseline is shifted one year before the rolling median, so the current year "
            "never contributes to the baseline it is judged against.", CAP)]

    f += [P("17. Point-in-time discipline and materiality", H2)]
    f += code([
        "PUBLICATION_LAG_MONTHS = 3",
        "known_at(FY) = 31-Mar-FY + 3 months  =  30-Jun-FY",
        "HORIZON_MONTHS = 24",
        "is_pre_event = 0 &lt; (event_date - known_at) &le; 24 months",
        "post_event   = event_date &le; known_at   -&gt; excluded from evaluation",
        "",
        "is_material  = ( total_assets &ge; 500 cr ) AND ( revenue &ge; 25 cr )",
        "FY2023: 151 material of 552 scored institutions",
    ])
    f += [P("Roughly a third of the Finance sector is dormant shells: no book, no income, "
            "often deeply negative equity. The score correctly calls them insolvent and they "
            "swamp any ranked screen, so they are flagged rather than dropped.")]

    f += [P("18. Worked example: Yes Bank, FY2019", H2)]
    f += [P("Accounts public 30 June 2019; moratorium 5 March 2020. Ranked against 39 banks. "
            "All figures in Rs crore.")]
    f += code([
        "equity   =     463 + 26,424 =  26,887",
        "assets   =                    380,860",
        "ROA      =   1,709 / 380,860 =  0.0045",
        "leverage = 335,982 / 26,887  =  12.50",
        "erosion  = (26,887 - 22,039) / 380,860 = 0.0127   [FY2017 equity 22,039]",
        "trend    = 0.00449 - 0.01531 = -0.0108            [FY2016 ROA 0.01531]",
    ])
    f += table(["Component", "Raw", "Percentile", "Weight", "Contribution"], [
        ["Capital buffer (thin capital)", "0.0706", "78.7", "0.30", "23.62"],
        ["Capital erosion", "0.0127", "57.1", "0.20", "11.43"],
        ["Profitability (ROA)", "0.0045", "51.3", "0.20", "10.26"],
        ["Leverage", "12.50", "80.4", "0.12", "9.65"],
        ["Interest burden", "0.6687", "71.8", "0.10", "7.18"],
        ["Earnings trend", "-0.0108", "85.3", "0.08", "6.82"],
        ["<b>Fundamental Distress Index</b>", "", "", "", "<b>68.96</b>"],
    ], [62 * mm, 25 * mm, 26 * mm, 22 * mm, 30 * mm],
        ["L", "R", "R", "R", "R"], highlight=[7])
    f += [P("69 is below the level threshold of 80, so a level-only screen stays silent. Yes "
            "Bank's trailing three-year median was <b>39.9</b>, making FY2019 a <b>+29.0</b> "
            "move against itself, and the deterioration leg fires <b>8.2 months before the "
            "moratorium</b>. Note what the accounts did not reveal: profitability still "
            "ranked at the 51st percentile.")]

    f += [P("19. Worked example: Reliance Capital, capital erosion", H2)]
    f += table(["Fiscal year", "Reserves (Rs cr)", "Equity (Rs cr)", "Equity / assets",
                "FDI", "Alert"], [
        ["FY2016", "13,890", "14,143", "0.211", "65.0", "no"],
        ["FY2017", "15,081", "15,334", "0.186", "70.2", "no"],
        ["FY2018", "760", "1,013", "0.012", "92.1", "<b>yes</b>"],
        ["FY2019", "-1,202", "-949", "-0.011", "90.1", "yes"],
        ["FY2020", "-2,547", "-2,294", "-0.035", "84.4", "yes"],
        ["FY2021", "-11,791", "-11,538", "-0.178", "92.9", "yes"],
    ], [26 * mm, 30 * mm, 28 * mm, 30 * mm, 21 * mm, 20 * mm],
        ["L", "R", "R", "R", "R", "C"], highlight=[3])
    f += [P("FY2018 accounts became public 30 June 2018, <b>41 months</b> before RBI "
            "superseded the board. From FY2019 the negative-equity rule pins both capital "
            "components at 100.", CAP)]

    # ================= PART III =================
    f += part("III", "Low Level: Merton Structural Credit Risk",
              "The option-pricing analysis, the price pipeline behind it, and the "
              "corporate-action problem that had to be solved exactly rather than "
              "approximately.")

    f += [P("20. The model", H2)]
    f += code([
        "E  = V*N(d1) - D*exp(-r*T)*N(d2)",
        "sE = (V/E) * N(d1) * sV",
        "",
        "d1 = [ ln(V/D) + (r + sV^2/2)*T ] / ( sV*sqrt(T) )",
        "d2 = d1 - sV*sqrt(T)",
        "",
        "   E  = market value of equity        V  = market value of assets",
        "   sE = equity volatility             sV = asset volatility",
        "   D  = default point (debt)          T  = horizon, 1 year",
        "",
        "DD = [ ln(V/D) + (r - sV^2/2)*T ] / ( sV*sqrt(T) )",
        "PD = N(-DD)",
    ])
    f += [P("E and sE are observable; V and sV are not. The two equations are solved "
            "simultaneously by fixed-point iteration, the standard KMV approach: start at "
            "V = E + D and sV = sE*E/(E+D), substitute repeatedly until both move by less "
            "than 1e-6, capped at 300 iterations. Non-convergence returns null rather than a "
            "partial answer - which happens mostly when equity is tiny against debt, itself "
            "an informative state.")]

    f += [P("21. Why not yfinance", H2)]
    f += [P("The project brief suggests yfinance. Yahoo's endpoint IP-throttled this machine "
            "with HTTP 429 on every attempt across roughly 45 tries, and the usual fallback "
            "source gates behind a bot-detection challenge, which is not something to work "
            "around.")]
    f += [P("NSE publishes its <b>daily bhavcopy</b> as plain static ZIP files - the primary "
            "source Yahoo itself derives from. One file holds every symbol traded that day, "
            "so a single request covers all 180 listed institutions in the panel at once. "
            "The full 2013-2023 archive is <b>303,995 daily closes across 180 symbols over "
            "2,713 trading days</b>. Volatility uses 250-day windows scaled by sqrt(252).")]
    f += [P("An earlier version of this pipeline sampled weekly to save requests. That turned "
            "out to be a false economy: weekly sampling made corporate actions impossible to "
            "identify reliably, which is the subject of the next section.")]

    f += [P("22. The corporate-action problem", H2)]
    f += [P("The first run produced nonsense. Yes Bank showed 170% equity volatility through "
            "mid-2018 and an implied default probability of 68% at a time when it traded at "
            "Rs 170 and was considered healthy. HDFC Bank's price appeared to halve in "
            "September 2019.")]
    f += [P("Both were <b>missed stock splits</b> - Yes Bank 5:1 in 2017, HDFC Bank 1:2 in "
            "2019 - sitting in the return series as fake 80% and 50% crashes and poisoning "
            "the rolling volatility for a full year afterwards.")]
    f += [P("<b>The obvious fix is unsafe.</b> Treating any large drop whose ratio is near a "
            "round number as a split would have deleted a real event: Yes Bank genuinely "
            "halved in a single week in 2019 on real news. A loose heuristic cannot separate "
            "the two cases, and getting it wrong erases exactly the collapse the project "
            "exists to detect.")]
    f += [P("<b>A first attempt at an exact test was based on a false premise.</b> It assumed "
            "NSE's PREVCLOSE field was already adjusted for corporate actions, so that "
            "CLOSE/PREVCLOSE would give a clean return across a split. It is not adjusted. "
            "On Yes Bank's split day the file reports CLOSE 377.05 against PREVCLOSE 1880.10 "
            "- the raw drop. Every computed factor collapsed to 1 and the detector returned "
            "nothing but noise from illiquid symbols. The weekly sampling was abandoned and "
            "the full daily series collected instead.")]
    f += [P("<b>What actually works</b> is the single-day ratio on the daily series. Because "
            "the opening price is adjusted mechanically on the ex-date, a corporate action "
            "lands almost exactly on a conventional fraction, while a crash does not:")]
    f += code([
        "Yes Bank   21 Sep 2017:   377.05 / 1880.10 = 0.2005   (1/5, 0.25% off)",
        "HDFC Bank  19 Sep 2019:  1101.05 / 2187.75 = 0.5033   (1/2, 0.66% off)",
        "",
        "accept if the ratio is within 1.5% of 1/k or k, for",
        "k in [1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 20]",
    ])
    f += [P("Three guards were added, each after inspecting a real false positive in the "
            "output:")]
    f += table(["Guard", "Threshold", "The false positive it removed"], [
        ["Exclude the 20% circuit band", "1.25 removed from the ratio list",
         "0.80 is exactly India's lower circuit limit, so locked-down days land on it "
         "precisely. It was labelling three of Reliance Capital's 2019 crash days as bonus "
         "issues."],
        ["Market breadth", "reject days where &gt;6% of symbols moved &gt;10%",
         "19 March 2020 had 12.5% breadth and was reading Indiabulls Housing's COVID crash "
         "as a 1.5x split. Genuine split days show 1.4-3.4% breadth."],
        ["Minimum history", "60 prior trading days",
         "Ujjivan Small Finance Bank's listing-day pop."],
        ["No clustering", "drop pairs within 30 days",
         "Two opposite 1.5x 'actions' five days apart in an illiquid micro-cap."],
    ], [38 * mm, 42 * mm, 85 * mm], ["L", "L", "L"])
    f += [P("The result is <b>12 corporate actions</b> across the panel, all of which check "
            "out against the public record: Axis 5:1 (2014), Bank of Baroda 5:1 (2015), "
            "ICICI 5:1 (2014), Kotak 1:1 bonus (2015), Karur Vysya 5:1 (2016), REC 1:1 bonus "
            "(2016), Yes Bank 5:1 (2017), Cholamandalam 5:1 (2019), HDFC Bank 1:2 (2019), "
            "and three smaller names.")]

    f += [P("23. Market capitalisation and share count", H2)]
    f += [P("Splits and bonus issues both halve the price, but they do different things to "
            "the share count, so they cannot be handled alike. A split cuts the face value "
            "and leaves equity capital untouched. A bonus capitalises reserves, so equity "
            "capital rises with the share count. Since the archive reports equity capital "
            "annually, the two are told apart by checking whether equity capital jumped "
            "across the action date.")]
    f += [P("The two uses of the price series then need different inputs:")]
    f += code([
        "VOLATILITY  needs clean returns, so it uses prices adjusted for every",
        "            mechanical action - splits, bonuses and rights alike.",
        "",
        "MARKET CAP  needs the true value of equity on the day:",
        "",
        "   face_value[t] = face_value_current * product of SPLIT factors after t",
        "   shares[t]     = equity_capital[t] / face_value[t]",
        "   E[t]          = raw_close[t] * shares[t]",
        "   D[t]          = borrowings[fy] * debt_fraction",
    ])
    f += [P("Bonuses are deliberately excluded from that product. Counting one twice - once "
            "in the price adjustment and again through the higher equity capital - would "
            "halve the market capitalisation before the event. Splits must be counted, "
            "because equity capital does not move. Genuine issuance comes through equity "
            "capital, so Yes Bank's fivefold FY2021 dilution is tracked rather than mistaken "
            "for a price collapse.")]
    f += [P("The fix is verifiable on both cases. Yes Bank's market capitalisation is now "
            "continuous across its September 2017 split (Rs 83,988 crore in July against "
            "Rs 79,800 crore in September, with no artificial fivefold step) and its equity "
            "volatility sits at a realistic 28-30% rather than 170%. HDFC Bank's is "
            "continuous across its September 2019 split at roughly Rs 6.8 lakh crore.")]
    f += [P("The debt figure and share count for any date come from the most recent fiscal "
            "year already public on that date, on the same 30 June rule as Analysis 1.")]

    f += [P("24. Parameters and their defaults", H2)]
    f += table(["Parameter", "Default", "Note"], [
        ["Horizon T", "1 year", "Standard KMV convention"],
        ["Risk-free rate r", "6.5%", "Approximate RBI repo over the window; a slider in the "
         "tool"],
        ["Default point D", "1.0 x borrowings", "KMV uses short-term debt plus half of "
         "long-term. The archive reports only total borrowings, so this scales it; also a "
         "slider"],
        ["Volatility window", "250 trading days", "Minimum 120 observations inside the window"],
        ["Annualisation", "sqrt(252)", "Daily returns; the solver is evaluated on a weekly grid"],
    ], [32 * mm, 30 * mm, 103 * mm], ["L", "L", "L"])
    f += [P("Because the default point and risk-free rate are genuinely uncertain, the tool "
            "shows a sensitivity grid across both. If the ordering of institutions survives "
            "those shifts, the ranking is trustworthy even where the level is not.")]

    f += [P("25. What it produces", H2)]
    f += [P("153 institutions solved, roughly 44,900 weekly distance-to-default and "
            "implied-PD points from June 2013 to December 2023. For Yes Bank the series "
            "does what the original deck only illustrated with invented numbers:")]
    f += table(["Date", "Price", "Market cap (Rs cr)", "Equity vol", "DD", "Implied 1y PD"], [
        ["Jul 2017", "1,841.8", "83,988", "30%", "3.99", "0.0%"],
        ["Sep 2017", "350.0", "79,800", "28%", "4.23", "0.0%"],
        ["Aug 2018", "373.2", "86,023", "28%", "4.07", "0.0%"],
        ["Sep 2018", "183.7", "42,331", "48%", "2.20", "1.4%"],
        ["Jan 2019", "219.6", "50,618", "58%", "1.75", "4.0%"],
        ["May 2019", "141.2", "32,547", "75%", "1.17", "12.1%"],
        ["Sep 2019", "68.5", "15,869", "88%", "0.77", "22.0%"],
        ["Jan 2020", "47.1", "10,904", "98%", "0.56", "28.8%"],
        ["Mar 2020", "16.1", "3,739", "128%", "-0.04", "51.5%"],
    ], [24 * mm, 22 * mm, 34 * mm, 24 * mm, 20 * mm, 30 * mm],
        ["L", "R", "R", "R", "R", "R"], highlight=[5, 9])
    f += [P("Two things to read off this. The price falls fivefold between July and "
            "September 2017 while market capitalisation barely moves - that is the 5:1 "
            "split, correctly handled. And the inflection is <b>September 2018</b>, which is "
            "when the RBI refused to extend the chief executive's term; the model had no "
            "knowledge of that event and picked it up from price and volatility alone.")]
    f += [P("The moratorium was 5 March 2020. The accounts-based index only reached 69 on "
            "the FY2019 filings; the market was pricing roughly a one-in-three chance of "
            "default four months before the event, and had been above 10% since mid-2019. "
            "<b>This is the clearest evidence for running both analyses</b>, and the "
            "comparative page of the tool is built on exactly that disagreement.")]

    # ================= PART IV =================
    f += part("IV", "Validation",
              "How the test was constructed, what it returned, and why the conventional "
              "accuracy metric gives the wrong answer on this event set.")

    f += [P("26. The event set", H2)]
    f += [P("Eleven events, each with a date and public source, recorded in "
            "<font face='Courier' size='8.5'>events.csv</font>. Three are hard credit events; "
            "eight are RBI Prompt Corrective Action placements, which are supervisory "
            "judgements of distress with known dates and so serve as genuine labels. "
            "Searches for Lakshmi Vilas Bank, SREI and DHFL confirmed they are absent from "
            "the archive entirely - see Limitations.")]

    f += [P("27. Lead-time results", H2)]
    f += [P("Eighteen events. A teal dot marks the seven institutions recovered from source in Part V - the frozen model had never seen any of them.")]
    f += table(["Institution", "Event", "Date", "First alert", "Lead"],
        [["Indian Overseas Bank", "PCA", "Oct 2015", "FY2012", "39 mo"], ["Dhanlaxmi Bank", "PCA", "Nov 2015", "FY2012", "40 mo"], ["United Bank of India <font color='#2C7A7B'>&#9679;</font>", "PCA", "Jan 2017", "FY2013", "42 mo"], ["UCO Bank", "PCA", "May 2017", "FY2012", "58 mo"], ["Dena Bank <font color='#2C7A7B'>&#9679;</font>", "PCA", "May 2017", "FY2016", "10 mo"], ["IDBI Bank", "PCA", "May 2017", "-", "<font color='#9D3528'><b>missed</b></font>"], ["Central Bank of India", "PCA", "Jun 2017", "FY2012", "59 mo"], ["Bank of Maharashtra", "PCA", "Jun 2017", "FY2012", "59 mo"], ["Oriental Bank of Commerce <font color='#2C7A7B'>&#9679;</font>", "PCA", "Oct 2017", "FY2017", "3 mo"], ["Bank of India", "PCA", "Dec 2017", "FY2016", "17 mo"], ["Corporation Bank <font color='#2C7A7B'>&#9679;</font>", "PCA", "Dec 2017", "FY2014", "41 mo"], ["Allahabad Bank <font color='#2C7A7B'>&#9679;</font>", "PCA", "Jan 2018", "FY2015", "30 mo"], ["Religare Enterprises", "default", "Jan 2019", "FY2013", "67 mo"], ["Reliance Home Finance", "default", "Sep 2019", "FY2019", "2 mo"], ["Lakshmi Vilas Bank <font color='#2C7A7B'>&#9679;</font>", "PCA", "Sep 2019", "FY2013", "75 mo"], ["Yes Bank", "moratorium", "Mar 2020", "FY2019", "8 mo"], ["SREI Infrastructure Finance <font color='#2C7A7B'>&#9679;</font>", "resolution", "Oct 2021", "FY2021", "3 mo"], ["Reliance Capital", "resolution", "Nov 2021", "FY2018", "41 mo"]],
        [52 * mm, 23 * mm, 22 * mm, 26 * mm, 22 * mm], ["L", "L", "L", "L", "R"], highlight=[6])
    f += [P("Alerted before the event: <b>17 of 18</b>. Alerted inside the 24-month actionable window: <b>14 of 18</b>. IDBI Bank remains the only institution never flagged. Leads beyond about three years should be read as standing concern rather than timed warning.")]

    f += [P("28. Separation, and the AUC trap", H2)]
    f += table(["Signal", "AUC", "Persistence", "Permanently flagged 8+ yrs",
                "of which failed"], [
        ["Fundamental Distress Index", "0.900", "38%", "3", "0"],
        ["Borrowings / equity alone", "<b>0.976</b>", "62%", "22", "<b>0</b>"],
        ["Equity / total assets alone", "0.932", "-", "-", "-"],
        ["Return on assets alone", "0.762", "-", "-", "-"],
    ], [52 * mm, 18 * mm, 24 * mm, 40 * mm, 27 * mm], ["L", "R", "R", "C", "C"],
        highlight=[2])
    f += [P("AUC is the Mann-Whitney probability that a randomly chosen pre-event "
            "company-year scores worse than a randomly chosen other one. Persistence is the "
            "share of a flagged institution's observed years spent on the alert list.", CAP)]
    f += [P("Two cautions. Equity/total-assets and borrowings/equity are the <b>same ratio "
            "inverted</b> (Spearman -0.86), so they are one baseline reported twice, not two "
            "independent confirmations. And the event set is clustered: with 13 of 18 events "
            "being thin-capital banks under PCA, a capital ratio is partly just detecting "
            "ownership type.")]
    f += [P("The decisive column is the last. Leverage alone permanently flags 22 "
            "institutions for eight years or more and <b>none of them ever failed</b>. It is "
            "a classification of business model, not a warning. <b>AUC is the wrong headline "
            "metric for an early-warning system on a clustered event set;</b> lead time, "
            "persistence and watchlist size are what matter.")]

    f += [P("29. Cost of the alert list, and controls", H2)]
    f += [P("Universe averages 502 institutions per year, of which 112 are material.")]
    f += table(["Rule", "Caught", "Names / yr", "Material names / yr"], [
        ["Level only: FDI &ge; 70", "16 / 18", "82", "34"],
        ["Level only: FDI &ge; 80", "13 / 18", "32", "12"],
        ["Level only: FDI &ge; 90", "4 / 18", "11", "3"],
        ["<b>Level OR deterioration (used)</b>", "<b>14 / 18</b>", "<b>54</b>", "<b>15</b>"],
    ], [66 * mm, 24 * mm, 32 * mm, 43 * mm], ["L", "C", "R", "R"], highlight=[4])
    f += [P("Six institutions that never came close to distress, tracked FY2013-FY2023: "
            "Kotak Mahindra Bank 27-35, HDFC Bank 30-43, Axis Bank 36-62, ICICI Bank 38-59, "
            "Bajaj Finance 52-70, State Bank of India 63-76. The highest reading any control "
            "produced was 76, below the alert line.")]

    f += [P("30. Components removed after testing", H2)]
    f += table(["Removed component", "AUC", "Why it fails"], [
        ["Growth burst<br/><i>2-year borrowings CAGR</i>", "0.27",
         "The intuition runs backwards at this horizon. A lender still growing its book is "
         "one wholesale markets still fund; firms about to fail are already shrinking."],
        ["Funding stress<br/><i>operating cash flow / assets</i>", "0.42",
         "For a lender, operating cash flow is dominated by loan-book movement, so it is "
         "noise rather than a liquidity read."],
    ], [48 * mm, 16 * mm, 101 * mm], ["L", "R", "L"])
    f += [P("Both scored below a coin flip in the PSU-bank cluster and the "
            "idiosyncratic-failure cluster independently, so the sign is consistent rather "
            "than small-sample noise. They were removed rather than down-weighted.")]

    # ================= PART V =================
    f += part("V", "Pre-Mortem",
              "Working backwards from the assumption that the system has already failed. "
              "Three experiments, each aimed at one of the ways that is most likely to "
              "happen. All three are reproducible: python3 premortem.py.")

    f += [P("31. The two ways this fails", H2)]
    f += [P("<b>False negatives:</b> it misses a distressed institution, or flags it too "
            "late to act. <b>False positives:</b> it flags so many institutions, so "
            "persistently, that nobody reads the list any more. The second failure is the "
            "more likely one, and the leverage baseline in Part IV is a worked example of "
            "what it looks like.")]

    f += [P("32. Experiment 1 - the unseen-event test", H2)]
    f += [P("<b>Risk:</b> the two dropped components and the alert thresholds were chosen "
            "while looking at every event then available, so the backtest may be measuring the "
            "selection rather than the model.")]
    f += [P("<b>Test:</b> redo the component decision using only the eleven events before "
            "2018 and only accounts up to FY2016, freeze everything, then run it on the seven "
            "later events it has never seen.")]
    f += table(["Component", "AUC on development data only", "Decision"], [
        ["capital_buffer", "0.883", "keep"],
        ["leverage", "0.878", "keep"],
        ["profitability", "0.809", "keep"],
        ["interest_burden", "0.775", "keep"],
        ["capital_erosion", "0.705", "keep"],
        ["earnings_trend", "0.673", "keep"],
        ["funding_stress", "0.417", "<b>drop</b>"],
        ["growth_burst", "0.270", "<b>drop</b>"],
    ], [50 * mm, 65 * mm, 50 * mm], ["L", "R", "L"], highlight=[7, 8])
    f += [P("<b>Result:</b> the kept set is <b>identical</b> to the shipped model. The drop "
            "decision replicates without ever seeing the later events, so it is not an "
            "artefact of hindsight. The frozen model then caught <b>7 of 7</b> held-out "
            "events, with a watchlist of 66 names a year (21 material):")]
    f += table(["Held-out event", "Type", "First alert", "Lead"], [
        ["Lakshmi Vilas Bank", "PCA", "FY2013", "75 months"],
        ["Religare Enterprises", "default", "FY2013", "67 months"],
        ["Reliance Capital", "resolution", "FY2018", "41 months"],
        ["Allahabad Bank", "PCA", "FY2015", "30 months"],
        ["Yes Bank", "moratorium", "FY2019", "8 months"],
        ["SREI Infrastructure Finance", "resolution", "FY2021", "3 months"],
        ["Reliance Home Finance", "default", "FY2019", "2 months"],
    ], [52 * mm, 28 * mm, 32 * mm, 53 * mm], ["L", "L", "L", "R"])
    f += [P("<b>What this does not prove.</b> Seven events is still few, and the split is "
            "temporal rather than random, so the two halves differ in composition as well as "
            "date. It rules out one specific failure - that the result is purely an artefact "
            "of the selection step - and nothing more.")]

    f += [P("33. Experiment 2 - the alert-utility test", H2)]
    f += [P("<b>Risk:</b> a rule can score well on recall and still be unusable, because it "
            "flags structural leverage rather than approaching distress.")]
    f += [P("<b>Test:</b> score every rule on what an analyst actually experiences - how "
            "many names land on the desk, how often an alert is followed by an event, and "
            "how many institutions are permanently lit up.")]
    f += table(["Rule", "Caught", "Precision", "Alerts/yr",
                "Material/yr", "Persistence", "Always-on"], [
        ["FDI &ge; 80 (level only)", "13/18", "5.9%", "32", "12", "33%", "2"],
        ["FDI &ge; 70 (level only)", "16/18", "3.7%", "82", "34", "42%", "8"],
        ["<b>FDI level OR deterioration</b>", "<b>14/18</b>", "3.9%", "<b>54</b>",
         "<b>15</b>", "<b>27%</b>", "<b>2</b>"],
        ["Borrowings/equity, top decile", "15/18", "6.8%", "49", "45", "62%", "22"],
        ["Equity/assets, worst decile", "17/18", "7.0%", "51", "33", "60%", "19"],
        ["<b>Merton DD, worst decile</b>", "4/18", "<b>7.2%</b>", "<b>9</b>", "4",
         "23%", "<b>0</b>"],
    ], [46 * mm, 17 * mm, 20 * mm, 20 * mm, 22 * mm, 22 * mm, 18 * mm],
        ["L", "C", "R", "R", "R", "R", "C"], highlight=[3, 6])
    f += [P("Precision is the share of alert-years followed by an event within 24 months; "
            "persistence is the share of a flagged firm's observed years spent on the list; "
            "always-on counts firms flagged in every one of their 8 or more observed years.",
            CAP)]
    f += [P("<b>Every precision figure is low single digits, and that is the honest "
            "headline.</b> With 18 events among roughly 500 institutions the base rate is "
            "about 0.4%, so even a good screen produces mostly non-events. These numbers are "
            "only usable relative to each other.")]
    f += [P("Read that way, two things stand out. The single-ratio baselines keep 19 and 22 "
            "institutions permanently lit, against 2 for the composite - the same finding as "
            "Part IV, now in the units an analyst cares about. And the <b>market-based model "
            "still has the best precision of anything tested (7.2%) on much the smallest "
            "watchlist (9 names a year) with no always-on names at all</b>, while catching "
            "only 4 of 18 events. Its watchlist is small partly because it can only rank the "
            "~150 listed institutions, so the figure is not strictly like-for-like.")]
    f += [P("That is not a defect, it is the division of labour the two-analysis design "
            "predicts. Merton only sees listed firms, and it is structurally blind to the "
            "public-sector banks that dominate the event set, because their share prices "
            "embed an implicit state guarantee and never priced distress. Where it can see, "
            "it is sharp and selective. Where it cannot, the accounts are all there is.")]

    f += [P("34. Experiment 3 - the coverage test, and closing the gap", H2)]
    f += [P("<b>Risk:</b> the archive may systematically exclude the hardest cases, making "
            "the system look more reliable than it is.")]
    f += [P("<b>Test:</b> enumerate the Indian bank and NBFC distress events of 2013-2023 "
            "that a complete study would cover, and check how many are present. The first "
            "run of this test was the worst result in the project: <b>only 11 of 22 were "
            "evaluable, and every single missing name was a failure.</b> The archive keeps "
            "survivors and drops institutions that merge, resolve or delist.")]
    f += [P("<b>That gap has since been closed, not merely documented.</b> The archive's "
            "schema is screener.in's balance-sheet layout, so the same statements could be "
            "pulled for the missing institutions in identical accounting definitions and "
            "dropped straight into the panel - no reconciliation, no re-derivation. Seven "
            "of the eleven were recovered this way:")]
    f += table(["", "Count", "Institutions"], [
        ["Originally evaluable", "11", "Yes Bank, Reliance Capital, Reliance Home Finance, "
         "Religare, Dhanlaxmi, IDBI, Indian Overseas, UCO, Central Bank, Bank of "
         "Maharashtra, Bank of India"],
        ["<b>Recovered from source</b>", "<b>7</b>", "<b>Allahabad, Corporation, Dena, "
         "Oriental Bank of Commerce, United Bank of India, Lakshmi Vilas Bank, SREI "
         "Infrastructure Finance</b>"],
        ["Still unrecoverable", "4", "DHFL (delisted, statements withdrawn); IL&amp;FS and "
         "Altico Capital (never listed); Punjab &amp; Maharashtra Co-op (outside the listed "
         "universe)"],
    ], [38 * mm, 18 * mm, 109 * mm], ["L", "C", "L"], highlight=[2])
    f += [P("Coverage rises from <b>11 of 22 (50%) to 18 of 22 (82%)</b>, and the panel "
            "grows to 563 institutions and 6,223 company-years. Every recovered institution "
            "is a failure, so this removes the most damaging part of the bias rather than a "
            "random slice of it.")]
    f += [P("<b>The recovered institutions were scored by a model frozen before they "
            "existed in the panel</b> - same components, same weights, same thresholds, no "
            "retuning of any kind. On the seven it had never seen, the frozen rule alerted "
            "inside the 24-month window for six:")]
    f += table(["Recovered institution", "Event", "Date", "Alerted in 24m", "Lead"], [
        ["United Bank of India", "PCA", "Jan 2017", "yes", "18 months"],
        ["Dena Bank", "PCA", "May 2017", "yes", "10 months"],
        ["Oriental Bank of Commerce", "PCA", "Oct 2017", "yes", "3 months"],
        ["Corporation Bank", "PCA", "Dec 2017", "yes", "17 months"],
        ["Allahabad Bank", "PCA", "Jan 2018", "<font color='#9D3528'><b>no</b></font>",
         "- (peak 81)"],
        ["Lakshmi Vilas Bank", "PCA", "Sep 2019", "yes", "15 months"],
        ["SREI Infrastructure Finance", "resolution", "Oct 2021", "yes", "3 months"],
    ], [50 * mm, 22 * mm, 22 * mm, 30 * mm, 30 * mm],
        ["L", "L", "L", "C", "R"], highlight=[5])
    f += [P("Adding seven banks moved the existing peer groups only marginally - the Banks "
            "group goes from 39 to 41 in FY2017, and the control range for HDFC Bank shifts "
            "from 30-43 to 28-43, Kotak from 27-35 to 25-32. The ranking is not being "
            "rewritten by the new entrants.")]
    f += [P("<b>What remains.</b> Four events are still unevaluable and all four are "
            "failures, so measured recall stays somewhat optimistic. DHFL is the painful "
            "one: a large housing-finance default whose statements have been withdrawn from "
            "the source, and recovering it would need annual reports transcribed by hand.")]

    f += [P("35. What would change the verdict", H2)]
    f += [P("The question worth holding the team to: <i>if an Indian NBFC defaults tomorrow, "
            "what evidence would show the model genuinely had a chance to see it coming?</i> "
            "Concretely:")]
    f += bullets([
        "The institution was in the scored universe at the time, with accounts no more than "
        "18 months stale.",
        "Its index was already elevated, or had moved sharply against its own history, on "
        "the last filing published before the event.",
        "It appeared on a watchlist of a size someone could actually work through - a few "
        "dozen names, not several hundred.",
        "If listed, its distance to default had been falling for more than one quarter.",
        "And the contrary evidence: if the alert had been continuously on for five years, "
        "the model did not predict anything. It described a weak institution, which is a "
        "different and much cheaper claim.",
    ])

    # ================= PART V =================
    f += [P("36. Experiment 1, corrected - the contamination I had missed", H2)]
    f += [P("Experiment 1 as first run re-selected the <i>components</i> on pre-2018 "
            "evidence but kept the alert <i>thresholds</i> that were chosen while all "
            "events then available were visible. That matters specifically because the "
            "deterioration rule was designed around Yes Bank's FY2019 score of 69 - and "
            "Yes Bank sits in the held-out set. The original held-out claim was therefore not "
            "clean.")]
    f += [P("Re-deriving the thresholds on development events alone, under a selection "
            "rule fixed before searching (maximise development events caught, tie-break "
            "on the smaller material watchlist):")]
    f += table(["", "Shipped thresholds", "Re-derived on development data only"], [
        ["Level trigger", "FDI &ge; 80", "FDI &ge; 70"],
        ["Deterioration trigger", "FDI &ge; 60 and jump &ge; +15",
         "FDI &ge; 65 and jump &ge; +25"],
        ["Development events caught", "-", "10 of 11"],
        ["Material watchlist", "15 names/yr", "35 names/yr"],
        ["<b>Held-out events caught</b>", "7 of 7 (contaminated)",
         "<b>7 of 7 (clean)</b>"],
    ], [42 * mm, 48 * mm, 75 * mm], ["L", "L", "L"], highlight=[5])
    f += [P("The re-derived thresholds are <b>different</b> from the shipped ones, and "
            "they still catch all seven held-out events - Yes Bank at 8 months, now "
            "through a rule that never saw it. That is a stronger result than the "
            "original claim, and an honest one. It comes at a real cost: the "
            "development-derived rule is looser and more than doubles the material "
            "watchlist, from 15 names a year to 35.")]

    f += [P("37. The permutation test - could this be chance?", H2)]
    f += [P("With eighteen events among roughly 500 institutions, the question that matters "
            "is not AUC or recall but whether the result could arise by luck. The null "
            "hypothesis is that the alert rule carries no information about <i>which</i> "
            "institution failed.")]
    f += [P("The null keeps the real event dates and the real sector of each event, and "
            "permutes only which institution failed, drawn from institutions of the same "
            "sector actually scored in that window. Scattering events uniformly across the "
            "panel would make the test far too easy to pass. 4,000 permutations.")]
    f += table(["Statistic", "Observed", "Null mean", "Null 95th pct", "p-value"], [
        ["Events alerted (all 18)", "17", "7.20", "11.0", "&lt; 0.00025"],
        ["Alert precision", "2.55%", "1.02%", "1.55%", "&lt; 0.00025"],
        ["<b>Events alerted (held-out 7 only)</b>", "<b>7</b>", "<b>2.18</b>", "-",
         "<b>0.0003</b>"],
    ], [58 * mm, 24 * mm, 24 * mm, 29 * mm, 30 * mm],
        ["L", "C", "R", "R", "R"], highlight=[3])
    f += [P("The first two rows use a rule whose thresholds were derived on 11 of those 18 "
            "events, so they are partly in-sample. <b>The third row is the clean one:</b> "
            "on the seven events the thresholds never saw, catching all seven has a "
            "probability of 0.03% under the null. Under chance, a random same-sector "
            "institution is alerted before its assigned event about 2.2 times out of 7.")]
    f += [P("This is the strongest statistical statement the project can make, and it is "
            "worth being precise about what it does and does not establish. It rules out "
            "the hypothesis that the alert rule is picking institutions at random. It says "
            "nothing about the four distress events still missing from the panel, and a "
            "permutation test cannot repair a biased sample.")]

    f += [P("38. Intervals and event types", H2)]
    f += [P("Every headline figure with an interval attached, so that no two of them get "
            "compared as though the difference were real:")]
    f += table(["Measure", "Estimate", "95% confidence interval"], [
        ["Overall recall within 24 months", "14 of 18 (78%)", "52% to 94%"],
        ["Median lead time", "12 months", "6 to 17 months"],
        ["Recall, PCA placements", "9 of 13 (69%)", "39% to 91%"],
        ["Recall, credit events", "5 of 5 (100%)", "48% to 100%"],
        ["Held-out recall (Experiment 1)", "7 of 7 (100%)", "59% to 100%"],
    ], [60 * mm, 40 * mm, 65 * mm], ["L", "L", "L"])
    f += [P("Recall intervals are Clopper-Pearson; the lead-time interval is a bootstrap "
            "over 5,000 resamples.", CAP)]
    f += [P("Two things follow. First, the overall recall interval now <b>excludes 50%</b>, "
            "which it did not before the seven institutions were recovered - that is the "
            "single clearest benefit of closing the coverage gap. Second, the PCA and "
            "credit-event intervals still overlap heavily, so the gap between 69% and "
            "100% is not evidence that the model handles credit events better.")]
    f += [P("The same logic retires several comparisons made earlier in this report: the "
            "precision figures in section 33 sit inside each other's error bars and should not be "
            "read as one rule beating another.")]

    f += [P("39. Testing five more signal families", H2)]
    f += [P("Both existing analyses share a blind spot: one reads the accounts, the other "
            "needs a liquid listed share, and neither sees funding pressure or earnings "
            "quality directly. Further signal families were built and tested, each as a "
            "separate module scored on the same peer-relative scale, at the same "
            "point-in-time date, against the same 18 events.")]
    f += [P("Three could not be built at all, and it is worth being explicit about why: "
            "<b>credit-rating actions</b> have no free, consistent historical feed of "
            "Indian rating changes with dates; <b>bond and CDS spreads</b> are not publicly "
            "available at instrument level for Indian issuers; <b>trading volume</b> was "
            "discarded when the price extracts were cached and would need a full re-fetch.")]
    f += table(["Signal", "Coverage", "AUC (to FY2016)", "AUC (FY2017+)"], [
        ["Market: drawdown from peak", "20%", "0.631", "0.777"],
        ["Market: abnormal 12-month return", "17%", "0.533", "0.769"],
        ["Market: volatility spike", "17%", "0.478", "0.599"],
        ["<b>Funding: loan book shrinking</b>", "<b>61%</b>", "<b>0.736</b>", "<b>0.624</b>"],
        ["Funding: financing cash outflow", "98%", "0.566", "0.536"],
        ["Funding: thin liquid buffer", "100%", "0.390", "0.534"],
        ["Quality: profit minus operating cash", "98%", "0.321", "0.438"],
        ["Quality: other-income reliance", "97%", "0.299", "0.496"],
        ["<i>FDI composite, for reference</i>", "<i>100%</i>", "<i>0.906</i>", "<i>0.892</i>"],
    ], [60 * mm, 25 * mm, 38 * mm, 36 * mm], ["L", "R", "R", "R"], highlight=[4, 9])
    f += [P("Only one of the eight has both a usable AUC and enough coverage to matter: a "
            "shrinking loan book. The market signals discriminate well in the later period "
            "but exist for only a fifth of the panel.")]

    f += [P("40. Do they add anything? Mostly not", H2)]
    f += [P("Discrimination is not the test. The test is whether adding a signal to the "
            "alert rule catches events the index misses, warns earlier, or shrinks the "
            "watchlist. Each row adds one signal as an OR condition firing on its worst "
            "decile:")]
    f += table(["Added signal", "Events caught", "Names/yr", "Material/yr"], [
        ["<i>Baseline: FDI alert rule</i>", "<i>14 / 18</i>", "<i>54</i>", "<i>15</i>"],
        ["+ Market: drawdown", "14 / 18", "63", "19"],
        ["+ Market: abnormal return", "14 / 18", "60", "19"],
        ["+ Market: volatility spike", "14 / 18", "62", "20"],
        ["<b>+ Funding: loan book shrinking</b>", "<b>15 / 18</b>", "<b>85</b>", "<b>18</b>"],
        ["+ Funding: financing outflow", "14 / 18", "97", "23"],
        ["+ Funding: thin liquid buffer", "14 / 18", "94", "26"],
        ["+ Quality: profit minus cash", "14 / 18", "100", "26"],
        ["+ Quality: other-income reliance", "14 / 18", "98", "23"],
    ], [60 * mm, 32 * mm, 30 * mm, 33 * mm], ["L", "C", "R", "R"], highlight=[5])
    f += [P("<b>Seven of the eight add nothing and cost a great deal.</b> They catch no "
            "additional event while enlarging the watchlist by between 10% and 85%. The "
            "eighth, loan-book contraction, buys one extra event for 31 more names a year "
            "- worth noting, not obviously worth making. <b>None of these signals has been "
            "added to the model.</b>")]
    f += [P("Two findings are worth more than the negative result itself. First, "
            "<b>earnings-quality measures are inverted for lenders.</b> The "
            "profit-minus-cash gap scores 0.32, well below chance, because a lender's "
            "operating cash flow is dominated by loan-book movement: a shrinking book "
            "releases cash, so distressed lenders show cash above profit, not below. The "
            "corporate-finance intuition does not transfer, and the same mechanism "
            "explains why funding-stress was dropped from the index in the first place.")]
    f += [P("Second, the signals are not independent of the index in the way the "
            "architecture assumed. The institutions a drawdown signal flags are largely "
            "the ones the accounts already condemn; the market adds timing, which Analysis "
            "2 already captures, rather than new names. That is an argument for keeping "
            "Merton as a separate instrument and against folding market data into the "
            "fundamental score.")]
    f += [P("On the four events the index misses - IDBI, Central Bank of India, Bank of "
            "Maharashtra and Allahabad Bank, all PCA placements in 2017-18 - loan-book "
            "contraction reaches the 92nd and 85th percentile for Central Bank and "
            "Allahabad, but only the 71st and 47th for IDBI and Bank of Maharashtra. No "
            "signal tested catches all four, and none catches IDBI.")]

    # ================= PART VI =================
    f += part("VI", "External Validation on US Bank Failures",
              "The Indian study is limited by events, not data. The only way to test "
              "whether the methodology generalises is to run it, unchanged, where the "
              "event population is large.")

    f += [P("41. Why this test, and why the United States", H2)]
    f += [P("Eighteen events cannot settle whether a method works. The FDIC publishes, "
            "free and without authentication, every US bank failure since 1934 and "
            "quarterly call-report financials for every insured institution, joined on a "
            "single identifier. That gives three things the Indian data cannot:")]
    f += bullets([
        "<b>Events at scale.</b> 547 evaluable failures against 18.",
        "<b>Quarterly frequency.</b> The index can move four times a year instead of once.",
        "<b>No survivorship bias.</b> Failed banks remain in the data with the call reports "
        "they filed before failing &mdash; the exact defect that required recovering seven "
        "Indian institutions by hand.",
    ])
    f += [P("<b>Nothing was refitted.</b> Same six components, same weights, same dual "
            "anchoring, same peer-relative percentiles, same alert rule (80 / 60 / +15), "
            "same 24-month horizon, same point-in-time discipline. Only the field names "
            "change, because a call report and a balance sheet record the same quantities "
            "under different labels.")]
    f += table(["Component", "India", "United States"], [
        ["capital_buffer", "equity / total assets", "EQ / ASSET"],
        ["capital_erosion", "2-year change in equity", "8-quarter change in EQ"],
        ["profitability", "net profit / total assets", "ROA"],
        ["leverage", "borrowings / equity", "(ASSET &minus; EQ) / EQ"],
        ["interest_burden", "interest expense / revenue", "EINTEXP / INTINC"],
        ["earnings_trend", "3-year change in ROA", "12-quarter change in ROA"],
    ], [45 * mm, 60 * mm, 60 * mm], ["L", "L", "L"])
    f += [P("Field mapping. The model is unchanged; only its inputs are renamed.", CAP)]

    f += [P("42. Scale of the test", H2)]
    f += table(["", "India", "United States"], [
        ["Panel", "6,223 company-years", "<b>416,285 bank-quarters</b>"],
        ["Institutions", "563", "<b>10,341</b>"],
        ["Period", "FY2006&ndash;FY2023, annual", "2003&ndash;2015, quarterly"],
        ["Evaluable events", "18", "<b>547</b>"],
        ["Pre-event observations", "36", "<b>4,309</b>"],
    ], [50 * mm, 55 * mm, 60 * mm], ["L", "L", "L"], highlight=[4, 5])

    f += [P("43. Result: the method transfers", H2)]
    f += table(["Measure", "Value"], [
        ["Failures alerted within 24 months", "<b>535 of 547  (98%)</b>"],
        ["Median lead time", "<b>19.6 months</b>  (quartiles 13.1 / 22.5)"],
        ["Alert precision", "7.32% against a 1.04% base rate &mdash; <b>7.1x lift</b>"],
        ["Watchlist", "829 of 8,005 banks per quarter (10%)"],
    ], [75 * mm, 90 * mm], ["L", "L"], highlight=[1])
    f += [P("A 98% recall is bought with a watchlist of a tenth of the banking system, "
            "which is the honest cost and would be too wide for some users. The "
            "discriminating figure is the 7.1x lift over the base rate, and the "
            "permutation result below.")]

    f += [P("44. The AUC trap, settled", H2)]
    f += [P("Part IV reported an uncomfortable finding: on the Indian data a single "
            "leverage ratio scored a <i>higher</i> AUC than the composite (0.976 against "
            "0.912), and the defence was that the event set was clustered on thin-capital "
            "public-sector banks. That defence is testable here, where no such clustering "
            "exists.")]
    f += table(["Signal", "AUC", "Caught", "Persistence", "Always-on"], [
        ["<b>Distress index composite</b>", "<b>0.861</b>", "<b>535 / 547</b>", "<b>19%</b>", "<b>2</b>"],
        ["Leverage alone", "0.828", "511 / 547", "27%", "27"],
    ], [60 * mm, 25 * mm, 35 * mm, 30 * mm, 28 * mm],
        ["L", "R", "C", "R", "C"], highlight=[1])
    f += [P("<b>On 547 events the composite beats leverage on every measure, including "
            "AUC.</b> The Indian ranking was an artefact of a clustered event set, exactly "
            "as argued, and leverage alone remains the worse alarm: 27 institutions "
            "permanently flagged against 2.")]

    f += [P("45. Permutation test at scale", H2)]
    f += table(["Statistic", "Observed", "Null mean", "Null 95th pct", "p-value"], [
        ["Failures alerted", "<b>535</b>", "141.9", "160", "<b>&lt; 0.001</b>"],
    ], [55 * mm, 30 * mm, 30 * mm, 30 * mm, 30 * mm], ["L", "C", "R", "R", "R"],
        highlight=[1])
    f += [P("The null preserves failure dates and size terciles, permuting only which bank "
            "failed, over 1,000 draws. Chance assigns an alert to roughly 142 of 547; the "
            "rule finds 535. This is the same test as Part V, on thirty times the events.")]

    f += [P("46. What it reveals about the Indian data", H2)]
    f += [P("The call reports carry a non-performing-assets ratio for every bank-quarter. "
            "Tested as a standalone signal it scores <b>AUC 0.887 at 100% coverage</b> &mdash; "
            "stronger than any single component in the model.")]
    f += [P("The Indian archive carries the same quantity only from 2020 and for a tenth of "
            "the panel, which is why it was excluded from that backtest. <b>The implication "
            "is that the principal weakness of the Indian system is a missing input, not a "
            "flawed structure.</b> Obtaining a historical asset-quality series for Indian "
            "lenders &mdash; from quarterly exchange filings or RBI statistical tables &mdash; "
            "would plausibly do more for performance than any further modelling.")]
    f += [P("<b>What this does not establish.</b> US and Indian banking differ in "
            "regulation, funding structure and resolution practice, and the US window is "
            "dominated by one crisis. Transferring well to US failures is evidence that the "
            "method is not an artefact of the Indian sample; it is not evidence that the "
            "Indian results themselves are precise.")]

    f += [P("47. Building it from scratch on US data", H2)]
    f += [P("Section 41 asked a narrow question: does the frozen model transfer? It does. "
            "A different question is what the same design produces when the data is good "
            "enough to build on. The panel was extended to <b>588,177 bank-quarters across "
            "10,459 institutions, 2003-2023</b>, and three components the Indian archive "
            "could not support were added:")]
    f += bullets([
        "<b>Non-performing assets ratio.</b> Reported every quarter for every bank. The "
        "Indian archive carries it only from 2020, for a tenth of the panel.",
        "<b>Reserve shortfall</b> &mdash; bad loans not covered by loss reserves. Measures "
        "whether a bank has recognised the losses it already has.",
        "<b>Deposit contraction.</b> Deposits are reported quarterly, so funding flight can "
        "be measured directly rather than proxied by a shrinking loan book.",
    ])
    f += [P("The split is across <b>two different crises</b>, not merely two date ranges: "
            "components and thresholds are derived on the 529 failures before 2013 (the "
            "2008-12 wave) and tested on the 68 from 2013-2023, which includes the 2023 "
            "regional bank failures.")]

    f += [P("48. Component selection on 529 development failures", H2)]
    f += table(["Component", "AUC on development data"], [
        ["<b>Non-performing assets ratio *</b>", "<b>0.875</b>"],
        ["<b>Reserve shortfall *</b>", "<b>0.856</b>"],
        ["Profitability", "0.830"],
        ["Leverage", "0.815"],
        ["Capital buffer", "0.814"],
        ["Earnings trend", "0.783"],
        ["Interest burden", "0.779"],
        ["Capital erosion", "0.768"],
        ["Deposit contraction *", "0.580"],
    ], [95 * mm, 60 * mm], ["L", "R"], highlight=[1, 2])
    f += [P("* unavailable in the Indian data. All nine clear the 0.5 bar, so none is "
            "dropped &mdash; and the two asset-quality measures are the strongest signals "
            "available anywhere in this project.", CAP)]

    f += [P("49. A flaw in the selection rule, caught and fixed", H2)]
    f += [P("The first run selected thresholds by maximising development recall, breaking "
            "ties on watchlist size. With 529 events that rule loosens the threshold until "
            "almost everything is flagged: it chose <font face='Courier' size='8.5'>FDI &ge; "
            "70</font> and produced a watchlist of <b>18% of the banking system</b> &mdash; "
            "precisely the failure Part IV criticises in the leverage baseline.")]
    f += [P("The rule was replaced with one stated before searching: <b>maximise recall "
            "subject to a watchlist no larger than 5% of banks</b>. That is a judgement "
            "about what an analyst can work through, and it belongs in the selection rule "
            "rather than in the commentary afterwards.")]
    f += table(["Selection rule", "Thresholds", "Held-out watchlist", "Held-out precision"], [
        ["Maximise recall", "70 / 50 / +10", "18% of banks", "0.74%  (4.7x lift)"],
        ["<b>Recall subject to 5% cap</b>", "<b>85 / 65 / +20</b>", "<b>2.8% of banks</b>",
         "<b>3.93%  (24.8x lift)</b>"],
    ], [52 * mm, 35 * mm, 38 * mm, 40 * mm], ["L", "C", "R", "R"], highlight=[2])

    f += [P("50. Held-out result, and what better data actually buys", H2)]
    f += table(["Measure", "Value"], [
        ["Failures alerted within 24 months", "<b>55 of 68  (81%)</b>"],
        ["Median lead time", "14.5 months  (quartiles 8.2 / 22.1)"],
        ["Watchlist", "159 of 5,675 banks per quarter (2.8%)"],
        ["Precision", "3.93% against a 0.16% base rate &mdash; <b>24.8x lift</b>"],
        ["Permutation test", "observed 55, null mean 4.6, <b>p &lt; 0.001</b>"],
    ], [72 * mm, 93 * mm], ["L", "L"], highlight=[1])
    f += [P("Tested on a regime it was not developed on, the model catches four failures in "
            "five with a list of under 3% of banks, at roughly twenty-five times the base "
            "rate. Under chance, the same list would have caught about five.")]
    f += [P("<b>The most useful comparison is what the three new components changed:</b>")]
    f += table(["Model", "Caught", "Median lead", "Precision", "AUC"], [
        ["Six components, as in India", "55 / 68", "14.4 months", "2.04%", "0.895"],
        ["<b>Nine, with asset quality and funding</b>", "<b>55 / 68</b>", "14.5 months",
         "<b>3.93%</b>", "0.894"],
    ], [62 * mm, 25 * mm, 32 * mm, 25 * mm, 21 * mm], ["L", "C", "R", "R", "R"],
        highlight=[2])
    f += [P("<b>Identical recall, identical lead time, identical AUC &mdash; and half the "
            "false alarms.</b> Asset quality is the strongest standalone signal in the "
            "project (AUC 0.875), yet adds nothing to <i>which</i> institutions are caught, "
            "because capital and profitability already identify them. What it adds is "
            "discrimination among the ones that look weak: it halves the list needed to "
            "catch the same failures.")]
    f += [P("That is a precise answer to what better Indian data would be worth. Not more "
            "events detected &mdash; a watchlist half the size for the same detection. On "
            "the Indian panel, where the material watchlist runs to 14 names a year, that "
            "is the difference between a list someone reads and a list someone ignores.")]

    f += part("VII", "Limitations",
              "Read this before quoting any number in this report. Several are serious "
              "enough to change how the output should be described.")

    f += [P("51. Statistical", H2)]
    f += bullets([
        "<b>Eighteen events is still a small sample.</b> Every Indian figure carries wide "
        "error bars; the external validation in Part VI exists precisely because 18 events "
        "cannot settle whether the method works.",
        "<b>Component selection used the same events it was tested on.</b> Dropping two "
        "components after observing their performance is a mild form of fitting. There is no "
        "held-out set, so reported accuracy is optimistic.",
        "<b>The event set is clustered.</b> Thirteen of eighteen events are banks "
        "placed under PCA within a 26-month span, so the test leans heavily on one failure "
        "mode in one part of the cycle.",
        "<b>Peer groups are small.</b> 39 banks means one institution moves roughly 2.5 "
        "percentile points by existing, and NBFC size terciles are recomputed annually, so a "
        "firm can change group - and score - without changing itself.",
    ])

    f += [P("52. Interpretation", H2)]
    f += bullets([
        "<b>The fundamental score is a rank, not a probability.</b> An 88 means “worse "
        "than 88% of its peers”, not “88% likely to default”. The original "
        "project deck frames the output as Probability of Default; that wording should "
        "change, because readers will take a percentage as a likelihood.",
        "<b>The Merton probability is a model output, not a forecast.</b> It assumes "
        "lognormal asset value, a single debt maturity and no external support. Its "
        "comparative movement is trustworthy; its level is not.",
        "<b>A high score is not a prediction of failure.</b> Most institutions scoring above "
        "80 will not fail. The claim is narrower: institutions that failed were usually "
        "scoring high beforehand.",
        "<b>Long lead times are not a success.</b> A 59-month warning on a bank that scored "
        "badly every year is a standing concern, not a timed signal.",
    ])

    f += [P("53. Data", H2)]
    f += bullets([
        "<b>Analysis 1 can only see what the accounts admit, and this is the deepest "
        "limitation.</b> Yes Bank's reported profitability ranked mid-pack to the end "
        "because the bad loans were not yet recognised. A model built on filings inherits "
        "whatever those filings understate or conceal. Analysis 2 exists because of this.",
        "<b>The archive deletes its own hardest cases.</b> Institutions that merge or resolve "
        "leave it. Seven were recovered from source filings (Part V), but four failures "
        "remain unevaluable - DHFL, IL&amp;FS, Punjab &amp; Maharashtra Co-op and Altico - "
        "and all four are failures, so measured recall stays optimistic.",
        "<b>Annual accounting data only.</b> The fundamental index updates once per filing "
        "cycle at best. Quarterly NPA data begins only in 2020 and covers about a tenth of "
        "the panel, so it is shown as current context and excluded from the backtest.",
        "<b>Volatility is a trailing estimate.</b> The 250-day window smooths genuine regime "
        "changes, so the market signal lags a sudden repricing by weeks.",
        "<b>Accounting quality is not verified.</b> Reserves are taken as reported and may "
        "include revaluation and other non-loss-absorbing items.",
        "<b>The snapshot ends in 2023.</b> Nothing after that is covered.",
    ])

    f += [P("54. Scope", H2)]
    f += bullets([
        "<b>Analysis 2 covers only listed institutions with a liquid quote</b> - 152 of 556. "
        "It cannot be applied to unlisted NBFCs, and should not be faked for them.",
        "<b>No notion of sovereign or parent support.</b> IRFC and LIC Housing score in the "
        "80s on thin equity and high leverage; both are government-linked and were never near "
        "distress. Merton makes the same mistake in the other direction for public-sector "
        "banks, whose market prices embed an implicit state guarantee.",
        "<b>Group and related-party exposure is invisible.</b> The mechanism that actually "
        "brought down IL&amp;FS and Reliance Capital - lending into a connected web of "
        "subsidiaries - does not appear in a standalone balance sheet.",
        "<b>Not a credit rating and not investment advice.</b> An academic decision-support "
        "exercise built entirely from public data.",
    ])

    f += [P("55. Reproducing this", H2)]
    f += code([
        "pip install pandas numpy streamlit jinja2",
        "",
        "python3 build_panel.py        # archive  -&gt; panel.csv   (6,139 rows)",
        "python3 score.py              # index    -&gt; scored.csv",
        "python3 validate.py           # backtest -&gt; lead_times.csv",
        "python3 fetch_nse_prices.py   # NSE      -&gt; prices_weekly.csv",
        "python3 resolve_splits.py     # actions  -&gt; splits.csv",
        "python3 merton.py             # model    -&gt; merton.csv",
        "python3 premortem.py          # the three experiments in Part V",
        "python3 validation2.py        # thresholds, permutation test, intervals",
        "python3 recover_missing.py    # the 7 institutions the archive dropped",
        "python3 signals.py            # the five extra signal families in Part V",
        "python3 fdic_fetch.py         # US failures + call reports -&gt; fdic_panel.csv",
        "python3 fdic_validate.py      # the frozen model on 547 US failures (Part VI)",
        "python3 fdic_model.py         # the US-native build, 597 failures, two regimes",
        "python3 recover_missing.py    # the 7 institutions the archive dropped",
        "python3 signals.py            # the five extra signal families in Part V",
        "python3 fdic_fetch.py         # US failures + call reports -&gt; fdic_panel.csv",
        "python3 fdic_validate.py      # the frozen model on 547 US failures (Part VI)",
        "python3 fdic_model.py         # the US-native build, 597 failures, two regimes",
        "",
        "streamlit run app.py          # the interactive tool",
    ])
    f += [P("Every number in this report is produced by those scripts from the archive and "
            "NSE's public price files.", CAP)]

    doc.build(f)
    print(f"wrote {OUT} ({os.path.getsize(OUT)/1024:.0f} KB)")


if __name__ == "__main__":
    build()
