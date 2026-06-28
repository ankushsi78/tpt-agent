#!/usr/bin/env python3
"""
Emit the daily account-equity series for the TPT portfolio dashboard chart.

Source: the bot log (Trading/tpt_agent.log) logs "Account: equity=$X" on every
run — we take the LAST valid reading per calendar day (skipping $0.00 abort
lines). The live equity from the Tradier balances API is appended as today's
point so the curve always ends on the current value.

Prints JSON: {starting_capital, current_equity, total_return_pct, points:[{date,value}]}
"""

import os
import re
import json
import requests
from collections import OrderedDict

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
TRADING_DIR = os.path.abspath(os.path.join(SKILL_DIR, "..", "..", ".."))
LOG_PATH = os.path.join(TRADING_DIR, "tpt_agent.log")
ENV_PATH = os.path.join(TRADING_DIR, ".env")

STARTING_CAPITAL = float(os.getenv("STARTING_CAPITAL", "100000"))


def load_env():
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def month_day(iso: str) -> str:
    y, m, d = iso.split("-")
    months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{months[int(m)]} {int(d)}"


# ── Daily equity from the log (last valid reading per day) ────────────────────
day_equity = OrderedDict()
pat = re.compile(r"^(\d{4}-\d{2}-\d{2}).*equity=\$([0-9,]+\.\d{2})")
if os.path.exists(LOG_PATH):
    with open(LOG_PATH) as f:
        for line in f:
            m = pat.search(line)
            if m:
                val = float(m.group(2).replace(",", ""))
                if val > 0:
                    day_equity[m.group(1)] = val

# ── Append live equity as today's point ───────────────────────────────────────
load_env()
TOKEN = os.getenv("TRADIER_TOKEN")
ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
BASE = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1")
current_equity = None
if TOKEN and ACCOUNT_ID:
    try:
        from datetime import date
        bal = requests.get(f"{BASE}/accounts/{ACCOUNT_ID}/balances",
                           headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
                           timeout=15).json().get("balances", {})
        current_equity = float(bal.get("total_equity", 0) or 0)
        if current_equity > 0:
            day_equity[date.today().isoformat()] = current_equity
    except Exception:
        pass

points = [{"date": month_day(d), "value": round(v, 2)} for d, v in day_equity.items()]
if current_equity is None and points:
    current_equity = points[-1]["value"]

ret = ((current_equity - STARTING_CAPITAL) / STARTING_CAPITAL * 100) if current_equity else 0.0

print(json.dumps({
    "starting_capital": STARTING_CAPITAL,
    "current_equity": round(current_equity, 2) if current_equity else None,
    "total_return_pct": round(ret, 2),
    "points": points,
}, indent=2))
