#!/usr/bin/env python3
"""
TPT Portfolio Report — pulls all trades from the Tradier paper account and
prints per-trade P&L (realized for closed, unrealized for open) plus the
cash-secured-put collateral summary.

Credentials are read from Trading/.env (TRADIER_TOKEN, TRADIER_ACCOUNT_ID,
TRADIER_BASE_URL) — nothing is hardcoded.
"""

import os
import re
import sys
import requests

# ── Load creds from .env (two dirs up: .claude/skills/<skill>/ → Trading/) ────
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
TRADING_DIR = os.path.abspath(os.path.join(SKILL_DIR, "..", "..", ".."))
ENV_PATH = os.path.join(TRADING_DIR, ".env")


def load_env():
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
TOKEN = os.getenv("TRADIER_TOKEN")
ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
BASE = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1")
HDR = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

if not TOKEN or not ACCOUNT_ID:
    sys.exit("ERROR: TRADIER_TOKEN / TRADIER_ACCOUNT_ID not found in .env")


def occ_pretty(sym: str) -> str:
    m = re.match(r"^([A-Z.]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$", sym)
    if not m:
        return sym
    t, yy, mm, dd, cp, k = m.groups()
    return f"{t} ${int(k)/1000:g}{cp} {mm}/{dd}/{yy}"


def occ_parts(sym: str):
    m = re.match(r"^([A-Z.]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$", sym)
    if not m:
        return None
    t, yy, mm, dd, cp, k = m.groups()
    return {"ticker": t, "type": cp, "strike": int(k) / 1000, "exp": f"{mm}/{dd}/{yy}"}


def get(path, params=None):
    return requests.get(f"{BASE}/{path}", headers=HDR, params=params, timeout=15).json()


# ── REALIZED (closed) ─────────────────────────────────────────────────────────
print("=" * 72)
print("REALIZED (CLOSED) TRADES")
print("=" * 72)
gl = get(f"accounts/{ACCOUNT_ID}/gainloss", {"limit": 500}).get("gainloss")
realized_total = 0.0
if not gl or gl == "null":
    print("  None")
else:
    items = gl.get("closed_position", [])
    if isinstance(items, dict):
        items = [items]
    for p in sorted(items, key=lambda x: x.get("close_date", "")):
        gain = float(p.get("gain_loss", 0) or 0)
        pct = float(p.get("gain_loss_percent", 0) or 0)
        realized_total += gain
        print(f"  {occ_pretty(p['symbol']):<24} qty={p.get('quantity')}  "
              f"open {p.get('open_date','')[:10]}  close {p.get('close_date','')[:10]}  "
              f"P&L=${gain:>9.2f} ({pct:>+6.1f}%)  [REALIZED]")
    print(f"\n  TOTAL REALIZED P&L: ${realized_total:,.2f}")

# ── UNREALIZED (open) ─────────────────────────────────────────────────────────
print("\n" + "=" * 72)
print("UNREALIZED (OPEN) POSITIONS")
print("=" * 72)
pos = get(f"accounts/{ACCOUNT_ID}/positions").get("positions")
unreal_total = 0.0
csp_collateral = 0.0
csp_rows = []
if not pos or pos == "null":
    print("  None")
    items = []
else:
    items = pos.get("position", [])
    if isinstance(items, dict):
        items = [items]
    syms = ",".join(p["symbol"] for p in items)
    quotes = get("markets/quotes", {"symbols": syms, "greeks": "false"}).get("quotes", {}).get("quote", [])
    if isinstance(quotes, dict):
        quotes = [quotes]
    price_map = {}
    for q in quotes:
        bid = float(q.get("bid", 0) or 0)
        ask = float(q.get("ask", 0) or 0)
        last = float(q.get("last", 0) or 0)
        price_map[q.get("symbol")] = (bid + ask) / 2 if (bid > 0 and ask > 0) else last
    for p in sorted(items, key=lambda x: x["symbol"]):
        sym = p["symbol"]
        qty = float(p["quantity"])
        avg = abs(float(p["cost_basis"])) / (abs(qty) * 100) if qty else 0
        cur = price_map.get(sym, avg)
        pnl = (avg - cur) * abs(qty) * 100 if qty < 0 else (cur - avg) * qty * 100
        pct = (pnl / (avg * abs(qty) * 100) * 100) if avg > 0 else 0
        unreal_total += pnl
        info = occ_parts(sym) or {}
        kind = "CSP" if (info.get("type") == "P" and qty < 0) else ("LEAPS" if info.get("type") == "C" and qty > 0 else "OPT")
        print(f"  {occ_pretty(sym):<24} {kind:<6} qty={qty:>3.0f}  "
              f"acq {p.get('date_acquired','')[:10]}  entry=${avg:>6.2f} cur=${cur:>6.2f}  "
              f"P&L=${pnl:>9.2f} ({pct:>+6.1f}%)  [UNREALIZED]")
        if kind == "CSP":
            coll = info["strike"] * 100 * abs(qty)
            csp_collateral += coll
            csp_rows.append((occ_pretty(sym), int(qty), info["strike"], coll))
    print(f"\n  TOTAL UNREALIZED P&L: ${unreal_total:,.2f}")

# ── CSP COLLATERAL ────────────────────────────────────────────────────────────
print("\n" + "=" * 72)
print("CASH-SECURED-PUT COLLATERAL")
print("=" * 72)
if not csp_rows:
    print("  No open CSPs")
else:
    for name, qty, strike, coll in sorted(csp_rows, key=lambda x: -x[3]):
        print(f"  {name:<24} qty={qty:>3}  strike=${strike:<7g}  collateral=${coll:>11,.0f}")
    print(f"\n  TOTAL CSP COLLATERAL: ${csp_collateral:,.0f}")

# ── ACCOUNT SNAPSHOT ──────────────────────────────────────────────────────────
bal = get(f"accounts/{ACCOUNT_ID}/balances").get("balances", {})
equity = float(bal.get("total_equity", 0) or 0)
cash = float(bal.get("total_cash", 0) or 0)
sub = bal.get("margin") or bal.get("pdt") or bal.get("cash") or {}
obp = float(sub.get("option_buying_power", cash) or cash)

print("\n" + "=" * 72)
print("ACCOUNT SNAPSHOT")
print("=" * 72)
print(f"  Total equity:          ${equity:,.2f}")
print(f"  Cash on hand:          ${cash:,.2f}")
print(f"  Option buying power:   ${obp:,.2f}")
print(f"  CSP collateral locked: ${csp_collateral:,.0f}")
print(f"\n  Realized + Unrealized P&L: ${realized_total + unreal_total:,.2f}")
print("=" * 72)
