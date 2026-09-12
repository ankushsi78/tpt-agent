#!/usr/bin/env python3
"""Generate a one-page Put Credit Spread setup cheat-sheet PDF."""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

OUT = "PutCreditSpread_Golden_Rules_Cheatsheet.pdf"

# ---- palette ----
INK      = colors.HexColor("#1a2332")
SLATE    = colors.HexColor("#37475a")
GREEN    = colors.HexColor("#0f7b3f")
GREEN_BG = colors.HexColor("#e7f4ec")
BLUE     = colors.HexColor("#12507e")
BLUE_BG  = colors.HexColor("#e8f0f7")
AMBER    = colors.HexColor("#8a5a00")
AMBER_BG = colors.HexColor("#fbf1dc")
RED      = colors.HexColor("#9a1f1f")
RED_BG   = colors.HexColor("#fbeaea")
GREY_BG  = colors.HexColor("#f2f4f7")
LINE     = colors.HexColor("#c9d2dd")

styles = getSampleStyleSheet()

def P(text, size=8, leading=None, color=INK, bold=False, align=TA_LEFT, space=0):
    return ParagraphStyle(
        f"p{size}{bold}{color}", parent=styles["Normal"],
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size, leading=leading or size + 2.2,
        textColor=color, alignment=align, spaceAfter=space,
    )

def para(text, style):
    return Paragraph(text, style)

# ---- section box builder ----
def section(title, header_color, bg_color, rows):
    """rows: list of html strings (bullet lines)."""
    hdr = Table([[para(title, P(9, color=colors.white, bold=True))]],
                colWidths=[3.55 * inch])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), header_color),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    body_items = [[para(r, P(7.6, leading=9.6))] for r in rows]
    body = Table(body_items, colWidths=[3.55 * inch])
    body.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg_color),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, LINE),
    ]))
    wrap = Table([[hdr], [body]], colWidths=[3.55 * inch])
    wrap.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (0, 0), 0),
        ("BOTTOMPADDING", (0, 1), (0, 1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, header_color),
    ]))
    return wrap

CK = '<font color="#0f7b3f">&#10003;</font>'   # check
X  = '<font color="#9a1f1f">&#10007;</font>'    # cross
WN = '<font color="#8a5a00">&#9888;</font>'     # warning
B  = lambda t: f"<b>{t}</b>"

# ---------------- LEFT COLUMN ----------------
iv = section("1 &#183; IMPLIED VOLATILITY  (the paycheck)", GREEN, GREEN_BG, [
    f"{CK} {B('SELL when IV is HIGH')} &#8212; IV Rank / Percentile <b>&gt; 50</b> (ideal &gt; 70).",
    f"{CK} Prefer {B('IV &gt; HV')} &#8212; options priced richer than realized moves.",
    f"{CK} Sell {B('into fear')}: post-drop / post-news IV spikes pay the most.",
    f"{X} Avoid {B('IVR &lt; 20&#8211;25')} &#8212; credit too thin, poor reward/risk.",
    f"{WN} High IV in a <b>downtrend</b> is a trap &#8212; direction still rules.",
])

trend = section("2 &#183; TREND &amp; MAs  (direction + floor)", BLUE, BLUE_BG, [
    f"{CK} Price {B('above the 200-SMA')} = long-term uptrend (baseline green light).",
    f"{CK} {B('Stacked: 20-EMA &gt; 50-EMA &gt; 200-SMA')}, all rising = A+ structure.",
    f"{CK} Best entry = {B('pullback TO a rising 20/50-EMA')} that holds.",
    f"&#127919; Park the {B('short strike below a rising major MA')} (dynamic support).",
    f"{X} Never sell puts below a <b>falling 50/200</b> (downtrend).",
])

bb = section("3 &#183; BOLLINGER BANDS  (entry + strikes)", BLUE, BLUE_BG, [
    f"{CK} Ideal: price {B('bouncing off the LOWER / mid band')} inside an uptrend.",
    f"{CK} {B('%B near 0&#8211;0.2')} after a dip = stretched, bounce likely.",
    f"&#127919; Anchor {B('short strike at / below the lower band')} (&#8776; 2 SD).",
    f"{X} Beware the {B('band walk')} &#8212; price rides lower band in a downtrend.",
    f"{WN} {B('Squeeze')} (tight bands) = big move coming, direction unknown.",
])

# ---------------- RIGHT COLUMN ----------------
rsi = section("4 &#183; RSI  (timing the turn)", AMBER, AMBER_BG, [
    f"{CK} Sweet spot: {B('RSI turning UP from 35&#8211;45')} (dip exhausting).",
    f"{CK} {B('Bullish divergence')} (price lower-low, RSI higher-low) = strong.",
    f"{WN} {B('45&#8211;60 &amp; rising')} = healthy trend, fine to sell.",
    f"{X} {B('&lt; 30 &amp; still falling')} = falling knife &#8212; wait for the turn.",
    f"{WN} {B('&gt; 70 overbought')} = less cushion / snap-back risk.",
])

macd = section("5 &#183; MACD  (momentum confirm)", AMBER, AMBER_BG, [
    f"{CK} {B('Bullish cross')} (MACD &gt; signal) &#8212; best when <b>below zero</b>.",
    f"{CK} {B('Histogram positive &amp; expanding')} = momentum building.",
    f"{CK} {B('MACD above zero')} = bullish regime overall.",
    f"{X} Skip on a <b>bearish cross</b> or deep, expanding-negative histogram.",
])

build = section("6 &#183; STRIKES, DTE &amp; MANAGEMENT", SLATE, GREY_BG, [
    f"&#127919; Short strike {B('delta ~0.16&#8211;0.30')} (&#8776; 70&#8211;84% PoP).",
    f"&#127919; Place it {B('below a confluence of support')}; breakeven below it.",
    f"&#128197; {B('30&#8211;45 DTE')} sweet spot &#8212; {B('no earnings')} inside the trade.",
    f"&#128176; {B('Liquidity')}: tight bid/ask, OI &gt; 100&#8211;500.",
    f"{CK} {B('Take profit at ~50%')} of max credit.",
    f"&#9201; {B('Close / roll by ~21 DTE')} regardless (gamma risk).",
    f"&#128721; {B('Exit / roll')} if short strike breached or loss &#8776; 2&#215; credit.",
])

# ---- build document ----
doc = SimpleDocTemplate(
    OUT, pagesize=letter,
    leftMargin=0.4 * inch, rightMargin=0.4 * inch,
    topMargin=0.38 * inch, bottomMargin=0.32 * inch,
)

story = []

# Title bar
title_tbl = Table([[para(
    "PUT CREDIT SPREAD &#8212; GOLDEN RULES", P(15, color=colors.white, bold=True))],
    [para("The A+ setup checklist for high-probability premium selling",
          P(8.5, color=colors.HexColor("#d6e6f5")))]],
    colWidths=[7.2 * inch])
title_tbl.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), INK),
    ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ("TOPPADDING", (0, 0), (0, 0), 7),
    ("BOTTOMPADDING", (0, 0), (0, 0), 0),
    ("TOPPADDING", (0, 1), (0, 1), 0),
    ("BOTTOMPADDING", (0, 1), (0, 1), 7),
]))
story.append(title_tbl)
story.append(Spacer(1, 6))

# Meta rule callout
meta = Table([[para(
    "&#9733; <b>META-RULE:</b> A put credit spread bets price stays <b>ABOVE</b> your short strike. "
    "<b>Trend</b> gives direction &#183; <b>IV</b> gives the paycheck &#183; <b>RSI / MACD / Bollinger</b> give the timing. "
    "Never sell on IV alone if the chart is broken; never sell a great chart when IV is dead.",
    P(8.2, leading=10.5, color=INK))]], colWidths=[7.2 * inch])
meta.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff8e6")),
    ("BOX", (0, 0), (-1, -1), 1, AMBER),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
]))
story.append(meta)
story.append(Spacer(1, 8))

# Two columns
left_col = Table([[iv], [trend], [bb]], colWidths=[3.55 * inch])
left_col.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("TOPPADDING", (0, 0), (-1, -1), 0),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
right_col = Table([[rsi], [macd], [build]], colWidths=[3.55 * inch])
right_col.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
cols = Table([[left_col, right_col]], colWidths=[3.6 * inch, 3.6 * inch])
cols.setStyle(TableStyle([
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (0, 0), 0),
    ("RIGHTPADDING", (0, 0), (0, 0), 5),
    ("LEFTPADDING", (1, 0), (1, 0), 5),
    ("RIGHTPADDING", (1, 0), (1, 0), 0),
    ("TOPPADDING", (0, 0), (-1, -1), 0),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
]))
story.append(cols)
story.append(Spacer(1, 2))

# A+ checklist strip
aplus = Table([[para(
    "&#127942; <b>THE A+ SETUP (one screen):</b> Uptrend (price &gt; rising 50 &amp; 200) "
    "<b>+</b> pullback to a rising 20/50-EMA <b>+</b> bounce off lower/mid Bollinger band "
    "<b>+</b> RSI turning up from 35&#8211;45 <b>+</b> MACD bullish cross <b>+</b> "
    "<b>IV Rank &gt; 50</b> <b>+</b> short strike (~0.20&#8211;0.30&#916;) below clear support, "
    "30&#8211;45 DTE, no earnings, take profit at 50%.",
    P(8.2, leading=10.5, color=colors.white))]], colWidths=[7.2 * inch])
aplus.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), GREEN),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
]))
story.append(aplus)
story.append(Spacer(1, 5))

# R/R reference + disclaimer
rr = Table([
    [para("<b>Reward : Risk cheat</b>", P(7.4, color=INK, bold=True)),
     para("Credit &#247; (Width &#8722; Credit)", P(7.4, color=SLATE))],
    [para("~20% of width", P(7.2, color=SLATE)), para("&#8776; 1 : 4  (higher PoP)", P(7.2, color=SLATE))],
    [para("~33% of width", P(7.2, color=SLATE)), para("&#8776; 1 : 2  (the sweet spot)", P(7.2, color=GREEN, bold=True))],
    [para("~50% of width", P(7.2, color=SLATE)), para("&#8776; 1 : 1  (directional)", P(7.2, color=SLATE))],
], colWidths=[1.4 * inch, 2.0 * inch])
rr.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), GREY_BG),
    ("BOX", (0, 0), (-1, -1), 0.5, LINE),
    ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
    ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ("TOPPADDING", (0, 0), (-1, -1), 1.5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
]))
disc = para(
    "<i>Take-profit, deltas and DTE reflect common tastytrade-style premium-selling "
    "research. Educational reference on options mechanics &#8212; not personalized "
    "investment advice. Verify live IV Rank, support levels and earnings dates before "
    "every trade.</i>", P(6.8, leading=8.4, color=SLATE))
foot = Table([[rr, disc]], colWidths=[3.5 * inch, 3.7 * inch])
foot.setStyle(TableStyle([
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (0, 0), 0),
    ("LEFTPADDING", (1, 0), (1, 0), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ("TOPPADDING", (0, 0), (-1, -1), 2),
]))
story.append(foot)

doc.build(story)
print(f"Wrote {OUT}")
