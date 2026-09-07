#!/usr/bin/env python3
"""
tastytrade portfolio report — READ ONLY.

Pulls the tastytrade account (balances + positions) and prints a categorized
snapshot: cash equities, short puts (CSPs) with collateral, short calls,
long calls (LEAPS), long puts, futures, and crypto, plus per-position
unrealized P&L and an account summary.

Places no orders. Reads credentials/session via tastytrade_client.py.

    python3 tastytrade_report.py            # text report
    python3 tastytrade_report.py --json     # machine-readable JSON (dashboards)
"""

import sys
import json
import asyncio
import datetime as dt
from collections import defaultdict

import tastytrade_client as tt


def parse_occ(symbol):
    """Parse an OCC option symbol like 'AAPL  260918P00230000'.
    The last 15 chars are date(6)+type(1)+strike(8); the rest is the root.
    Returns (underlying, expiry 'YYYY-MM-DD', 'P'/'C', strike float)."""
    tail = symbol[-15:]
    root = symbol[:-15].strip()
    yy, mm, dd = tail[0:2], tail[2:4], tail[4:6]
    pc = tail[6]
    strike = int(tail[7:]) / 1000.0
    expiry = f"20{yy}-{mm}-{dd}"
    return root, expiry, pc, strike


def _f(x):
    return float(x) if x is not None else 0.0


def classify(bal, positions):
    equities, futures, crypto = [], [], []
    short_puts, short_calls, long_calls, long_puts = [], [], [], []

    for p in positions:
        itype = str(p.instrument_type)
        is_short = str(p.quantity_direction).lower() == "short"
        sign = -1 if is_short else 1
        qty = _f(p.quantity)                       # magnitude
        mult = _f(p.multiplier) or 1.0
        open_px = _f(p.average_open_price)
        mark_px = _f(p.mark_price) if p.mark_price is not None else _f(p.close_price)

        # market value (signed) and unrealized P&L
        mkt = sign * mark_px * qty * mult
        # long: (mark-open); short: (open-mark)  -> both = (mark-open)*sign
        upl = (mark_px - open_px) * qty * mult * sign

        if itype == "Equity":
            equities.append({"symbol": p.symbol, "qty": sign * qty,
                             "avg": open_px, "mkt": mkt, "upl": upl})
        elif itype == "Cryptocurrency":
            crypto.append({"symbol": p.symbol, "qty": sign * qty, "mkt": mkt, "upl": upl})
        elif itype in ("Future",):
            futures.append({"symbol": p.symbol, "qty": sign * qty, "mkt": mkt, "upl": upl})
        elif itype in ("Equity Option", "Future Option"):
            root, expiry, pc, strike = parse_occ(p.symbol)
            rec = {"underlying": root, "expiry": expiry, "strike": strike,
                   "qty": sign * qty, "avg": open_px, "mkt": mkt, "upl": upl}
            if pc == "P" and is_short:
                rec["collateral"] = strike * 100 * qty
                short_puts.append(rec)
            elif pc == "C" and is_short:
                short_calls.append(rec)
            elif pc == "C":
                long_calls.append(rec)
            elif pc == "P":
                long_puts.append(rec)

    return {
        "bal": bal, "equities": equities, "futures": futures, "crypto": crypto,
        "short_puts": short_puts, "short_calls": short_calls,
        "long_calls": long_calls, "long_puts": long_puts,
    }


def _money(x):
    return f"${float(x):,.2f}"


def print_report(d, account):
    bal = d["bal"]
    print("=" * 64)
    print(f"  TASTYTRADE PORTFOLIO REPORT — ...{account.account_number[-4:]}")
    print("=" * 64)

    print("\nACCOUNT SNAPSHOT")
    print(f"  Net liquidation value : {_money(bal.net_liquidating_value)}")
    print(f"  Cash balance          : {_money(bal.cash_balance)}")
    print(f"  Equity buying power   : {_money(bal.equity_buying_power)}")
    print(f"  Derivative buying pwr : {_money(bal.derivative_buying_power)}")
    print(f"  Maint. requirement    : {_money(bal.maintenance_requirement)}")
    print(f"  Long equity value     : {_money(bal.long_equity_value)}")
    print(f"  Short deriv value     : {_money(bal.short_derivative_value)}")

    total_upl = 0.0

    if d["equities"]:
        print("\nEQUITIES / SHARES")
        print(f"  {'Symbol':<8}{'Qty':>8}{'Avg':>10}{'Mkt Value':>14}{'Unreal P&L':>14}")
        for e in sorted(d["equities"], key=lambda x: -x["mkt"]):
            total_upl += e["upl"]
            print(f"  {e['symbol']:<8}{e['qty']:>8.0f}{e['avg']:>10.2f}"
                  f"{_money(e['mkt']):>14}{_money(e['upl']):>14}")

    if d["short_puts"]:
        today = dt.date.today()
        print("\nSHORT PUTS (Cash-Secured Puts)")
        print(f"  {'Underlying':<10}{'Strike':>8}{'Exp':>12}{'Qty':>5}"
              f"{'Collateral':>12}{'Unreal P&L':>12}{'ROC%':>8}{'ARR':>9}")
        tot_coll = tot_upl_sp = 0.0
        for p in sorted(d["short_puts"], key=lambda x: x["expiry"]):
            total_upl += p["upl"]
            tot_coll += p["collateral"]; tot_upl_sp += p["upl"]
            dte = (dt.date.fromisoformat(p["expiry"]) - today).days
            if p["upl"] < 0 or dte <= 0:
                arr = "N/A"
            else:
                arr = f"{abs(p['mkt']) / p['collateral'] * 365 / dte * 100:.1f}%"
            print(f"  {p['underlying']:<10}{p['strike']:>8.1f}{p['expiry']:>12}"
                  f"{abs(p['qty']):>5.0f}{_money(p['collateral']):>12}"
                  f"{_money(p['upl']):>12}{p['upl']/p['collateral']*100:>7.2f}%{arr:>9}")
        print(f"  {'':<10}{'':>8}{'':>12}{'TOT':>5}{_money(tot_coll):>12}"
              f"{_money(tot_upl_sp):>12}")

    if d["short_calls"]:
        print("\nSHORT CALLS")
        print(f"  {'Underlying':<10}{'Strike':>8}{'Exp':>12}{'Qty':>5}{'Unreal P&L':>14}")
        for p in sorted(d["short_calls"], key=lambda x: (x["underlying"], x["expiry"])):
            total_upl += p["upl"]
            print(f"  {p['underlying']:<10}{p['strike']:>8.1f}{p['expiry']:>12}"
                  f"{abs(p['qty']):>5.0f}{_money(p['upl']):>14}")

    if d["long_calls"]:
        print("\nLONG CALLS (LEAPS / directional)")
        print(f"  {'Underlying':<10}{'Strike':>8}{'Exp':>12}{'Qty':>5}"
              f"{'Mkt Value':>14}{'Unreal P&L':>14}")
        for p in sorted(d["long_calls"], key=lambda x: -x["mkt"]):
            total_upl += p["upl"]
            print(f"  {p['underlying']:<10}{p['strike']:>8.1f}{p['expiry']:>12}"
                  f"{abs(p['qty']):>5.0f}{_money(p['mkt']):>14}{_money(p['upl']):>14}")

    if d["long_puts"]:
        print("\nLONG PUTS (hedges)")
        print(f"  {'Underlying':<10}{'Strike':>8}{'Exp':>12}{'Qty':>5}{'Unreal P&L':>14}")
        for p in sorted(d["long_puts"], key=lambda x: (x["underlying"], x["expiry"])):
            total_upl += p["upl"]
            print(f"  {p['underlying']:<10}{p['strike']:>8.1f}{p['expiry']:>12}"
                  f"{abs(p['qty']):>5.0f}{_money(p['upl']):>14}")

    if d["futures"]:
        print("\nFUTURES")
        for p in d["futures"]:
            total_upl += p["upl"]
            print(f"  {p['symbol']:<12}{p['qty']:>8.0f}{_money(p['mkt']):>16}{_money(p['upl']):>14}")

    if d["crypto"]:
        print("\nCRYPTO")
        for p in d["crypto"]:
            total_upl += p["upl"]
            print(f"  {p['symbol']:<12}{p['qty']:>14.6f}{_money(p['mkt']):>16}{_money(p['upl']):>14}")

    print("\n" + "-" * 64)
    print(f"  TOTAL UNREALIZED P&L (open positions): {_money(total_upl)}")
    print("-" * 64)


async def fetch():
    session = await tt.get_session()
    account = await tt.get_account(session)
    bal = await account.get_balances(session)
    positions = await account.get_positions(session, include_marks=True)
    return account, bal, positions


def _jsonable(d, account):
    out = {"account_number": account.account_number}
    bal = d["bal"]
    out["balances"] = {
        "net_liquidating_value": str(bal.net_liquidating_value),
        "cash_balance": str(bal.cash_balance),
        "equity_buying_power": str(bal.equity_buying_power),
        "derivative_buying_power": str(bal.derivative_buying_power),
        "maintenance_requirement": str(bal.maintenance_requirement),
    }
    for k in ("equities", "short_puts", "short_calls", "long_calls",
              "long_puts", "futures", "crypto"):
        out[k] = d[k]
    return out


if __name__ == "__main__":
    account, bal, positions = asyncio.run(fetch())
    data = classify(bal, positions)
    if "--json" in sys.argv:
        print(json.dumps(_jsonable(data, account), indent=2, default=str))
    else:
        print_report(data, account)
