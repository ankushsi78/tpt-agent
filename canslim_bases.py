#!/usr/bin/env python3
"""
CAN SLIM base detector + "Watchlist Status" tab for the CANSLIM Screener Google Sheet.

This is a bar-by-bar port of tradingview/canslim_bases.pine (v2.4): cup with handle, double bottom
and flat base, a frozen pivot while a base is active, and the same BUY / BO? / EXT / failed events.
Keep the two in sync — the defaults live in canslim_config.yaml under `bases:`.

Tickers come from the sheet's "My Watchlist" tab (column A, one ticker per row). The tab is created
from `watchlist.tickers` in the config the first time; after that, edit the list in the sheet.

Usage:
  python3 canslim_bases.py [--config canslim_config.yaml] [--no-sheet] [--tickers NVDA,AMD]
"""

import argparse
import datetime as dt
import math
import os
import sys

import numpy as np
import pandas as pd
import yaml
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
INPUT_TAB = "My Watchlist"
STATUS_TAB = "Watchlist Status"


def log(msg):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


# ── Detector (port of the Pine script) ────────────────────────────────────────

def detect(df, p):
    """Run the base state machine over a daily OHLCV frame. Returns (final_state, events)."""
    h, l, c, v = (df[k].to_numpy(float) for k in ("High", "Low", "Close", "Volume"))
    n = len(df)
    dates = df.index
    avg_vol = pd.Series(v).rolling(50).mean().to_numpy()
    sma200 = pd.Series(c).rolling(200).mean().to_numpy()

    def prior_low(t, off):
        return l[t - off - 63:t - off + 1].min()

    st = {"type": "", "pivot": np.nan, "inval": np.nan, "bar": None, "crossed": False, "weak": False,
          "attempts": 0}
    last_end_bar, last_end_piv = 0, np.nan
    sl_val, sl_bar = [], []                       # confirmed swing lows (double bottom)
    events = []
    k = p["dbK"]

    for t in range(n):
        trend_ok = (not p["trendFilter"]) or (not np.isnan(sma200[t]) and c[t] > sma200[t])

        # ── cup with handle
        cup = None
        if t > p["cupMaxLen"] + p["hMaxLen"] + 80:
            win = h[t - p["hMaxLen"]:t + 1]
            r_off = int(np.argmax(win[::-1]))                            # bars since the right-side high
            R = h[t - r_off]
            if p["hMinLen"] <= r_off <= p["hMaxLen"]:
                h_low = l[t - r_off + 1:t + 1].min()
                h_avg_vol = v[t - r_off + 1:t + 1].mean()
                h_depth = (R - h_low) / R * 100
                lip = R * (1 - p["lipTol"] / 100)
                lowest, low_off, l_off, inner_hi = R, r_off, -1, 0.0
                for i in range(r_off + 1, r_off + p["cupMaxLen"] + 1):
                    if (R - lowest) / R * 100 >= p["cupMinDepth"] and h[t - i] >= lip:
                        l_off = i
                        break
                    inner_hi = max(inner_hi, h[t - i])
                    if l[t - i] < lowest:
                        lowest, low_off = l[t - i], i
                    if (lip - lowest) / lip * 100 > p["cupMaxDepth"]:
                        break
                if l_off > 0:
                    L = h[t - l_off]
                    max_off = min(l_off + 10, r_off + p["cupMaxLen"])
                    for j in range(l_off + 1, max_off + 1):
                        if h[t - j] > L:
                            L, l_off = h[t - j], j
                    depth = (L - lowest) / L * 100
                    right_ok = L * (1 - p["lipTol"] / 100) <= R <= L * (1 + p["lipTol"] / 100) and inner_hi <= max(L, R)
                    upper_ok = (not p["hUpperHalf"]) or h_low >= lowest + 0.5 * (L - lowest)
                    vol_ok = (not p["hVolDry"]) or h_avg_vol < avg_vol[t]
                    p_low = prior_low(t, l_off)
                    adv_ok = (L - p_low) / p_low * 100 >= p["priorAdv"]
                    if (l_off - r_off >= p["cupMinLen"] and p["cupMinDepth"] <= depth <= p["cupMaxDepth"] and right_ok
                            and h_depth <= p["hMaxDepth"] and upper_ok and vol_ok and adv_ok and c[t] < R + p["pivotAdd"]):
                        cup = {"pivot": R + p["pivotAdd"], "inval": lowest + 0.5 * (L - lowest)}

        # ── double bottom (swing lows confirmed k bars later, like ta.pivotlow)
        if t >= 2 * k:
            ctr = t - k
            if l[ctr] < l[ctr - k:ctr].min() and l[ctr] <= l[ctr + 1:t + 1].min():
                sl_val.append(l[ctr]); sl_bar.append(ctr)
                if len(sl_val) > 12:
                    sl_val.pop(0); sl_bar.pop(0)
        db = None
        ns = len(sl_val)
        if ns >= 2 and t > p["dbMaxSpan"] + p["dbLeftLook"] + 70:
            s2v, s2b = sl_val[-1], sl_bar[-1]
            o2 = t - s2b
            if o2 <= 30 and c[t] > s2v:
                for j in range(ns - 2, max(0, ns - 8) - 1, -1):
                    s1v, s1b = sl_val[j], sl_bar[j]
                    o1 = t - s1b
                    if s2b - s1b < p["dbMinGap"] or o1 > p["dbMaxSpan"]:
                        continue
                    tol_ok = s1v * (1 - p["dbUnder"] / 100) <= s2v <= s1v * (1 + p["dbOver"] / 100)
                    mid = h[t - o1 + 1:t - o2]                  # bars strictly between the lows
                    M = mid.max()
                    low_between = l[t - o1 + 1:t - o2].min()
                    left = h[t - o1 - p["dbLeftLook"]:t - o1]
                    H0 = left.max()
                    h0_off = o1 + (len(left) - int(np.argmax(left)))
                    hi_since = h[t - o2 + 1:t + 1].max()
                    lows = min(s1v, s2v)
                    depth = (H0 - lows) / H0 * 100
                    p_low = prior_low(t, h0_off)
                    adv_ok = (H0 - p_low) / p_low * 100 >= p["priorAdv"]
                    if (tol_ok and low_between >= lows and M >= max(s1v, s2v) * (1 + p["dbMinMid"] / 100) and M < H0
                            and p["dbMinDepth"] <= depth <= p["dbMaxDepth"] and h0_off >= p["dbMinLen"] and adv_ok
                            and hi_since < M + p["pivotAdd"]):
                        db = {"pivot": M + p["pivotAdd"], "inval": lows}
                        break

        # ── flat base
        flat = None
        max_back = min(p["flatMaxLen"] - 1, t - last_end_bar - 1)
        if t > p["flatMaxLen"] + 70 and max_back >= p["flatMinLen"] - 1:
            hh, hh_off, ll, win_end = h[t], 0, l[t], 0
            for i in range(1, max_back + 1):
                nh, nl = max(hh, h[t - i]), min(ll, l[t - i])
                if (nh - nl) / nh * 100 > p["flatMaxDepth"]:
                    break
                if h[t - i] > hh:
                    hh_off = i
                hh, ll, win_end = nh, nl, i
            start_off = hh_off
            for i in range(win_end, hh_off - 1, -1):
                if h[t - i] >= hh * (1 - p["flatNearTop"] / 100):
                    start_off = i
                    break
            f_len = start_off + 1
            if f_len >= p["flatMinLen"] and hh_off >= p["flatHighAge"]:
                half = f_len // 2
                seg = c[t - start_off:t + 1][::-1]               # offset 0 first
                drift = abs(seg[:half].mean() / seg[half:].mean() - 1) * 100
                p_low = prior_low(t, start_off)
                if drift <= p["flatSlopeMax"] and (hh - p_low) / p_low * 100 >= p["priorAdv"] and c[t] < hh + p["pivotAdd"]:
                    flat = {"pivot": hh + p["pivotAdd"], "inval": hh * (1 - p["flatMaxDepth"] / 100)}

        # ── state machine
        ev_piv = np.nan
        if st["type"]:
            if c[t] > st["pivot"]:
                in_zone = c[t] <= st["pivot"] * (1 + p["buyZonePct"] / 100)
                st["crossed"] = True
                ev_piv = st["pivot"]
                if in_zone and v[t] >= p["volMult"] * avg_vol[t - 1]:
                    events.append((dates[t], "BUY", st["type"], st["pivot"], v[t] / avg_vol[t - 1]))
                    st["type"] = ""
                elif not in_zone:
                    events.append((dates[t], "EXT", st["type"], st["pivot"], v[t] / avg_vol[t - 1]))
                    st["type"] = ""
                elif not st["weak"]:
                    events.append((dates[t], "BO?", st["type"], st["pivot"], v[t] / avg_vol[t - 1]))
                    st["weak"] = True
            elif c[t] < st["inval"] or t - st["bar"] > p["actMaxBars"]:
                events.append((dates[t], "FAILED" if c[t] < st["inval"] else "RETIRED", st["type"], st["pivot"], None))
                st["type"] = ""
            elif h[t] > st["pivot"]:
                st["crossed"] = True
                st["attempts"] += 1
            if not st["type"]:
                last_end_piv = ev_piv if not np.isnan(ev_piv) else st["pivot"]
                st["pivot"] = np.nan
                last_end_bar = t

        cand = cup and ("Cup with Handle", cup) or db and ("Double Bottom", db) or flat and ("Flat Base", flat)
        if cand:
            same = (not np.isnan(last_end_piv) and abs(cand[1]["pivot"] / last_end_piv - 1) < 0.01
                    and t - last_end_bar < 15)
            if not st["type"] and last_end_bar != t and trend_ok and not same:
                st.update(type=cand[0], pivot=cand[1]["pivot"], inval=cand[1]["inval"], bar=t,
                          crossed=False, weak=False, attempts=0)
                events.append((dates[t], "DETECTED", cand[0], cand[1]["pivot"], None))

    st["days"] = (n - 1 - st["bar"]) if st["type"] else None
    return st, events


# ── Status table ──────────────────────────────────────────────────────────────

def status_row(tkr, df, p):
    st, events = detect(df, p)
    c, h = df["Close"].to_numpy(float), df["High"].to_numpy(float)
    close = c[-1]
    vol_ratio = df["Volume"].iloc[-1] / df["Volume"].iloc[-51:-1].mean()
    sma50, sma200 = df["Close"].tail(50).mean(), df["Close"].tail(200).mean()
    off_high = (1 - close / h[-252:].max()) * 100
    last_sig = next((e for e in reversed(events) if e[1] != "DETECTED"), None)
    row = {"Ticker": tkr, "Close": round(close, 2), "% Off 52w High": round(off_high, 1),
           "Vol vs 50d": round(vol_ratio, 2),
           "Trend": ("Above 50d & 200d" if close > sma50 and close > sma200 else
                     "Above 200d only" if close > sma200 else "Below 200d")}
    if st["type"]:
        piv = st["pivot"]
        vs = (close / piv - 1) * 100
        if close > piv:
            status, note = "Above pivot (light vol)", "Closed above the buy point without volume — needs a ≥1.4× volume day to confirm"
        elif vs >= -p["nearPct"]:
            status, note = "Near pivot", f"Within {p['nearPct']:g}% of the buy point — watch for a volume breakout"
        else:
            status, note = "In base", "Base forming — wait for price to approach the buy point"
        row.update({"Status": status, "Base": st["type"], "Pivot (Buy Point)": round(piv, 2),
                    "Buy Zone Top": round(piv * (1 + p["buyZonePct"] / 100), 2), "% vs Pivot": round(vs, 1),
                    "Days in Base": st["days"], "Attempts Above Pivot": st["attempts"], "Note": note})
    else:
        status, note = "No base", "Not in a recognized base"
        if last_sig:
            age = (df.index[-1] - last_sig[0]).days
            zone_top = last_sig[3] * (1 + p["buyZonePct"] / 100)
            if last_sig[1] == "BUY" and close <= zone_top:
                status, note = "Breakout — in buy zone", f"BUY {age}d ago; still within 5% of {last_sig[3]:.2f}"
            elif last_sig[1] == "BUY":
                status, note = "Extended after BUY", f"BUY {age}d ago at {last_sig[3]:.2f}; now past the buy zone — wait for a new base"
            elif last_sig[1] == "EXT" and close > zone_top:
                status, note = "Extended", "Left the buy zone without volume confirmation — wait for a new base"
            elif last_sig[1] == "FAILED" and age <= 45:
                status, note = "Base failed", "Last base broke down — wait for a new base"
            else:
                note = f"Not in a recognized base (last signal {age}d ago)"
        row.update({"Status": status, "Base": "", "Pivot (Buy Point)": "", "Buy Zone Top": "", "% vs Pivot": "",
                    "Days in Base": "", "Attempts Above Pivot": "", "Note": note})
    if last_sig:
        row.update({"Last Signal": f"{last_sig[1]} ({last_sig[2]} {last_sig[3]:.2f})",
                    "Last Signal Date": last_sig[0].strftime("%Y-%m-%d")})
    else:
        row.update({"Last Signal": "", "Last Signal Date": ""})
    return row


STATUS_ORDER = ["Near pivot", "Above pivot (light vol)", "Breakout — in buy zone", "In base",
                "Extended after BUY", "Extended", "Base failed", "No base"]
COLS = ["Ticker", "Status", "Base", "Pivot (Buy Point)", "Buy Zone Top", "Close", "% vs Pivot", "Days in Base",
        "Attempts Above Pivot", "Last Signal", "Last Signal Date", "Vol vs 50d", "% Off 52w High", "Trend", "Note"]


def build_status(tickers, cfg, extra=None):
    """Status DataFrame for `tickers`. `extra` (screener frame) adds RS / Group Rank / Checks when given."""
    p = cfg["bases"]
    data = yf.download(tickers, period="5y", auto_adjust=False,   # split- but not dividend-adjusted, like TradingView
                        group_by="ticker", threads=True, progress=False)
    rows = []
    for t in tickers:
        try:
            df = (data[t] if isinstance(data.columns, pd.MultiIndex) else data).dropna()
            if len(df) < 300:
                rows.append({"Ticker": t, "Status": "Not enough history", "Note": f"{len(df)} daily bars"})
                continue
            rows.append(status_row(t, df, p))
        except Exception as e:                                   # noqa: BLE001 — one bad ticker shouldn't stop the table
            rows.append({"Ticker": t, "Status": "Error", "Note": str(e)[:120]})
    out = pd.DataFrame(rows).reindex(columns=COLS)
    if extra is not None:
        add = extra.set_index("ticker")[["rs", "group_rank"]].rename(columns={"rs": "RS", "group_rank": "Group Rank"})
        if "checks_passed" in extra:
            add["CAN SLIM Checks"] = extra.set_index("ticker")["checks_passed"]
        out = out.join(add, on="Ticker")
        out = out[COLS[:2] + [c for c in ("RS", "Group Rank", "CAN SLIM Checks") if c in out] + COLS[2:]]
    out["_o"] = out["Status"].map({s: i for i, s in enumerate(STATUS_ORDER)}).fillna(99)
    out["_v"] = pd.to_numeric(out["% vs Pivot"], errors="coerce").fillna(-999)
    return out.sort_values(["_o", "_v"], ascending=[True, False]).drop(columns=["_o", "_v"]).reset_index(drop=True)


# ── Google Sheet ──────────────────────────────────────────────────────────────

STATUS_COLORS = {"Near pivot": (1.0, 0.95, 0.75), "Above pivot (light vol)": (1.0, 0.9, 0.8),
                 "Breakout — in buy zone": (0.8, 0.94, 0.8), "In base": (0.9, 0.93, 1.0),
                 "Base failed": (0.98, 0.85, 0.85)}


def open_sheet(cfg):
    import gspread
    from google.oauth2.service_account import Credentials
    o = cfg["output"]
    creds = Credentials.from_service_account_file(os.path.join(HERE, o["creds_file"]),
                                                  scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key(o["sheet_id"])


def read_watchlist(sh, cfg):
    """Tickers from the 'My Watchlist' tab; creates it from the config list the first time."""
    titles = [ws.title for ws in sh.worksheets()]
    if INPUT_TAB not in titles:
        seed = cfg["watchlist"]["tickers"]
        ws = sh.add_worksheet(title=INPUT_TAB, rows=200, cols=3)
        ws.update([["Ticker", "", "Add or remove tickers in column A — the status tab follows this list"]] +
                  [[t] for t in seed], "A1")
        ws.format("A1:C1", {"textFormat": {"bold": True}})
        log(f"created '{INPUT_TAB}' tab with {len(seed)} tickers")
        return seed
    col = sh.worksheet(INPUT_TAB).col_values(1)[1:]
    return [t.strip().upper().split(":")[-1] for t in col if t.strip()]


def write_status(sh, df, note):
    from canslim_screener import to_values
    values = [[note]] + to_values(df)
    titles = {ws.title: ws for ws in sh.worksheets()}
    ws = titles.get(STATUS_TAB) or sh.add_worksheet(title=STATUS_TAB, rows=len(values) + 10, cols=len(df.columns) + 2)
    ws.clear()
    ws.resize(rows=max(len(values) + 5, 20), cols=max(len(df.columns), 5))
    ws.update(values, "A1", value_input_option="USER_ENTERED")
    ws.format("A2:2", {"textFormat": {"bold": True}})
    ws.freeze(rows=2, cols=1)
    status_col = list(df.columns).index("Status")
    col_letter = chr(ord("A") + status_col)
    fmts = [{"range": f"{col_letter}3:{col_letter}{len(values)}", "format": {"backgroundColor": {"red": 1, "green": 1, "blue": 1}}}]
    for i, s in enumerate(df["Status"], start=3):
        if s in STATUS_COLORS:
            r, g, b = STATUS_COLORS[s]
            fmts.append({"range": f"A{i}:B{i}", "format": {"backgroundColor": {"red": r, "green": g, "blue": b}}})
    ws.batch_format(fmts)
    try:                                                         # show the status tab first
        sh.reorder_worksheets([ws] + [w for w in sh.worksheets() if w.id != ws.id])
    except Exception:                                            # noqa: BLE001 — ordering is cosmetic
        pass
    log(f"sheet tab '{STATUS_TAB}': {len(df)} rows")


def status_note(df):
    counts = df["Status"].value_counts()
    parts = [f"{counts[s]} {s.lower()}" for s in STATUS_ORDER if s in counts]
    return (f"Updated {dt.datetime.now():%Y-%m-%d %H:%M} · " + ", ".join(parts) +
            " · Same rules as the TradingView 'CANSLIM' indicator (pivot frozen per base; BUY = close in buy zone on ≥1.4× volume)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "canslim_config.yaml"))
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--tickers", default="")
    args = ap.parse_args()
    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    sh = None if args.no_sheet else open_sheet(cfg)
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or \
        (read_watchlist(sh, cfg) if sh else cfg["watchlist"]["tickers"])
    log(f"{len(tickers)} tickers")
    df = build_status(tickers, cfg)
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.max_colwidth", 60):
        print(df.drop(columns=["Note"]).to_string(index=False))
    if sh:
        write_status(sh, df, status_note(df))


if __name__ == "__main__":
    sys.exit(main())
