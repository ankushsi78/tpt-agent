#!/usr/bin/env python3
"""
CAN SLIM base detector + "Watchlist Status" tab for the CANSLIM Screener Google Sheet.

This is a bar-by-bar port of tradingview/canslim_bases.pine (v3): bases found on WEEKLY bars (or daily),
breakouts timed on daily bars — cup with/without handle, double bottom, flat base, DEEP bases, frozen pivot,
and the same BUY / BO? / EXT / failed events.
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

def _sc(x, weekly, lo):
    """Daily-bar length → weekly-bar length (Pine: math.max(lo, math.round(x / 5.0)))."""
    return max(lo, int(math.floor(x / 5.0 + 0.5))) if weekly else x


class Scanner:
    """Bar-by-bar base scan on one timeframe (Pine `detect()`). Call step(t) for t = 0, 1, 2, … in order."""

    def __init__(self, df, p, weekly):
        self.h, self.l, self.c, self.v = (df[k].to_numpy(float) for k in ("High", "Low", "Close", "Volume"))
        self.time = df.index
        self.p, self.w = p, weekly
        self.cMin, self.cMx = _sc(p["cupMinLen"], weekly, 2), _sc(p["cupMaxLen"], weekly, 10)
        self.hMn, self.hMx = _sc(p["hMinLen"], weekly, 1), _sc(p["hMaxLen"], weekly, 2)
        self.k, self.gap = _sc(p["dbK"], weekly, 2), _sc(p["dbMinGap"], weekly, 2)
        self.span, self.look = _sc(p["dbMaxSpan"], weekly, 10), _sc(p["dbLeftLook"], weekly, 5)
        self.dLen = _sc(p["dbMinLen"], weekly, 2)
        self.fMin, self.fMx, self.fAge = (_sc(p["flatMinLen"], weekly, 2), _sc(p["flatMaxLen"], weekly, 5),
                                          _sc(p["flatHighAge"], weekly, 1))
        self.plb, self.side, self.slide, self.recent = (13, 2, 2, 6) if weekly else (63, 10, 10, 30)
        deep = p.get("allowDeep", True)
        self.cupEff = max(p["cupMaxDepth"], p["deepMax"]) if deep else p["cupMaxDepth"]
        self.dbEff = max(p["dbMaxDepth"], p["deepMax"]) if deep else p["dbMaxDepth"]
        self.avgV = pd.Series(self.v).rolling(10 if weekly else 50).mean().to_numpy()
        self.sv, self.sb = [], []

    def _plow(self, t, off):
        return self.l[t - off - self.plb:t - off + 1].min()

    def step(self, t, flat_limit=None):
        h, l, c, v, p, T = self.h, self.l, self.c, self.v, self.p, self.time
        k = self.k
        if t >= 2 * k:                                           # ta.pivotlow(low, k, k)
            ctr = t - k
            if l[ctr] < l[ctr - k:ctr].min() and l[ctr] <= l[ctr + 1:t + 1].min():
                self.sv.append(l[ctr]); self.sb.append(ctr)
                if len(self.sv) > 12:
                    self.sv.pop(0); self.sb.pop(0)
        if t <= self.cMx + self.hMx + self.plb + 20:
            return None

        # cup with handle
        if p.get("useCup", True):
            win = h[t - self.hMx:t + 1]
            r_off = int(np.argmax(win[::-1]))
            R = h[t - r_off]
            if self.hMn <= r_off <= self.hMx:
                h_low = l[t - r_off + 1:t + 1].min()
                h_avg = v[t - r_off + 1:t + 1].mean()
                lip = R * (1 - p["lipTol"] / 100)
                lowest, low_off, l_off, inner = R, r_off, -1, 0.0
                for i in range(r_off + 1, r_off + self.cMx + 1):
                    if (R - lowest) / R * 100 >= p["cupMinDepth"] and h[t - i] >= lip:
                        l_off = i
                        break
                    inner = max(inner, h[t - i])
                    if l[t - i] < lowest:
                        lowest, low_off = l[t - i], i
                    if (lip - lowest) / lip * 100 > self.cupEff:
                        break
                if l_off > 0:
                    L = h[t - l_off]
                    for j in range(l_off + 1, min(l_off + self.slide, r_off + self.cMx) + 1):
                        if h[t - j] > L:
                            L, l_off = h[t - j], j
                    depth = (L - lowest) / L * 100
                    right_ok = L * (1 - p["lipTol"] / 100) <= R <= L * (1 + p["lipTol"] / 100) and inner <= max(L, R)
                    upper_ok = (not p["hUpperHalf"]) or h_low >= lowest + 0.5 * (L - lowest)
                    vol_ok = (not p["hVolDry"]) or h_avg < self.avgV[t]
                    p_low = self._plow(t, l_off)
                    if (l_off - r_off >= self.cMin and p["cupMinDepth"] <= depth <= self.cupEff and right_ok
                            and (R - h_low) / R * 100 <= p["hMaxDepth"] and upper_ok and vol_ok
                            and (L - p_low) / p_low * 100 >= p["priorAdv"] and c[t] < R + p["pivotAdd"]):
                        return {"code": 1, "type": "Cup with Handle", "pivot": R + p["pivotAdd"],
                                "inval": lowest + 0.5 * (L - lowest), "deep": depth > p["cupMaxDepth"],
                                "start": T[t - l_off], "depth": depth}

        # double bottom
        ns = len(self.sv)
        if p.get("useDb", True) and ns >= 2 and t > self.span + self.look + self.plb + 10:
            s2v, s2b = self.sv[-1], self.sb[-1]
            o2 = t - s2b
            if o2 <= self.recent and c[t] > s2v:
                for j in range(ns - 2, max(0, ns - 8) - 1, -1):
                    s1v, s1b = self.sv[j], self.sb[j]
                    o1 = t - s1b
                    if s2b - s1b < self.gap or o1 > self.span:
                        continue
                    tol_ok = s1v * (1 - p["dbUnder"] / 100) <= s2v <= s1v * (1 + p["dbOver"] / 100)
                    M = h[t - o1 + 1:t - o2].max()
                    low_between = l[t - o1 + 1:t - o2].min()
                    left = h[t - o1 - self.look:t - o1]
                    H0 = left.max()
                    h0_off = o1 + (len(left) - int(np.argmax(left)))
                    hi_since = h[t - o2 + 1:t + 1].max()
                    lows = min(s1v, s2v)
                    depth = (H0 - lows) / H0 * 100
                    p_low = self._plow(t, h0_off)
                    if (tol_ok and low_between >= lows and M >= max(s1v, s2v) * (1 + p["dbMinMid"] / 100) and M < H0
                            and p["dbMinDepth"] <= depth <= self.dbEff and h0_off >= self.dLen
                            and (H0 - p_low) / p_low * 100 >= p["priorAdv"] and hi_since < M + p["pivotAdd"]):
                        return {"code": 2, "type": "Double Bottom", "pivot": M + p["pivotAdd"], "inval": lows,
                                "deep": depth > p["dbMaxDepth"], "start": T[t - h0_off], "depth": depth}

        # cup without handle
        if p.get("useNoHandle", True):
            win = h[t - self.cMx:t + 1]
            nh_off = int(np.argmax(win[::-1]))
            if nh_off >= self.cMin:
                Ln = h[t - nh_off]
                seg = l[t - nh_off + 1:t + 1][::-1]                  # offsets 0 .. nh_off-1
                lo_off = int(np.argmin(seg))
                lo = seg[lo_off]
                depth = (Ln - lo) / Ln * 100
                p_low = self._plow(t, nh_off)
                if (p["cupMinDepth"] <= depth <= self.cupEff and (c[t] - lo) / (Ln - lo) >= 0.75
                        and c[t] < Ln + p["pivotAdd"] and lo_off >= self.side and nh_off - lo_off >= self.side
                        and (Ln - p_low) / p_low * 100 >= p["priorAdv"]):
                    return {"code": 3, "type": "Cup w/o Handle", "pivot": Ln + p["pivotAdd"],
                            "inval": lo + 0.5 * (Ln - lo), "deep": depth > p["cupMaxDepth"],
                            "start": T[t - nh_off], "depth": depth}

        # flat base
        f_lim = self.fMx - 1 if self.w else flat_limit
        if p.get("useFlat", True) and f_lim is not None and f_lim >= self.fMin - 1:
            hh, hh_off, ll, win_end = h[t], 0, l[t], 0
            for i in range(1, f_lim + 1):
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
            if f_len >= self.fMin and hh_off >= self.fAge:
                half = f_len // 2
                seg = c[t - start_off:t + 1][::-1]
                drift = abs(seg[:half].mean() / seg[half:].mean() - 1) * 100
                p_low = self._plow(t, start_off)
                if drift <= p["flatSlopeMax"] and (hh - p_low) / p_low * 100 >= p["priorAdv"] and c[t] < hh + p["pivotAdd"]:
                    return {"code": 4, "type": "Flat Base", "pivot": hh + p["pivotAdd"],
                            "inval": hh * (1 - p["flatMaxDepth"] / 100), "deep": False,
                            "start": T[t - start_off], "depth": (hh - ll) / hh * 100}
        return None


def weekly_bars(df):
    """Daily → weekly OHLCV (weeks labelled by their Monday, like TradingView)."""
    w = df.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
    w.index = w.index - pd.Timedelta(days=4)
    return w


def detect(df, p, timeframe="Weekly"):
    """Base state machine over a DAILY frame; bases come from `timeframe` bars. Returns (state, events)."""
    h, c, v = (df[k].to_numpy(float) for k in ("High", "Close", "Volume"))
    n, dates = len(df), df.index
    avg_vol = pd.Series(v).rolling(50).mean().to_numpy()
    sma200 = pd.Series(c).rolling(200).mean().to_numpy()

    weekly = timeframe == "Weekly"
    if weekly:                                                   # candidate of the last COMPLETED week, per daily bar
        wk = weekly_bars(df)
        ws = Scanner(wk, p, True)
        wc = [ws.step(i) for i in range(len(wk))]
        wpos = np.searchsorted(wk.index.values, dates.values, side="right") - 2    # week before the current one
    else:
        ds = Scanner(df, p, False)

    st = {"type": "", "pivot": np.nan, "inval": np.nan, "bar": None, "crossed": False, "weak": False,
          "attempts": 0, "tag": ""}
    last_end_bar, last_end_time, last_end_piv = 0, pd.Timestamp(0), np.nan
    events = []
    for t in range(n):
        if weekly:
            cand = wc[wpos[t]] if wpos[t] >= 0 else None
        else:
            cand = ds.step(t, min(p["flatMaxLen"] - 1, t - last_end_bar - 1))
        trend_ok = (not p["trendFilter"]) or (not np.isnan(sma200[t]) and c[t] > sma200[t])

        ev_piv = np.nan
        label = st["type"] + st["tag"]
        if st["type"]:
            if c[t] > st["pivot"]:
                in_zone = c[t] <= st["pivot"] * (1 + p["buyZonePct"] / 100)
                st["crossed"] = True
                ev_piv = st["pivot"]
                vr = v[t] / avg_vol[t - 1]
                if in_zone and v[t] >= p["volMult"] * avg_vol[t - 1]:
                    events.append((dates[t], "BUY", label, st["pivot"], vr)); st["type"] = ""
                elif not in_zone:
                    events.append((dates[t], "EXT", label, st["pivot"], vr)); st["type"] = ""
                elif not st["weak"]:
                    events.append((dates[t], "BO?", label, st["pivot"], vr)); st["weak"] = True
            elif c[t] < st["inval"] or t - st["bar"] > p["actMaxBars"]:
                events.append((dates[t], "FAILED" if c[t] < st["inval"] else "RETIRED", label, st["pivot"], None))
                st["type"] = ""
            elif h[t] > st["pivot"]:
                st["crossed"] = True
                st["attempts"] += 1
            if not st["type"]:
                last_end_piv = ev_piv if not np.isnan(ev_piv) else st["pivot"]
                st["pivot"] = np.nan
                last_end_bar, last_end_time = t, dates[t]

        cand_ok = cand is not None and c[t] < cand["pivot"] and (cand["code"] != 4 or cand["start"] > last_end_time)
        same = (cand_ok and not np.isnan(last_end_piv) and abs(cand["pivot"] / last_end_piv - 1) < 0.01
                and t - last_end_bar < 15)
        if not st["type"] and last_end_bar != t and trend_ok and cand_ok and not same:
            tag = (" DEEP" if cand["deep"] else "") + (" (W)" if weekly else " (D)")
            st.update(type=cand["type"], tag=tag, pivot=cand["pivot"], inval=cand["inval"], bar=t,
                      crossed=False, weak=False, attempts=0)
            events.append((dates[t], "DETECTED", cand["type"] + tag, cand["pivot"], None))

    st["days"] = (n - 1 - st["bar"]) if st["type"] else None
    return st, events


# ── Status table ──────────────────────────────────────────────────────────────

def status_row(tkr, df, p):
    st, events = detect(df, p, p.get("timeframe", "Weekly"))
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
        row.update({"Status": status, "Base": st["type"] + st["tag"], "Pivot (Buy Point)": round(piv, 2),
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
        if status in ("Breakout — in buy zone", "Extended after BUY", "Extended"):
            piv = last_sig[3]                                    # the base the stock just left
            row.update({"Base": last_sig[2], "Pivot (Buy Point)": round(piv, 2),
                        "Buy Zone Top": round(piv * (1 + p["buyZonePct"] / 100), 2),
                        "% vs Pivot": round((close / piv - 1) * 100, 1)})
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
    ranks = os.path.join(HERE, cfg["output"]["csv_dir"], "canslim_ranks_latest.csv")   # from the last screener run
    df = build_status(tickers, cfg, extra=pd.read_csv(ranks) if os.path.exists(ranks) else None)
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.max_colwidth", 60):
        print(df.drop(columns=["Note"]).to_string(index=False))
    if sh:
        write_status(sh, df, status_note(df))


if __name__ == "__main__":
    sys.exit(main())
