#!/usr/bin/env python3
"""
Spread-aware Available Cash for a broker report (Schwab or tastytrade format).

Why: the base skill treats every short put as a full cash-secured put (strike ×
100 × qty) and every long call as a standalone LEAP (full market value). That
over-counts capital when the position is actually a *vertical spread*, because
the other leg caps the risk. This helper pairs the legs and charges only the
capital a defined-risk spread actually ties up:

  • Put credit spread  (short higher-strike put + long lower-strike put, same
    underlying & expiry)  -> capital = width × 100 × qty  (width = short − long)
  • Call debit spread   (long lower-strike call + short higher-strike call, same
    underlying & expiry)  -> capital = net mark = (long_mark − short_mark) × qty
  • Unpaired short put   -> full collateral (strike × 100 × qty)   [naked CSP]
  • Unpaired long call    -> full market value                     [plain LEAP]
  • Unpaired long put     -> full market value                     [standalone hedge]
  • Unpaired short call   -> 0 (covered call / diagonal against shares or LEAPs;
                              the base framework never charged these, so neither
                              do we — flagged in the breakdown for review)
  • Stock                 -> full market value

Available Cash = NLV − (put capital + call capital + long-put capital
                        + stock value).

Reads a report JSON on stdin (or a file path via --report), pairs the legs, and
prints ONE account object to stdout so it can be dropped straight into the
accounts array for vix_target.py:

    {"name": "...", "nlv": ..., "available_cash": ...}

The human-readable leg-pairing breakdown is written to STDERR so it can be shown
to the user without polluting the JSON on stdout.

Usage:
    tastytrade_report.py --json | spread_capital.py --broker tastytrade \
        --name "tastytrade (…4301)"
    schwab_report.py --json | spread_capital.py --broker schwab \
        --name "Schwab (…9724, LIVE)"

Field expectations (both report formats share these keys):
  balances.net_liquidating_value  OR  metrics.nlv   -> NLV
  equities[].mkt
  short_puts[]:  underlying, expiry, strike, qty, collateral
  long_puts[]:   underlying, expiry, strike, qty, mkt
  long_calls[]:  underlying, expiry, strike, qty, mkt
  short_calls[]: underlying, expiry, strike, qty, mkt
"""

import sys
import json
import argparse


def _nlv(data):
    if "metrics" in data and data["metrics"].get("nlv") is not None:
        return float(data["metrics"]["nlv"])
    if "balances" in data:
        b = data["balances"]
        for k in ("net_liquidating_value", "nlv"):
            if b.get(k) is not None:
                return float(b[k])
    raise SystemExit("spread_capital: could not find NLV in report JSON")


def _legs(data, key):
    out = []
    for p in data.get(key, []) or []:
        out.append(dict(
            u=p.get("underlying"),
            e=p.get("expiry"),
            k=float(p.get("strike", 0) or 0),
            q=abs(float(p.get("qty", 0) or 0)),
            mkt=float(p.get("mkt", 0) or 0),
            coll=float(p.get("collateral", 0) or 0),
        ))
    return out


def pair_put_credit(shorts, longs, det):
    """Long put (lower strike) covers short put (higher strike), same u+e.
    Paired -> width×100×qty. Unpaired short -> full strike collateral.
    Returns (put_capital, leftover_long_put_mkt)."""
    long_by = {}
    for p in longs:
        long_by.setdefault((p["u"], p["e"]), []).append(dict(p))
    cap = 0.0
    for p in sorted(shorts, key=lambda x: -x["k"]):   # cover highest strikes first
        rem = p["q"]
        for lg in sorted(long_by.get((p["u"], p["e"]), []), key=lambda x: -x["k"]):
            if lg["k"] >= p["k"] or lg["q"] <= 0:
                continue
            pair = min(rem, lg["q"])
            if pair <= 0:
                continue
            width = p["k"] - lg["k"]
            c = width * 100 * pair
            cap += c
            lg["mkt"] -= lg["mkt"] / max(lg["q"], 1) * pair  # consume proportional mkt
            lg["q"] -= pair
            rem -= pair
            det.append(f"  PUT SPREAD  {p['u']:6} {p['k']:.0f}/{lg['k']:.0f} x{pair:.0f}"
                       f"  width {width:.0f}  -> ${c:,.0f}")
            if rem <= 0:
                break
        if rem > 0:
            c = p["k"] * 100 * rem
            cap += c
            det.append(f"  NAKED PUT   {p['u']:6} {p['k']:.0f} x{rem:.0f}"
                       f"           -> ${c:,.0f}  (full collateral)")
    leftover = sum(lg["mkt"] for lgs in long_by.values() for lg in lgs if lg["q"] > 0)
    for lgs in long_by.values():
        for lg in lgs:
            if lg["q"] > 0:
                det.append(f"  LONG PUT    {lg['u']:6} {lg['k']:.0f} x{lg['q']:.0f}"
                           f"           -> ${lg['mkt']:,.0f}  (standalone hedge)")
    return cap, leftover


def pair_call_debit(longs, shorts, det):
    """Short call (higher strike) nets against long call (lower strike), same u+e.
    Paired -> (long_mark − short_mark) × qty. Unpaired long -> full mkt.
    Unpaired short call -> ignored (covered/diagonal), but flagged.
    Returns call_capital."""
    short_by = {}
    for p in shorts:
        short_by.setdefault((p["u"], p["e"]), []).append(dict(p, used=0.0))
    cap = 0.0
    for p in sorted(longs, key=lambda x: x["k"]):     # long low strike first
        rem = p["q"]
        long_per = p["mkt"] / p["q"] if p["q"] else 0.0
        net = 0.0
        for sc in short_by.get((p["u"], p["e"]), []):
            avail_short = sc["q"] - sc["used"]
            if sc["k"] <= p["k"] or avail_short <= 0:
                continue
            pair = min(rem, avail_short)
            short_per = abs(sc["mkt"]) / sc["q"] if sc["q"] else 0.0
            c = (long_per - short_per) * pair
            net += c
            sc["used"] += pair
            rem -= pair
            det.append(f"  CALL DEBIT  {p['u']:6} {p['k']:.0f}/{sc['k']:.0f} x{pair:.0f}"
                       f"  net(long-short) -> ${c:,.0f}")
            if rem <= 0:
                break
        if rem > 0:
            c = long_per * rem
            net += c
            det.append(f"  LONG CALL   {p['u']:6} {p['k']:.0f} x{rem:.0f}"
                       f"            -> ${c:,.0f}")
        cap += net
    for scs in short_by.values():
        for sc in scs:
            unused = sc["q"] - sc["used"]
            if unused > 0:
                det.append(f"  SHORT CALL  {sc['u']:6} {sc['k']:.0f} x{unused:.0f}"
                           f"           -> $0  (covered/diagonal — not charged)")
    return cap


def main():
    ap = argparse.ArgumentParser(description="Spread-aware Available Cash for a broker report")
    ap.add_argument("--broker", choices=["schwab", "tastytrade"], required=True)
    ap.add_argument("--name", required=True, help="Account label for the dashboard row")
    ap.add_argument("--report", help="Path to report JSON ('-' or omit for stdin)")
    args = ap.parse_args()

    raw = sys.stdin.read() if not args.report or args.report == "-" else open(args.report).read()
    data = json.loads(raw)

    nlv = _nlv(data)
    stock = sum(p["mkt"] for p in _legs(data, "equities"))
    det = [f"=== {args.name} [{args.broker}] ==="]

    put_cap, leftover_lp = pair_put_credit(_legs(data, "short_puts"),
                                           _legs(data, "long_puts"), det)
    call_cap = pair_call_debit(_legs(data, "long_calls"),
                               _legs(data, "short_calls"), det)

    capital = put_cap + call_cap + stock + leftover_lp
    avail = nlv - capital

    det.append(f"  stock ${stock:,.0f}")
    det.append(f"  -> put/spread ${put_cap:,.0f} + call/LEAP ${call_cap:,.0f}"
               f" + long-put hedges ${leftover_lp:,.0f} + stock ${stock:,.0f}"
               f" = ${capital:,.0f}")
    det.append(f"  NLV ${nlv:,.2f}   AVAILABLE CASH ${avail:,.2f}")
    print("\n".join(det), file=sys.stderr)

    json.dump({"name": args.name, "nlv": round(nlv, 2),
               "available_cash": round(avail, 2)}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
