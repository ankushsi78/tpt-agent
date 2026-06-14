#!/usr/bin/env python3
"""
TPT Agent — Tradier Paper Trading Bot
Strategy: Cash-Secured Puts (CSP) + LEAPS Calls (mirrors experiment_bot.py)

Data sources (all real-time via Tradier):
  • Stock quotes and OHLCV history  → Tradier markets/quotes + markets/history
  • Options chains, IV, Greeks      → Tradier markets/options/chains (greeks=true)
  • VIX                             → Tradier markets/quotes ($VIX.X), yfinance fallback
  • Beta vs SPY                     → Computed from Tradier daily history
  • Earnings dates                  → yfinance only (Tradier has no earnings calendar)

Order execution → Tradier sandbox (paper trading account VA54665450)
Discord         → #beta-ai-trades only (hardcoded webhook)
"""

import os, math, logging, re, time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
from io import StringIO
from scipy.stats import norm

# ── Auto-load .env (for direct runs; launchd uses plist env vars) ─────────────
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
def log(msg: str):
    logging.info(msg)

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

# — Tradier —
TRADIER_TOKEN      = os.getenv("TRADIER_TOKEN",      "")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID", "")
TRADIER_BASE_URL   = os.getenv("TRADIER_BASE_URL",   "https://sandbox.tradier.com/v1")

TRADIER_HEADERS = {
    "Authorization": f"Bearer {TRADIER_TOKEN}",
    "Accept":        "application/json",
}

# — Discord — TPT Agent posts ONLY to #beta-ai-trades, hardcoded so no env var
# misconfiguration can accidentally redirect output to another channel.
BETA_AI_TRADES_WEBHOOK = (
    "https://discord.com/api/webhooks/1500631759606255817/"
    "n_npkYoa1Glmd_GUi0sGY58YBF-nQo7KXxz4_2qbTsvvwzEsElC4U1XPYAKODXsQFuU7"
)

# — Approved stocks —
APPROVED_STOCKS_URL = os.getenv("APPROVED_STOCKS_URL", "")

# — CSP DTE window —
MIN_DTE = int(os.getenv("MIN_DTE", "30"))
MAX_DTE = int(os.getenv("MAX_DTE", "45"))

# — CSP Delta by BB position (per-stock, replaces VIX-based global range) —
# Near lower BB (≤ 3% above):   aggressive  — stock oversold, mean-reversion likely
# Between lower BB and mid BB:  moderate    — partial pullback
# At or above mid BB:           conservative — at/above average, stay far OTM
CSP_BB_NEAR_LOWER_PCT    = float(os.getenv("CSP_BB_NEAR_LOWER_PCT",    "3.0"))
CSP_DELTA_NEAR_LOWER_MIN = float(os.getenv("CSP_DELTA_NEAR_LOWER_MIN", "0.25"))
CSP_DELTA_NEAR_LOWER_MAX = float(os.getenv("CSP_DELTA_NEAR_LOWER_MAX", "0.35"))
CSP_DELTA_MID_ZONE_MIN   = float(os.getenv("CSP_DELTA_MID_ZONE_MIN",   "0.15"))
CSP_DELTA_MID_ZONE_MAX   = float(os.getenv("CSP_DELTA_MID_ZONE_MAX",   "0.25"))
CSP_DELTA_ABOVE_MID_MIN  = float(os.getenv("CSP_DELTA_ABOVE_MID_MIN",  "0.08"))
CSP_DELTA_ABOVE_MID_MAX  = float(os.getenv("CSP_DELTA_ABOVE_MID_MAX",  "0.15"))

# — CSP RSI hard gate (new): overbought stocks disqualified for CSP —
CSP_RSI_OVERBOUGHT = float(os.getenv("CSP_RSI_OVERBOUGHT", "65"))

# — CSP ARR target (cap raised to 70%) —
MIN_ARR           = float(os.getenv("MIN_ARR",  "40"))
MAX_ARR           = float(os.getenv("MAX_ARR",  "70"))   # raised from 60
MIN_OPEN_INTEREST = int(os.getenv("MIN_OPEN_INTEREST", "50"))

# — Hard filters —
FILTER_BELOW_200_SMA          = os.getenv("FILTER_BELOW_200_SMA",          "true").lower() == "true"
FILTER_EARNINGS_IN_DTE_WINDOW = os.getenv("FILTER_EARNINGS_IN_DTE_WINDOW", "true").lower() == "true"

# — Scoring (max 5 pts) —
SCORE_ABOVE_50_SMA       = os.getenv("SCORE_ABOVE_50_SMA",    "true").lower() == "true"
SCORE_BELOW_MID_BB       = os.getenv("SCORE_BELOW_MID_BB",    "true").lower() == "true"
SCORE_DOWN_TODAY         = os.getenv("SCORE_DOWN_TODAY",       "true").lower() == "true"
SCORE_DOWN_TODAY_MIN_PCT = float(os.getenv("SCORE_DOWN_TODAY_MIN_PCT", "0.5"))
SCORE_DOWN_TODAY_MAX_PCT = float(os.getenv("SCORE_DOWN_TODAY_MAX_PCT", "5.0"))
SCORE_RSI_OVERSOLD       = float(os.getenv("SCORE_RSI_OVERSOLD", "50"))  # +1 if RSI < 50 (actively oversold)
SCORE_IV_MIN_PCT         = float(os.getenv("SCORE_IV_MIN_PCT", "40"))
MIN_SCORE_TO_TRADE       = int(os.getenv("MIN_SCORE_TO_TRADE", "3"))
SIZE_UP_SCORE            = int(os.getenv("SIZE_UP_SCORE",      "5"))

# — Top N candidates for execution —
TOP_N_CSP   = 5
TOP_N_LEAPS = 5

# — LEAPS —
LEAPS_MIN_DTE           = 365
LEAPS_MAX_DTE           = 730
LEAPS_MIN_DELTA         = float(os.getenv("LEAPS_MIN_DELTA",    "0.70"))  # #6: widened from 0.80
LEAPS_MAX_DELTA         = float(os.getenv("LEAPS_MAX_DELTA",    "0.85"))  # #6: lowered from 0.99
LEAPS_TARGET_DELTA      = float(os.getenv("LEAPS_TARGET_DELTA", "0.77"))  # #6: lowered from 0.85
LEAPS_RSI_OVERBOUGHT    = 70.0
LEAPS_RSI_PERIOD        = 14
LEAPS_MIN_SCORE         = 2
LEAPS_MAX_PORTFOLIO_PCT = 0.15                                             # #10: raised from 0.10 (15%)
LEAPS_MIN_OI            = int(os.getenv("LEAPS_MIN_OI", "50"))
# VIX gate: LEAPS enabled when VIX ≤ 18 (calm) OR VIX ≥ 21 (fear/opportunity)
# Zone 18–21 excluded — moderate stress where IV is neither cheap nor justified
LEAPS_VIX_CALM_MAX      = float(os.getenv("LEAPS_VIX_CALM_MAX", "18"))   # VIX gate: calm ceiling
LEAPS_VIX_FEAR_MIN      = float(os.getenv("LEAPS_VIX_FEAR_MIN", "21"))   # VIX gate: fear floor

# — Position management —
CSP_CLOSE_PREMIUM_PCT   = 0.50   # close CSP when 50% of premium captured
CSP_DTE_EXIT            = 21     # #1: close CSPs at 21 DTE regardless of P&L (if any profit or small loss)
CSP_STOP_LOSS_MULT      = 2.0    # #2: close CSP when loss = 2× premium received (current = 3× entry)
LEAPS_CLOSE_PROFIT_PCT  = 0.05   # #3: close LEAPS at +5% profit
LEAPS_STOP_LOSS_PCT     = 0.50   # #3 companion: close LEAPS if down 50%

# — VIX deployment tiers —
VIX_DEPLOY_HIGH     = 0.80
VIX_DEPLOY_ELEVATED = 0.70
VIX_DEPLOY_MODERATE = 0.60
VIX_DEPLOY_LOW      = 0.40
VIX_DEPLOY_VERY_LOW = 0.20

# TPT Agent does not use free-tier / trade-ideas posting

RF_RATE = 0.045   # risk-free rate for Black-Scholes


# ══════════════════════════════════════════════════════════════════════════════
# TRADIER API LAYER
# ══════════════════════════════════════════════════════════════════════════════

def tradier_get(path: str, params: dict = None) -> dict:
    url = f"{TRADIER_BASE_URL}/{path.lstrip('/')}"
    try:
        r = requests.get(url, headers=TRADIER_HEADERS, params=params, timeout=15)
        if r.status_code != 200:
            log(f"  Tradier GET {path} → HTTP {r.status_code}: {r.text[:200]}")
            return {}
        return r.json()
    except Exception as e:
        log(f"  Tradier GET error {path}: {e}")
        return {}


def tradier_post_order(form_data: dict) -> tuple[bool, dict]:
    """Place an option order via Tradier (form-encoded, not JSON)."""
    url = f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders"
    try:
        r = requests.post(
            url,
            headers={**TRADIER_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
            data=form_data,
            timeout=15,
        )
        resp = r.json()
        if r.status_code in (200, 201) and resp.get("order", {}).get("status") == "ok":
            return True, resp
        log(f"  Order rejected: {resp}")
        return False, resp
    except Exception as e:
        log(f"  Tradier order error: {e}")
        return False, {"error": str(e)}


def tradier_delete(path: str) -> bool:
    url = f"{TRADIER_BASE_URL}/{path.lstrip('/')}"
    try:
        r = requests.delete(url, headers=TRADIER_HEADERS, timeout=10)
        return r.status_code in (200, 204)
    except Exception as e:
        log(f"  Tradier DELETE error: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# ACCOUNT
# ══════════════════════════════════════════════════════════════════════════════

def get_account_info() -> dict:
    resp = tradier_get(f"accounts/{TRADIER_ACCOUNT_ID}/balances")
    bal  = resp.get("balances", {})
    equity = float(bal.get("total_equity", 0) or 0)
    cash   = float(bal.get("total_cash",   0) or 0)
    # Option buying power lives under margin / pdt / cash sub-key
    sub    = bal.get("margin") or bal.get("pdt") or bal.get("cash") or {}
    opt_bp = float(sub.get("option_buying_power", cash) or cash)
    log(f"  Account: equity=${equity:,.2f}  cash=${cash:,.2f}  option_bp=${opt_bp:,.2f}")
    return {
        "portfolio_value":     equity,
        "cash":                cash,
        "option_buying_power": opt_bp,
    }


def get_open_positions() -> list[dict]:
    resp  = tradier_get(f"accounts/{TRADIER_ACCOUNT_ID}/positions")
    raw   = resp.get("positions")
    if not raw or raw == "null":
        return []
    items = raw.get("position", [])
    if isinstance(items, dict):
        items = [items]

    results = []
    for p in items:
        sym        = p.get("symbol", "")
        qty        = float(p.get("quantity", 0))
        cost_basis = float(p.get("cost_basis", 0))
        if qty == 0:
            continue
        # abs() because Tradier stores cost_basis as negative for short positions
        # (credit received). We always want the per-share price as a positive number.
        avg_entry = abs(cost_basis) / (abs(qty) * 100) if qty != 0 else 0
        results.append({
            "symbol":        sym,
            "qty":           qty,
            "cost_basis":    cost_basis,
            "avg_entry":     avg_entry,
            "date_acquired": p.get("date_acquired", ""),
        })
    return results


def get_current_option_price(symbol: str) -> float | None:
    """Fetch live mid-price for an option from Tradier."""
    resp   = tradier_get("markets/quotes", {"symbols": symbol, "greeks": "false"})
    quotes = resp.get("quotes")
    if not quotes:
        return None
    q = quotes.get("quote", {})
    if isinstance(q, list):
        q = q[0] if q else {}
    bid  = float(q.get("bid",  0) or 0)
    ask  = float(q.get("ask",  0) or 0)
    last = float(q.get("last", 0) or 0)
    if bid > 0 and ask > 0:
        return round((bid + ask) / 2, 2)
    if ask > 0:
        return ask
    if bid > 0:
        return bid
    if last > 0:
        return last
    return None


def get_open_orders() -> list[dict]:
    resp  = tradier_get(f"accounts/{TRADIER_ACCOUNT_ID}/orders")
    raw   = resp.get("orders")
    if not raw or raw == "null":
        return []
    items = raw.get("order", [])
    if isinstance(items, dict):
        items = [items]
    return [o for o in items if o.get("status") in ("open", "pending", "partially_filled")]


# ══════════════════════════════════════════════════════════════════════════════
# MARKET DATA — STOCKS
# ══════════════════════════════════════════════════════════════════════════════

def get_stock_quote(ticker: str) -> dict | None:
    """Real-time stock quote from Tradier."""
    resp   = tradier_get("markets/quotes", {"symbols": ticker})
    quotes = resp.get("quotes")
    if not quotes:
        return None
    q = quotes.get("quote", {})
    if isinstance(q, list):
        q = q[0] if q else {}
    price = float(q.get("last", 0) or 0)
    prev  = float(q.get("prevclose", price) or price)
    if price <= 0:
        return None
    return {
        "price":   price,
        "day_chg": round(((price - prev) / prev * 100) if prev else 0, 2),
        "bid":     float(q.get("bid", 0) or 0),
        "ask":     float(q.get("ask", 0) or 0),
    }


def get_stock_history(ticker: str, calendar_days: int = 310) -> pd.DataFrame:
    """Daily OHLCV bars from Tradier — used for SMA / Bollinger / RSI."""
    start = (datetime.today() - timedelta(days=calendar_days)).strftime("%Y-%m-%d")
    end   = datetime.today().strftime("%Y-%m-%d")
    resp  = tradier_get("markets/history", {
        "symbol":   ticker,
        "interval": "daily",
        "start":    start,
        "end":      end,
    })
    hist = resp.get("history")
    if not hist or hist == "null":
        return pd.DataFrame()
    days = hist.get("day", [])
    if isinstance(days, dict):
        days = [days]
    df = pd.DataFrame(days)
    if df.empty or "close" not in df.columns:
        return pd.DataFrame()
    df["close"] = df["close"].astype(float)
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def _calculate_rsi(closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains  = np.where(deltas > 0,  deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_g  = np.mean(gains[:period])
    avg_l  = np.mean(losses[:period])
    for g, l in zip(gains[period:], losses[period:]):
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
    if avg_l == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_g / avg_l)), 1)


def compute_technicals(ticker: str, quote: dict | None = None) -> dict | None:
    """SMA 20/50/200, Bollinger Bands, RSI from Tradier history."""
    df = get_stock_history(ticker, calendar_days=310)

    if df.empty or len(df) < 20:
        log(f"    {ticker}: insufficient Tradier history — skipping")
        return None

    closes = df["close"].values
    n = len(closes)

    sma20  = float(np.mean(closes[-20:])) if n >= 20  else float(closes[-1])
    sma50  = float(np.mean(closes[-50:])) if n >= 50  else sma20
    sma200 = float(np.mean(closes[-200:])) if n >= 200 else sma20

    std20  = float(np.std(closes[-20:], ddof=1)) if n >= 20 else 0
    bb_mid = sma20
    bb_up  = sma20 + 2 * std20
    bb_lo  = sma20 - 2 * std20
    rsi    = _calculate_rsi(closes, LEAPS_RSI_PERIOD)

    if quote is None:
        quote = get_stock_quote(ticker) or {}
    price   = quote.get("price", float(closes[-1]))
    day_chg = quote.get("day_chg", 0.0)

    return {
        "price":   price,
        "day_chg": day_chg,
        "sma20":   round(sma20,  2),
        "sma50":   round(sma50,  2),
        "sma200":  round(sma200, 2),
        "bb_mid":  round(bb_mid, 2),
        "bb_up":   round(bb_up,  2),
        "bb_lo":   round(bb_lo,  2),
        "rsi":     rsi,
    }


# ══════════════════════════════════════════════════════════════════════════════
# VIX  (Tradier real-time, yfinance as fallback)
# ══════════════════════════════════════════════════════════════════════════════

def get_vix() -> float:
    # Try Tradier first — symbol is $VIX.X on most feeds
    for sym in ("$VIX.X", "VIX"):
        try:
            resp = tradier_get("markets/quotes", {"symbols": sym})
            q    = resp.get("quotes", {}).get("quote", {})
            if isinstance(q, list):
                q = q[0] if q else {}
            price = float(q.get("last", 0) or 0)
            if price > 0:
                log(f"  VIX={price:.2f} (Tradier, symbol={sym})")
                return round(price, 2)
        except Exception:
            pass

    # Fallback: yfinance (still needed if Tradier sandbox doesn't carry VIX)
    try:
        import yfinance as yf
        hist = yf.Ticker("^VIX").history(period="2d")
        if not hist.empty:
            price = round(float(hist["Close"].iloc[-1]), 2)
            log(f"  VIX={price:.2f} (yfinance fallback)")
            return price
    except Exception as e:
        log(f"  VIX fetch error: {e}")
    return 20.0


def vix_to_deploy_pct(vix: float) -> float:
    if vix >= 25: return VIX_DEPLOY_HIGH
    if vix >= 20: return VIX_DEPLOY_ELEVATED
    if vix >= 15: return VIX_DEPLOY_MODERATE
    if vix >= 12: return VIX_DEPLOY_LOW
    return VIX_DEPLOY_VERY_LOW


def delta_range_for_vix(vix: float) -> tuple[float, float]:
    if vix >= 25: return DELTA_MIN_HIGH_VIX, DELTA_MAX_HIGH_VIX
    if vix >= 15: return DELTA_MIN_MID_VIX,  DELTA_MAX_MID_VIX
    return DELTA_MIN_LOW_VIX, DELTA_MAX_LOW_VIX


# ══════════════════════════════════════════════════════════════════════════════
# EARNINGS FILTER  (yfinance — Tradier has no earnings calendar)
# ══════════════════════════════════════════════════════════════════════════════

def has_earnings_in_window(ticker: str, dte: int) -> bool:
    if not FILTER_EARNINGS_IN_DTE_WINDOW:
        return False
    try:
        import yfinance as yf
        cal = yf.Ticker(ticker).calendar
        if cal is None or cal.empty:
            return False
        for col in cal.columns:
            val = cal.loc["Earnings Date", col] if "Earnings Date" in cal.index else None
            if val is None:
                continue
            ed       = pd.Timestamp(val).date()
            days_out = (ed - date.today()).days
            if 0 <= days_out <= dte:
                return True
    except Exception:
        pass
    return False


# ══════════════════════════════════════════════════════════════════════════════
# APPROVED TICKERS
# ══════════════════════════════════════════════════════════════════════════════

def load_approved_tickers() -> list[str]:
    if not APPROVED_STOCKS_URL:
        return []
    try:
        r  = requests.get(APPROVED_STOCKS_URL, timeout=15)
        df = pd.read_csv(StringIO(r.text), header=None)
        tickers = []
        for cell in df.values.flatten():
            cell = str(cell).strip().upper()
            if cell and cell not in ("NAN", "TICKER") and cell.isalpha():
                tickers.append(cell)
        log(f"  Loaded {len(tickers)} approved tickers")
        return tickers
    except Exception as e:
        log(f"  Error loading approved tickers: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# BLACK-SCHOLES  (fallback when Tradier greeks are null)
# ══════════════════════════════════════════════════════════════════════════════

def bs_call_delta(S, K, T, r, sigma) -> float:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    return float(norm.cdf(d1))


def bs_put_delta_abs(S, K, T, r, sigma) -> float:
    """Absolute put delta (0–1 range)."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    return float(norm.cdf(-d1))


# ══════════════════════════════════════════════════════════════════════════════
# TRADIER OPTIONS CHAIN HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_option_expirations(ticker: str) -> list[str]:
    resp = tradier_get("markets/options/expirations", {
        "symbol":          ticker,
        "includeAllRoots": "true",
    })
    exps = resp.get("expirations")
    if not exps or exps == "null":
        return []
    dates = exps.get("date", [])
    if isinstance(dates, str):
        dates = [dates]
    return sorted(dates)


def get_option_chain(ticker: str, expiration: str) -> list[dict]:
    resp = tradier_get("markets/options/chains", {
        "symbol":     ticker,
        "expiration": expiration,
        "greeks":     "true",
    })
    opts = resp.get("options")
    if not opts or opts == "null":
        return []
    chain = opts.get("option", [])
    if isinstance(chain, dict):
        chain = [chain]
    return chain


def _contract_delta(contract: dict, S: float, T: float, opt_type: str) -> float:
    """Delta from Tradier greeks, falling back to Black-Scholes. Always returns abs value."""
    greeks = contract.get("greeks") or {}
    raw    = greeks.get("delta")
    if raw is not None:
        try:
            return abs(float(raw))
        except (TypeError, ValueError):
            pass
    # BS fallback
    K      = float(contract.get("strike", 0))
    iv_raw = greeks.get("mid_iv") or greeks.get("smv_vol")
    iv     = max(float(iv_raw), 0.15) if iv_raw else 0.30
    if opt_type == "put":
        return bs_put_delta_abs(S, K, T, RF_RATE, iv)
    return bs_call_delta(S, K, T, RF_RATE, iv)


def _contract_iv(contract: dict) -> float:
    greeks = contract.get("greeks") or {}
    for key in ("mid_iv", "smv_vol", "bid_iv", "ask_iv"):
        v = greeks.get(key)
        if v:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return 0.0


def _contract_mid(contract: dict) -> float | None:
    bid  = float(contract.get("bid",  0) or 0)
    ask  = float(contract.get("ask",  0) or 0)
    last = float(contract.get("last", 0) or 0)
    if bid > 0 and ask > 0:
        return (bid + ask) / 2
    if ask  > 0: return ask
    if bid  > 0: return bid
    if last > 0: return last
    return None


# ══════════════════════════════════════════════════════════════════════════════
# OCC SYMBOL UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def extract_underlying(occ_symbol: str) -> str:
    m = re.match(r'^([A-Z.]+)\d{6}[CP]\d{8}$', occ_symbol)
    return m.group(1) if m else occ_symbol


def classify_symbol(occ_symbol: str) -> dict:
    m = re.match(r'^([A-Z.]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$', occ_symbol)
    if not m:
        return {"ticker": occ_symbol, "type": "unknown", "strike": 0, "expiry": "", "dte": 0}
    ticker   = m.group(1)
    yy, mm, dd = m.group(2), m.group(3), m.group(4)
    opt_type = "call" if m.group(5) == "C" else "put"
    strike   = int(m.group(6)) / 1000.0
    exp_date = f"20{yy}-{mm}-{dd}"
    dte      = (datetime.strptime(exp_date, "%Y-%m-%d") - datetime.today()).days
    return {"ticker": ticker, "type": opt_type, "strike": strike, "expiry": exp_date, "dte": dte}


# ══════════════════════════════════════════════════════════════════════════════
# UNIFIED STOCK SCREENING  (single pass — shared by CSP and LEAPS)
# ══════════════════════════════════════════════════════════════════════════════

def delta_range_for_stock(stock: dict) -> tuple[float, float, str]:
    """
    Per-stock CSP delta range driven by Bollinger Band position.
    Near lower BB  → aggressive  (0.25–0.35): stock oversold, mean-reversion likely
    Between BBs    → moderate    (0.15–0.25): partial pullback
    At/above mid   → conservative(0.08–0.15): at/above average, stay far OTM
    """
    price  = stock["price"]
    bb_lo  = stock["bb_lo"]
    bb_mid = stock["bb_mid"]
    near_threshold = bb_lo * (1 + CSP_BB_NEAR_LOWER_PCT / 100)

    if price <= near_threshold:
        return (CSP_DELTA_NEAR_LOWER_MIN, CSP_DELTA_NEAR_LOWER_MAX,
                f"aggressive δ {CSP_DELTA_NEAR_LOWER_MIN}–{CSP_DELTA_NEAR_LOWER_MAX} (near lower BB)")
    elif price < bb_mid:
        return (CSP_DELTA_MID_ZONE_MIN, CSP_DELTA_MID_ZONE_MAX,
                f"moderate δ {CSP_DELTA_MID_ZONE_MIN}–{CSP_DELTA_MID_ZONE_MAX} (between BBs)")
    else:
        return (CSP_DELTA_ABOVE_MID_MIN, CSP_DELTA_ABOVE_MID_MAX,
                f"conservative δ {CSP_DELTA_ABOVE_MID_MIN}–{CSP_DELTA_ABOVE_MID_MAX} (at/above mid BB)")


def screen_all_stocks(tickers: list[str]) -> list[dict]:
    """
    Single pass over approved tickers:
      • Fetches quote + history once per ticker (shared by CSP + LEAPS)
      • Computes all technicals: SMA20/50/200, BB, RSI
      • Applies shared hard filters: 200 SMA + earnings window
      • RSI gate is CSP-specific — applied later in screen_ticker_csp()
    Returns list of stock dicts ready for both CSP and LEAPS screening.
    """
    results = []
    for ticker in tickers:
        # Skip sector header rows from the approved list
        if not ticker.replace(".", "").isalpha() or len(ticker) > 6:
            continue

        quote = get_stock_quote(ticker)
        if not quote or quote["price"] <= 0:
            continue

        tech = compute_technicals(ticker, quote)
        if not tech:
            continue

        # Hard filter 1: 200 SMA (applies to both CSP and LEAPS)
        if FILTER_BELOW_200_SMA and tech["price"] < tech["sma200"]:
            log(f"  ✗ {ticker}: below 200d SMA")
            continue

        # Hard filter 2: Earnings in DTE window (applies to both)
        if has_earnings_in_window(ticker, MAX_DTE):
            log(f"  ✗ {ticker}: earnings in window")
            continue

        results.append({
            "ticker":  ticker,
            "price":   tech["price"],
            "day_chg": tech["day_chg"],
            "sma20":   tech["sma20"],
            "sma50":   tech["sma50"],
            "sma200":  tech["sma200"],
            "bb_lo":   tech["bb_lo"],
            "bb_mid":  tech["bb_mid"],
            "bb_up":   tech["bb_up"],
            "rsi":     tech.get("rsi", 50.0),
        })
        time.sleep(0.3)   # Tradier rate limit

    log(f"  {len(results)}/{len([t for t in tickers if t.replace('.','').isalpha() and len(t)<=6])} "
        f"tickers passed shared hard filters")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# CSP SCREENING
# ══════════════════════════════════════════════════════════════════════════════

def find_best_csp(ticker: str, S: float, delta_min: float, delta_max: float) -> dict | None:
    expirations = get_option_expirations(ticker)
    today       = datetime.today()
    candidates  = []

    for exp_str in expirations:
        try:
            dte = (datetime.strptime(exp_str, "%Y-%m-%d") - today).days
        except ValueError:
            continue
        if not (MIN_DTE <= dte <= MAX_DTE):
            continue

        T     = dte / 365.0
        chain = get_option_chain(ticker, exp_str)

        for c in chain:
            if c.get("option_type") != "put":
                continue
            oi  = int(c.get("open_interest", 0) or 0)
            if oi < MIN_OPEN_INTEREST:   # rejects OI=0 too — CSP needs real liquidity
                continue
            mid = _contract_mid(c)
            if not mid or mid <= 0:
                continue
            delta = _contract_delta(c, S, T, "put")
            if not (delta_min <= delta <= delta_max):
                continue

            K   = float(c.get("strike", 0))
            iv  = _contract_iv(c) * 100
            arr = (mid / K) * (365 / dte) * 100 if dte > 0 else 0

            candidates.append({
                "option_symbol": c.get("symbol", ""),
                "expiration":    exp_str,
                "dte":           dte,
                "strike":        K,
                "bid":           round(float(c.get("bid", 0) or 0), 2),
                "ask":           round(float(c.get("ask", 0) or 0), 2),
                "mid":           round(mid, 2),
                "premium_total": round(mid * 100, 2),
                "delta":         round(delta, 3),
                "iv":            round(iv, 1),
                "arr":           round(arr, 1),
                "breakeven":     round(K - mid, 2),
                "otm_pct":       round((S - K) / S * 100, 1),
                "max_risk":      round(K * 100, 2),
                "open_interest": oi,
            })

    in_range = [c for c in candidates if MIN_ARR <= c["arr"] <= MAX_ARR]
    if in_range:
        return max(in_range, key=lambda x: x["arr"])
    if candidates:
        return min(candidates, key=lambda x: abs(x["arr"] - MIN_ARR))
    return None


def score_csp(stock: dict, contract: dict) -> tuple[int, list[str]]:
    """
    Score 0–5.  Criteria:
      +1  Strike above 50d SMA          (medium-term uptrend support)
      +1  Price at/below 20d SMA        (short-term pullback to mean)
      +1  Healthy pullback today 0.5–5% (entry timing)
      +1  RSI < 50                      (actively oversold — replaces price<$100)
      +1  IV ≥ SCORE_IV_MIN_PCT         (premium elevated)
    """
    score, reasons = 0, []
    if SCORE_ABOVE_50_SMA and contract["strike"] > stock["sma50"]:
        score += 1; reasons.append("Strike > 50d SMA")
    if SCORE_BELOW_MID_BB and stock["price"] < stock["bb_mid"]:
        score += 1; reasons.append("Price below BB midline")
    if (SCORE_DOWN_TODAY
            and stock["day_chg"] < 0
            and SCORE_DOWN_TODAY_MIN_PCT <= abs(stock["day_chg"]) <= SCORE_DOWN_TODAY_MAX_PCT):
        score += 1; reasons.append(f"Down {abs(stock['day_chg']):.1f}% today")
    if stock.get("rsi", 99) < SCORE_RSI_OVERSOLD:
        score += 1; reasons.append(f"RSI {stock['rsi']:.1f} — actively oversold")
    if contract["iv"] >= SCORE_IV_MIN_PCT:
        score += 1; reasons.append(f"IV {contract['iv']:.0f}%")
    return score, reasons


def screen_ticker_csp(stock: dict) -> dict | None:
    """
    CSP screening using pre-computed stock data from screen_all_stocks().
    Applies CSP-specific hard filter (RSI ≥ 65) and BB-based delta range.
    """
    ticker = stock["ticker"]
    rsi    = stock.get("rsi", 50.0)

    # CSP-specific hard filter: RSI overbought
    if rsi >= CSP_RSI_OVERBOUGHT:
        log(f"  ✗ {ticker}: RSI={rsi:.1f} ≥ {CSP_RSI_OVERBOUGHT} — overbought, skip CSP")
        return None

    # Per-stock BB-based delta range (3 tiers)
    delta_min, delta_max, delta_label = delta_range_for_stock(stock)
    log(f"  CSP {ticker}: RSI={rsi:.1f}  {delta_label}")

    contract = find_best_csp(ticker, stock["price"], delta_min, delta_max)
    if not contract:
        log(f"    {ticker}: no CSP contract found")
        return None

    score, reasons = score_csp(stock, contract)
    if score < MIN_SCORE_TO_TRADE:
        log(f"    {ticker}: score {score} < {MIN_SCORE_TO_TRADE} — skip")
        return None

    log(f"    {ticker} ✅  score={score}  ARR={contract['arr']:.1f}%  "
        f"K=${contract['strike']:.0f}  δ={contract['delta']:.3f}")
    return {
        "ticker":        ticker,
        "stock_price":   stock["price"],
        "day_chg":       stock["day_chg"],
        "sma20":         stock["sma20"],
        "sma50":         stock["sma50"],
        "sma200":        stock["sma200"],
        "bb_mid":        stock["bb_mid"],
        "rsi":           rsi,
        "delta_label":   delta_label,
        "score":         score,
        "score_reasons": reasons,
        **contract,
    }


# ══════════════════════════════════════════════════════════════════════════════
# LEAPS SCREENING
# ══════════════════════════════════════════════════════════════════════════════

def get_beta(ticker: str) -> float:
    """3-month beta vs SPY computed from Tradier daily history."""
    try:
        start = (datetime.today() - timedelta(days=95)).strftime("%Y-%m-%d")
        end   = datetime.today().strftime("%Y-%m-%d")

        stock_df = get_stock_history(ticker, calendar_days=95)
        if stock_df.empty or len(stock_df) < 20:
            return 1.0

        spy_resp = tradier_get("markets/history", {
            "symbol": "SPY", "interval": "daily", "start": start, "end": end,
        })
        spy_hist = spy_resp.get("history")
        if not spy_hist or spy_hist == "null":
            return 1.0
        spy_days = spy_hist.get("day", [])
        if isinstance(spy_days, dict):
            spy_days = [spy_days]
        spy_df = pd.DataFrame(spy_days)
        if spy_df.empty or "close" not in spy_df.columns:
            return 1.0

        spy_df["close"] = spy_df["close"].astype(float)
        spy_df["date"]  = pd.to_datetime(spy_df["date"])

        # Align both series on date and compute returns
        stock_df = stock_df.copy()
        stock_df["date"] = pd.to_datetime(stock_df["date"])
        merged = pd.merge(
            stock_df[["date", "close"]].rename(columns={"close": "s"}),
            spy_df[["date", "close"]].rename(columns={"close": "m"}),
            on="date",
        ).sort_values("date")

        if len(merged) < 20:
            return 1.0

        sr  = merged["s"].pct_change().dropna()
        mr  = merged["m"].pct_change().dropna()
        cov = sr.cov(mr)
        var = mr.var()
        return round(float(cov / var), 2) if var != 0 else 1.0
    except Exception:
        return 1.0


def find_best_leaps(stock: dict) -> dict | None:
    ticker      = stock["ticker"]
    S           = stock["price"]
    today       = datetime.today()
    expirations = get_option_expirations(ticker)
    qualifying  = []

    for exp_str in expirations:
        try:
            dte = (datetime.strptime(exp_str, "%Y-%m-%d") - today).days
        except ValueError:
            continue
        if not (LEAPS_MIN_DTE <= dte <= LEAPS_MAX_DTE):
            continue

        T     = dte / 365.0
        chain = get_option_chain(ticker, exp_str)

        for c in chain:
            if c.get("option_type") != "call":
                continue
            oi = int(c.get("open_interest", 0) or 0)
            if 0 < oi < LEAPS_MIN_OI:   # 0 = data unavailable, allow through
                continue
            mid = _contract_mid(c)
            if not mid or mid <= 0:
                continue

            K      = float(c.get("strike", 0))
            greeks = c.get("greeks") or {}

            # Prefer Tradier's own delta; fall back to Black-Scholes
            raw_delta = greeks.get("delta")
            if raw_delta is not None:
                try:
                    delta_val = abs(float(raw_delta))
                    iv        = _contract_iv(c) or 0.45
                except (TypeError, ValueError):
                    delta_val = None
            else:
                delta_val = None

            if delta_val is None:
                iv_raw = greeks.get("mid_iv") or greeks.get("smv_vol")
                iv = float(iv_raw) if (iv_raw and float(iv_raw) >= 0.20) else 0.45
                delta_val = bs_call_delta(S, K, T, RF_RATE, iv)

            if not (LEAPS_MIN_DELTA <= delta_val <= LEAPS_MAX_DELTA):
                continue

            qualifying.append({
                "ticker":            ticker,
                "stock_price":       S,
                "day_chg":           stock["day_chg"],
                "sma20":             stock["sma20"],
                "sma50":             stock["sma50"],
                "sma200":            stock["sma200"],
                "expiration":        exp_str,
                "dte":               dte,
                "strike":            K,
                "bid":               round(float(c.get("bid",  0) or 0), 2),
                "ask":               round(float(c.get("ask",  0) or 0), 2),
                "mid":               round(mid, 2),
                "cost_per_contract": round(mid * 100, 2),
                "delta":             round(delta_val, 3),
                "iv":                round(iv * 100, 1),
                "otm_pct":           round((K - S) / S * 100, 1),
                "open_interest":     oi,
                "breakeven":         round(K + mid, 2),
                "pct_to_breakeven":  round((K + mid - S) / S * 100, 1),
                "option_symbol":     c.get("symbol", ""),
            })

    if not qualifying:
        return None
    chosen = min(qualifying, key=lambda x: abs(x["delta"] - LEAPS_TARGET_DELTA))
    log(f"    LEAPS: {chosen['expiration']} ${chosen['strike']:.0f} Call  "
        f"Δ={chosen['delta']:.3f}  DTE={chosen['dte']}  cost=${chosen['cost_per_contract']:.0f}")
    return chosen


def score_leaps(stock: dict, rsi: float) -> tuple[int, list[str]]:
    score, reasons = 0, []
    if stock["price"] > stock["sma200"]:
        score += 1; reasons.append("Above 200d SMA ✅")
    if stock["price"] > stock["sma50"]:
        score += 1; reasons.append("Above 50d SMA ✅")
    if rsi < LEAPS_RSI_OVERBOUGHT:
        score += 1; reasons.append(f"RSI({LEAPS_RSI_PERIOD}) = {rsi:.1f} — not overbought ✅")
    return score, reasons


def screen_ticker_leaps(stock: dict) -> dict | None:
    """
    LEAPS screening using pre-computed stock data from screen_all_stocks().
    Beta is still computed here (LEAPS-specific, not needed for CSP).
    """
    ticker = stock["ticker"]
    rsi    = stock.get("rsi", 50.0)
    log(f"  LEAPS {ticker}: RSI={rsi:.1f}")

    beta     = get_beta(ticker)
    contract = find_best_leaps(stock)
    if not contract:
        return None

    leaps_score, leaps_reasons = score_leaps(stock, rsi)
    if leaps_score < LEAPS_MIN_SCORE:
        log(f"    {ticker}: LEAPS score {leaps_score} < {LEAPS_MIN_SCORE} — skip")
        return None

    log(f"    {ticker} LEAPS ✅  score={leaps_score}/3  Δ={contract['delta']:.3f}  cost=${contract['cost_per_contract']:.0f}")
    return {**contract, "leaps_score": leaps_score, "leaps_reasons": leaps_reasons,
            "rsi": rsi, "beta": beta}


# ══════════════════════════════════════════════════════════════════════════════
# POSITION MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

def place_order(option_symbol: str, underlying: str, side: str,
                qty: int, fallback_price: float) -> tuple[bool, dict]:
    """Place a limit order at the live mid-price (Tradier quote), fallback to provided price."""
    live_mid = get_current_option_price(option_symbol)
    px       = round(live_mid if live_mid else fallback_price, 2)
    if px <= 0:
        log(f"    {option_symbol}: zero price — cannot place order")
        return False, {"error": "zero price"}

    data = {
        "class":         "option",
        "symbol":        underlying,
        "option_symbol": option_symbol,
        "side":          side,           # buy_to_open / buy_to_close / sell_to_open / sell_to_close
        "quantity":      str(abs(qty)),
        "type":          "limit",
        "price":         str(px),
        "duration":      "day",
    }
    log(f"    {side} {abs(qty)}x {option_symbol} @ ${px:.2f}")
    return tradier_post_order(data)


def manage_existing_positions(positions: list[dict]) -> list[dict]:
    """
    Profit exits → place order automatically.
    Loss exits   → post Discord alert only (trader decides manually).

    CSP rules (in priority order):
      Stop-loss    current_price >= avg_entry × 3.0   → ALERT (loss)
      50% capture  premium_captured >= 50%             → ORDER (profit)
      21-DTE exit  DTE ≤ 21 AND captured ≥ 0%         → ORDER (profit)
      21-DTE exit  DTE ≤ 21 AND -50% ≤ captured < 0%  → ALERT (small loss)

    LEAPS rules:
      Profit +5%   profit_pct >= 5%                   → ORDER (profit)
      Stop-loss    profit_pct <= -50%                  → ALERT (loss)
    """
    actions = []
    for pos in positions:
        sym       = pos["symbol"]
        qty       = pos["qty"]
        avg_entry = pos["avg_entry"]
        cur_price = get_current_option_price(sym)
        if cur_price is None:
            log(f"  {sym}: no price — skip")
            continue

        info     = classify_symbol(sym)
        opt_type = info.get("type", "unknown")
        ticker   = info.get("ticker", extract_underlying(sym))
        dte      = info.get("dte", 999)

        if qty < 0 and opt_type == "put":
            # ── Short put (CSP) ───────────────────────────────────────────────
            premium_captured = (avg_entry - cur_price) / avg_entry if avg_entry > 0 else 0
            loss_mult        = (cur_price - avg_entry) / avg_entry if avg_entry > 0 else 0
            pnl              = round((avg_entry - cur_price) * abs(qty) * 100, 2)
            log(f"  {sym} CSP: entry=${avg_entry:.2f}  cur=${cur_price:.2f}  "
                f"captured={premium_captured*100:.1f}%  DTE={dte}")

            close_reason = None
            is_loss      = False

            # Rule — Stop-loss: option costs ≥ 3× what we received (loss = 2× premium)
            if loss_mult >= CSP_STOP_LOSS_MULT:
                close_reason = f"STOP-LOSS (loss={loss_mult*100:.0f}% of premium)"
                is_loss      = True

            # Rule — 50% premium captured (always a profit)
            elif premium_captured >= CSP_CLOSE_PREMIUM_PCT:
                close_reason = f"50% premium captured ({premium_captured*100:.0f}%)"

            # Rule — 21-DTE exit (profit if captured ≥ 0, small loss if < 0)
            elif dte <= CSP_DTE_EXIT and premium_captured >= -CSP_CLOSE_PREMIUM_PCT:
                close_reason = f"21-DTE time exit (DTE={dte}, captured={premium_captured*100:.0f}%)"
                is_loss      = (premium_captured < 0)

            if close_reason:
                if is_loss:
                    # Loss exit → alert only, no order
                    log(f"    → ⚠️  Loss alert (no order): {close_reason}")
                    post_loss_alert(sym, "CSP", "buy_to_close", int(abs(qty)),
                                    avg_entry, cur_price, pnl,
                                    premium_captured * 100, close_reason)
                    actions.append({
                        "symbol": sym, "action": "alert_csp", "reason": close_reason,
                        "pnl": pnl, "ok": None, "alerted": True,
                    })
                else:
                    # Profit exit → place order
                    log(f"    → Closing (profit): {close_reason}")
                    ok, resp = place_order(sym, ticker, "buy_to_close", int(abs(qty)), cur_price)
                    actions.append({
                        "symbol": sym, "action": "close_csp", "reason": close_reason,
                        "pnl": pnl, "ok": ok,
                    })
            else:
                log(f"    → Holding")

        elif qty > 0 and opt_type == "call":
            # ── Long call (LEAPS) ─────────────────────────────────────────────
            profit_pct = (cur_price - avg_entry) / avg_entry if avg_entry > 0 else 0
            pnl        = round((cur_price - avg_entry) * qty * 100, 2)
            log(f"  {sym} LEAPS: entry=${avg_entry:.2f}  cur=${cur_price:.2f}  "
                f"P&L={profit_pct*100:+.1f}%")

            close_reason = None
            is_loss      = False

            # Rule — Profit target: +5%
            if profit_pct >= LEAPS_CLOSE_PROFIT_PCT:
                close_reason = f"profit target (+{profit_pct*100:.0f}% ≥ +{LEAPS_CLOSE_PROFIT_PCT*100:.0f}%)"

            # Rule — Stop-loss: −50%
            elif profit_pct <= -LEAPS_STOP_LOSS_PCT:
                close_reason = f"stop-loss ({profit_pct*100:.0f}% ≤ -{LEAPS_STOP_LOSS_PCT*100:.0f}%)"
                is_loss      = True

            if close_reason:
                if is_loss:
                    # Loss exit → alert only, no order
                    log(f"    → ⚠️  Loss alert (no order): {close_reason}")
                    post_loss_alert(sym, "LEAPS", "sell_to_close", int(qty),
                                    avg_entry, cur_price, pnl,
                                    profit_pct * 100, close_reason)
                    actions.append({
                        "symbol": sym, "action": "alert_leaps", "reason": close_reason,
                        "pnl": pnl, "ok": None, "alerted": True,
                    })
                else:
                    # Profit exit → place order
                    log(f"    → Closing (profit): {close_reason}")
                    ok, resp = place_order(sym, ticker, "sell_to_close", int(qty), cur_price)
                    actions.append({
                        "symbol": sym, "action": "close_leaps", "reason": close_reason,
                    "pnl": round((cur_price - avg_entry) * qty * 100, 2),
                    "ok": ok,
                })
            else:
                log(f"    → Holding")

    return actions


# ══════════════════════════════════════════════════════════════════════════════
# TRADE EXECUTION
# ══════════════════════════════════════════════════════════════════════════════

def execute_leaps_trades(leaps_list: list[dict], portfolio_value: float,
                          budget_override: float | None = None) -> list[dict]:
    budget    = budget_override if budget_override is not None else portfolio_value * LEAPS_MAX_PORTFOLIO_PCT
    remaining = budget
    executed  = []
    log(f"  LEAPS budget: ${budget:,.0f}")

    for trade in leaps_list:
        sym    = trade.get("option_symbol", "")
        ticker = trade["ticker"]
        cost   = trade["cost_per_contract"]
        if not sym:
            log(f"    {ticker}: no option symbol — skip"); continue
        if remaining < cost:
            log(f"    {ticker}: cost ${cost:.0f} > remaining ${remaining:.0f} — skip"); continue

        ok, resp = place_order(sym, ticker, "buy_to_open", 1, trade["mid"])
        if ok:
            remaining -= cost
            log(f"    {ticker} placed — remaining budget ${remaining:,.0f}")
        else:
            log(f"    {ticker} FAILED: {resp}")
        executed.append({"ticker": ticker, "ok": ok, "cost": cost, "response": resp})

    return executed


def execute_csp_trades(csp_list: list[dict], option_buying_power: float,
                       open_positions: list[dict] | None = None) -> list[dict]:
    available = option_buying_power
    executed  = []
    log(f"  CSP buying power: ${available:,.0f}")

    # #5 — Build set of underlyings already holding a short put
    existing_csp_underlyings: set[str] = set()
    if open_positions:
        for pos in open_positions:
            info = classify_symbol(pos["symbol"])
            if info.get("type") == "put" and float(pos["qty"]) < 0:
                existing_csp_underlyings.add(info.get("ticker", ""))
    if existing_csp_underlyings:
        log(f"  Underlyings with existing CSP: {sorted(existing_csp_underlyings)}")

    # Track underlyings opened this run to avoid double-opening in same session
    opened_this_run: set[str] = set()

    for trade in sorted(csp_list, key=lambda x: x["score"], reverse=True):
        sym        = trade.get("option_symbol", "")
        ticker     = trade["ticker"]
        collateral = trade["strike"] * 100

        if not sym:
            log(f"    {ticker}: no option symbol — skip"); continue

        # #5 — One CSP per underlying
        if ticker in existing_csp_underlyings or ticker in opened_this_run:
            log(f"    {ticker}: CSP already open for this underlying — skip"); continue

        if available < collateral:
            log(f"    {ticker}: collateral ${collateral:.0f} > available ${available:.0f} — skip"); continue

        ok, resp = place_order(sym, ticker, "sell_to_open", 1, trade["mid"])
        if ok:
            available -= collateral
            opened_this_run.add(ticker)
            log(f"    {ticker} CSP placed — remaining BP ${available:,.0f}")
        else:
            log(f"    {ticker} CSP FAILED: {resp}")
        executed.append({"ticker": ticker, "ok": ok, "response": resp})

    return executed


# ══════════════════════════════════════════════════════════════════════════════
# DISCORD HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def post_loss_alert(sym: str, strategy: str, side: str, qty: int,
                    avg_entry: float, cur_price: float,
                    pnl: float, pnl_pct: float, reason: str):
    """
    Post a manual-action-required alert to Discord for loss exits.
    No order is placed — the trader decides whether and when to close.
    """
    pos_str  = _fmt_position(sym)
    s        = "+" if pnl >= 0 else ""
    action   = "BUY TO CLOSE" if side == "buy_to_close" else "SELL TO CLOSE"
    color    = 0xE74C3C   # red

    discord_post({"embeds": [{
        "title":       f"⚠️  Manual Action Required — {strategy} Loss Alert [TPT]",
        "description": "\n".join([
            f"**Position:** `{pos_str}`  (qty: {qty:+.0f})",
            f"**Entry:** ${avg_entry:.2f}  →  **Current:** ${cur_price:.2f}",
            f"**Unrealized P&L:** {s}${pnl:.2f}  ({s}{pnl_pct:.1f}%)",
            "",
            f"**Trigger:** {reason}",
            "",
            f"**Suggested action:** `{action} {abs(qty)} contract(s) at market`",
            "_No order placed — awaiting your decision._",
        ]),
        "color":  color,
        "footer": {"text": f"TPT Agent  |  {datetime.now().strftime('%Y-%m-%d %H:%M PT')}"},
    }]})
    log(f"    → ⚠️  Loss alert posted to Discord (no order placed)")


def discord_post(payload: dict) -> bool:
    try:
        r = requests.post(BETA_AI_TRADES_WEBHOOK, json=payload, timeout=10)
        return r.status_code in (200, 204)
    except Exception as e:
        log(f"  Discord error: {e}")
        return False


def _fmt_exp(s: str) -> str:
    """MM/DD/YY — kept for internal use."""
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%m/%d/%y")
    except Exception:
        return s


def _fmt_exp_short(s: str) -> str:
    """MonYY — 5 chars, e.g. Jun26, Jan28. Fits Discord embeds (LEAPS)."""
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%b%y")
    except Exception:
        return s[:5]


def _fmt_exp_mmdd(s: str) -> str:
    """MM/DD format, e.g. 07/17. For CSP table."""
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%m/%d")
    except Exception:
        return s[:5]


def _fmt_position(occ_symbol: str) -> str:
    """
    Convert full OCC symbol to compact 18-char display.
    AMD260626P00410000  →  AMD $410P Jun26
    ANET280121C00105000 →  ANET $105C Jan28
    """
    info = classify_symbol(occ_symbol)
    if not info or info.get("type") == "unknown":
        return occ_symbol[:18]
    ticker  = info["ticker"]
    strike  = info["strike"]
    pc      = "C" if info["type"] == "call" else "P"
    exp_str = _fmt_exp_short(info.get("expiry", ""))
    k_str   = f"${int(strike)}" if strike == int(strike) else f"${strike:.1f}"
    return f"{ticker} {k_str}{pc} {exp_str}"


def build_csp_embed(trade: dict, rank: int) -> dict:
    arrow     = "🔻" if trade["day_chg"] < 0 else "🔼"
    arr_stars = "🔥🔥🔥" if trade["arr"] >= 60 else ("🔥🔥" if trade["arr"] >= 50 else "🔥")
    score_str = "⭐" * trade["score"] + "☆" * (5 - trade["score"])
    conviction = "  🏆 HIGH CONVICTION" if trade["score"] >= SIZE_UP_SCORE else ""
    return {
        "title":  f"#{rank}  {trade['ticker']}  —  CSP Trade Idea [TPT]{conviction}",
        "color":  0x27AE60,
        "fields": [
            {"name": "📌 Action",       "value": f"**SELL TO OPEN** `{trade['expiration']} ${trade['strike']:.0f} Put`", "inline": False},
            {"name": "​", "value": "​", "inline": False},
            {"name": "💵 Stock Price",  "value": f"**${trade['stock_price']:.2f}** {arrow} {abs(trade['day_chg']):.2f}% today", "inline": True},
            {"name": "🎯 Strike / OTM", "value": f"**${trade['strike']:.0f}**  ({abs(trade['otm_pct']):.1f}% OTM)", "inline": True},
            {"name": "📅 DTE",          "value": f"**{trade['dte']} days**  (exp {trade['expiration']})", "inline": True},
            {"name": "💰 Bid / Ask",    "value": f"${trade['bid']:.2f} / ${trade['ask']:.2f}", "inline": True},
            {"name": "💲 Mid Premium",  "value": f"**${trade['mid']:.2f}**  (${trade['premium_total']:.0f}/contract)", "inline": True},
            {"name": "🛡️ Breakeven",   "value": f"**${trade['breakeven']:.2f}**", "inline": True},
            {"name": "⚠️ Max Risk",     "value": f"${trade['max_risk']:,.0f} / contract", "inline": True},
            {"name": "📐 Delta (abs)",  "value": f"**{trade['delta']:.3f}**", "inline": True},
            {"name": "📊 IV",           "value": f"**{trade['iv']:.1f}%**", "inline": True},
            {"name": f"📈 ARR {arr_stars}", "value": f"**{trade['arr']:.1f}%**", "inline": True},
            {"name": f"⭐ Score  {score_str}", "value": "  •  ".join(trade.get("score_reasons", [])) or "—", "inline": False},
        ],
        "footer": {"text": "TPT Agent — Tradier Paper Trading  |  Wheel / CSP Strategy"},
    }


def build_leaps_embed(trade: dict, rank: int) -> dict:
    score_str = "⭐" * trade.get("leaps_score", 0) + "☆" * (3 - trade.get("leaps_score", 0))
    arrow     = "🔻" if trade["day_chg"] < 0 else "🔼"
    return {
        "title":  f"#{rank}  {trade['ticker']}  —  LEAPS Trade Idea [TPT]",
        "color":  0x8E44AD,
        "fields": [
            {"name": "📌 Action",       "value": f"**BUY TO OPEN** `{trade['expiration']} ${trade['strike']:.0f} Call`", "inline": False},
            {"name": "​", "value": "​", "inline": False},
            {"name": "💵 Stock Price",  "value": f"**${trade['stock_price']:.2f}** {arrow} {abs(trade['day_chg']):.2f}% today", "inline": True},
            {"name": "🎯 Strike / ITM", "value": f"**${trade['strike']:.0f}**  ({abs(trade['otm_pct']):.1f}% ITM)", "inline": True},
            {"name": "📅 DTE",          "value": f"**{trade['dte']} days**  (exp {trade['expiration']})", "inline": True},
            {"name": "💰 Bid / Ask",    "value": f"${trade['bid']:.2f} / ${trade['ask']:.2f}", "inline": True},
            {"name": "💲 Cost",         "value": f"**${trade['mid']:.2f}**/share  (${trade['cost_per_contract']:,.0f}/contract)", "inline": True},
            {"name": "📐 Delta",        "value": f"**{trade['delta']:.2f}**", "inline": True},
            {"name": "📊 IV",           "value": f"**{trade['iv']:.1f}%**", "inline": True},
            {"name": "🏁 Breakeven",    "value": f"**${trade['breakeven']:.2f}**  ({trade['pct_to_breakeven']:.1f}% above current)", "inline": True},
            {"name": f"⭐ Score  {score_str}", "value": "  •  ".join(trade.get("leaps_reasons", [])) or "—", "inline": False},
        ],
        "footer": {"text": "TPT Agent — Tradier Paper Trading  |  LEAPS Deep ITM Call Strategy"},
    }


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY POSTING
# ══════════════════════════════════════════════════════════════════════════════

def post_run_summary(opening_info: dict, vix: float, deploy_pct: float,
                     closed_actions: list[dict], csp_executed: list[dict],
                     leaps_executed: list[dict], closing_info: dict,
                     open_positions: list[dict]):
    opening_val  = opening_info["portfolio_value"]
    closing_val  = closing_info["portfolio_value"]
    closing_cash = closing_info["cash"]
    cash_pct     = (closing_cash / closing_val * 100) if closing_val else 0
    net_pnl      = closing_val - opening_val
    sign         = "+" if net_pnl >= 0 else ""

    lines = [
        f"**Opening Balance:** ${opening_val:,.2f}",
        f"**VIX:** {vix:.1f}  →  Deploy **{deploy_pct*100:.0f}%** of capital",
        "",
    ]
    profit_closes = [a for a in closed_actions if not a.get("alerted")]
    loss_alerts   = [a for a in closed_actions if a.get("alerted")]

    if profit_closes:
        lines.append("**📤 Closed Positions (profit exits):**")
        for a in profit_closes:
            pnl   = a.get("pnl", 0)
            s     = "+" if pnl >= 0 else ""
            flag  = "✅" if a.get("ok") else "❌"
            short = _fmt_position(a["symbol"])
            lines.append(f"  {flag} `{short}` — P&L: {s}${pnl:.2f}")
        lines.append("")
    if loss_alerts:
        lines.append("**⚠️ Loss Alerts (manual action required):**")
        for a in loss_alerts:
            pnl   = a.get("pnl", 0)
            s     = "+" if pnl >= 0 else ""
            short = _fmt_position(a["symbol"])
            lines.append(f"  ⚠️ `{short}` — P&L: {s}${pnl:.2f}  _(alert sent, no order placed)_")
        lines.append("")
    if csp_executed:
        lines.append("**📥 New CSP Positions:**")
        for e in csp_executed:
            lines.append(f"  {'✅' if e['ok'] else '❌'} `{e['ticker']}`")
        lines.append("")
    if leaps_executed:
        lines.append("**📥 New LEAPS Positions:**")
        for e in leaps_executed:
            lines.append(f"  {'✅' if e['ok'] else '❌'} `{e['ticker']}`  (cost ${e['cost']:,.0f})")
        lines.append("")
    lines += [
        f"**Closing Balance:** ${closing_val:,.2f}  ({sign}${abs(net_pnl):,.2f})",
        f"**Cash:** ${closing_cash:,.2f}  ({cash_pct:.1f}% of portfolio)",
    ]

    embed1 = {
        "title":       "📊  TPT Agent — Run Summary",
        "description": "\n".join(lines),
        "color":       0x2980B9,
        "footer":      {"text": f"Tradier Paper Trading  |  {datetime.now().strftime('%Y-%m-%d %H:%M PT')}"},
    }

    if open_positions:
        # Target ≤ 40 chars — Discord desktop embeds wrap at ~42 chars.
        # ENTRY and CUR removed: focus is profit/loss visibility only.
        # POSITION(16) + QTY(3) + P&L$(7) + P&L%(6) = 38 chars
        hdr  = f"{'POSITION':<16}  {'QTY':>3}  {'P&L $':>7}  {'P&L%':>6}"
        sep  = "─" * len(hdr)
        rows = [hdr, sep]
        total_pnl = 0
        for p in sorted(open_positions, key=lambda x: x.get("pnl_pct", 0), reverse=True):
            pos_str = _fmt_position(p["symbol"])
            pnl     = p.get("pnl", 0)
            pct     = p.get("pnl_pct", 0)
            s       = "+" if pnl >= 0 else ""
            rows.append(f"{pos_str:<16}  {p['qty']:>3.0f}  "
                        f"{s}${pnl:>5.0f}  {s}{pct:>5.1f}%")
            total_pnl += pnl
        rows.append(sep)
        s = "+" if total_pnl >= 0 else ""
        rows.append(f"{'TOTAL UNREALIZED P&L':>31}  {s}${total_pnl:>5.0f}")
        embed2 = {
            "title":       "📋  Open Positions [TPT]",
            "description": "```\n" + "\n".join(rows) + "\n```",
            "color":       0x27AE60 if total_pnl >= 0 else 0xE74C3C,
        }
        discord_post({"embeds": [embed1, embed2]})
    else:
        discord_post({"embeds": [embed1]})

    log("  ✓ Run summary posted")


def post_leaps_ideas(leaps_trades: list[dict], vix: float, vix_ok: bool):
    gate_desc = f"≤ {LEAPS_VIX_CALM_MAX:.0f} or ≥ {LEAPS_VIX_FEAR_MIN:.0f}"
    vix_str = (
        f"VIX = {vix:.1f} — ✅ LEAPS gate OPEN (gate: {gate_desc})"
        if vix_ok else
        f"VIX = {vix:.1f} — ❌ LEAPS gate CLOSED (gate: {gate_desc})"
    )
    discord_post({"embeds": [{
        "title":       "🎯  LEAPS Screening Criteria [TPT]",
        "description": "\n".join([
            f"**DTE Range:** {LEAPS_MIN_DTE}–{LEAPS_MAX_DTE} days",
            f"**Target Δ:** {LEAPS_TARGET_DELTA:.2f}  (range {LEAPS_MIN_DELTA:.2f}–{LEAPS_MAX_DELTA:.2f})",
            f"**Min Score:** {LEAPS_MIN_SCORE}/3",
            f"**{vix_str}**",
        ]),
        "color": 0x8E44AD,
    }]})

    if not (vix_ok and leaps_trades):
        return

    # LEAPS table: TICKER(6) STRIKE(6) Δ(2) EXP(8) COST(7) = 39 chars
    # Δ as 2-digit integer: 0.769 → 77
    # EXP in MM/DD/YY format: 01/21/28
    hdr  = f"{'TICKER':<6}  {'STRIKE':>6}  {'Δ':>2}  {'EXP':<8}  {'COST':>7}"
    sep  = "─" * len(hdr)
    rows = [hdr, sep]
    for t in leaps_trades:
        d = f"{int(round(t['delta'] * 100)):02d}"   # "77" — 2-digit integer
        rows.append(
            f"{t['ticker']:<6}  "
            f"${t['strike']:>5.0f}  {d:>2}  {_fmt_exp(t['expiration']):<8}  "
            f"${t['cost_per_contract']:>6,.0f}"
        )
    discord_post({"embeds": [{
        "title":       "📋  Summary — LEAPS Opportunities [TPT]",
        "description": "```\n" + "\n".join(rows) + "\n```",
        "color":       0x8E44AD,
        "footer":      {"text": "Δ=call delta (×100)  COST=per contract  target Δ=77"},
    }]})
    log("  ✓ LEAPS summary posted")


def post_csp_ideas(csp_trades: list[dict]):
    if not csp_trades:
        return
    # CSP table: TICKER(6) STRIKE(6) Δ(2) EXP(5) PREM(5) ARR(4) = 38 chars
    # Δ as 2-digit integer: 0.172 → 17  (consistent with LEAPS table)
    hdr  = f"{'TICKER':<6}  {'STRIKE':>6}  {'Δ':>2}  {'EXP':<5}  {'PREM':>6}  {'ARR':>4}"
    sep  = "─" * len(hdr)
    rows = [hdr, sep]
    for t in csp_trades:
        d = f"{int(round(t['delta'] * 100)):02d}"   # "17" — 2-digit integer
        rows.append(
            f"{t['ticker']:<6}  "
            f"${t['strike']:>5.0f}  {d:>2}  {_fmt_exp_mmdd(t['expiration']):<5}  "
            f"${t['mid']:>5.2f}  {t['arr']:>3.0f}%"
        )
    discord_post({"embeds": [{
        "title":       "📋  Summary — CSP Opportunities [TPT]",
        "description": "```\n" + "\n".join(rows) + "\n```",
        "color":       0x27AE60,
        "footer":      {"text": "Δ=put delta (×100, BB-adjusted)  PREM=mid/share  ARR=Ann. Return on Risk"},
    }]})
    log("  ✓ CSP summary posted")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RUN PIPELINE — 9 Phases
# ══════════════════════════════════════════════════════════════════════════════

def run():
    log("=" * 65)
    log("TPT AGENT — Run Start")
    log("=" * 65)

    # ── Phase 1: VIX + opening account state ─────────────────────────────────
    log("Phase 1: VIX + account state")
    vix              = get_vix()
    deploy_pct       = vix_to_deploy_pct(vix)
    # CSP delta is now per-stock (BB-based) — no global delta_range_for_vix() needed
    # LEAPS VIX gate: ON when VIX ≤ 18 (calm) OR VIX ≥ 21 (fear/opportunity)
    # Zone 18–21 excluded — moderate stress, IV neither cheap nor justified
    vix_ok_leaps     = (vix <= LEAPS_VIX_CALM_MAX) or (vix >= LEAPS_VIX_FEAR_MIN)
    vix_gate_desc    = (f"VIX ≤ {LEAPS_VIX_CALM_MAX:.0f} or ≥ {LEAPS_VIX_FEAR_MIN:.0f}")
    opening_info     = get_account_info()
    portfolio_value  = opening_info["portfolio_value"]
    log(f"  VIX={vix:.1f}  deploy={deploy_pct*100:.0f}%  portfolio=${portfolio_value:,.2f}")
    log(f"  LEAPS gate: {'✅ ON' if vix_ok_leaps else '❌ OFF'} ({vix_gate_desc})")

    if portfolio_value <= 0:
        log("  ⚠️  Portfolio value unreadable — aborting")
        return

    # ── Phase 2: Manage existing positions ───────────────────────────────────
    log("Phase 2: Manage existing positions")
    positions      = get_open_positions()
    log(f"  {len(positions)} open positions")
    closed_actions = manage_existing_positions(positions)

    # ── Phase 3: Refresh capital after closes ────────────────────────────────
    log("Phase 3: Refresh capital")
    time.sleep(2)
    refreshed        = get_account_info()
    portfolio_value  = refreshed["portfolio_value"]
    opt_buying_power = refreshed["option_buying_power"]
    deploy_capital   = portfolio_value * deploy_pct
    csp_capital      = min(opt_buying_power, deploy_capital)
    leaps_budget     = portfolio_value * LEAPS_MAX_PORTFOLIO_PCT
    log(f"  Portfolio=${portfolio_value:,.2f}  OBP=${opt_buying_power:,.2f}  "
        f"CSP cap=${csp_capital:,.2f}  LEAPS budget=${leaps_budget:,.2f}")

    # ── Phase 4: Load tickers + unified stock screening ──────────────────────
    log("Phase 4: Load tickers + unified stock screening")
    tickers = load_approved_tickers()
    if not tickers:
        log("  No tickers — aborting")
        return
    # Single pass: one quote + one history call per ticker, shared hard filters
    stock_universe = screen_all_stocks(tickers)
    if not stock_universe:
        log("  No stocks passed hard filters — aborting")
        return
    log(f"  {len(stock_universe)} stocks ready for CSP + LEAPS screening")

    # ── Phase 5: CSP scoring + contract selection ─────────────────────────────
    log("Phase 5: CSP screening")
    csp_candidates = []
    for stock in stock_universe:
        result = screen_ticker_csp(stock)
        if result:
            csp_candidates.append(result)
    # Sort: score DESC → ARR/Delta ratio DESC (normalized risk-adjusted return)
    #       → DTE DESC (more time cushion) → ARR DESC (final tie-breaker)
    # ARR/Delta ratio rewards higher premium per unit of directional risk taken,
    # correctly ranking e.g. delta=0.14 ARR=69% above delta=0.20 ARR=47%.
    csp_candidates.sort(key=lambda x: (
        -x["score"],
        -(x["arr"] / x["delta"]) if x.get("delta", 0) > 0 else 0,
        -x.get("dte", 0),
        -x["arr"],
    ))
    top_csps = csp_candidates[:TOP_N_CSP]
    log(f"  {len(csp_candidates)} qualified → top {len(top_csps)} selected: "
        f"{[t['ticker'] for t in top_csps]}")

    # ── Phase 6: LEAPS scoring + contract selection ───────────────────────────
    log("Phase 6: LEAPS screening")
    leaps_candidates = []
    if vix_ok_leaps:
        for stock in stock_universe:
            result = screen_ticker_leaps(stock)
            if result:
                leaps_candidates.append(result)
            time.sleep(0.3)   # extra pause for LEAPS chain fetches
        leaps_candidates.sort(key=lambda x: (-x.get("leaps_score", 0), x.get("rsi", 99)))
        top_leaps = leaps_candidates[:TOP_N_LEAPS]
        log(f"  {len(leaps_candidates)} qualified → top {len(top_leaps)} selected: "
            f"{[t['ticker'] for t in top_leaps]}")
    else:
        top_leaps = []
        log(f"  VIX {vix:.1f} in excluded zone ({LEAPS_VIX_CALM_MAX:.0f}–{LEAPS_VIX_FEAR_MIN:.0f}) — skipping LEAPS")

    # ── Phase 7: Execute LEAPS ───────────────────────────────────────────────
    log("Phase 7: Execute LEAPS")
    leaps_executed = []
    if vix_ok_leaps and top_leaps:
        leaps_executed = execute_leaps_trades(top_leaps, portfolio_value, leaps_budget)

    # ── Phase 8: Execute CSPs ────────────────────────────────────────────────
    log("Phase 8: Execute CSPs")
    csp_executed = []
    if top_csps and csp_capital > 0:
        # Pass current positions for one-per-underlying dedup (#5)
        csp_executed = execute_csp_trades(top_csps, csp_capital, positions)

    # ── Phase 9: Final state + Discord ───────────────────────────────────────
    log("Phase 9: Post summary to Discord")
    time.sleep(3)
    closing_info    = get_account_info()
    open_positions  = get_open_positions()

    # Enrich positions with current price and P&L
    enriched = []
    for pos in open_positions:
        cur = get_current_option_price(pos["symbol"]) or pos["avg_entry"]
        qty = pos["qty"]
        avg = pos["avg_entry"]
        pnl = (avg - cur) * abs(qty) * 100 if qty < 0 else (cur - avg) * qty * 100
        pnl_pct = (pnl / (avg * abs(qty) * 100) * 100) if avg > 0 else 0
        enriched.append({**pos, "current_price": cur,
                          "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 1)})

    post_run_summary(opening_info, vix, deploy_pct, closed_actions,
                     csp_executed, leaps_executed, closing_info, enriched)
    post_leaps_ideas(top_leaps, vix, vix_ok_leaps)
    post_csp_ideas(top_csps)

    log("=" * 65)
    log("TPT AGENT — Run Complete")
    log("=" * 65)


if __name__ == "__main__":
    run()
