#!/usr/bin/env python3
"""Weekly Trade Ideas Analysis — CSP Wheel Bot performance report generator.

Downloads the CSP Wheel Bot trade tracker Google Sheet, analyzes the trades
for a given weekly expiration date, computes overall portfolio stats, renders
charts, and builds a polished multi-page PDF report.

Usage:
    python3 generate_report.py                     # auto-detect latest past expiry
    python3 generate_report.py --expiry 2026-07-02 # specific expiration date
    python3 generate_report.py --out /path/to/dir  # custom output directory

Methodology: every position is assumed to be closed at expiration (wins expire
worthless, losses are bought back for intrinsic value on expiry day). No
assignment / share-holding is modeled — the sheet's posted Outcome and P&L
columns are taken as final.
"""

import argparse
import csv
import io
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SHEET_ID = "1ABYAKLvMgoHbM2gccwrfFGYsP6U-Y0VYFnU9SFOPjVo"
SHEET_GID = "0"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"
DEFAULT_OUT_DIR = "/Users/ankushsinghal/Documents/Trading/reports"

NAVY_HEX = "#13253F"
GOLD_HEX = "#C9A24B"
GREEN_HEX = "#2E7D4F"
RED_HEX = "#B3402A"
GREY_HEX = "#8A8F98"


# ---------------------------------------------------------------- parsing ---

def parse_money(s):
    if not s:
        return 0.0
    s = s.replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_pct(s):
    if not s:
        return None
    s = s.replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def load_trades():
    """Download the sheet and return (header, data_rows).

    Uses curl rather than urllib because the framework Python on macOS often
    lacks root SSL certificates (CERTIFICATE_VERIFY_FAILED)."""
    result = subprocess.run(
        ["curl", "-sL", "--max-time", "60", CSV_URL],
        capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        sys.exit(f"ERROR: failed to download the sheet (curl exit "
                 f"{result.returncode}). Check network access and that the "
                 f"sheet is still public: {CSV_URL}")
    text = result.stdout
    lines = text.splitlines(keepends=True)
    header_idx = next(
        (i for i, l in enumerate(lines) if l.startswith("Date Posted")), None)
    if header_idx is None:
        sys.exit("ERROR: could not find 'Date Posted' header row in the sheet. "
                 "The sheet layout may have changed — inspect it manually.")
    rows = list(csv.reader(io.StringIO("".join(lines[header_idx:]))))
    return rows[0], [r for r in rows[1:] if len(r) > 14 and r[1].strip()]


# Column indexes in the sheet
COL_POSTED, COL_TICKER, COL_STRIKE, COL_EXPIRY, COL_DTE = 0, 1, 2, 3, 4
COL_PREM_D, COL_OUTCOME, COL_PNL, COL_RET = 6, 14, 15, 16


def pick_expiry(data, requested):
    """Return the expiry to report on: requested, else latest expiry with
    closed outcomes that is not in the future."""
    if requested:
        return requested
    today = datetime.now().date()
    candidates = set()
    for r in data:
        if r[COL_OUTCOME].strip() in ("WIN", "LOSS"):
            try:
                d = datetime.strptime(r[COL_EXPIRY].strip(), "%Y-%m-%d").date()
            except ValueError:
                continue
            if d <= today:
                candidates.add(d)
    if not candidates:
        sys.exit("ERROR: no past expiration dates with closed outcomes found.")
    return max(candidates).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- analysis ---

def analyze(data, expiry):
    wins = [r for r in data if r[COL_OUTCOME].strip() == "WIN"]
    losses = [r for r in data if r[COL_OUTCOME].strip() == "LOSS"]
    pending = [r for r in data if r[COL_OUTCOME].strip() == "PENDING"]
    closed = wins + losses

    week = [r for r in data if r[COL_EXPIRY].strip() == expiry]
    week_w = [r for r in week if r[COL_OUTCOME].strip() == "WIN"]
    week_l = [r for r in week if r[COL_OUTCOME].strip() == "LOSS"]
    week_closed = week_w + week_l

    if not week_closed:
        sys.exit(f"ERROR: no closed trades found for expiration {expiry}. "
                 "Check the date or wait for the sheet to be updated.")

    a = {}
    a["expiry"] = expiry
    a["week"] = week
    a["week_w"], a["week_l"] = week_w, week_l
    a["week_net"] = sum(parse_money(r[COL_PNL]) for r in week_closed)
    a["week_loss_dollars"] = sum(parse_money(r[COL_PNL]) for r in week_l)
    a["week_win_rate"] = len(week_w) / len(week_closed) * 100
    a["week_loss_tickers"] = sorted(set(r[COL_TICKER] for r in week_l))
    a["week_win_tickers"] = sorted(set(r[COL_TICKER] for r in week_w))

    a["wins"], a["losses"], a["pending"], a["closed"] = wins, losses, pending, closed
    a["total_trades"] = len(data)
    a["win_dollars"] = sum(parse_money(r[COL_PNL]) for r in wins)
    a["loss_dollars"] = sum(parse_money(r[COL_PNL]) for r in losses)
    a["net_pnl"] = a["win_dollars"] + a["loss_dollars"]
    a["win_rate"] = len(wins) / len(closed) * 100 if closed else 0
    a["profit_factor"] = (a["win_dollars"] / abs(a["loss_dollars"])
                          if a["loss_dollars"] else float("inf"))

    dtes = [parse_float(r[COL_DTE]) for r in closed if parse_float(r[COL_DTE]) is not None]
    a["avg_dte"] = sum(dtes) / len(dtes) if dtes else 0
    rets = [parse_pct(r[COL_RET]) for r in closed if parse_pct(r[COL_RET]) is not None]
    a["avg_return"] = sum(rets) / len(rets) if rets else 0
    collateral = sum(parse_money(r[COL_STRIKE]) * 100 for r in closed)
    a["capw_return"] = a["net_pnl"] / collateral * 100 if collateral else 0
    a["annualized"] = a["capw_return"] / a["avg_dte"] * 365 if a["avg_dte"] else 0

    a["open_prem"] = sum(parse_money(r[COL_PREM_D]) for r in pending)
    a["open_collateral"] = sum(parse_money(r[COL_STRIKE]) * 100 for r in pending)
    open_dtes = [parse_float(r[COL_DTE]) for r in pending if parse_float(r[COL_DTE]) is not None]
    a["open_avg_dte"] = sum(open_dtes) / len(open_dtes) if open_dtes else 0

    by_ticker = defaultdict(lambda: [0, 0, 0.0])  # n, wins, net
    for r in closed:
        t = by_ticker[r[COL_TICKER]]
        t[0] += 1
        t[1] += 1 if r[COL_OUTCOME].strip() == "WIN" else 0
        t[2] += parse_money(r[COL_PNL])
    a["by_ticker"] = dict(by_ticker)

    open_by_ticker = defaultdict(int)
    for r in pending:
        open_by_ticker[r[COL_TICKER]] += 1
    a["open_by_ticker"] = dict(open_by_ticker)

    perfect = [(t, v) for t, v in by_ticker.items() if v[1] == v[0] and v[0] >= 2]
    perfect.sort(key=lambda x: -x[1][2])
    a["perfect"] = perfect
    a["perfect_total"] = sum(v[2] for _, v in perfect)

    negative = [(t, v) for t, v in by_ticker.items() if v[2] < 0]
    negative.sort(key=lambda x: x[1][2])
    a["negative"] = negative
    return a


# ------------------------------------------------------------------ charts ---

def make_charts(a, chart_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.edgecolor": "#D9D9D9",
        "axes.labelcolor": "#3A3A3A",
        "text.color": "#222222",
        "xtick.color": "#3A3A3A",
        "ytick.color": "#3A3A3A",
    })

    # -- win-rate donuts: this week vs overall
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.6), dpi=200)

    def donut(ax, w, l, title):
        wedges, _ = ax.pie(
            [w, l], colors=[GREEN_HEX, RED_HEX], startangle=90,
            counterclock=False,
            wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2))
        pct = w / (w + l) * 100 if (w + l) else 0
        ax.text(0, 0.06, f"{pct:.0f}%", ha="center", va="center",
                fontsize=20, fontweight="bold", color=NAVY_HEX)
        ax.text(0, -0.22, "Win Rate", ha="center", va="center",
                fontsize=9, color=GREY_HEX)
        ax.set_title(title, fontsize=11, fontweight="bold", color=NAVY_HEX, pad=6)
        ax.legend(wedges, [f"Wins\n{w}", f"Losses\n{l}"], loc="lower center",
                  bbox_to_anchor=(0.5, -0.28), ncol=2, frameon=False,
                  fontsize=8, handlelength=1.2)

    exp_dt = datetime.strptime(a["expiry"], "%Y-%m-%d")
    donut(axes[0], len(a["week_w"]), len(a["week_l"]),
          f"This Week (Exp. {exp_dt.month}/{exp_dt.day}/{exp_dt.year})")
    donut(axes[1], len(a["wins"]), len(a["losses"]), "Overall Closed Trades")
    plt.tight_layout()
    plt.savefig(f"{chart_dir}/win_rate_donuts.png", transparent=True)
    plt.close()

    # -- cumulative realized P&L by expiration cycle
    by_exp = defaultdict(float)
    for r in a["closed"]:
        by_exp[r[COL_EXPIRY].strip()] += parse_money(r[COL_PNL])
    exp_sorted = sorted(by_exp, key=lambda d: datetime.strptime(d, "%Y-%m-%d"))
    cum, running = [], 0.0
    for d in exp_sorted:
        running += by_exp[d]
        cum.append(running)

    fig, ax = plt.subplots(figsize=(7.4, 3.6), dpi=200)
    xlabels = [datetime.strptime(d, "%Y-%m-%d").strftime("%-m/%-d") for d in exp_sorted]
    ax.plot(xlabels, cum, color=NAVY_HEX, linewidth=2.2, marker="o",
            markersize=4.5, markerfacecolor=GOLD_HEX, markeredgecolor=NAVY_HEX, zorder=3)
    ax.fill_between(xlabels, cum, color=NAVY_HEX, alpha=0.06, zorder=1)
    ax.set_title("Cumulative Realized P&L by Expiration Cycle",
                 fontsize=12, fontweight="bold", color=NAVY_HEX, pad=12)
    ax.set_ylabel("Cumulative P&L ($)")
    ax.grid(axis="y", color="#E7E7E7", linewidth=0.7, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    if a["expiry"] in exp_sorted:
        idx = exp_sorted.index(a["expiry"])
        pad = max(abs(c) for c in cum) * 0.12 or 1
        ax.annotate("This Week", xy=(idx, cum[idx]), xytext=(idx, cum[idx] + pad),
                    ha="center", fontsize=8.5, color=RED_HEX, fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color=RED_HEX, lw=1.2))
    plt.tight_layout()
    plt.savefig(f"{chart_dir}/cumulative_pnl.png", transparent=True)
    plt.close()

    # -- net realized P&L by ticker
    items = sorted(a["by_ticker"].items(), key=lambda x: x[1][2])
    tickers = [t for t, _ in items]
    vals = [v[2] for _, v in items]
    colors_ = [GREEN_HEX if v >= 0 else RED_HEX for v in vals]

    fig, ax = plt.subplots(figsize=(7.4, 4.6), dpi=200)
    bars = ax.barh(tickers, vals, color=colors_, height=0.62, zorder=3)
    ax.axvline(0, color="#B0B0B0", linewidth=0.8, zorder=2)
    ax.set_xlabel("Net Realized P&L ($)")
    ax.set_title("Net Realized P&L by Ticker (Closed Trades)",
                 fontsize=12, fontweight="bold", color=NAVY_HEX, pad=12)
    ax.grid(axis="x", color="#E7E7E7", linewidth=0.7, zorder=0)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    for b, v in zip(bars, vals):
        x, y = b.get_width(), b.get_y() + b.get_height() / 2
        off, ha = (5, "left") if x >= 0 else (-5, "right")
        ax.annotate(f"${v:,.0f}", xy=(x, y), xytext=(off, 0),
                    textcoords="offset points", va="center", ha=ha,
                    fontsize=8, color="#333333")
    lo, hi = min(vals + [0]), max(vals + [0])
    # generous left margin so negative-value labels clear the ticker names
    ax.set_xlim(lo * 2.6 if lo < 0 else -hi * 0.05, hi * 1.28)
    plt.tight_layout()
    plt.savefig(f"{chart_dir}/pnl_by_ticker.png", transparent=True)
    plt.close()


# --------------------------------------------------------------------- pdf ---

def build_pdf(a, chart_dir, out_path):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (HRFlowable, Image, PageBreak, Paragraph,
                                    SimpleDocTemplate, Spacer, Table, TableStyle)

    NAVY = colors.HexColor(NAVY_HEX)
    NAVY_LIGHT = colors.HexColor("#1F3B5C")
    GOLD = colors.HexColor(GOLD_HEX)
    GREEN = colors.HexColor(GREEN_HEX)
    GREEN_BG = colors.HexColor("#EAF5EE")
    RED = colors.HexColor(RED_HEX)
    RED_BG = colors.HexColor("#FBEDE9")
    GREY = colors.HexColor("#5A5F66")
    LIGHT_GREY = colors.HexColor("#F4F5F7")
    LINE_GREY = colors.HexColor("#DCDFE3")

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("SectionHeader", fontName="Helvetica-Bold",
                              fontSize=15, leading=18, textColor=NAVY,
                              spaceBefore=6, spaceAfter=10))
    styles.add(ParagraphStyle("SubHeader", fontName="Helvetica-Bold",
                              fontSize=11, leading=14, textColor=NAVY_LIGHT,
                              spaceBefore=4, spaceAfter=6))
    styles.add(ParagraphStyle("Body", fontName="Helvetica", fontSize=9.5,
                              leading=14, textColor=colors.HexColor("#2A2E33"),
                              alignment=TA_LEFT))
    styles.add(ParagraphStyle("BodySmall", fontName="Helvetica", fontSize=8.5,
                              leading=12.5, textColor=GREY, alignment=TA_LEFT))
    styles.add(ParagraphStyle("KpiValue", fontName="Helvetica-Bold", fontSize=18,
                              leading=20, textColor=NAVY, alignment=TA_CENTER))
    styles.add(ParagraphStyle("KpiLabel", fontName="Helvetica", fontSize=8,
                              leading=10, textColor=GREY, alignment=TA_CENTER))
    styles.add(ParagraphStyle("TakeawayBullet", fontName="Helvetica", fontSize=9.5,
                              leading=14, textColor=colors.HexColor("#2A2E33"),
                              leftIndent=14, bulletIndent=0))
    styles.add(ParagraphStyle("TakeawayHeader", fontName="Helvetica-Bold",
                              fontSize=12, leading=15, textColor=colors.white))
    styles.add(ParagraphStyle("FooterText", fontName="Helvetica", fontSize=7.3,
                              leading=10, textColor=GREY, alignment=TA_CENTER))

    def kpi_card(value, label, value_color=NAVY):
        st = ParagraphStyle("kv", parent=styles["KpiValue"], textColor=value_color)
        t = Table([[Paragraph(value, st)], [Paragraph(label, styles["KpiLabel"])]],
                  colWidths=[1.55 * inch])
        t.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 9),
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
            ("BOX", (0, 0), (-1, -1), 0.6, LINE_GREY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return t

    def kpi_row(cards):
        row = Table([cards], colWidths=[1.62 * inch] * len(cards), hAlign="LEFT")
        row.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return row

    def divider():
        return HRFlowable(width="100%", thickness=0.75, color=LINE_GREY,
                          spaceBefore=10, spaceAfter=12)

    def takeaway_box(title, points, header_bg, body_bg, border):
        head = Table([[Paragraph(title, styles["TakeawayHeader"])]],
                     colWidths=[6.9 * inch])
        head.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), header_bg),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ]))
        flow = []
        for p in points:
            flow.append(Paragraph(f"&#8226;&nbsp;&nbsp;{p}", styles["TakeawayBullet"]))
            flow.append(Spacer(1, 5))
        body = Table([[f] for f in flow], colWidths=[6.9 * inch])
        body.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), body_bg),
            ("BOX", (0, 0), (-1, -1), 0.6, border),
            ("TOPPADDING", (0, 0), (-1, 0), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
        ]))
        return [head, body]

    exp_dt = datetime.strptime(a["expiry"], "%Y-%m-%d")
    week_ending = exp_dt.strftime("%m/%d/%Y")
    generated_on = datetime.now().strftime("%B %d, %Y")

    def draw_header_footer(canvas, doc):
        canvas.saveState()
        w, h = letter
        canvas.setFillColor(NAVY)
        canvas.rect(0, h - 1.15 * inch, w, 1.15 * inch, stroke=0, fill=1)
        canvas.setFillColor(GOLD)
        canvas.rect(0, h - 1.15 * inch, w, 0.045 * inch, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 16)
        canvas.drawString(0.75 * inch, h - 0.55 * inch,
                          "CSP Wheel Bot — Weekly Performance Report")
        canvas.setFont("Helvetica", 9.5)
        canvas.setFillColor(colors.HexColor("#C9D4E0"))
        canvas.drawString(0.75 * inch, h - 0.78 * inch,
                          "Cash-Secured Put Wheel Strategy  |  Automated Trade Tracker")
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(GOLD)
        canvas.drawRightString(w - 0.75 * inch, h - 0.55 * inch,
                               f"Week Ending {week_ending}")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#C9D4E0"))
        canvas.drawRightString(w - 0.75 * inch, h - 0.78 * inch,
                               f"Generated {generated_on}")
        canvas.setFillColor(GREY)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(0.75 * inch, 0.5 * inch,
                          "optionwheelpro.com  |  Data source: CSP Wheel Bot trade log")
        canvas.drawRightString(w - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
        canvas.setStrokeColor(LINE_GREY)
        canvas.setLineWidth(0.5)
        canvas.line(0.75 * inch, 0.68 * inch, w - 0.75 * inch, 0.68 * inch)
        canvas.restoreState()

    story = []
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph(
        "This report summarizes the performance of the automated cash-secured-put "
        "wheel strategy for the community: results for positions expiring this week, "
        "and a full-book view of every open and closed position tracked to date.",
        styles["Body"]))
    story.append(Spacer(1, 0.05 * inch))
    story.append(divider())

    # ---- Section 1: This Week
    title_date = exp_dt.strftime("%B %-d, %Y")
    story.append(Paragraph(
        f"1. This Week Summary  —  Expirations of {title_date}",
        styles["SectionHeader"]))
    n_week = len(a["week_w"]) + len(a["week_l"])
    story.append(Paragraph(
        f"{n_week} cash-secured put positions reached expiration this week. "
        "All results assume positions are closed at expiration (no assignment).",
        styles["Body"]))
    story.append(Spacer(1, 0.14 * inch))

    week_wr = a["week_win_rate"]
    net_color = GREEN if a["week_net"] >= 0 else RED
    story.append(kpi_row([
        kpi_card(str(n_week), "Positions Expired"),
        kpi_card(f"{len(a['week_w'])} / {len(a['week_l'])}", "Wins / Losses"),
        kpi_card(f"{week_wr:.1f}%", "Win Rate",
                 GREEN if week_wr >= a["win_rate"] else RED),
        kpi_card(f"{'+' if a['week_net'] >= 0 else ''}${a['week_net']:,.0f}",
                 "Net P&amp;L", net_color),
    ]))
    story.append(Spacer(1, 0.18 * inch))

    tbl = [["Ticker", "Strike", "Outcome", "P&L ($)", "Return %"]]
    week_closed = sorted(a["week_w"] + a["week_l"],
                         key=lambda r: -parse_money(r[COL_PNL]))
    for r in week_closed:
        tbl.append([r[COL_TICKER], r[COL_STRIKE], r[COL_OUTCOME].strip(),
                    r[COL_PNL], r[COL_RET]])
    t = Table(tbl, colWidths=[1.3 * inch, 1.15 * inch, 1.15 * inch,
                              1.35 * inch, 1.15 * inch])
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.8),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE_GREY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i, row in enumerate(tbl[1:], start=1):
        cmds.append(("TEXTCOLOR", (2, i), (3, i),
                     GREEN if row[2] == "WIN" else RED))
    t.setStyle(TableStyle(cmds))
    story.append(t)
    story.append(Spacer(1, 0.12 * inch))

    if a["week_l"]:
        lt = a["week_loss_tickers"]
        if len(lt) == 1:
            loss_note = (f"<b>Note:</b> all {len(a['week_l'])} losses this week were "
                         f"the same underlying — {lt[0]} — accounting for 100% of this "
                         f"week's losses (-${abs(a['week_loss_dollars']):,.0f} combined).")
        else:
            loss_note = (f"<b>Note:</b> this week's {len(a['week_l'])} losses came from "
                         f"{', '.join(lt)} (-${abs(a['week_loss_dollars']):,.0f} combined).")
        loss_note += (f" The {len(a['week_w'])} winning trades spanned "
                      f"{len(a['week_win_tickers'])} different tickers "
                      f"({', '.join(a['week_win_tickers'])}).")
        story.append(Paragraph(loss_note, styles["BodySmall"]))

    story.append(Spacer(1, 0.1 * inch))
    story.append(Image(f"{chart_dir}/win_rate_donuts.png",
                       width=5.9 * inch, height=2.87 * inch, hAlign="CENTER"))
    story.append(Spacer(1, 0.1 * inch))
    story.append(divider())

    # ---- Section 2: Overall Portfolio
    story.append(Paragraph("2. Overall Portfolio Summary", styles["SectionHeader"]))
    first_post = min(r[COL_POSTED].strip() for r in a["closed"] + a["pending"]
                     if r[COL_POSTED].strip())
    story.append(Paragraph(
        f"Since the bot began posting trades on {first_post}, it has generated "
        f"{a['total_trades']} total trade signals: {len(a['closed'])} have reached "
        f"a final closed outcome and {len(a['pending'])} remain open.",
        styles["Body"]))
    story.append(Spacer(1, 0.14 * inch))

    story.append(Paragraph("Open Positions", styles["SubHeader"]))
    story.append(kpi_row([
        kpi_card(str(len(a["pending"])), "Open Positions"),
        kpi_card(f"${a['open_prem']:,.0f}", "Premium Collected"),
        kpi_card(f"${a['open_collateral']/1e6:.2f}M", "Collateral Deployed"),
        kpi_card(f"{a['open_avg_dte']:.1f} days", "Avg. Days to Expiry"),
    ]))
    story.append(Spacer(1, 0.18 * inch))

    story.append(Paragraph("Closed Positions", styles["SubHeader"]))
    story.append(kpi_row([
        kpi_card(str(len(a["closed"])), "Closed Positions"),
        kpi_card(f"{len(a['wins'])} / {len(a['losses'])}", "Wins / Losses"),
        kpi_card(f"{a['win_rate']:.1f}%", "Win Rate", GREEN),
        kpi_card(f"{'+' if a['net_pnl'] >= 0 else ''}${a['net_pnl']:,.0f}",
                 "Net Realized P&amp;L", GREEN if a["net_pnl"] >= 0 else RED),
    ]))
    story.append(Spacer(1, 0.12 * inch))
    story.append(kpi_row([
        kpi_card(f"{a['avg_dte']:.1f} days", "Avg. Days to Close"),
        kpi_card(f"{a['avg_return']:.2f}%", "Avg. Return / Trade"),
        kpi_card(f"{a['capw_return']:.2f}%", "Capital-Wtd. Return"),
        kpi_card(f"~{a['annualized']:.0f}%", "Annualized Return",
                 GREEN if a["annualized"] >= 0 else RED),
    ]))
    story.append(Spacer(1, 0.14 * inch))

    story.append(Paragraph(
        "<b>Methodology note:</b> results assume every position that finishes "
        "in-the-money at expiration is closed out for the booked loss on expiry day "
        "— no shares are assigned or held afterward. Under this rule, realized "
        "P&amp;L equals the bot's own posted \"Outcome\" figures with no additional "
        "holding drag. The annualized figure is the <i>realized</i>, capital-weighted "
        "annualized return after actual losses — a more honest measure than the "
        "theoretical ARR posted at trade entry.",
        styles["BodySmall"]))

    story.append(Spacer(1, 0.05 * inch))
    story.append(divider())
    story.append(Image(f"{chart_dir}/cumulative_pnl.png",
                       width=6.3 * inch, height=3.07 * inch, hAlign="CENTER"))
    story.append(Spacer(1, 0.08 * inch))
    story.append(Image(f"{chart_dir}/pnl_by_ticker.png",
                       width=6.3 * inch, height=3.89 * inch, hAlign="CENTER"))

    story.append(PageBreak())

    # ---- Section 3: Key Takeaways (data-driven)
    story.append(Paragraph("3. Key Takeaways", styles["SectionHeader"]))

    good = [
        f"<b>Strong overall edge:</b> {a['win_rate']:.1f}% win rate across "
        f"{len(a['closed'])} closed trades with a profit factor of "
        f"{a['profit_factor']:.1f}x (${a['win_dollars']:,.0f} in wins vs. "
        f"${abs(a['loss_dollars']):,.0f} in losses).",
    ]
    if a["perfect"]:
        names = ", ".join(t for t, _ in a["perfect"][:6])
        n_perfect_trades = sum(v[0] for _, v in a["perfect"])
        good.append(
            f"<b>Core names are effectively flawless:</b> {names} have a "
            f"<b>0-loss record</b> across {n_perfect_trades} trades, contributing "
            f"roughly ${a['perfect_total']:,.0f} of the ${a['net_pnl']:,.0f} "
            f"total realized P&amp;L.")
    good.append(
        f"<b>Short, disciplined holding periods:</b> average {a['avg_dte']:.1f} days "
        f"to close, translating to a realized annualized return of roughly "
        f"{a['annualized']:.0f}% on deployed capital — closing (not holding through "
        f"assignment) at expiration avoids compounding further downside on losing names.")
    good.append(
        f"<b>Consistent premium generation:</b> ${a['open_prem']:,.0f} in premium "
        f"currently collected on {len(a['pending'])} open positions, keeping the "
        f"pipeline of future realized gains full.")

    bad = []
    if a["negative"]:
        wt, wv = a["negative"][0]
        open_ct = a["open_by_ticker"].get(wt, 0)
        pct_of_book = (wv[0] + open_ct) / a["total_trades"] * 100
        bad.append(
            f"<b>{wt} concentration:</b> {wv[0] + open_ct} of {a['total_trades']} "
            f"trades ({pct_of_book:.0f}%) with {open_ct} still open — yet it has a "
            f"net negative closed P&amp;L (-${abs(wv[2]):,.0f}, "
            f"{wv[1]}W/{wv[0] - wv[1]}L).")
    if a["week_l"] and len(a["week_loss_tickers"]) == 1:
        bad.append(
            f"<b>This week's losses were 100% {a['week_loss_tickers'][0]}:</b> all "
            f"{len(a['week_l'])} losing trades on the {title_date} expiration were "
            f"the same underlying — a concentration risk, not a broad strategy failure.")
    elif a["week_l"]:
        bad.append(
            f"<b>This week's losses:</b> {len(a['week_l'])} trades across "
            f"{', '.join(a['week_loss_tickers'])} for "
            f"-${abs(a['week_loss_dollars']):,.0f} combined.")
    if a["pending"]:
        pct_open = len(a["pending"]) / a["total_trades"] * 100
        bad.append(
            f"<b>{pct_open:.0f}% of the book is still unresolved:</b> "
            f"{len(a['pending'])} of {a['total_trades']} trades remain open, so the "
            f"headline {a['win_rate']:.0f}% win rate and ${a['net_pnl']:,.0f} P&amp;L "
            f"will move as those positions expire.")
    if not bad:
        bad.append("No notable weaknesses this cycle — all closed positions were "
                   "profitable and no single name is dragging the book.")

    story.extend(takeaway_box("&#10004;  WHAT'S WORKING", good,
                              GREEN, GREEN_BG, colors.HexColor("#BFE0CC")))
    story.append(Spacer(1, 0.16 * inch))
    story.extend(takeaway_box("&#10008;  WHAT'S NOT WORKING", bad,
                              RED, RED_BG, colors.HexColor("#EFC5B8")))

    story.append(Spacer(1, 0.18 * inch))
    story.append(Paragraph("Bottom Line", styles["SubHeader"]))
    if a["negative"]:
        wt = a["negative"][0][0]
        bottom = (
            f"The strategy is net profitable with a strong realized win rate and a "
            f"healthy annualized return once losses are cut cleanly at expiration. "
            f"The book's overall quality is being diluted, not destroyed, by repeated "
            f"allocation to {wt}. Tightening the selection filter — or capping "
            f"position size/frequency on high-IV, momentum-driven tickers — is the "
            f"single highest-leverage change available to improve results.")
    else:
        bottom = (
            "The strategy is net profitable with a strong realized win rate and a "
            "healthy annualized return. Maintain the current selection discipline "
            "and continue monitoring concentration as the book grows.")
    story.append(Paragraph(bottom, styles["Body"]))

    story.append(Spacer(1, 0.25 * inch))
    story.append(divider())
    story.append(Paragraph(
        "Disclaimer: This report is for informational and educational purposes only "
        "and does not constitute investment advice. Past performance of this automated "
        "strategy is not indicative of future results. Options trading involves "
        "substantial risk of loss and is not suitable for all investors.",
        styles["FooterText"]))

    doc = SimpleDocTemplate(
        str(out_path), pagesize=letter,
        topMargin=1.35 * inch, bottomMargin=0.85 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        title="CSP Wheel Bot — Weekly Performance Report",
        author="Option Wheel Pro")
    doc.build(story, onFirstPage=draw_header_footer, onLaterPages=draw_header_footer)


# -------------------------------------------------------------------- main ---

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expiry", help="Expiration date YYYY-MM-DD "
                    "(default: most recent past expiry with closed trades)")
    ap.add_argument("--out", default=DEFAULT_OUT_DIR,
                    help=f"Output directory (default: {DEFAULT_OUT_DIR})")
    args = ap.parse_args()

    print("Downloading trade tracker sheet...")
    _, data = load_trades()
    print(f"Loaded {len(data)} trade rows.")

    expiry = pick_expiry(data, args.expiry)
    print(f"Reporting on expiration: {expiry}")

    a = analyze(data, expiry)
    print(f"This week: {len(a['week_w'])}W/{len(a['week_l'])}L, "
          f"net ${a['week_net']:,.0f} | Overall: {len(a['wins'])}W/"
          f"{len(a['losses'])}L ({a['win_rate']:.1f}%), "
          f"net ${a['net_pnl']:,.0f}, {len(a['pending'])} open")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"CSP_Wheel_Bot_Weekly_Report_{expiry}.pdf"

    with tempfile.TemporaryDirectory() as chart_dir:
        make_charts(a, chart_dir)
        build_pdf(a, chart_dir, out_path)

    print(f"PDF written to {out_path}")


if __name__ == "__main__":
    main()
