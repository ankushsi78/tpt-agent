---
name: vix-cash-allocation
description: Build a cross-brokerage cash-deployment dashboard that sizes how much capital to put to work based on the current VIX. Pulls total value and available (uninvested) cash from every real brokerage account (Schwab, both Robinhood accounts, tastytrade), reads the live VIX, derives a target cash % by interpolating within the VIX band, and computes cash-to-deploy per account. Use this whenever the user asks how much cash they can deploy, what their cash allocation is versus the VIX, whether they're holding too much/too little cash, "run the VIX cash allocation", "how much dry powder do I have", "am I positioned for this VIX", or asks to size deployment across accounts. Trigger it even when the user only mentions "cash to deploy", "target cash", or "VIX allocation" without naming the skill.
---

# VIX Cash Allocation

Produces one dashboard answering: **given today's VIX, how much cash should I be
holding, and how much do I have free to deploy — per account and in total?**

Read-only. This skill never places, previews, or moves anything — it only reads
balances and prints an allocation table.

## The five steps (what the user's framework computes)

1. **Total portfolio value (NLV)** per account.
2. **Available Cash** = NLV − (capital tied up), where capital tied up = CSP
   collateral + LEAPS + stock value — **but vertical spreads are charged only the
   capital a defined-risk spread actually ties up, not full collateral**:
   - **Put credit spread** (short higher-strike put + long lower-strike put, same
     underlying & expiry) → capital = **width × 100 × qty** (width = short − long),
     *not* the short's full strike collateral.
   - **Call debit spread** (long lower-strike call + short higher-strike call, same
     underlying & expiry) → capital = **net mark = (long − short) × qty**, *not* the
     long call's full value as if it were a standalone LEAP.
   - Unpaired short put → full collateral (naked CSP). Unpaired long call → full
     value (plain LEAP). Unpaired short call → not charged (covered call / diagonal).

   This is the *uninvested* capital — cash not tied up as spread/put collateral,
   long options, or shares. It can be **negative** (account is over-deployed on
   margin) — report that honestly, don't floor it at zero. The bundled
   `spread_capital.py` helper does this pairing automatically (Step B).
3. **Current Cash %** = Available Cash ÷ NLV.
4. **Target Cash %** — from the VIX (see the band table below), interpolated by
   where VIX sits within its band.
5. **Cash to Deploy** = Available Cash − (Target Cash % × NLV). Positive = surplus
   cash available to put to work; negative = already at/above the invested target.

## Accounts in scope

Include every **real-money / real** brokerage account, sorted largest NLV first:

| Broker | Account | How to read it |
|---|---|---|
| Schwab | Margin …9724 (LIVE) | `schwab_report.py --json` |
| Robinhood | Roth IRA …9277 | Robinhood MCP |
| tastytrade | Individual …4301 | `tastytrade_report.py --json` |
| Robinhood | Long Term …0963 | Robinhood MCP |
| Robinhood | Agentic …8615 | Robinhood MCP (usually $0) |

**Exclude paper accounts** (Tradier, Alpaca) — they aren't real capital. Account
numbers drift over time; confirm the live set with `get_accounts` (Robinhood)
rather than hard-trusting the list above, and skip any deactivated account.

## Step A — Get the VIX

Robinhood MCP: `get_indexes` with `symbols="VIX"` to get the instrument id, then
`get_index_quotes` with that id. Use the returned `value`. Note its timestamp —
if the market is closed, say it's the last close. If the tool returns VIX under
`restricted`, relay that message and ask the user for the level instead.

## Step B — Get NLV + Available Cash per account

### Schwab and tastytrade — pipe the report through `spread_capital.py`
Both accounts run vertical spreads (Schwab: MU/DRAM call debit spreads, IREN put
spread; tastytrade: a book of put credit spreads). The helper pairs the legs by
underlying + expiry, charges spreads at width/net (per step 2), and emits a
ready-to-use account object (`{name, nlv, available_cash}`) on **stdout**, with a
line-by-line pairing breakdown on **stderr** (show that to the user). Run from the
Trading project root:

```bash
PY=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
SK=/Users/ankushsinghal/Documents/Trading/.claude/skills/vix-cash-allocation/scripts

# Schwab (LIVE, real money)
$PY /Users/ankushsinghal/Documents/Trading/schwab_report.py --json \
  | $PY $SK/spread_capital.py --broker schwab --name "Schwab (…9724, LIVE)"

# tastytrade
$PY /Users/ankushsinghal/Documents/Trading/tastytrade_report.py --json \
  | $PY $SK/spread_capital.py --broker tastytrade --name "tastytrade (…4301)"
```

Do **not** use Schwab's `metrics.cash_allocation` directly anymore — it counts
long-call LEAPs at full value and ignores the offsetting short calls, so it
over-states capital tied up on the MU/DRAM debit spreads. The helper is the source
of truth. (If the helper's unpaired-leg breakdown flags a put or call you expected
to be part of a spread, the legs may differ in expiry — check before trusting it.)

### Robinhood (both accounts) — decompose the pieces
For each account, `account_number` from `get_accounts`:

- **NLV** = `get_portfolio(account_number).total_value`
- **Stock value** = `get_portfolio(account_number).equity_value` (already the
  market value of shares — no need to re-quote)
- **CSP collateral** = for each **short put**: `strike × 100 × quantity`, summed.
  Get positions via `get_option_positions(account_number, nonzero=true)`, then
  `get_option_instruments(ids=...)` to read each contract's `type` and
  `strike_price`. **Only short PUTS count as CSP collateral.** Short *calls* are
  covered calls — their collateral is the underlying shares, already inside stock
  value, so do NOT add them.
- **LEAPS** = for each **long call**: `mark_price × 100 × quantity`, summed. Get
  marks from `get_option_quotes(instrument_ids=[...])` (`mark_price`). If long
  puts (hedges) exist, add their market value too and mention them — they tie up
  capital the same way.
- **Available Cash** = NLV − (CSP collateral + LEAPS + stock value).

**Spreads in a Robinhood account:** the RH accounts are usually plain CSPs +
covered calls + LEAPs, so the decomposition above is enough. But if one ever holds
a **long put whose underlying + expiry matches a short put** (put credit spread) or
a **short call above a long call, same expiry** (call debit spread), apply the same
step-2 spread rule by hand: charge the put spread `width × 100 × qty` (not full
collateral) and the call spread `(long − short) mark × qty` (not the full LEAP). No
helper for RH — it isn't fed by a report script.

Cross-check (optional sanity): for a cash/limited-margin account, Available Cash
should land near `get_portfolio().buying_power`. A large gap usually means a
short call was miscounted as a CSP, or a long put/spread pairing was missed.

Do the instrument/quote lookups in as few batched calls as possible (pass all
option ids for an account at once).

## Step C — Compute and render with the bundled script

Assemble a small JSON array (one entry per in-scope account, largest NLV first)
and pipe it to the calculator. Use the `spread_capital.py` output objects verbatim
for Schwab and tastytrade, and the decomposed figures for the Robinhood accounts.
The calculator owns the VIX→target interpolation and the table formatting so the
math is identical every run:

```bash
echo '[
  {"name": "Schwab (…9724, LIVE)", "nlv": 1193902, "available_cash": 296373.05},
  {"name": "RH Roth IRA (…9277)",  "nlv": 533817.25, "available_cash": 152924.45},
  {"name": "tastytrade (…4301)",   "nlv": 339139.97, "available_cash": 292387.47},
  {"name": "RH Long Term (…0963)", "nlv": 138167.28, "available_cash": -7151.49},
  {"name": "RH Agentic (…8615)",   "nlv": 0, "available_cash": 0}
]' | /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
  /Users/ankushsinghal/Documents/Trading/.claude/skills/vix-cash-allocation/scripts/vix_target.py \
  --vix 14.53 --accounts -
```
`--vix` alone (no `--accounts`) just prints the band + interpolated target, handy
for a quick check.

## The VIX → target cash guide (interpolation)

Higher VIX = more fear = be more invested = **hold less cash**. Within a band the
target scales linearly from the high-cash edge (low VIX) to the low-cash edge
(high VIX). The script encodes this; the bands are:

| VIX | Sentiment | Cash | Invested |
|---|---|---|---|
| ≤ 12 | Extreme Greed | 40–50% | 50–60% |
| 12–15 | Greed | 30–40% | 60–70% |
| 15–20 | Slight Fear | 20–25% | 75–80% |
| 20–25 | Fear | 10–15% | 85–90% |
| 25–30 | Very Fearful | 5–10% | 90–95% |
| ≥ 30 | Extreme Fear | 0–5% | 95–100% (add new cash to brokerage) |

Example: VIX 14.53 sits 84% up the 12–15 band → target = 40% − 0.84×(40−30) ≈
**31.57%**.

## Output — present exactly this

Lead with the script's markdown table (VIX + target header, then the per-account
rows and TOTAL). Keep the columns lean: **Account · Total Value (NLV) · Current
Cash · Target Cash · Cash to Deploy**. Then add a short read-out below it:

- **How to read Cash to Deploy**: positive = deployable surplus; negative = how
  far past the invested target the account already is.
- **Where the deployable cash actually sits.** Call out which account(s) hold the
  surplus. Add the critical caveat: **capital is not fungible across brokerages
  without a transfer**, so the practically deployable amount is the sum of the
  *positive* per-account figures, not the netted TOTAL (which lets one account's
  surplus mask another's deficit).
- Flag any account with **negative Available Cash** (over-deployed / on margin).
- One line noting the marks are as-of the quote timestamp (last close if the
  market is shut) and will move at the next open.

Only build a visual (visualize `show_widget`) if the user asks — the table is the
deliverable.

## Safety

Read-only across all four brokerages, one of which (Schwab) is real money. Never
place, preview, or transmit orders or transfers from this skill. If asked to
actually deploy the cash, hand back to the user / the per-broker order tooling —
this skill only sizes the opportunity.
