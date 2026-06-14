#!/usr/bin/env python3
"""Generate TPT Agent Algorithm PDF — print-ready."""

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.platypus.flowables import HRFlowable
from datetime import datetime

OUTPUT = "/Users/ankushsinghal/Documents/Trading/TPT_Agent_Algorithm.pdf"

# ── Colour palette ────────────────────────────────────────────────────────────
DARK_BLUE   = colors.HexColor("#1A3557")
MID_BLUE    = colors.HexColor("#2980B9")
LIGHT_BLUE  = colors.HexColor("#D6E8F7")
GREEN       = colors.HexColor("#1E8449")
LIGHT_GREEN = colors.HexColor("#D5F5E3")
PURPLE      = colors.HexColor("#6C3483")
LIGHT_PURPLE= colors.HexColor("#E8DAEF")
ORANGE      = colors.HexColor("#E67E22")
LIGHT_ORANGE= colors.HexColor("#FDEBD0")
RED         = colors.HexColor("#C0392B")
LIGHT_RED   = colors.HexColor("#FADBD8")
GREY_LIGHT  = colors.HexColor("#F2F3F4")
GREY_MID    = colors.HexColor("#BDC3C7")
GREY_DARK   = colors.HexColor("#566573")
BLACK       = colors.black
WHITE       = colors.white

# ── Styles ────────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def S(name, **kw):
    return ParagraphStyle(name, **kw)

TITLE      = S("MyTitle",   fontName="Helvetica-Bold",   fontSize=26, textColor=WHITE,       alignment=TA_CENTER, leading=32)
SUBTITLE   = S("MySub",     fontName="Helvetica",        fontSize=13, textColor=LIGHT_BLUE,  alignment=TA_CENTER, leading=18)
H1         = S("MyH1",      fontName="Helvetica-Bold",   fontSize=14, textColor=WHITE,       leading=18, spaceAfter=4)
H2         = S("MyH2",      fontName="Helvetica-Bold",   fontSize=11, textColor=DARK_BLUE,   leading=15, spaceBefore=8, spaceAfter=4)
H3         = S("MyH3",      fontName="Helvetica-Bold",   fontSize=10, textColor=GREY_DARK,   leading=14, spaceBefore=6, spaceAfter=2)
BODY       = S("MyBody",    fontName="Helvetica",        fontSize=9,  textColor=BLACK,       leading=14, spaceAfter=4, alignment=TA_JUSTIFY)
BODY_SMALL = S("MySmall",   fontName="Helvetica",        fontSize=8,  textColor=GREY_DARK,   leading=12)
CODE       = S("MyCode",    fontName="Courier",          fontSize=8,  textColor=DARK_BLUE,   leading=12, backColor=GREY_LIGHT, leftIndent=8, rightIndent=8)
BULLET     = S("MyBullet",  fontName="Helvetica",        fontSize=9,  textColor=BLACK,       leading=13, leftIndent=14, firstLineIndent=-8, spaceAfter=2)
CAPTION    = S("MyCaption", fontName="Helvetica-Oblique",fontSize=8,  textColor=GREY_DARK,   alignment=TA_CENTER, spaceBefore=2)
PHASE_NUM  = S("MyPhaseN",  fontName="Helvetica-Bold",   fontSize=18, textColor=WHITE,       alignment=TA_CENTER, leading=22)
PHASE_NAME = S("MyPhaseNm", fontName="Helvetica-Bold",   fontSize=11, textColor=WHITE,       alignment=TA_CENTER, leading=14)
NOTE       = S("MyNote",    fontName="Helvetica-Oblique",fontSize=8,  textColor=GREY_DARK,   leading=12, leftIndent=8, spaceAfter=4)
TABLE_HDR  = S("MyTHdr",    fontName="Helvetica-Bold",   fontSize=9,  textColor=WHITE,       leading=12, alignment=TA_CENTER)
TABLE_CELL = S("MyTCell",   fontName="Helvetica",        fontSize=8,  textColor=BLACK,       leading=11)
TABLE_CELL_C=S("MyTCellC",  fontName="Helvetica",        fontSize=8,  textColor=BLACK,       leading=11, alignment=TA_CENTER)
TABLE_BOLD = S("MyTBold",   fontName="Helvetica-Bold",   fontSize=8,  textColor=BLACK,       leading=11)
FOOTER_TXT = S("MyFooter",  fontName="Helvetica",        fontSize=7,  textColor=GREY_DARK,   alignment=TA_CENTER)

# ── Helpers ───────────────────────────────────────────────────────────────────
def hr(color=GREY_MID, thickness=0.5):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceAfter=6, spaceBefore=6)

def spacer(h=0.12):
    return Spacer(1, h * inch)

def bullet(text):
    return Paragraph(f"<bullet>&bull;</bullet> {text}", BULLET)

def phase_badge(num, name, color):
    data = [[Paragraph(str(num), PHASE_NUM), Paragraph(name, PHASE_NAME)]]
    t = Table(data, colWidths=[0.55*inch, 5.9*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), color),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",(0,0), (-1,-1), 8),
        ("RIGHTPADDING",(0,0),(-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
        ("ROUNDEDCORNERS",[4]),
    ]))
    return t

def section_header(title, color=DARK_BLUE):
    data = [[Paragraph(title, H1)]]
    t = Table(data, colWidths=[6.5*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), color),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    return t

def info_box(text, bg=LIGHT_BLUE, border=MID_BLUE):
    data = [[Paragraph(text, BODY)]]
    t = Table(data, colWidths=[6.5*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), bg),
        ("BOX",           (0,0), (-1,-1), 1, border),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    return t

def data_table(headers, rows, col_widths, header_color=DARK_BLUE, stripe=True):
    data = [[Paragraph(h, TABLE_HDR) for h in headers]]
    for i, row in enumerate(rows):
        data.append([Paragraph(str(c), TABLE_CELL) for c in row])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND",    (0,0), (-1,0), header_color),
        ("TEXTCOLOR",     (0,0), (-1,0), WHITE),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("GRID",          (0,0), (-1,-1), 0.4, GREY_MID),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]
    if stripe:
        for i in range(1, len(data)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0,i), (-1,i), GREY_LIGHT))
    t.setStyle(TableStyle(style))
    return t

# ── Page callbacks ────────────────────────────────────────────────────────────
def on_page(canvas, doc):
    canvas.saveState()
    w, h = letter
    # Header bar
    canvas.setFillColor(DARK_BLUE)
    canvas.rect(0, h - 0.45*inch, w, 0.45*inch, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(0.5*inch, h - 0.28*inch, "TPT Agent — Algorithm Documentation")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(w - 0.5*inch, h - 0.28*inch, f"Tradier Paper Trading | Confidential")
    # Footer
    canvas.setFillColor(GREY_DARK)
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(w/2, 0.3*inch, f"Page {doc.page}   |   Generated {datetime.now().strftime('%B %d, %Y')}")
    canvas.restoreState()

def on_first_page(canvas, doc):
    canvas.saveState()
    w, h = letter
    # Full cover background
    canvas.setFillColor(DARK_BLUE)
    canvas.rect(0, h*0.38, w, h*0.62, fill=1, stroke=0)
    # Accent strip
    canvas.setFillColor(MID_BLUE)
    canvas.rect(0, h*0.36, w, 0.035*inch*6, fill=1, stroke=0)
    canvas.restoreState()

# ── Build story ───────────────────────────────────────────────────────────────
story = []

# ════════════════════════════════════════════════════════════
# COVER PAGE
# ════════════════════════════════════════════════════════════
story.append(Spacer(1, 2.4*inch))
story.append(Paragraph("TPT Agent", TITLE))
story.append(Spacer(1, 0.12*inch))
story.append(Paragraph("Algorithm Documentation", SUBTITLE))
story.append(Spacer(1, 0.08*inch))
story.append(Paragraph("Tradier Paper Trading — Full Strategy Reference", SUBTITLE))
story.append(Spacer(1, 0.5*inch))

cover_meta = [
    ["Strategy", "Cash-Secured Puts (CSP) + LEAPS Deep ITM Calls"],
    ["Broker",   "Tradier Sandbox (Paper Trading) — Account VA54665450"],
    ["Schedule", "Daily at 6:35 AM PT (every day)"],
    ["Data",     "Tradier real-time APIs + yfinance (earnings only)"],
    ["Discord",  "#beta-ai-trades — Summary cards only"],
    ["Version",  f"Generated {datetime.now().strftime('%B %d, %Y')}"],
]
t = Table(cover_meta, colWidths=[1.4*inch, 5.1*inch])
t.setStyle(TableStyle([
    ("FONTNAME",      (0,0), (0,-1), "Helvetica-Bold"),
    ("FONTNAME",      (1,0), (1,-1), "Helvetica"),
    ("FONTSIZE",      (0,0), (-1,-1), 9),
    ("TEXTCOLOR",     (0,0), (-1,-1), WHITE),
    ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ("LEFTPADDING",   (0,0), (-1,-1), 6),
    ("TOPPADDING",    (0,0), (-1,-1), 5),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("LINEBELOW",     (0,0), (-1,-2), 0.3, colors.HexColor("#4A90D9")),
]))
story.append(t)
story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# 1. OVERVIEW
# ════════════════════════════════════════════════════════════
story.append(section_header("1.  Overview"))
story.append(spacer(0.1))
story.append(Paragraph(
    "The TPT Agent is a fully automated options trading bot that runs on Tradier's paper trading "
    "sandbox. It executes two parallel options strategies on the same curated stock watchlist: "
    "Cash-Secured Puts (CSP Wheel strategy) and LEAPS deep ITM calls (stock replacement). "
    "The bot runs once per day at 6:35 AM PT, screens the entire approved stock universe, "
    "manages existing positions, and opens new ones based on a rules-based scoring system.", BODY))
story.append(spacer(0.1))

story.append(info_box(
    "<b>Key design principles:</b>  (1) Never trade below the 200-day SMA. "
    "(2) Never sell a CSP into an earnings window. "
    "(3) Size up only on high-conviction setups (score 5/5). "
    "(4) Close winners early — CSPs at 50% premium captured, LEAPS at +5% profit. "
    "(5) VIX gates deployment amount; LEAPS gate is VIX ≤ 18 OR ≥ 21.", LIGHT_BLUE, MID_BLUE))
story.append(spacer(0.15))

# Architecture table
story.append(Paragraph("System Architecture", H2))
arch_rows = [
    ["Component",           "Detail"],
    ["Bot file",            "tpt_agent.py"],
    ["Scheduler",           "macOS launchd — com.ankushsinghal.tptagent.plist"],
    ["Trigger time",        "6:35 AM PT, every day"],
    ["Broker",              "Tradier sandbox (paper trading)"],
    ["Account",             "VA54665450"],
    ["Stock universe",      "Google Sheets CSV — curated approved watchlist"],
    ["Options data",        "Tradier markets/options/chains (greeks=true) — real-time"],
    ["Stock price data",    "Tradier markets/history + markets/quotes — real-time"],
    ["VIX",                 "Tradier markets/quotes ($VIX.X) — yfinance fallback"],
    ["Earnings filter",     "yfinance only (Tradier has no earnings calendar)"],
    ["Order type",          "Limit orders at live mid-price (bid+ask)/2"],
    ["Log file",            "tpt_agent.log"],
    ["Discord channel",     "#beta-ai-trades (hardcoded webhook — no other channel)"],
    ["Discord output",      "Run summary + open positions table + CSP summary + LEAPS summary"],
]
story.append(data_table(arch_rows[0], arch_rows[1:],
             [2.0*inch, 4.5*inch], DARK_BLUE))
story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# 2. DATA SOURCES
# ════════════════════════════════════════════════════════════
story.append(section_header("2.  Data Sources"))
story.append(spacer(0.1))
story.append(Paragraph(
    "All market data is fetched in real-time via Tradier's REST APIs. "
    "yfinance is retained only for earnings dates, which Tradier does not provide.", BODY))
story.append(spacer(0.1))

ds_rows = [
    ["Data Point",                  "Source",           "Latency",      "Used For"],
    ["Stock OHLCV bars",            "Tradier /markets/history",  "Real-time", "SMA 20/50/200, Bollinger Bands, RSI"],
    ["Real-time stock quote",       "Tradier /markets/quotes",   "Real-time", "Current price, day change %"],
    ["Options chain (bid/ask/OI)",  "Tradier /markets/options/chains", "Real-time", "Strike selection, ARR, OI filter"],
    ["Implied Volatility (IV)",     "Tradier greeks.mid_iv",     "Real-time", "IV scoring criterion, BS delta fallback"],
    ["Options Delta (CSP)",         "Tradier greeks.delta",      "Real-time", "Delta filter vs BB-position-based range (per stock)"],
    ["Options Delta (LEAPS)",       "Black-Scholes computed",    "Real-time", "Always recomputed — Tradier greeks unreliable for 1-2yr options"],
    ["VIX",                         "Tradier $VIX.X → yfinance fallback", "Real-time", "Deploy % and LEAPS gate"],
    ["Earnings dates",              "yfinance (only yfinance use)", "Daily",  "Hard filter — skip if earnings within EARNINGS_FILTER_DAYS (10)"],
    ["Option expirations",          "Tradier /markets/options/expirations", "Real-time", "Finding valid DTE windows"],
    ["Live mid-price at execution", "Tradier /markets/quotes",   "Real-time", "Limit price on every order placed"],
]
story.append(data_table(ds_rows[0], ds_rows[1:],
             [1.55*inch, 1.85*inch, 0.9*inch, 2.2*inch], DARK_BLUE))
story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# 3. 9-PHASE PIPELINE
# ════════════════════════════════════════════════════════════
story.append(section_header("3.  Run Pipeline — 9 Phases"))
story.append(spacer(0.1))
story.append(Paragraph(
    "Every time the bot fires at 6:35 AM PT it executes nine sequential phases. "
    "Each phase depends on the results of the previous one.", BODY))
story.append(spacer(0.1))

phases = [
    (MID_BLUE,   "1", "VIX + Account Snapshot",            "Fetch VIX, portfolio value, cash, and all open positions from Tradier."),
    (GREEN,      "2", "Manage Existing Positions",          "Profit exits placed automatically. Loss exits post Discord alert — trader closes manually."),
    (MID_BLUE,   "3", "Refresh Capital After Closes",       "Re-fetch account after any closes to get updated cash and buying power."),
    (GREY_DARK,  "4", "Load Tickers + Hard Filters",        "Pull approved stock list, fetch price history, apply 200 SMA and earnings hard filters."),
    (GREEN,      "5", "CSP Screening + Scoring",            "Score each stock on 5 technical signals, find best put contract, rank by score then ARR/Delta ratio."),
    (PURPLE,     "6", "LEAPS Screening",                    "If VIX ≤ 18 or ≥ 21: score stocks on 3 LEAPS criteria, find best deep ITM call contract."),
    (PURPLE,     "7", "Execute LEAPS Trades",               "Top-ranked first, 1 contract per pick, until 15% portfolio budget exhausted."),
    (GREEN,      "8", "Execute CSP Trades",                 "Top-scored first, 1 contract per pick, until VIX-adjusted cash budget exhausted."),
    (MID_BLUE,   "9", "Post Discord Summary",               "Post run summary, open positions table, CSP summary table, LEAPS summary table."),
]

for color, num, name, desc in phases:
    story.append(KeepTogether([
        phase_badge(num, name, color),
        spacer(0.05),
        Paragraph(desc, BODY),
        spacer(0.08),
    ]))

story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# 4. PHASE 1 — VIX & ACCOUNT STATE
# ════════════════════════════════════════════════════════════
story.append(section_header("4.  Phase 1 — VIX & Account State", DARK_BLUE))
story.append(spacer(0.1))

story.append(Paragraph("CSP Delta — BB-Based Per Stock (replaces VIX-global range)", H2))
story.append(info_box(
    "CSP put delta is no longer determined by VIX globally. "
    "Each stock gets its own delta range based on its Bollinger Band position at screening time. "
    "See Phase 5 (Section 7) for the full 3-tier table.", LIGHT_BLUE, MID_BLUE))
story.append(spacer(0.1))

story.append(Paragraph("VIX → Cash Deployment Percentage", H2))
vix_deploy = [
    ["VIX Level",  "Deploy %",  "Rationale"],
    ["> 25",       "80%",       "Fear = opportunity, deploy aggressively"],
    ["20 – 25",    "70%",       "Elevated vol, still good entry conditions"],
    ["15 – 20",    "60%",       "Moderate vol, standard deployment"],
    ["12 – 15",    "40%",       "Low vol, be selective and conservative"],
    ["< 12",       "20%",       "Very low vol, premiums too thin to deploy much"],
]
story.append(data_table(vix_deploy[0], vix_deploy[1:], [1.2*inch, 1.0*inch, 4.3*inch], MID_BLUE))
story.append(spacer(0.1))

story.append(Paragraph("Budget Calculations", H2))
story.append(bullet("<b>CSP Budget</b> = Cash × VIX deploy %"))
story.append(bullet("<b>LEAPS Budget</b> = Portfolio Value × 15% − Current LEAPS Exposure  (never exceeds 15% of portfolio total)"))
story.append(bullet("<b>LEAPS VIX Gate</b> = Screen and execute LEAPS when <b>VIX ≤ 18  OR  VIX ≥ 21</b>"))
story.append(spacer(0.05))
story.append(info_box(
    "<i>Rationale for LEAPS VIX gate (≤18 or ≥21):</i> VIX ≤ 18 = calm market, "
    "stocks fairly valued — ideal LEAPS entry. VIX ≥ 21 = fear-driven selloff, "
    "stocks oversold — excellent LEAPS entry at depressed prices. "
    "Zone 18–21 excluded: moderate stress where IV is neither cheap nor justified.", LIGHT_PURPLE, PURPLE))

story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# 5. PHASE 2 — POSITION MANAGEMENT
# ════════════════════════════════════════════════════════════
story.append(section_header("5.  Phase 2 — Position Management", DARK_BLUE))
story.append(spacer(0.1))
story.append(Paragraph(
    "Before opening any new positions, the bot scans every open position. "
    "Three independent rules evaluate each position. "
    "<b>Profit exits are placed automatically. Loss exits post a Discord alert — the trader decides manually.</b>", BODY))
story.append(spacer(0.1))

story.append(info_box(
    "🤖  <b>Auto-order:</b>  Profit exits only — bot places the closing order immediately.<br/>"
    "⚠️  <b>Discord alert:</b>  Loss exits only — bot posts a recommendation, no order placed. "
    "Trader reviews and closes manually.",
    LIGHT_BLUE, MID_BLUE))
story.append(spacer(0.1))

story.append(Paragraph("CSP Exit Rules — Short Puts (checked in priority order)", H2))

csp_exit_rows = [
    ["Rule", "Trigger", "P&L State", "Action"],
    ["#1 — 50% Capture",
     "(Avg Entry − Current) / Avg Entry ≥ 50%",
     "Profit",
     "🤖 AUTO — BUY TO CLOSE"],
    ["#2 — 21-DTE Exit\n(flat or profit)",
     "DTE ≤ 21 AND captured ≥ 0%",
     "Profit / Flat",
     "🤖 AUTO — BUY TO CLOSE"],
    ["#2 — 21-DTE Exit\n(small loss)",
     "DTE ≤ 21 AND −50% ≤ captured < 0%",
     "Small loss",
     "⚠️ ALERT — manual close"],
    ["#3 — Stop-Loss",
     "Current ≥ Avg Entry × 3.0\n(loss = 2× premium received)",
     "Loss",
     "⚠️ ALERT — manual close"],
]
story.append(data_table(csp_exit_rows[0], csp_exit_rows[1:],
             [1.3*inch, 2.3*inch, 1.0*inch, 1.8*inch], GREEN))
story.append(spacer(0.1))

story.append(Paragraph("LEAPS Exit Rules — Long Calls", H2))

leaps_exit_rows = [
    ["Rule", "Trigger", "P&L State", "Action"],
    ["#1 — Profit Target",
     "(Current − Avg Entry) / Avg Entry ≥ 5%",
     "Profit",
     "🤖 AUTO — SELL TO CLOSE"],
    ["#2 — Stop-Loss",
     "(Current − Avg Entry) / Avg Entry ≤ −50%",
     "Loss",
     "⚠️ ALERT — manual close"],
]
story.append(data_table(leaps_exit_rows[0], leaps_exit_rows[1:],
             [1.3*inch, 2.3*inch, 1.0*inch, 1.8*inch], PURPLE))
story.append(spacer(0.1))

story.append(Paragraph("Discord Loss Alert Format", H2))
story.append(info_box(
    "When a loss exit triggers, the bot posts an alert to <b>#beta-ai-trades</b> containing:<br/>"
    "  •  Position (compact format: e.g. NVDA $195P Jun26)<br/>"
    "  •  Entry price → current price<br/>"
    "  •  Unrealized P&amp;L ($ and %)<br/>"
    "  •  Trigger reason (which rule fired)<br/>"
    "  •  Suggested action (BUY/SELL TO CLOSE N contracts at market)<br/>"
    "  •  Confirmation: <i>No order placed — awaiting your decision.</i>",
    LIGHT_RED, RED))
story.append(spacer(0.1))

story.append(Paragraph("Order Execution Mechanics (profit exits only)", H2))
story.append(bullet("Fetch live bid/ask from Tradier <b>markets/quotes</b> endpoint"))
story.append(bullet("Calculate mid-price: <b>(bid + ask) / 2</b>"))
story.append(bullet("Place a <b>limit order at mid-price</b>, time-in-force = day"))
story.append(bullet("If no live quote available: fallback to last known price"))

story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# 6. PHASE 4 — STOCK SCREENING & HARD FILTERS
# ════════════════════════════════════════════════════════════
story.append(section_header("6.  Phase 4 — Stock Universe & Hard Filters", DARK_BLUE))
story.append(spacer(0.1))
story.append(Paragraph(
    "The bot loads a curated watchlist from Google Sheets, fetches 310 calendar days "
    "of daily OHLCV bars from Tradier for each ticker, computes technical indicators, "
    "then applies two hard filters. Any stock failing either filter is completely "
    "excluded from both CSP and LEAPS screening.", BODY))
story.append(spacer(0.1))

story.append(Paragraph("Technical Indicators Computed", H2))
tech_rows = [
    ["Indicator",       "Calculation",                          "Used In"],
    ["SMA 20",          "Mean of last 20 daily closes",         "Bollinger Band midline, CSP scoring"],
    ["SMA 50",          "Mean of last 50 daily closes",         "CSP scoring (strike above 50 SMA)"],
    ["SMA 200",         "Mean of last 200 daily closes",        "Hard filter — must be above this"],
    ["Bollinger Upper", "SMA 20 + 2 × std(last 20 closes)",     "Reference"],
    ["Bollinger Lower", "SMA 20 − 2 × std(last 20 closes)",     "LEAPS scoring (near lower band)"],
    ["RSI (14)",        "Wilder's smoothed 14-period RSI",      "CSP hard gate (≥65=skip) + CSP scoring (<50=+1) + LEAPS scoring (<70=+1)"],
    ["Day Change %",    "(current − prev_close) / prev_close",  "CSP scoring (healthy pullback)"],
]
story.append(data_table(tech_rows[0], tech_rows[1:],
             [1.3*inch, 2.5*inch, 2.7*inch], DARK_BLUE))
story.append(spacer(0.1))

story.append(Paragraph("Hard Filters", H2))
hf_rows = [
    ["Filter",                      "Logic",                        "Skip if"],
    ["200-day SMA",                 "Is stock in long-term uptrend?","Price ≤ SMA 200"],
    ["Earnings (CSP + LEAPS)",      "Earnings report imminent?",    "Earnings date falls within next EARNINGS_FILTER_DAYS (10) days"],
    ["RSI overbought (CSP only)",   "Applied in Phase 5 per stock", "RSI ≥ 65 — stock is overbought, skip CSP screening"],
]
story.append(data_table(hf_rows[0], hf_rows[1:],
             [1.8*inch, 2.2*inch, 2.5*inch], RED))
story.append(spacer(0.05))
story.append(Paragraph(
    "⚠  Earnings data is fetched from yfinance — the only remaining yfinance dependency. "
    "Tradier does not provide an earnings calendar.", NOTE))

story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# 7. PHASE 5 — CSP SCREENING & SCORING
# ════════════════════════════════════════════════════════════
story.append(section_header("7.  Phase 5 — CSP Screening & Scoring", DARK_BLUE))
story.append(spacer(0.1))

story.append(Paragraph("Step 1 — RSI Hard Gate", H2))
story.append(info_box(
    "<b>If RSI ≥ 65 → SKIP immediately.</b>  Overbought stocks have high mean-reversion risk "
    "within the 30–45 DTE window.  No options lookup is performed.", LIGHT_RED, RED))
story.append(spacer(0.1))

story.append(Paragraph("Step 2 — Pre-Score Gate (skip chain fetch early)", H2))
story.append(info_box(
    "Before fetching any option chain, compute the <b>stock-level pre-score</b> (max 3): "
    "price below BB midline, healthy pullback today, RSI &lt; 50. "
    "The other 2 score points (strike &gt; 50 SMA, IV ≥ 40%) are contract-level. "
    "Since MIN_SCORE_TO_TRADE = 3 and at most 2 contract points can be added, any stock with "
    "pre-score &lt; 1 can never qualify → <b>skip the chain fetch.</b> "
    "Correctness-preserving: it cannot drop a stock that would have qualified.", LIGHT_BLUE, MID_BLUE))
story.append(spacer(0.1))

story.append(Paragraph("Step 3 — BB-Based Delta Range", H2))
bb_delta_rows = [
    ["BB Position",                         "Delta Range",   "Rationale"],
    ["Price ≤ Lower BB + 3%",               "0.25 – 0.35\n(Aggressive)",   "Stock oversold → high reversal probability → sell closer to ATM"],
    ["Between Lower BB and Mid BB",         "0.15 – 0.25\n(Moderate)",     "Partial pullback → standard entry quality"],
    ["Price ≥ Mid BB (SMA 20)",             "0.08 – 0.15\n(Conservative)", "At/above average → more downside room → stay far OTM"],
]
story.append(data_table(bb_delta_rows[0], bb_delta_rows[1:],
             [2.2*inch, 1.4*inch, 2.9*inch], GREEN))
story.append(spacer(0.1))

story.append(Paragraph("Step 4 — Technical Scoring (max 5 points)", H2))
score_rows = [
    ["Signal",                      "Points", "Condition"],
    ["Above 50-day SMA",            "+1",     "Stock price > SMA 50 (medium-term uptrend)"],
    ["At/below 20-day SMA",         "+1",     "Stock price ≤ SMA 20 / BB midline (short-term pullback)"],
    ["Healthy pullback today",      "+1",     "Day change between −0.5% and −5.0%"],
    ["RSI < 50",                    "+1",     "Actively oversold — best entry timing (replaces price<$100)"],
    ["IV ≥ 40%",                    "+1",     "Elevated implied volatility — premium is rich"],
]
story.append(data_table(score_rows[0], score_rows[1:],
             [2.5*inch, 0.7*inch, 3.3*inch], GREEN))
story.append(spacer(0.08))
story.append(Paragraph(
    "Require final score ≥ MIN_SCORE_TO_TRADE (3) to qualify.  "
    "Score = 5 → flagged HIGH CONVICTION.", NOTE))
story.append(spacer(0.1))

story.append(Paragraph("Step 5 — Find Best Put Contract (Tradier Options Chain)", H2))
story.append(Paragraph(
    "For each expiration date between MIN_DTE (30) and MAX_DTE (45) days:", BODY))
story.append(bullet("Fetch full options chain from Tradier with <b>greeks=true</b>"))
story.append(bullet("Filter puts: Open Interest ≥ 50 (rejects OI = 0),  valid bid/ask quote"))
story.append(bullet("Get delta from <b>Tradier greeks.delta</b>; fallback to Black-Scholes if null"))
story.append(bullet("Apply BB-position-based delta filter (per-stock tier: aggressive / moderate / conservative)"))
story.append(bullet("Calculate <b>ARR = (mid / strike) × (365 / DTE) × 100</b>"))
story.append(spacer(0.08))

story.append(Paragraph("Strike Selection Logic (ARR band 40–70%):", H3))
story.append(info_box(
    "<b>Contracts within band (40% ≤ ARR ≤ 70%):</b>  Pick the highest ARR in band.<br/>"
    "<b>If ALL contracts are above the cap (ARR &gt; 70%):</b>  Step down to the lowest "
    "(safest) ARR above the cap.<br/>"
    "<b>If NO contract reaches the floor (all ARR &lt; 40%):</b>  Skip the stock entirely — "
    "MIN_ARR is a HARD floor, never breached. (This is why e.g. a 30%-ARR contract will not be selected.)",
    LIGHT_ORANGE, ORANGE))
story.append(spacer(0.1))

story.append(Paragraph("Step 6 — Rank and Select Top 5", H2))
story.append(bullet("Sort qualifying CSPs by the following priority:"))
story.append(bullet("<b>1. Score DESC</b> — technical setup quality (primary)"))
story.append(bullet("<b>2. ARR ÷ Delta DESC</b> — normalized risk-adjusted return (secondary)"))
story.append(bullet("   Rationale: a lower delta + higher ARR means the market pays you MORE for taking LESS"))
story.append(bullet("   directional risk. ARR/Delta correctly ranks e.g. delta=0.14 ARR=69% (ratio=493)"))
story.append(bullet("   above delta=0.20 ARR=47% (ratio=235). Pure ARR alone would invert this."))
story.append(bullet("<b>3. DTE DESC</b> — more time = more cushion for recovery"))
story.append(bullet("<b>4. ARR DESC</b> — final tie-breaker only"))
story.append(bullet("Take top 5"))

story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# 8. PHASE 6 — LEAPS SCREENING
# ════════════════════════════════════════════════════════════
story.append(section_header("8.  Phase 6 — LEAPS Screening", DARK_BLUE))
story.append(spacer(0.1))
story.append(info_box(
    "<b>VIX Hard Gate:</b>  LEAPS screening runs ONLY when <b>VIX ≤ 18  OR  VIX ≥ 21</b>. "
    "Zone 18–21 is excluded (moderate stress — IV inflated without directional clarity). "
    "Outside both zones the entire LEAPS phase is skipped.", LIGHT_ORANGE, ORANGE))
story.append(spacer(0.1))
story.append(Paragraph(
    "Runs on the same stock universe that passed the hard filters in Phase 4.", BODY))
story.append(spacer(0.1))

story.append(Paragraph("LEAPS Scoring Criteria (3 points total — all stock-level)", H2))
leaps_score_rows = [
    ["Criterion",          "Points", "Logic",            "Notes"],
    ["Above 200-day SMA",  "+1",     "Price &gt; SMA 200", "Long-term uptrend confirmed"],
    ["Above 50-day SMA",   "+1",     "Price &gt; SMA 50",  "Medium-term momentum intact"],
    ["RSI not overbought", "+1",     "RSI(14) &lt; 70",    "Wilder's smoothed RSI from Tradier daily bars"],
]
story.append(data_table(leaps_score_rows[0], leaps_score_rows[1:],
             [1.5*inch, 0.7*inch, 1.5*inch, 2.8*inch], PURPLE))
story.append(spacer(0.08))
story.append(bullet("Minimum score to qualify for LEAPS: <b>2 out of 3</b>"))
story.append(bullet("All three criteria are <b>stock-level</b> — the score is computed BEFORE any "
                    "option chain is fetched, so chains are only pulled for stocks that already qualify."))
story.append(spacer(0.1))

story.append(Paragraph("LEAPS Contract Selection (Tradier Options Chain)", H2))
story.append(bullet("Expiration window: <b>365 to 730 days (1–2 years out)</b>"))
story.append(bullet("<b>Farthest expiry first:</b> fetch the longest-dated expiry in the window "
                    "(max time value, lowest theta — ideal for stock replacement). Fall back to the "
                    "next-farthest only if it yields no qualifying contract. ~1 chain/stock vs 6–10 before."))
story.append(bullet("Contract type: <b>Call options only</b>"))
story.append(bullet("OI filter: skip only if confirmed OI &gt; 0 but &lt; 50 (OI = 0 means data unavailable, allow through)"))
story.append(bullet("Price: (bid+ask)/2 → ask → bid → lastPrice (in priority order)"))
story.append(bullet("Delta: use <b>Tradier greeks.delta</b> if available, otherwise compute via <b>Black-Scholes</b>"))
story.append(bullet("For BS computation: use Tradier IV if IV ≥ 0.20, else default to <b>0.45</b> (LEAPS greeks are unreliable in data feeds)"))
story.append(bullet("Delta filter: <b>0.70 ≤ delta ≤ 0.85</b> (deep in the money)"))
story.append(bullet("Selection: within the chosen expiry, pick the contract whose delta is <b>closest to 0.77 (target)</b>"))
story.append(spacer(0.1))

story.append(Paragraph("LEAPS Ranking", H2))
story.append(bullet("Sort by: <b>leaps_score DESC</b>, then <b>RSI ASC</b> (most oversold first)"))
story.append(bullet("Take top 5"))

story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# 9. PHASES 7 & 8 — ORDER EXECUTION
# ════════════════════════════════════════════════════════════
story.append(section_header("9.  Phases 7 & 8 — Trade Execution", DARK_BLUE))
story.append(spacer(0.1))

story.append(Paragraph("LEAPS Execution (Phase 7)", H2))
story.append(info_box(
    "<b>Budget:</b>  Portfolio Value × 15%  (minus current LEAPS exposure already on the books)<br/><br/>"
    "<b>Allocation:</b>  Top-ranked first. 1 contract per pick. Full remaining budget available for each pick.<br/>"
    "Skip a pick only if the remaining budget is too small for its cost — move to the next pick.",
    LIGHT_PURPLE, PURPLE))
story.append(spacer(0.08))

story.append(Paragraph("For each LEAPS pick (in ranked order):", H3))
story.append(bullet("If remaining budget &lt; cost_per_contract → skip, try next"))
story.append(bullet("Fetch live mid-price from Tradier quotes"))
story.append(bullet("Place <b>limit BUY TO OPEN</b> order at mid-price, qty = 1, time-in-force = day"))
story.append(bullet("Deduct cost from remaining budget and continue to next pick"))
story.append(spacer(0.1))

story.append(Paragraph("CSP Execution (Phase 8)", H2))
story.append(info_box(
    "<b>Budget:</b>  Cash × VIX deploy %<br/><br/>"
    "<b>Collateral:</b>  Each CSP requires Strike × $100 in cash as collateral.<br/>"
    "<b>Allocation:</b>  Top-scored first. 1 contract per pick.",
    LIGHT_GREEN, GREEN))
story.append(spacer(0.08))

story.append(Paragraph("For each CSP pick (in score-ranked order):", H3))
story.append(bullet("If remaining cash &lt; strike × $100 → skip, try next"))
story.append(bullet("Fetch live mid-price from Tradier quotes"))
story.append(bullet("Place <b>limit SELL TO OPEN</b> order at mid-price, qty = 1, time-in-force = day"))
story.append(bullet("Deduct collateral from remaining cash and continue to next pick"))
story.append(spacer(0.1))

story.append(Paragraph("Order Format (Tradier API)", H2))
story.append(Paragraph("All orders are placed as form-encoded POST requests to Tradier:", BODY))
order_rows = [
    ["Parameter",       "CSP Value",            "LEAPS Value"],
    ["class",           "option",               "option"],
    ["symbol",          "Underlying ticker",    "Underlying ticker"],
    ["option_symbol",   "OCC put symbol",       "OCC call symbol"],
    ["side",            "sell_to_open",         "buy_to_open"],
    ["quantity",        "1",                    "1"],
    ["type",            "limit",                "limit"],
    ["price",           "Live Tradier mid",     "Live Tradier mid"],
    ["duration",        "day",                  "day"],
]
story.append(data_table(order_rows[0], order_rows[1:],
             [1.6*inch, 2.4*inch, 2.5*inch], DARK_BLUE))

story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# 10. KEY PARAMETERS
# ════════════════════════════════════════════════════════════
story.append(section_header("10.  Key Parameters Reference", DARK_BLUE))
story.append(spacer(0.1))
story.append(Paragraph(
    "All parameters are set via environment variables in the launchd plist "
    "(com.ankushsinghal.tptagent.plist). The defaults below are the current live values.", BODY))
story.append(spacer(0.1))

story.append(Paragraph("CSP Parameters", H2))
csp_param_rows = [
    ["Parameter",               "Default", "Description"],
    ["MIN_DTE",                   "30",        "Minimum days to expiration for CSP puts"],
    ["MAX_DTE",                   "45",        "Maximum days to expiration for CSP puts"],
    ["EARNINGS_FILTER_DAYS",      "10",        "Earnings hard-filter look-ahead — skip stock if earnings within this many days (applies to BOTH CSP and LEAPS; decoupled from MAX_DTE)"],
    ["MIN_ARR",                   "40%",       "Minimum annualized return on risk to qualify"],
    ["MAX_ARR",                   "70%",       "ARR cap — step down to safer strike if exceeded"],
    ["MIN_OPEN_INTEREST",         "50",        "Minimum open interest for liquidity (rejects OI = 0 — CSP needs real liquidity)"],
    ["CSP_RSI_OVERBOUGHT",        "65",        "Hard gate — skip stock if RSI ≥ this (overbought)"],
    ["CSP_DELTA_NEAR_LOWER_MIN/MAX", "0.25/0.35", "Delta range when price ≤ lower BB + 3% (aggressive)"],
    ["CSP_DELTA_MID_ZONE_MIN/MAX",   "0.15/0.25", "Delta range when price between lower and mid BB (moderate)"],
    ["CSP_DELTA_ABOVE_MID_MIN/MAX",  "0.08/0.15", "Delta range when price ≥ mid BB (conservative)"],
    ["MIN_SCORE_TO_TRADE",        "3",         "Minimum score (out of 5) to qualify for execution"],
    ["SIZE_UP_SCORE",             "5",         "Score threshold for HIGH CONVICTION label"],
    ["SCORE_IV_MIN_PCT",          "40%",       "IV threshold for +1 scoring point"],
    ["SCORE_RSI_OVERSOLD",        "50",        "RSI below this earns +1 score point (actively oversold)"],
    ["SCORE_DOWN_TODAY_MIN_PCT",  "0.5%",      "Min pullback today to earn the pullback score point"],
    ["SCORE_DOWN_TODAY_MAX_PCT",  "5.0%",      "Max pullback today (beyond this = potential problem)"],
    ["CSP_CLOSE_PREMIUM_PCT",     "50%",       "Close CSP when this % of premium has been captured"],
    ["CSP_DTE_EXIT",              "21",        "Close CSP at DTE ≤ this with positive/neutral P&L (gamma gate)"],
    ["CSP_STOP_LOSS_MULT",        "2.0×",      "Close CSP when loss ≥ 2× premium received"],
]
story.append(data_table(csp_param_rows[0], csp_param_rows[1:],
             [2.2*inch, 1.0*inch, 3.3*inch], GREEN))
story.append(spacer(0.1))

story.append(Paragraph("LEAPS Parameters", H2))
leaps_param_rows = [
    ["Parameter",               "Default",   "Description"],
    ["LEAPS_MIN_DTE",           "365 days",  "Minimum DTE for LEAPS contracts"],
    ["LEAPS_MAX_DTE",           "730 days",  "Maximum DTE for LEAPS contracts (1–2 years)"],
    ["LEAPS_MIN_DELTA",         "0.70",      "Minimum call delta (lowered from 0.80)"],
    ["LEAPS_MAX_DELTA",         "0.85",      "Maximum call delta (lowered from 0.99)"],
    ["LEAPS_TARGET_DELTA",      "0.77",      "Target delta — pick contract closest to this (lowered from 0.85)"],
    ["LEAPS_VIX_CALM_MAX",      "18",        "LEAPS enabled when VIX ≤ this (calm zone)"],
    ["LEAPS_VIX_FEAR_MIN",      "21",        "LEAPS also enabled when VIX ≥ this (fear/opportunity zone)"],
    ["LEAPS_MIN_SCORE",         "2",         "Minimum LEAPS criteria score (out of 3)"],
    ["LEAPS_MIN_OI",            "50",        "Minimum OI (only enforced when OI > 0 from API)"],
    ["LEAPS_MAX_PORTFOLIO_PCT", "15%",       "Hard cap on total LEAPS exposure as % of portfolio (raised from 10%)"],
    ["LEAPS_RSI_OVERBOUGHT",    "70",        "RSI threshold — below this = not overbought (+1 pt)"],
    ["LEAPS_RSI_PERIOD",        "14",        "RSI calculation period (Wilder's smoothed)"],
    ["LEAPS_CLOSE_PROFIT_PCT",  "5%",        "Close LEAPS when unrealized profit reaches this (lowered from 25%)"],
    ["LEAPS_STOP_LOSS_PCT",     "50%",       "Close LEAPS when unrealized loss reaches this"],
]
story.append(data_table(leaps_param_rows[0], leaps_param_rows[1:],
             [2.2*inch, 1.0*inch, 3.3*inch], PURPLE))
story.append(spacer(0.1))

story.append(Paragraph("Performance Parameters", H2))
perf_param_rows = [
    ["Parameter",   "Default", "Description"],
    ["MAX_WORKERS", "6",       "Thread-pool size for parallel per-ticker screening (Phases 4, 5, 6)"],
]
story.append(data_table(perf_param_rows[0], perf_param_rows[1:],
             [2.2*inch, 1.0*inch, 3.3*inch], DARK_BLUE))
story.append(spacer(0.05))
story.append(Paragraph(
    "Performance: per-ticker screening runs in parallel; option expirations are cached "
    "per ticker; LEAPS fetch only the farthest expiry; CSP and LEAPS gate on stock-level "
    "score before any chain fetch. A full run takes ≈ 1 minute (down from ≈ 7 minutes).", NOTE))

story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# 11. DISCORD OUTPUT
# ════════════════════════════════════════════════════════════
story.append(section_header("11.  Discord Output", DARK_BLUE))
story.append(spacer(0.1))
story.append(Paragraph(
    "All output goes exclusively to <b>#beta-ai-trades</b>. The webhook URL is hardcoded "
    "in tpt_agent.py — it cannot be redirected to another channel via configuration. "
    "Only summary tables are posted; no individual trade detail cards.", BODY))
story.append(spacer(0.1))

discord_rows = [
    ["Post #", "Content",               "Always Posted?",   "Format"],
    ["1",      "Run Summary",           "Yes",              "Embed: balance, VIX, profit closes (auto-ordered), loss alerts (manual), new positions"],
    ["2",      "Open Positions Table",  "If positions exist","Code block: position, qty, P&L $, P&L %"],
    ["3",      "Loss Alert (per position)", "If loss exit triggered", "Red embed: position, P&L, trigger reason, suggested action. No order placed."],
    ["4",      "LEAPS Criteria Embed",  "Yes",              "Embed: VIX gate status, criteria list, DTE/delta targets"],
    ["5",      "LEAPS Summary Table",   "If VIX in range + picks found", "Code block: ticker, strike, delta, expiry, cost"],
    ["6",      "CSP Summary Table",     "If picks found",   "Code block: ticker, strike, delta, expiry, premium, ARR"],
]
story.append(data_table(discord_rows[0], discord_rows[1:],
             [0.5*inch, 1.6*inch, 1.5*inch, 2.9*inch], DARK_BLUE))
story.append(spacer(0.08))
story.append(Paragraph(
    "All embeds and tables include [TPT] label to distinguish from the Experiment Bot "
    "which posts to the same channel.", NOTE))

story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# 12. DECISION FLOW
# ════════════════════════════════════════════════════════════
story.append(section_header("12.  Full Decision Flow", DARK_BLUE))
story.append(spacer(0.1))

flow = [
    ("START  6:35 AM PT trigger", DARK_BLUE),
    ("Fetch VIX → determine deploy %; LEAPS gate: VIX ≤ 18 OR ≥ 21", MID_BLUE),
    ("Fetch Tradier account: portfolio value, cash, option buying power", MID_BLUE),
    ("Fetch all open positions", MID_BLUE),
    ("─── POSITION MANAGEMENT ───", GREY_DARK),
    ("For each open SHORT PUT (CSP):", GREEN),
    ("    • If stop-loss triggered (loss ≥ 2× premium)  →  ⚠️ DISCORD ALERT only, no order", RED),
    ("    • If 50% premium captured  →  🤖 BUY TO CLOSE at mid (auto)", GREEN),
    ("    • If DTE ≤ 21 and in profit  →  🤖 BUY TO CLOSE at mid (auto)", GREEN),
    ("    • If DTE ≤ 21 and at loss  →  ⚠️ DISCORD ALERT only, no order", RED),
    ("For each open LONG CALL (LEAPS):", PURPLE),
    ("    • If stop-loss triggered (loss ≥ 50%)  →  ⚠️ DISCORD ALERT only, no order", RED),
    ("    • If profit target reached (gain ≥ 5%)  →  🤖 SELL TO CLOSE at mid (auto)", PURPLE),
    ("Re-fetch account to capture released capital", MID_BLUE),
    ("─── STOCK SCREENING ───", GREY_DARK),
    ("Load approved ticker list from Google Sheets", GREY_DARK),
    ("For each ticker (parallel, ThreadPoolExecutor — MAX_WORKERS=6):", GREY_DARK),
    ("    • Fetch 310 days OHLCV + quote from Tradier  →  compute SMA20/50/200, BB, RSI", GREY_DARK),
    ("    • HARD FILTER 1: skip if price ≤ SMA 200", RED),
    ("    • HARD FILTER 2: skip if earnings within EARNINGS_FILTER_DAYS=10 (yfinance)", RED),
    ("─── CSP SCORING (parallel) ───", GREEN),
    ("For each stock passing hard filters:", GREEN),
    ("    • Hard gate: RSI ≥ 65 → skip (overbought)", GREEN),
    ("    • Pre-score gate: skip chain fetch if stock-level pre-score can't reach 3", GREEN),
    ("    • BB-based delta range: near lower BB=0.25–0.35 / between BBs=0.15–0.25 / above mid=0.08–0.15", GREEN),
    ("    • Fetch put chain from Tradier (greeks=true)", GREEN),
    ("    • Filter puts: OI≥50 (rejects OI=0), delta in BB-tier range, ARR 40–70%", GREEN),
    ("    • Score: strike>50 SMA (+1), below mid BB (+1), pullback 0.5–5% (+1), RSI<50 (+1), IV≥40% (+1)", GREEN),
    ("    • If final score < 3: skip", GREEN),
    ("Sort CSPs: score DESC → ARR/Delta DESC → DTE DESC → ARR DESC  →  take top 5", GREEN),
    ("─── LEAPS SCORING (parallel; only if VIX ≤ 18 OR ≥ 21) ───", PURPLE),
    ("For each stock passing hard filters:", PURPLE),
    ("    • Score FIRST (stock-level): above 200 SMA (+1), above 50 SMA (+1), RSI<70 (+1)", PURPLE),
    ("    • If score < 2: skip (no chain fetch)", PURPLE),
    ("    • Fetch ONLY the farthest expiry chain (DTE 365–730); fall back if no contract", PURPLE),
    ("    • Filter calls: OI≥50, delta 0.70–0.85; pick closest to delta 0.77", PURPLE),
    ("Sort LEAPS by score DESC, RSI ASC  →  take top 5", PURPLE),
    ("─── EXECUTION ───", DARK_BLUE),
    ("LEAPS: iterate top-ranked first, 1 contract each, until 15% budget exhausted", PURPLE),
    ("CSP:   iterate top-scored first, 1 contract each, until VIX-deploy cash exhausted", GREEN),
    ("All orders: limit at live Tradier mid-price, time-in-force = day", DARK_BLUE),
    ("─── DISCORD ───", MID_BLUE),
    ("Post run summary, open positions, CSP table, LEAPS table to #beta-ai-trades", MID_BLUE),
    ("END", DARK_BLUE),
]

for text, color in flow:
    indent = 0
    txt = text
    if text.startswith("    "):
        indent = 14
        txt = text.strip()

    is_header = text.startswith("───")
    bg = color if is_header else None
    fg = WHITE if is_header else color

    cell_style = ParagraphStyle(
        "flow_cell",
        fontName="Helvetica-Bold" if is_header else "Helvetica",
        fontSize=8,
        textColor=WHITE if is_header else color,
        leading=11,
        leftIndent=indent,
    )
    p = Paragraph(txt, cell_style)
    row_data = [[p]]
    t = Table(row_data, colWidths=[6.5*inch])
    ts = [
        ("LEFTPADDING",   (0,0), (-1,-1), 8 + indent),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("TOPPADDING",    (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]
    if is_header:
        ts.append(("BACKGROUND", (0,0), (-1,-1), color))
    else:
        ts.append(("LINEBELOW", (0,0), (-1,-1), 0.3, GREY_LIGHT))
    t.setStyle(TableStyle(ts))
    story.append(t)

story.append(spacer(0.15))
story.append(Paragraph(
    "* The experiment_bot.py (Alpaca) runs an identical strategy independently. "
    "Trade picks are generated separately for each broker — they are not shared. "
    "This allows side-by-side comparison of broker execution quality.", NOTE))

# ════════════════════════════════════════════════════════════
# BUILD
# ════════════════════════════════════════════════════════════
doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=letter,
    leftMargin=0.75*inch,
    rightMargin=0.75*inch,
    topMargin=0.7*inch,
    bottomMargin=0.6*inch,
    title="TPT Agent — Algorithm Documentation",
    author="Ankush Singhal",
    subject="Tradier Paper Trading Bot Strategy",
)
doc.build(story, onFirstPage=on_first_page, onLaterPages=on_page)
print(f"✅  PDF saved → {OUTPUT}")
