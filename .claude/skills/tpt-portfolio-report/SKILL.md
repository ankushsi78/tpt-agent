---
name: tpt-portfolio-report
description: Report all trades and P&L from the Tradier paper trading account. Use when the user asks for their TPT/Tradier portfolio, trade P&L, realized vs unrealized gains, account balance, or cash-secured-put collateral. Triggers include "show my trades", "portfolio report", "what's my P&L", "CSP collateral", "account status".
---

# TPT Portfolio Report

Pulls every trade from the Tradier paper trading account and reports per-trade
P&L, marking each as **realized** (closed) or **unrealized** (open), plus the
cash-secured-put collateral and an account snapshot.

## How to run

Run the bundled script from the skill directory:

```bash
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
  /Users/ankushsinghal/Documents/Trading/.claude/skills/tpt-portfolio-report/report.py
```

The script reads Tradier credentials from `Trading/.env`
(`TRADIER_TOKEN`, `TRADIER_ACCOUNT_ID`, `TRADIER_BASE_URL`) — nothing is
hardcoded, so it works as long as that file is present.

## Presenting the results

After running the script, present the output to the user as clean markdown:

1. **Realized (Closed)** table — Trade · Qty · Opened · Closed · P&L · Return
2. **Unrealized (Open)** table — Trade · Type · Qty · Opened · Entry · Current · P&L · Return
3. **CSP Collateral** table — CSP · Strike · Collateral (sorted largest first) + total
4. **Account Snapshot** — total equity, cash, option buying power, collateral locked, combined P&L

Use 🟢 for realized and 🔵 for unrealized section headers. Round currency to
cents and returns to one decimal. Bold the P&L figures.

## Optional: balance-over-time chart

If the user also asks for an equity curve / balance over time, extract the
daily equity from the bot log (`Trading/tpt_agent.log`) — each run logs a line
like `Account: equity=$X` — taking the last reading per calendar day (skip
`$0.00` abort lines). The Tradier sandbox does not expose a transaction-history
endpoint, so the log is the source for the daily series. Render it with the
visualization tool as a line chart vs a $100,000 starting-capital reference.

## Notes

- Short puts (qty < 0, type P) are CSPs; collateral = strike × 100 × contracts.
- Long calls (qty > 0, type C) are LEAPS and need no collateral.
- P&L sign convention: short put profits when price falls; long call profits
  when price rises. Tradier stores `cost_basis` as negative for shorts, so the
  script uses `abs(cost_basis)` for the per-share entry price.
