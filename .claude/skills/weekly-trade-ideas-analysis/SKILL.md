---
name: weekly-trade-ideas-analysis
description: Weekly Trade Ideas Analysis — settle the week's expired positions in the CSP Wheel Bot trade tracker Google Sheet (fill Stock @ Expiry from Current Price), analyze the results, and generate the community-shareable weekly performance PDF report. Use whenever the user asks for the weekly trade analysis, weekly wheel bot report, CSP bot performance summary, win/loss results for an expiration week, or to "run the weekly report". Also trigger for phrases like "analyze this week's expirations", "settle this week's trades", "how did the bot do this week", or "generate the community PDF".
---

# Weekly Trade Ideas Analysis

Analyzes the CSP Wheel Bot trade tracker (public Google Sheet) and produces a
polished multi-page PDF report for community sharing, covering:

1. **This Week Summary** — win/loss outcomes and net P&L for positions expiring
   in the requested week, with a per-trade table and win-rate donut charts.
2. **Overall Portfolio Summary** — open positions (count, premium collected,
   collateral, avg DTE) and closed positions (win rate, net realized P&L, avg
   days to close, avg return, capital-weighted annualized return), plus
   cumulative-P&L and per-ticker P&L charts.
3. **Key Takeaways** — data-driven "what's working / what's not working" boxes
   and a bottom-line assessment.

## How to run

Two bundled scripts, run in order.

**Step 1 — settle the week's expired positions.** This replicates the user's
manual step: for every row whose expiration has passed and whose
"Stock @ Expiry" (column N) is still empty, copy the live "Current Price"
(column R) into N as a plain value. The sheet's own formulas then compute
Outcome / P&L / Return. Only empty N cells are written; settled rows are never
touched, so re-running is safe.

```bash
python3 "/Users/ankushsinghal/Documents/Trading/.claude/skills/weekly-trade-ideas-analysis/settle_expiry.py"
```

Add `--dry-run` to preview, or `--expiry YYYY-MM-DD` to restrict to one date.
It authenticates with the service account JSON at
`/Users/ankushsinghal/Documents/Trading/csp-wheel-bot-e3194c27a5f7.json`
(same account `sheets_logger.py` uses). Heed its staleness warning: prices are
only accurate if run on/near expiry day — if it warns that rows expired more
than 5 days ago, tell the user those expiry prices may be off.

**Step 2 — generate the report.**

```bash
# Auto-detect the most recent past expiration with closed trades:
python3 "/Users/ankushsinghal/Documents/Trading/.claude/skills/weekly-trade-ideas-analysis/generate_report.py"

# Or report on a specific expiration date:
python3 "/Users/ankushsinghal/Documents/Trading/.claude/skills/weekly-trade-ideas-analysis/generate_report.py" --expiry 2026-07-02
```

If the user names a week/date (e.g. "the July 2nd expirations"), pass it as
`--expiry YYYY-MM-DD` to BOTH scripts. Otherwise let them auto-detect —
settle_expiry settles everything past due, and generate_report picks the most
recent expiration date on or before today that has closed (WIN/LOSS) outcomes.

The PDF is written to `/Users/ankushsinghal/Documents/Trading/reports/`
as `CSP_Wheel_Bot_Weekly_Report_<expiry>.pdf`. Override with `--out <dir>`.

Dependencies: `reportlab`, `matplotlib`, and `gspread` (already installed for
the default python3). If an import fails,
`python3 -m pip install reportlab matplotlib gspread`.

## Data source and methodology

- Sheet: https://docs.google.com/spreadsheets/d/1ABYAKLvMgoHbM2gccwrfFGYsP6U-Y0VYFnU9SFOPjVo/ (gid=0),
  downloaded via the CSV export endpoint — no auth needed, it's public.
- The script locates the header row starting with `Date Posted`; summary rows
  above it are skipped. If the script errors saying the header row wasn't
  found, the sheet layout changed — download the CSV manually and inspect it.
- **Methodology (important, agreed with the user):** every position is treated
  as closed at expiration. Wins expire worthless; losses are the sheet's booked
  P&L (buyback at intrinsic value on expiry day). The sheet's
  "Profit on Assigned" column (post-assignment share holding) is deliberately
  ignored — no assignment drag is modeled. Don't add it back in.

## Presenting the results

After the script finishes:

1. Verify the PDF rendered correctly — render a page or two to PNG (PyMuPDF
   `fitz` is installed) and view them, especially checking that chart labels
   don't overlap and no section spills awkwardly across pages.
2. Give the user a concise chat summary: this week's W/L, win rate, and net
   P&L; overall win rate and net realized P&L; and the top takeaway (which
   names are carrying the book, which name is dragging it).
3. Link the PDF path so they can open/share it.
