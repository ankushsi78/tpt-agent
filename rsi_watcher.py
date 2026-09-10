#!/usr/bin/env python3
"""
Daily RSI(14) watcher for QQQ / SPY using Schwab price data.

Pulls daily candles from Schwab (via schwab_client.get_client), computes the
Wilder RSI(14) on the closing prices, and pings Discord when RSI is at or
below the trigger threshold (default 35 = oversold).

Design notes
------------
- Read-only: only calls get_price_history_every_day. Never touches accounts
  or orders, so there is no live-trading risk here.
- De-duped: state is kept in rsi_watcher_state.json so you get ONE alert per
  crossing into oversold, not a fresh ping every run while RSI sits below 35.
  A symbol re-arms once RSI climbs back above the re-arm level (default 40).
- Uses the most recent COMPLETED daily bar. If run intraday the latest bar is
  still forming; pass --intraday to include it, otherwise it is dropped so the
  RSI matches what you'd see on a daily TradingView chart at the close.

Usage
-----
    python3 rsi_watcher.py                 # check QQQ + SPY, alert if RSI<=35
    python3 rsi_watcher.py --test          # post a sample embed to Discord and exit
    python3 rsi_watcher.py --threshold 30  # different trigger
    python3 rsi_watcher.py --intraday      # include today's still-forming bar
    python3 rsi_watcher.py --force         # alert even if already alerted (ignore state)

Schedule it (e.g. weekdays ~15 min before the close, 3:45pm ET):
    45 15 * * 1-5   cd /Users/ankushsinghal/Documents/Trading && ./run_rsi_watcher.sh
"""

import os
import sys
import json
import argparse
import datetime as dt

import requests

from schwab_client import get_client  # loads .env + cached OAuth token

# ── Config ────────────────────────────────────────────────────────────────────
SYMBOLS         = ["QQQ", "SPY"]
RSI_PERIOD      = 14
DEFAULT_TRIGGER = 35.0     # alert when RSI touches/crosses down through this
REARM_LEVEL     = 40.0     # re-arm a symbol once RSI recovers above this
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")

_HERE       = os.path.dirname(os.path.abspath(__file__))
STATE_PATH  = os.path.join(_HERE, "rsi_watcher_state.json")


# ── RSI (Wilder's smoothing, matches TradingView's default RSI) ─────────────────
def wilder_rsi(closes, period=RSI_PERIOD):
    """Return the RSI series (list, aligned to closes; first `period` are None)."""
    if len(closes) < period + 1:
        raise ValueError(f"need at least {period + 1} closes, got {len(closes)}")

    gains, losses = [], []
    for i in range(1, len(closes)):
        chg = closes[i] - closes[i - 1]
        gains.append(max(chg, 0.0))
        losses.append(max(-chg, 0.0))

    rsi = [None] * len(closes)

    # Seed: simple average of the first `period` gains/losses.
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi[period] = _rsi_from(avg_gain, avg_loss)

    # Wilder smoothing for the rest.
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rsi[i + 1] = _rsi_from(avg_gain, avg_loss)

    return rsi


def _rsi_from(avg_gain, avg_loss):
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


# ── Schwab price data ───────────────────────────────────────────────────────────
def fetch_daily_closes(client, symbol, include_forming_bar=False):
    """Return (dates, closes) of daily candles, most recent last.

    By default the last (still-forming) intraday bar is dropped so the RSI
    matches a completed daily chart.
    """
    resp = client.get_price_history_every_day(
        symbol,
        start_datetime=dt.datetime.now() - dt.timedelta(days=200),
        end_datetime=dt.datetime.now(),
        need_extended_hours_data=False,
    )
    resp.raise_for_status()
    candles = resp.json().get("candles", [])
    if not candles:
        raise RuntimeError(f"{symbol}: no candles returned from Schwab")

    dates  = [dt.datetime.fromtimestamp(c["datetime"] / 1000).date() for c in candles]
    closes = [c["close"] for c in candles]

    # Drop the last bar if it's today's still-forming candle.
    if not include_forming_bar and dates[-1] == dt.date.today():
        dates, closes = dates[:-1], closes[:-1]

    return dates, closes


# ── State (de-dupe alerts) ──────────────────────────────────────────────────────
def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


# ── Discord ─────────────────────────────────────────────────────────────────────
def post_alert(triggered, threshold):
    """Post one Discord embed listing the symbol(s) that hit the threshold."""
    if not DISCORD_WEBHOOK:
        sys.exit("ERROR: DISCORD_WEBHOOK_URL not set in .env")

    fields = []
    for t in triggered:
        fields.append({
            "name":  f"📉 {t['symbol']}  —  RSI {t['rsi']:.1f}",
            "value": (f"Close **${t['close']:.2f}** on {t['date']}\n"
                      f"RSI(14) crossed **≤ {threshold:.0f}** → oversold"),
            "inline": False,
        })

    embed = {
        "title":       f"🚨 Oversold Alert — RSI(14) ≤ {threshold:.0f}",
        "description": "Daily RSI has dropped into oversold territory. "
                       "Consider it a signal to review — not an auto-entry.",
        "color":       0xE74C3C,  # red
        "fields":      fields,
        "footer":      {"text": "rsi_watcher.py · Schwab daily data"},
        "timestamp":   dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    r = requests.post(DISCORD_WEBHOOK, json={"embeds": [embed]}, timeout=10)
    r.raise_for_status()


def post_test():
    sample = [{"symbol": "QQQ", "rsi": 33.7, "close": 452.10,
               "date": dt.date.today().isoformat()}]
    post_alert(sample, DEFAULT_TRIGGER)
    print("Posted a test embed to Discord.")


# ── Main ─────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Daily RSI(14) watcher for QQQ/SPY (Schwab data).")
    ap.add_argument("--threshold", type=float, default=DEFAULT_TRIGGER,
                    help=f"RSI trigger level (default {DEFAULT_TRIGGER})")
    ap.add_argument("--symbols", nargs="+", default=SYMBOLS,
                    help=f"symbols to watch (default {' '.join(SYMBOLS)})")
    ap.add_argument("--intraday", action="store_true",
                    help="include today's still-forming bar")
    ap.add_argument("--force", action="store_true",
                    help="alert even if already alerted (ignore de-dupe state)")
    ap.add_argument("--test", action="store_true",
                    help="post a sample Discord embed and exit")
    args = ap.parse_args()

    if args.test:
        post_test()
        return

    client = get_client(interactive=False)
    state  = load_state()
    triggered = []

    for sym in args.symbols:
        dates, closes = fetch_daily_closes(client, sym, include_forming_bar=args.intraday)
        rsi_series = wilder_rsi(closes, RSI_PERIOD)
        rsi   = rsi_series[-1]
        close = closes[-1]
        date  = dates[-1].isoformat()

        prev = state.get(sym, {})
        already_alerted = prev.get("alerted", False)

        # Re-arm once RSI recovers above the re-arm level.
        if already_alerted and rsi > REARM_LEVEL:
            already_alerted = False

        is_oversold = rsi <= args.threshold
        print(f"{sym}: close ${close:.2f} on {date}  RSI(14)={rsi:.1f}"
              f"{'  ⚠️ OVERSOLD' if is_oversold else ''}"
              f"{'  (already alerted)' if is_oversold and already_alerted else ''}")

        if is_oversold and (args.force or not already_alerted):
            triggered.append({"symbol": sym, "rsi": rsi, "close": close, "date": date})

        state[sym] = {"alerted": is_oversold if not args.force else True,
                      "rsi": round(rsi, 2), "date": date}

    if triggered:
        post_alert(triggered, args.threshold)
        print(f"→ Posted Discord alert for: {', '.join(t['symbol'] for t in triggered)}")
    else:
        print("→ Nothing oversold (or already alerted). No Discord post.")

    save_state(state)


if __name__ == "__main__":
    main()
