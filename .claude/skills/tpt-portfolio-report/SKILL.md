---
name: tpt-portfolio-report
description: Report all trades and P&L from the Tradier paper trading account. Use when the user asks for their TPT/Tradier portfolio, trade P&L, realized vs unrealized gains, account balance, or cash-secured-put collateral. Triggers include "show my trades", "portfolio report", "what's my P&L", "CSP collateral", "account status".
---

# TPT Portfolio Report

Pulls every trade from the Tradier paper trading account and reports per-trade
P&L, marking each as **realized** (closed) or **unrealized** (open), plus the
cash-secured-put collateral and an account snapshot.

## How to run

Run BOTH bundled scripts from the skill directory:

```bash
# 1. Per-trade P&L + collateral + account snapshot (text)
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
  /Users/ankushsinghal/Documents/Trading/.claude/skills/tpt-portfolio-report/report.py

# 2. Daily equity series for the dashboard chart (JSON)
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
  /Users/ankushsinghal/Documents/Trading/.claude/skills/tpt-portfolio-report/equity_series.py
```

Both scripts read Tradier credentials from `Trading/.env`
(`TRADIER_TOKEN`, `TRADIER_ACCOUNT_ID`, `TRADIER_BASE_URL`) — nothing is
hardcoded, so they work as long as that file is present.

## Presenting the results

Always produce BOTH the markdown tables AND the visual dashboard.

### A. Markdown tables (from report.py output)

1. **Realized (Closed)** table — Trade · Qty · Opened · Closed · P&L · Return
2. **Unrealized (Open)** table — Trade · Type · Qty · Opened · Entry · Current · P&L · Return
3. **CSP Collateral** table — CSP · Strike · Collateral (sorted largest first) + total
4. **Account Snapshot** — total equity, cash, option buying power, collateral locked, combined P&L

Use 🟢 for realized and 🔵 for unrealized section headers. Round currency to
cents and returns to one decimal. Bold the P&L figures.

### B. Visual dashboard (always include — use the visualize show_widget tool)

Feed `equity_series.py`'s JSON into a single widget containing:

1. **Three metric cards** across the top:
   - Starting capital → `starting_capital` (e.g. $100,000)
   - Current equity → `current_equity`
   - Total return → `total_return_pct` (color green if ≥ 0 via `--color-text-success`, red `--color-text-danger` if < 0)
2. **Line chart** of the daily equity curve (`points[].date` / `points[].value`)
   with a dashed reference line at `starting_capital`. Use Chart.js (per the
   visualize chart guidance): green line `#1D9E75` with light fill when the
   curve is net positive, red `#E24B4A` when net negative; dashed gray
   reference line; y-axis padded ~$1k beyond the data range; `autoSkip:false`
   x-axis labels; tooltip formats as `$xx,xxx.xx`.
3. A small **legend** (Account equity / Starting capital) below the chart.

Then below the widget, restate the Summary (Realized / Unrealized / Combined)
as a short markdown table and a one-line "equity went $X → $Y (±Z%)" sentence.

Keep all explanatory prose OUTSIDE the widget (in the chat response) — the
widget holds only the metric cards + chart + legend.

## Notes

- Short puts (qty < 0, type P) are CSPs; collateral = strike × 100 × contracts.
- Long calls (qty > 0, type C) are LEAPS and need no collateral.
- P&L sign convention: short put profits when price falls; long call profits
  when price rises. Tradier stores `cost_basis` as negative for shorts, so the
  script uses `abs(cost_basis)` for the per-share entry price.
