#!/usr/bin/env python3
"""
Update "Option Price Now" (col O) on the LEAPS tab for every OPEN trade.

Price = mid of bid/ask from Tradier (TRADIER_TOKEN / TRADIER_BASE_URL in .env),
which tracks Robinhood's mark. Only column O of OPEN rows is written; CLOSED
rows and every other column are left alone. Rows whose O cell holds a formula,
or whose contract can't be quoted, are skipped and logged.

Scheduled via launchd: com.ankushsinghal.leapsprice (weekdays 7:30 AM and 12:55 PM PT).
Usage:
    python3 leaps_price_updater.py            # update the sheet
    python3 leaps_price_updater.py --dry-run  # print what would change
"""

import os
import sys
from datetime import date, datetime, timedelta

import gspread
import requests
from google.oauth2.service_account import Credentials

# ── Auto-load .env from this script's directory (matches csp_bot.py) ──────────
_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_dir, ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# ── Config ─────────────────────────────────────────────────────────────────────
CREDS_FILE   = os.path.join(_dir, "csp-wheel-bot-e3194c27a5f7.json")
SHEET_ID     = "1ABYAKLvMgoHbM2gccwrfFGYsP6U-Y0VYFnU9SFOPjVo"
TAB_NAME     = "LEAPS"
SCOPES       = ["https://www.googleapis.com/auth/spreadsheets"]
DATA_START   = 14   # first trade row (headers on row 13)
TRADIER_URL  = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1").rstrip("/")
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")

# 0-based column indexes within A:AB
COL_TICKER, COL_TYPE, COL_STRIKE, COL_EXP = 1, 2, 3, 4
COL_PRICE, COL_STATUS = 14, 26      # O, AA


def _to_date(v) -> date:
    """Expiration arrives as a date serial (UNFORMATTED) or 'YYYY-MM-DD'."""
    if isinstance(v, (int, float)):
        return date(1899, 12, 30) + timedelta(days=int(v))
    return datetime.strptime(str(v).strip(), "%Y-%m-%d").date()


def _occ_symbol(ticker, opt_type, strike, exp: date) -> str:
    cp = "C" if str(opt_type).strip().upper().startswith("C") else "P"
    return f"{ticker.strip().upper()}{exp:%y%m%d}{cp}{int(round(float(strike) * 1000)):08d}"


def _quotes(symbols):
    r = requests.get(
        f"{TRADIER_URL}/markets/quotes",
        params={"symbols": ",".join(symbols), "greeks": "false"},
        headers={"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    q = (r.json().get("quotes") or {}).get("quote") or []
    return {x["symbol"]: x for x in (q if isinstance(q, list) else [q])}


def _mark(q):
    bid, ask = q.get("bid") or 0, q.get("ask") or 0
    if bid > 0 and ask > 0:
        return round((bid + ask) / 2, 2)
    return round(q["last"], 2) if q.get("last") else None


def main(dry_run=False):
    if not TRADIER_TOKEN:
        sys.exit("ERROR: set TRADIER_TOKEN in .env")

    print(f"Run started: {datetime.now():%Y-%m-%d %H:%M:%S %Z}")
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    ws = gspread.authorize(creds).open_by_key(SHEET_ID).worksheet(TAB_NAME)

    raw = ws.get(f"A{DATA_START}:AB", value_render_option="UNFORMATTED_VALUE")
    formulas = ws.get(f"O{DATA_START}:O", value_render_option="FORMULA")

    open_rows = []  # (row_num, occ, old_price)
    for i, r in enumerate(raw):
        r = list(r) + [""] * (28 - len(r))
        if not str(r[COL_TICKER]).strip():
            break
        if str(r[COL_STATUS]).strip().upper() != "OPEN":
            continue
        row = DATA_START + i
        f = formulas[i][0] if i < len(formulas) and formulas[i] else ""
        if str(f).startswith("="):
            print(f"  SKIP row {row}: column O holds a formula ({f})")
            continue
        try:
            occ = _occ_symbol(r[COL_TICKER], r[COL_TYPE], r[COL_STRIKE], _to_date(r[COL_EXP]))
        except (ValueError, TypeError) as e:
            print(f"  SKIP row {row}: can't build contract symbol ({e})")
            continue
        open_rows.append((row, occ, r[COL_PRICE]))

    if not open_rows:
        print("No OPEN rows found.")
        return

    quotes = _quotes(sorted({occ for _, occ, _ in open_rows}))
    updates = []
    for row, occ, old in open_rows:
        q = quotes.get(occ)
        mark = _mark(q) if q else None
        if mark is None:
            print(f"  SKIP row {row}: no quote for {occ}")
            continue
        print(f"  row {row}: {occ}  {old} -> {mark}  (bid {q.get('bid')} / ask {q.get('ask')})")
        updates.append({"range": f"O{row}", "values": [[mark]]})

    if dry_run:
        print(f"Dry run: {len(updates)} cell(s) would be updated.")
        return
    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
    summary = ws.get("A2:I2")[0]
    print(f"Updated {len(updates)} cell(s). Portfolio value {summary[4]}, growth {summary[8]}")
    print(f"Run finished: {datetime.now():%Y-%m-%d %H:%M:%S %Z}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
