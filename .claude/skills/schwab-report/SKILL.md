---
name: schwab-report
description: Generate a read-only portfolio report and 7-metric dashboard for the LIVE Charles Schwab brokerage account. Use when the user asks for their Schwab portfolio, Schwab account status, net liquidation value, cash allocation, balance growth / realized gains (YTD or MTD), or allocation/concentration by ticker. Triggers include "Schwab report", "show my Schwab portfolio", "what's my NLV", "Schwab allocation", "am I over-concentrated", "Schwab realized gains".
---

# Schwab Portfolio Report

Pulls the **live** Schwab account (real money — Margin ...9724) read-only and
produces a categorized position report plus a 7-metric dashboard. Places no
orders and moves no money.

## Data source & limits (read first)

- Auth/positions come from `schwab_client.py` (schwab-py + cached OAuth token
  `schwab_token.json`). If the token is stale (~7 days), the run fails — tell
  the user to run `python3 schwab_login.py` in their terminal (it opens a
  browser; only they can log in).
- The Schwab **Trader API has no historical-balance and no realized-gain
  endpoint**, and transaction history only reaches back ~9 months. So
  beginning-of-year / beginning-of-month NLV and the **official realized YTD
  gain** are read from `schwab_anchors.json`, which the user maintains from
  Schwab statements + the Realized G/L report. NEVER reconstruct realized YTD
  from transactions — it overstates (older lots truncated). Realized MTD is
  reconstructed live (recent positions only) and is labeled preliminary.

## How to run

Both from the Trading project root:

```bash
# Text report: positions by category + the 7 dashboard metrics
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
  /Users/ankushsinghal/Documents/Trading/schwab_report.py

# Same data as JSON (positions + a "metrics" object) for the dashboard widget
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
  /Users/ankushsinghal/Documents/Trading/schwab_report.py --json
```

## The 7 metrics

1. **Net liquidation value** — `metrics.nlv`
2. **Cash allocation** — `metrics.cash_allocation` / `cash_allocation_pct`
   (= NLV − [CSP collateral + stock value + long option value])
3. **Balance growth YTD** — `metrics.growth_ytd` / `growth_ytd_pct`
   (vs beginning-of-year NLV; MTD variant also available)
4. **Realized gain YTD** — `metrics.realized_ytd` / `realized_ytd_pct_boy`
   (Schwab official, % of beginning-of-year balance)
5. **Realized gain MTD** — `metrics.realized_mtd` / `realized_mtd_pct_bom`
   (reconstructed, preliminary — note today's expirations may be unsettled)
6. **Allocation by ticker** — `metrics.allocation[]` (`ticker`, `value`, `pct`,
   `flag`); includes CSP collateral + long options + stock shares
7. **Concentration flag** — any ticker with `flag: true` (pct > `flag_pct`,
   default 10% of NLV)

## Presenting the results

Produce BOTH a markdown summary AND the visual dashboard.

### A. Markdown tables (from the text output)

1. **Account snapshot** — NLV, money-market reserve, cash balance, long market
   value, short option value, buying power, total unrealized P&L.
2. **Short puts / CSP collateral** — Underlying · Strike · Expiry · Qty ·
   Collateral · Unreal P&L · P&L%prem (P&L / premium collected) · ROC%
   (P&L / collateral) · ARR (remaining annualized return if held to expiry =
   |mkt| / collateral × 365/DTE; "N/A" when the position is in a loss or
   expires today). Sorted best→worst P&L%prem, with a TOTAL row.
3. **Long calls (LEAPS) / short calls / long puts / equities** as needed —
   highlight the biggest unrealized winners and losers.
4. **Allocation by ticker** — Ticker · $ · % of NLV, largest first, with 🚩 on
   any row where `flag` is true.

Use 🟢/🔴 for positive/negative P&L. Round currency to cents (dollars in
summaries), percentages to 1–2 decimals.

### B. Visual dashboard (use the visualize show_widget tool)

One widget:

0. **Realized MTD gains + target meter** (top, full width): realized gain MTD
   ($ and % of BoM) with a horizontal progress meter toward the monthly target
   (`metrics.monthly_target_pct`, default 4% of BoM). Fill = realized MTD % /
   target %; label "N% of 4% monthly target" and the target dollar
   (target% × BoM NLV). Always note it's preliminary early in the month while
   that week's expirations are unsettled. NOTE: the meter/MTD gain here is
   REALIZED gains, not balance growth.
1. **Four metric cards**: NLV; cash allocation ($ + %); balance growth YTD
   (green/red); realized gain YTD ($ + % of BoY, green/red).
2. **Horizontal bar chart** — allocation by ticker as % of NLV (top ~16–20
   rows). Bars over the flag threshold in red (`#e34948`), the rest blue
   (`#2a78d6`); a dashed red reference line at the flag % labeled "10% limit";
   tooltip shows `% · $value`. Include a small "N over 10% limit" note.

Keep all explanatory prose OUTSIDE the widget (in the chat response).

Below the widget, restate the key flags in one or two lines: which ticker(s)
breached the concentration limit, and the realized-vs-growth story (realized
YTD can exceed NLV growth when open positions carry unrealized drawdown).

## Monthly maintenance to remind the user about

At the start of each month, update `schwab_anchors.json`:
- `beginning_of_month.nlv` → the new month's opening NLV (from the prior
  month-end statement), and `beginning_of_month.date`.
- `realized_ytd` → refresh from Schwab's Realized G/L report (Accounts >
  History > Realized G/L, Current year, include option contracts).

## Safety

Read-only. This is a real-money account — never place, preview, or transmit
orders from this skill. Order tooling lives in `schwab_client.py` and is
dry-run gated separately.
