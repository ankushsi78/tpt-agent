#!/usr/bin/env python3
"""
VIX-based target cash allocation + cash-to-deploy calculator.

Two modes:

  1. Target only — given the VIX level, print the sentiment band, the cash
     range, and the interpolated target cash % (position of VIX within its band):

         python3 vix_target.py --vix 14.53

  2. Full dashboard — also pass a JSON list of accounts (each with a name, NLV,
     and available_cash) to print the deployment table:

         python3 vix_target.py --vix 14.53 --accounts accounts.json
         cat accounts.json | python3 vix_target.py --vix 14.53 --accounts -

     accounts.json:
       [
         {"name": "Schwab (…9724, LIVE)", "nlv": 1193902, "available_cash": 296373.05},
         {"name": "RH Roth IRA (…9277)",  "nlv": 533817.25, "available_cash": 152924.45}
       ]

Interpolation model (why): the guide gives each VIX band a *range* of cash
(e.g. 12–15 → 30–40%). Higher VIX = more fear = be more invested = LESS cash,
so within a band cash scales linearly from the high-cash end (low VIX) to the
low-cash end (high VIX). This avoids a flat midpoint and reflects exactly where
VIX sits in its band.
"""

import sys
import json
import argparse

# Each band: (vix_low, vix_high, cash_at_low_vix, cash_at_high_vix, label)
# cash_at_low_vix is the cash % at the LOW-VIX edge (more greed → more cash),
# cash_at_high_vix at the HIGH-VIX edge (more fear → less cash).
# The two open-ended bands (≤12 and ≥30) use practical VIX anchors (10 and 35)
# so they can still interpolate; values are clamped outside those anchors.
BANDS = [
    (10.0, 12.0, 50.0, 40.0, "Extreme Greed"),
    (12.0, 15.0, 40.0, 30.0, "Greed"),
    (15.0, 20.0, 25.0, 20.0, "Slight Fear"),
    (20.0, 25.0, 15.0, 10.0, "Fear"),
    (25.0, 30.0, 10.0, 5.0, "Very Fearful"),
    (30.0, 35.0, 5.0, 0.0, "Extreme Fear"),
]

# The nominal ranges exactly as written in the guide (for display).
DISPLAY_RANGE = {
    "Extreme Greed": "40–50%",
    "Greed": "30–40%",
    "Slight Fear": "20–25%",
    "Fear": "10–15%",
    "Very Fearful": "5–10%",
    "Extreme Fear": "0–5%",
}


def target_for_vix(vix):
    """Return (label, display_range, interpolated_target_pct)."""
    # Clamp to the outer anchors so extreme readings resolve cleanly.
    if vix <= BANDS[0][0]:
        b = BANDS[0]
        return b[4], DISPLAY_RANGE[b[4]], b[2]          # very low VIX → max cash
    if vix >= BANDS[-1][1]:
        b = BANDS[-1]
        return b[4], DISPLAY_RANGE[b[4]], b[3]          # very high VIX → min cash

    for vlo, vhi, clo, chi, label in BANDS:
        # lower-bound inclusive; boundary VIX (e.g. 15.0) falls into the higher band
        if vlo <= vix < vhi:
            frac = (vix - vlo) / (vhi - vlo)
            target = clo + frac * (chi - clo)
            return label, DISPLAY_RANGE[label], target
    # Fallback (shouldn't hit): use last band's low edge
    b = BANDS[-1]
    return b[4], DISPLAY_RANGE[b[4]], b[2]


def _money(x):
    neg = x < 0
    s = f"${abs(x):,.0f}"
    return f"−{s}" if neg else s


def _deploy(x):
    # signed, with an explicit + for surplus (deployable) capital
    if x >= 0:
        return f"+${x:,.0f}"
    return f"−${abs(x):,.0f}"


def print_target(vix):
    label, rng, target = target_for_vix(vix)
    print(f"VIX: {vix:.2f}  |  Band: {label} ({rng} cash)  |  "
          f"Interpolated target cash: {target:.2f}%")
    return target


def print_table(vix, accounts):
    label, rng, target = target_for_vix(vix)
    tpct = target / 100.0

    print(f"**VIX: {vix:.2f} ({label}) | Target Cash Allocation: {target:.2f}%** "
          f"*(interpolated within the {rng} band)*\n")
    print(f"| Account | Total Value (NLV) | Current Cash | "
          f"Target Cash ({target:.2f}%) | Cash to Deploy |")
    print("|---|--:|--:|--:|--:|")

    tot_nlv = tot_avail = tot_target = 0.0
    for a in accounts:
        nlv = float(a["nlv"])
        avail = float(a["available_cash"])
        cur_pct = (avail / nlv * 100.0) if nlv else 0.0
        tgt = tpct * nlv
        deploy = avail - tgt
        tot_nlv += nlv; tot_avail += avail; tot_target += tgt
        cur = f"{cur_pct:.1f}%" if nlv else "—"
        print(f"| {a['name']} | {_money(nlv)} | {cur} | "
              f"{_money(tgt)} | **{_deploy(deploy)}** |")

    tot_cur = (tot_avail / tot_nlv * 100.0) if tot_nlv else 0.0
    tot_deploy = tot_avail - tot_target
    print(f"| **TOTAL** | **{_money(tot_nlv)}** | **{tot_cur:.1f}%** | "
          f"**{_money(tot_target)}** | **{_deploy(tot_deploy)}** |")


def main():
    ap = argparse.ArgumentParser(description="VIX target cash allocation calculator")
    ap.add_argument("--vix", type=float, required=True, help="Current VIX level")
    ap.add_argument("--accounts", help="Path to accounts JSON ('-' for stdin)")
    args = ap.parse_args()

    if not args.accounts:
        print_target(args.vix)
        return

    raw = sys.stdin.read() if args.accounts == "-" else open(args.accounts).read()
    accounts = json.loads(raw)
    print_table(args.vix, accounts)


if __name__ == "__main__":
    main()
