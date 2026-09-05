#!/usr/bin/env python3
"""
Schwab portfolio report — READ ONLY.

Pulls the Schwab account (accounts, positions, balances) and prints a
categorized snapshot: cash equities, short puts (CSPs) with collateral,
short calls, long calls (LEAPS), long puts, and money-market/mutual funds,
plus per-position unrealized P&L and an account summary.

Places no orders. Reads credentials/token via schwab_client.py.

    python3 schwab_report.py            # text report
    python3 schwab_report.py --json     # machine-readable JSON (for dashboards)
"""

import os
import sys
import json
import datetime as dt
from collections import defaultdict
import schwab_client as s

ANCHORS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "schwab_anchors.json")


def parse_occ(symbol):
    """Parse an OCC option symbol like 'CRDO  260918P00230000'.
    Returns (underlying, expiry 'YYYY-MM-DD', 'P'/'C', strike float)."""
    root = symbol[:6].strip()
    tail = symbol[6:]
    yy, mm, dd = tail[0:2], tail[2:4], tail[4:6]
    pc = tail[6]
    strike = int(tail[7:]) / 1000.0
    expiry = f"20{yy}-{mm}-{dd}"
    return root, expiry, pc, strike


def fetch():
    c = s.get_client()
    h = s.get_account_hash(c)
    r = c.get_account(h, fields=c.Account.Fields.POSITIONS)
    r.raise_for_status()
    return r.json()["securitiesAccount"]


def classify(acct):
    bal = acct.get("currentBalances", {})
    positions = acct.get("positions", [])

    equities, mmf = [], []
    short_puts, short_calls, long_calls, long_puts = [], [], [], []

    for p in positions:
        inst = p["instrument"]
        atype = inst.get("assetType")
        lq = p.get("longQuantity", 0.0)
        sq = p.get("shortQuantity", 0.0)
        mv = p.get("marketValue", 0.0)
        # unrealized P&L: shorts use shortOpenProfitLoss, longs longOpenProfitLoss
        upl = p.get("shortOpenProfitLoss") if sq else p.get("longOpenProfitLoss", 0.0)
        upl = upl or 0.0

        if atype == "EQUITY":
            equities.append({
                "symbol": inst["symbol"], "qty": lq - sq,
                "avg": p.get("averagePrice", 0.0), "mkt": mv, "upl": upl,
            })
        elif atype in ("MUTUAL_FUND", "CASH_EQUIVALENT"):
            mmf.append({"symbol": inst["symbol"], "qty": lq - sq, "mkt": mv})
        elif atype == "OPTION":
            root, expiry, pc, strike = parse_occ(inst["symbol"])
            rec = {
                "underlying": root, "expiry": expiry, "strike": strike,
                "qty": (lq - sq), "avg": p.get("averagePrice", 0.0),
                "mkt": mv, "upl": upl, "desc": inst.get("description", ""),
            }
            if pc == "P" and sq:
                rec["collateral"] = strike * 100 * sq
                short_puts.append(rec)
            elif pc == "C" and sq:
                short_calls.append(rec)
            elif pc == "C" and lq:
                long_calls.append(rec)
            elif pc == "P" and lq:
                long_puts.append(rec)

    return {
        "balances": bal, "equities": equities, "mmf": mmf,
        "short_puts": short_puts, "short_calls": short_calls,
        "long_calls": long_calls, "long_puts": long_puts,
        "account_number": acct.get("accountNumber", ""),
        "type": acct.get("type", ""),
    }


def _money(x):
    return f"${x:,.2f}"


def print_report(d):
    bal = d["balances"]
    print("=" * 64)
    print(f"  SCHWAB PORTFOLIO REPORT — {d['type']} ...{d['account_number'][-4:]}")
    print("=" * 64)

    liq = bal.get("liquidationValue", 0.0)
    print("\nACCOUNT SNAPSHOT")
    print(f"  Liquidation value : {_money(liq)}")
    print(f"  Cash balance      : {_money(bal.get('cashBalance', 0))}")
    print(f"  Money mkt fund    : {_money(bal.get('moneyMarketFund', 0))}")
    print(f"  Buying power      : {_money(bal.get('buyingPower', 0))}")
    print(f"  Available funds   : {_money(bal.get('availableFunds', 0))}")
    print(f"  Maint. requirement: {_money(bal.get('maintenanceRequirement', 0))}")
    print(f"  Long mkt value    : {_money(bal.get('longMarketValue', 0))}")
    print(f"  Short opt value   : {_money(bal.get('shortOptionMarketValue', 0))}")

    total_upl = 0.0

    if d["equities"]:
        print("\nEQUITIES / SHARES")
        print(f"  {'Symbol':<8}{'Qty':>8}{'Avg':>10}{'Mkt Value':>14}{'Unreal P&L':>14}")
        for e in sorted(d["equities"], key=lambda x: -x["mkt"]):
            total_upl += e["upl"]
            print(f"  {e['symbol']:<8}{e['qty']:>8.0f}{e['avg']:>10.2f}"
                  f"{_money(e['mkt']):>14}{_money(e['upl']):>14}")

    if d["short_puts"]:
        print("\nSHORT PUTS (Cash-Secured Puts)")
        print(f"  {'Underlying':<10}{'Strike':>8}{'Exp':>12}{'Qty':>5}"
              f"{'Collateral':>14}{'Unreal P&L':>14}")
        tot_coll = 0.0
        for p in sorted(d["short_puts"], key=lambda x: -x["collateral"]):
            total_upl += p["upl"]; tot_coll += p["collateral"]
            print(f"  {p['underlying']:<10}{p['strike']:>8.1f}{p['expiry']:>12}"
                  f"{abs(p['qty']):>5.0f}{_money(p['collateral']):>14}"
                  f"{_money(p['upl']):>14}")
        print(f"  {'':<10}{'':>8}{'':>12}{'TOTAL':>5}{_money(tot_coll):>14}")

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

    if d["mmf"]:
        print("\nMONEY MARKET / MUTUAL FUNDS")
        for m in d["mmf"]:
            print(f"  {m['symbol']:<8}{m['qty']:>14,.2f}{_money(m['mkt']):>16}")

    print("\n" + "-" * 64)
    print(f"  TOTAL UNREALIZED P&L (open positions): {_money(total_upl)}")
    print("-" * 64)


def load_anchors():
    with open(ANCHORS_PATH) as f:
        return json.load(f)


def compute_metrics(d, anchors):
    """Compute the 7 dashboard metrics from positions + anchor balances."""
    nlv = d["balances"]["liquidationValue"]

    csp_coll = sum(p["collateral"] for p in d["short_puts"])
    long_eq = sum(e["mkt"] for e in d["equities"])
    long_opt = sum(p["mkt"] for p in d["long_calls"]) + \
        sum(p["mkt"] for p in d["long_puts"])
    committed = csp_coll + long_eq + long_opt
    cash_alloc = nlv - committed

    # allocation by ticker: CSP collateral + long options + stock shares
    alloc = defaultdict(float)
    for p in d["short_puts"]:
        alloc[p["underlying"]] += p["collateral"]
    for p in d["long_calls"] + d["long_puts"]:
        alloc[p["underlying"]] += p["mkt"]
    for e in d["equities"]:
        alloc[e["symbol"]] += e["mkt"]
    flag_pct = anchors.get("concentration_flag_pct", 10.0)
    alloc_rows = sorted(
        ({"ticker": t, "value": v, "pct": v / nlv * 100,
          "flag": (v / nlv * 100) > flag_pct} for t, v in alloc.items()),
        key=lambda x: -x["value"])

    boy = anchors["beginning_of_year"]["nlv"]
    bom = anchors["beginning_of_month"]["nlv"]
    rz = anchors["realized_ytd"]["net_gain"]

    return {
        "nlv": nlv,
        "cash_allocation": cash_alloc,
        "cash_allocation_pct": cash_alloc / nlv * 100,
        "committed": committed,
        "growth_ytd": nlv - boy,
        "growth_ytd_pct": (nlv - boy) / boy * 100,
        "growth_mtd": nlv - bom,
        "growth_mtd_pct": (nlv - bom) / bom * 100,
        "realized_ytd": rz,
        "realized_ytd_pct_boy": rz / boy * 100,
        "realized_mtd": reconstruct_realized_mtd(),
        "realized_mtd_pct_bom": reconstruct_realized_mtd() / bom * 100,
        "allocation": alloc_rows,
        "flag_pct": flag_pct,
    }


def reconstruct_realized_mtd():
    """Month-to-date realized P&L from closed positions (cash-flow method).

    Reliable for the current month only (recent positions are within the
    ~1yr transaction history). YTD is NOT reconstructed here — it comes from
    Schwab's official report via schwab_anchors.json, because older lots are
    truncated by the API's limited history.
    """
    c = s.get_client()
    h = s.get_account_hash(c)
    today = dt.datetime.now()
    som = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # pull a wider window so positions opened earlier but closed this month
    # still have their opening leg captured
    start = som - dt.timedelta(days=120)
    r = c.get_transactions(h, start_date=start, end_date=today)
    r.raise_for_status()
    include = {"TRADE", "RECEIVE_AND_DELIVER"}

    def secqty(t):
        q = 0.0
        for it in t.get("transferItems", []):
            if it.get("instrument", {}).get("assetType") in ("EQUITY", "OPTION"):
                q += it.get("amount", 0.0)
        return q

    pos = defaultdict(lambda: {"net": 0.0, "qty": 0.0, "last": None})
    for t in r.json():
        pid = t.get("positionId")
        if pid is None or t["type"] not in include:
            continue
        p = pos[pid]
        p["net"] += t.get("netAmount", 0.0)
        p["qty"] += secqty(t)
        dte = t["tradeDate"][:10]
        p["last"] = max(p["last"], dte) if p["last"] else dte
    som_str = som.strftime("%Y-%m-%d")
    return sum(p["net"] for p in pos.values()
               if abs(p["qty"]) < 1e-6 and p["last"] and p["last"] >= som_str)


def print_metrics(m, anchors):
    print("\n" + "=" * 64)
    print("  DASHBOARD METRICS")
    print("=" * 64)
    print(f"  1. Net liquidation value : {_money(m['nlv'])}")
    print(f"  2. Cash allocation       : {_money(m['cash_allocation'])}"
          f"  ({m['cash_allocation_pct']:.1f}%)")
    print(f"  3. Balance growth YTD    : {_money(m['growth_ytd'])}"
          f"  ({m['growth_ytd_pct']:+.2f}%)")
    print(f"     Balance growth MTD    : {_money(m['growth_mtd'])}"
          f"  ({m['growth_mtd_pct']:+.2f}%)")
    print(f"  4. Realized gain YTD     : {_money(m['realized_ytd'])}"
          f"  ({m['realized_ytd_pct_boy']:+.2f}% of BoY)  [Schwab official]")
    print(f"  5. Realized gain MTD     : {_money(m['realized_mtd'])}"
          f"  ({m['realized_mtd_pct_bom']:+.2f}% of BoM)  [preliminary]")
    print(f"  6/7. Allocation by ticker (>{m['flag_pct']:.0f}% flagged):")
    for a in m["allocation"]:
        flag = "  <<< FLAG" if a["flag"] else ""
        print(f"        {a['ticker']:<7}{_money(a['value']):>14}"
              f"{a['pct']:>7.1f}%{flag}")


if __name__ == "__main__":
    acct = fetch()
    data = classify(acct)
    anchors = load_anchors()
    if "--json" in sys.argv:
        out = dict(data)
        out["metrics"] = compute_metrics(data, anchors)
        print(json.dumps(out, indent=2, default=str))
    else:
        print_report(data)
        print_metrics(compute_metrics(data, anchors), anchors)
