#!/usr/bin/env python3
"""
tastytrade brokerage client for the Trading project.

Wraps the `tastytrade` SDK (v13, OAuth) with:
  - .env credential loading (same convention as schwab_client.py / csp_bot.py)
  - an OAuth refresh-token session (NO password is ever stored or handled)
  - helpers to read accounts / balances / positions
  - an order builder that DRY-RUNS by default (prints the order, does NOT send)

Live order placement is OFF unless you pass live=True *and* set
TT_ALLOW_LIVE=1 in the environment. This double gate mirrors the Schwab client.

The tastytrade SDK is fully async; this module exposes small synchronous
wrappers (via asyncio.run) so it behaves like the Schwab client on the CLI.

──────────────────────────────────────────────────────────────────────────────
FIRST-TIME SETUP (you do this yourself in the tastytrade web UI — I never touch
your credentials):

  1. Log in at https://my.tastytrade.com  ->  Manage  ->  API  ->  OAuth
     Create a "Personal OAuth Grant" (a.k.a. personal access application).
  2. Copy the two values it gives you:
        - Client Secret   -> put in .env as  TT_SECRET
        - Refresh Token   -> put in .env as  TT_REFRESH
     (The refresh token is long-lived; the client exchanges it for a short
      ~15-minute access token on each run. Your password is never used here.)
  3. Add to Trading/.env:
        TT_SECRET=<your client secret>
        TT_REFRESH=<your refresh token>
        # optional:
        TT_ACCOUNT_NUMBER=<specific account, else the first is used>
        TT_ENV=prod            # or 'sandbox' for the certification environment
        TT_ALLOW_LIVE=0        # keep 0; live orders are double-gated

Then:
    python3 tastytrade_client.py     # smoke test: prints account summary
"""

import os
import sys
import asyncio

# ── Auto-load .env from this script's directory (matches schwab_client.py) ────
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from tastytrade import Session, Account
from tastytrade.order import (
    NewOrder, Leg, OrderType, OrderTimeInForce, OrderAction, InstrumentType,
)
from tastytrade.instruments import Equity

# ── Config ────────────────────────────────────────────────────────────────────
SECRET     = os.getenv("TT_SECRET")                       # OAuth client secret
REFRESH    = os.getenv("TT_REFRESH")                      # OAuth refresh token
ACCOUNT_NO = os.getenv("TT_ACCOUNT_NUMBER")               # optional pin
IS_TEST    = os.getenv("TT_ENV", "prod").lower() in ("sandbox", "cert", "test")
ALLOW_LIVE = os.getenv("TT_ALLOW_LIVE", "0") == "1"


# ── Auth ────────────────────────────────────────────────────────────────────
async def get_session():
    """Build an authenticated tastytrade session from the OAuth refresh token.

    Exchanges the long-lived refresh token for a short-lived access token.
    """
    if not SECRET or not REFRESH:
        sys.exit(
            "ERROR: set TT_SECRET and TT_REFRESH in .env "
            "(create a Personal OAuth Grant at my.tastytrade.com -> API). "
            "See the setup notes at the top of tastytrade_client.py."
        )
    session = Session(provider_secret=SECRET, refresh_token=REFRESH, is_test=IS_TEST)
    await session.refresh()          # get the access token
    return session


async def get_account(session):
    """Return the target Account (TT_ACCOUNT_NUMBER, else the first one)."""
    if ACCOUNT_NO:
        return await Account.get(session, ACCOUNT_NO)
    accounts = await Account.get(session)
    if not accounts:
        sys.exit("No tastytrade accounts found for these credentials.")
    return accounts[0]


# ── Read helpers ──────────────────────────────────────────────────────────────
def _money(x):
    return f"${float(x):,.2f}"


async def account_summary(session, account):
    bal = await account.get_balances(session)
    positions = await account.get_positions(session, include_marks=True)

    print(f"Account #    : ...{account.account_number[-4:]}")
    print(f"Nickname     : {account.nickname or account.account_type_name}")
    print(f"Net liq (NLV): {_money(bal.net_liquidating_value)}")
    print(f"Cash         : {_money(bal.cash_balance)}")
    print(f"Equity BP    : {_money(bal.equity_buying_power)}")
    print(f"Deriv BP     : {_money(bal.derivative_buying_power)}")
    print(f"Maint. req.  : {_money(bal.maintenance_requirement)}")

    if positions:
        print(f"\nPositions ({len(positions)}):")
        for p in positions:
            sign = -1 if str(p.quantity_direction).lower() == "short" else 1
            qty = sign * float(p.quantity)
            print(f"  {p.symbol:<22} {p.instrument_type:<14} qty {qty:>8.0f}")
    else:
        print("\nNo open positions.")
    return bal, positions


# ── Order builder (DRY-RUN by default; double-gated for live) ─────────────────
async def place_equity_order(session, account, *, symbol, side, qty,
                             limit_price=None, live=False):
    """Build an equity order and DRY-RUN it by default.

    side: 'buy' or 'sell'
    limit_price: float for a LIMIT order; None => MARKET order
    live: must be True AND env TT_ALLOW_LIVE=1 to actually transmit.
    """
    side = side.lower()
    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'")

    equity = (await Equity.get(session, [symbol]))[0]
    action = OrderAction.BUY_TO_OPEN if side == "buy" else OrderAction.SELL_TO_CLOSE
    leg = equity.build_leg(qty, action)

    if limit_price is not None:
        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[leg],
            price=(-abs(limit_price) if side == "buy" else abs(limit_price)),
        )
        desc = f"{side.upper()} {qty} {symbol} @ ${limit_price} (LIMIT)"
    else:
        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.MARKET,
            legs=[leg],
        )
        desc = f"{side.upper()} {qty} {symbol} @ MARKET"

    if not (live and ALLOW_LIVE):
        print("── DRY RUN (not transmitted) ──")
        print(desc)
        # dry-run against the API without placing (validates buying power etc.)
        preview = await account.place_order(session, order, dry_run=True)
        print("buying-power effect:", preview.buying_power_effect.change_in_buying_power)
        if live and not ALLOW_LIVE:
            print("\n[blocked] live=True but TT_ALLOW_LIVE != 1. Refusing to transmit.")
        else:
            print("\nTo transmit: pass live=True AND set TT_ALLOW_LIVE=1")
        return {"dry_run": True, "description": desc, "preview": preview}

    # ── Live path ──
    resp = await account.place_order(session, order, dry_run=False)
    print(f"LIVE ORDER SUBMITTED: {desc}  (order id {resp.order.id})")
    return {"dry_run": False, "order_id": resp.order.id, "description": desc}


# ── Sync CLI entry ─────────────────────────────────────────────────────────────
async def _main():
    session = await get_session()
    account = await get_account(session)
    await account_summary(session, account)


if __name__ == "__main__":
    asyncio.run(_main())
