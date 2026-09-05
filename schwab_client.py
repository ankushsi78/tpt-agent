#!/usr/bin/env python3
"""
Schwab brokerage client for the Trading project.

Wraps schwab-py with:
  - .env credential loading (same convention as csp_bot.py)
  - a cached OAuth token (schwab_token.json) so you only log in occasionally
  - helpers to read accounts/positions/quotes
  - an order builder that DRY-RUNS by default (prints the order, does NOT send)

Live order placement is OFF unless you pass live=True *and* set
SCHWAB_ALLOW_LIVE=1 in the environment. This double gate is deliberate.

First-time setup:
    python3 schwab_login.py      # one-time browser login -> writes schwab_token.json
Then:
    python3 schwab_client.py     # smoke test: prints account summary
"""

import os
import sys

# ── Auto-load .env from this script's directory (matches csp_bot.py) ──────────
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from schwab.auth import client_from_token_file, client_from_login_flow
from schwab.orders.equities import (
    equity_buy_limit, equity_sell_limit,
    equity_buy_market, equity_sell_market,
)

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY      = os.getenv("SCHWAB_API_KEY")        # client ID from developer.schwab.com
API_SECRET   = os.getenv("SCHWAB_API_SECRET")     # client secret
CALLBACK_URL = os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182")
TOKEN_PATH   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schwab_token.json")
ALLOW_LIVE   = os.getenv("SCHWAB_ALLOW_LIVE", "0") == "1"


def get_client(interactive=False):
    """Return an authenticated schwab-py client.

    Uses the cached token if present; otherwise (interactive=True) runs the
    one-time browser login flow and caches the token.
    """
    if not API_KEY or not API_SECRET:
        sys.exit("ERROR: set SCHWAB_API_KEY and SCHWAB_API_SECRET in .env")

    if os.path.exists(TOKEN_PATH):
        return client_from_token_file(TOKEN_PATH, API_KEY, API_SECRET)

    if not interactive:
        sys.exit(
            f"No token at {TOKEN_PATH}. Run:  python3 schwab_login.py"
        )

    # One-time login: opens a browser, you approve, token gets cached.
    return client_from_login_flow(
        API_KEY, API_SECRET, CALLBACK_URL, TOKEN_PATH,
    )


def get_account_hash(client):
    """Schwab addresses accounts by an opaque hash, not the account number."""
    resp = client.get_account_numbers()
    resp.raise_for_status()
    data = resp.json()
    # Returns list of {accountNumber, hashValue}; use the first by default.
    acct_num = os.getenv("SCHWAB_ACCOUNT_NUMBER")
    if acct_num:
        for a in data:
            if a["accountNumber"] == acct_num:
                return a["hashValue"]
        sys.exit(f"Account {acct_num} not found among {[a['accountNumber'] for a in data]}")
    return data[0]["hashValue"]


def account_summary(client, account_hash):
    resp = client.get_account(account_hash, fields=client.Account.Fields.POSITIONS)
    resp.raise_for_status()
    acct = resp.json()["securitiesAccount"]
    bal = acct.get("currentBalances", {})
    print(f"Account type : {acct.get('type')}")
    print(f"Account #    : ...{acct.get('accountNumber', '')[-4:]}")
    print(f"Cash         : ${bal.get('cashBalance', 0):,.2f}")
    print(f"Liquidation  : ${bal.get('liquidationValue', 0):,.2f}")
    print(f"Buying power : ${bal.get('buyingPower', 0):,.2f}")
    positions = acct.get("positions", [])
    if positions:
        print(f"\nPositions ({len(positions)}):")
        for p in positions:
            sym = p["instrument"]["symbol"]
            qty = p.get("longQuantity", 0) - p.get("shortQuantity", 0)
            mv  = p.get("marketValue", 0)
            print(f"  {sym:<8} qty {qty:>8}   mkt ${mv:,.2f}")
    else:
        print("\nNo open positions.")
    return acct


def place_equity_order(client, account_hash, *, symbol, side, qty,
                       limit_price=None, live=False):
    """Build an equity order and DRY-RUN it by default.

    side: 'buy' or 'sell'
    limit_price: float for a limit order; None => market order
    live: must be True AND env SCHWAB_ALLOW_LIVE=1 to actually transmit.
    """
    side = side.lower()
    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'")

    if limit_price is not None:
        builder = (equity_buy_limit if side == "buy" else equity_sell_limit)(
            symbol, qty, limit_price)
        desc = f"{side.upper()} {qty} {symbol} @ ${limit_price} (LIMIT)"
    else:
        builder = (equity_buy_market if side == "buy" else equity_sell_market)(
            symbol, qty)
        desc = f"{side.upper()} {qty} {symbol} @ MARKET"

    spec = builder.build()

    if not (live and ALLOW_LIVE):
        print("── DRY RUN (not transmitted) ──")
        print(desc)
        print("order spec:", spec)
        if live and not ALLOW_LIVE:
            print("\n[blocked] live=True but SCHWAB_ALLOW_LIVE != 1. "
                  "Refusing to transmit.")
        else:
            print("\nTo transmit: pass live=True AND set SCHWAB_ALLOW_LIVE=1")
        return {"dry_run": True, "order": spec, "description": desc}

    # ── Live path ──
    resp = client.place_order(account_hash, builder)
    resp.raise_for_status()
    order_id = resp.headers.get("location", "").rstrip("/").split("/")[-1]
    print(f"LIVE ORDER SUBMITTED: {desc}  (order id {order_id})")
    return {"dry_run": False, "order_id": order_id, "description": desc}


if __name__ == "__main__":
    c = get_client(interactive=False)
    h = get_account_hash(c)
    account_summary(c, h)
