#!/usr/bin/env python3
"""Settle expired CSP Wheel Bot positions in the trade tracker sheet.

Replicates the manual weekly step: for every row whose expiration date has
passed and whose "Stock @ Expiry" (column N) is still empty, copy the live
"Current Price" (column R) into column N as a static value. The sheet's own
formulas in columns O/P/Q then compute Outcome, P&L and Return.

Run this BEFORE generate_report.py each week.

Usage:
    python3 settle_expiry.py                      # settle all past-due rows
    python3 settle_expiry.py --expiry 2026-07-10  # settle one expiration only
    python3 settle_expiry.py --dry-run            # show what would change

Only empty N cells are ever written — already-settled rows are never touched.
Prices are only accurate if run on/near expiry day; the script warns when a
row expired more than 5 days ago.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1ABYAKLvMgoHbM2gccwrfFGYsP6U-Y0VYFnU9SFOPjVo"
CREDS_FILE = Path("/Users/ankushsinghal/Documents/Trading/csp-wheel-bot-e3194c27a5f7.json")
SCOPES = ["https://spreadsheets.google.com/feeds",
          "https://www.googleapis.com/auth/drive"]
DATA_START = 10  # first trade data row (1-indexed, matches sheets_logger.py)

# 0-indexed columns: D=expiration, N=stock @ expiry, R=current price, B=ticker
COL_TICKER, COL_EXPIRY, COL_STOCK_AT_EXPIRY, COL_CURRENT = 1, 3, 13, 17


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expiry", help="Only settle rows with this expiration "
                    "date (YYYY-MM-DD). Default: all past-due rows.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be written without writing.")
    args = ap.parse_args()

    if not CREDS_FILE.exists():
        sys.exit(f"ERROR: service account file not found: {CREDS_FILE}")

    creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
    ws = gspread.authorize(creds).open_by_key(SHEET_ID).sheet1
    all_vals = ws.get_all_values()

    today = datetime.now().date()
    updates = []   # (sheet_row, ticker, expiry, price_str)
    stale = []

    for i, row in enumerate(all_vals[DATA_START - 1:], start=DATA_START):
        if len(row) <= COL_CURRENT or not row[COL_TICKER].strip():
            continue
        exp_str = row[COL_EXPIRY].strip()
        try:
            exp = datetime.strptime(exp_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if args.expiry:
            if exp_str != args.expiry:
                continue
        elif exp > today:
            continue
        if row[COL_STOCK_AT_EXPIRY].strip():
            continue  # already settled — never overwrite
        price = row[COL_CURRENT].strip()
        if not price:
            print(f"  WARN row {i}: {row[COL_TICKER]} {exp_str} has no "
                  f"current price in column R — skipping.")
            continue
        if (today - exp).days > 5:
            stale.append((i, row[COL_TICKER], exp_str))
        updates.append((i, row[COL_TICKER], exp_str, price))

    if not updates:
        print("Nothing to settle — all past-due rows already have "
              "'Stock @ Expiry' filled.")
        return

    for row_i, ticker, exp_str, price in updates:
        print(f"  row {row_i}: {ticker} exp {exp_str} → Stock @ Expiry = {price}")
    if stale:
        print(f"\nWARNING: {len(stale)} row(s) expired more than 5 days ago — "
              f"today's price may not reflect the true expiry-day price:")
        for row_i, ticker, exp_str in stale:
            print(f"  row {row_i}: {ticker} exp {exp_str}")

    if args.dry_run:
        print(f"\nDry run — {len(updates)} row(s) would be settled. "
              "No changes written.")
        return

    # Batch write plain values into column N. parse_money-style cleanup:
    # column R is display-formatted (e.g. "$38.82"); write the bare number so
    # the sheet's numeric formulas work.
    cells = []
    for row_i, _, _, price in updates:
        clean = price.replace("$", "").replace(",", "").strip()
        cells.append(gspread.Cell(row=row_i, col=COL_STOCK_AT_EXPIRY + 1,
                                  value=clean))
    ws.update_cells(cells, value_input_option="USER_ENTERED")
    print(f"\nSettled {len(updates)} row(s).")


if __name__ == "__main__":
    main()
