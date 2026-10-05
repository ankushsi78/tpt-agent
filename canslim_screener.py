#!/usr/bin/env python3
"""
CAN SLIM screener — ranks every US stock and builds a watchlist in Google Sheets.

  C  quarterly EPS & sales growth (YoY)           SEC XBRL "frames" API (all filers at once)
  A  3-year annual EPS CAGR + ROE                  SEC XBRL frames
  N  within X% of 52-week high                     Yahoo Finance daily prices
  S  50-day up/down volume ratio (accumulation)    Yahoo Finance
  L  IBD-style RS rating (1-99) + industry group rank
  I  not available from free data — check IBD's Accumulation/Distribution & fund ownership
  M  SPY/QQQ trend + distribution-day count

Universe = all NYSE/Nasdaq/AMEX stocks from Nasdaq's screener (with industry), filtered by
price and market cap from canslim_config.yaml. All thresholds live in that config.

Usage:
  python3 canslim_screener.py [--config canslim_config.yaml] [--no-sheet] [--tickers NVDA,PLTR]
  --no-sheet : write the CSVs only
  --tickers  : also print a detail line for these tickers (ranking still uses the full universe)
"""

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import sys
import time

import pandas as pd
import requests
import yaml
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
              "Accept": "application/json"}

EPS_CONCEPTS = ["EarningsPerShareDiluted", "EarningsPerShareBasic"]
REV_CONCEPTS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


class Cache:
    def __init__(self, cfg):
        self.dir = os.path.join(HERE, cfg["output"]["cache_dir"])
        self.ttl = cfg["output"]["cache_hours"] * 3600
        self.sec_headers = {"User-Agent": cfg["output"]["sec_user_agent"]}
        if "@" not in self.sec_headers["User-Agent"]:
            sys.exit("SEC requires a contact email in output.sec_user_agent, e.g. 'BayFin Research you@example.com'")
        os.makedirs(self.dir, exist_ok=True)

    def get_json(self, url, sec=False):
        """GET JSON with an on-disk cache. Returns None on 404."""
        path = os.path.join(self.dir, hashlib.md5(url.encode()).hexdigest() + ".json")
        if os.path.exists(path) and time.time() - os.path.getmtime(path) < self.ttl:
            with open(path) as f:
                return json.load(f)
        for attempt in range(3):
            r = requests.get(url, headers=self.sec_headers if sec else BROWSER_UA, timeout=60)
            if sec:
                time.sleep(0.15)                      # SEC fair-access: < 10 requests/second
            if r.status_code == 404:
                data = None
                break
            if r.ok:
                data = r.json()
                break
            time.sleep(2 * (attempt + 1))
        else:
            r.raise_for_status()
        with open(path, "w") as f:
            json.dump(data, f)
        return data


def num(x):
    try:
        return float(str(x).replace("$", "").replace(",", ""))
    except ValueError:
        return float("nan")


def growth(cur, prev):
    """YoY % growth; None when the base is non-positive (turnarounds aren't growth rates)."""
    if cur is None or prev is None or prev <= 0:
        return None
    return (cur - prev) / prev * 100


# ── Universe ───────────────────────────────────────────────────────────────────

def load_universe(cfg, cache):
    data = cache.get_json("https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true")
    df = pd.DataFrame(data["data"]["rows"])
    df["price"] = df["lastsale"].map(num)
    df["market_cap"] = df["marketCap"].map(num)
    df["ticker"] = df["symbol"].str.strip().str.replace("/", "-", regex=False)
    u = cfg["universe"]
    keep = (df["price"] >= u["min_price"]) & (df["market_cap"] >= u["min_market_cap"]) \
        & ~df["ticker"].str.contains(r"\^", regex=True)
    df = df[keep]
    extra_file = u.get("extra_tickers_file")
    if extra_file and os.path.exists(os.path.join(HERE, extra_file)):
        with open(os.path.join(HERE, extra_file)) as f:
            extra = {t.strip().upper() for t in f if t.strip() and not t.startswith("#")}
        missing = extra - set(df["ticker"])
        df = pd.concat([df, pd.DataFrame({"ticker": sorted(missing)})], ignore_index=True)
    df["industry"] = df["industry"].fillna("").replace("", "Unclassified")
    return df[["ticker", "name", "sector", "industry", "market_cap"]].drop_duplicates("ticker").reset_index(drop=True)


# ── Prices ─────────────────────────────────────────────────────────────────────

def _yf_batch(part, threads):
    d = yf.download(part, period="400d", auto_adjust=True, group_by="ticker",
                    threads=threads, progress=False)
    if not isinstance(d.columns, pd.MultiIndex):
        d.columns = pd.MultiIndex.from_product([part, d.columns])
    d = d.loc[:, d.columns.get_level_values(0).isin(part)]
    return d.loc[:, ~d.xs("Close", level=1, axis=1).isna().all().reindex(d.columns.get_level_values(0)).values]


def download_prices(tickers, chunk=400, retries=2):
    """Batch download from Yahoo; tickers that fail (Yahoo drops connections under load) are retried."""
    frames, todo = [], list(tickers)
    for attempt in range(retries + 1):
        threads = attempt == 0
        size = chunk if attempt == 0 else 100
        for i in range(0, len(todo), size):
            part = todo[i:i + size]
            log(f"prices {'retry ' * (attempt > 0)}{i + len(part)}/{len(todo)}")
            frames.append(_yf_batch(part, threads))
        got = {t for f in frames for t in f.columns.get_level_values(0)}
        todo = [t for t in todo if t not in got]
        if not todo:
            break
        time.sleep(5)
    if todo:
        log(f"no price data for {len(todo)} tickers (likely delisted/renamed)")
    d = pd.concat(frames, axis=1).sort_index()
    return d.xs("Close", level=1, axis=1), d.xs("High", level=1, axis=1), d.xs("Volume", level=1, axis=1)


def technicals(close, high, vol, weights):
    last = close.ffill().iloc[-1]
    traded = close.iloc[-1].notna()                         # dropped/halted names are excluded
    rets = {}
    for n in weights:
        rets[n] = last / close.shift(n).ffill().iloc[-1] - 1 if len(close) > n else pd.Series(float("nan"), index=close.columns)
    num_ = sum(rets[n].fillna(0) * w for n, w in weights.items())
    den = sum(rets[n].notna() * w for n, w in weights.items())
    rs_score = (num_ / den.replace(0, float("nan"))).where(rets[min(weights)].notna())

    chg = close.diff()
    v50 = vol.tail(50)
    up_vol = v50.where(chg.tail(50) > 0, 0).sum()
    dn_vol = v50.where(chg.tail(50) < 0, 0).sum()
    t = pd.DataFrame({
        "price": last,
        "sma50": close.rolling(50).mean().iloc[-1],
        "sma200": close.rolling(200).mean().iloc[-1],
        "high_52w": high.tail(252).max(),
        "avg_dollar_vol": (close * vol).tail(50).mean(),
        "up_down_vol": up_vol / dn_vol.replace(0, float("nan")),
        "ret_3m": rets[63] * 100 if 63 in rets else float("nan"),
        "ret_12m": rets[252] * 100 if 252 in rets else float("nan"),
        "rs_score": rs_score,
    })
    t = t[traded & t["rs_score"].notna()]
    t["off_high_pct"] = (1 - t["price"] / t["high_52w"]) * 100
    # IBD-style RS rating: percentile rank of the weighted score across the universe, 1..99
    t["rs"] = (t["rs_score"].rank(pct=True) * 98 + 1).round().astype(int)
    return t


# ── Fundamentals (SEC XBRL frames) ─────────────────────────────────────────────

def recent_quarters(n):
    today = dt.date.today()
    y, q = today.year, (today.month - 1) // 3 + 1
    out = []
    for _ in range(n):
        out.append((y, q))
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return out


def frame(cache, concept, unit, period):
    data = cache.get_json(f"https://data.sec.gov/api/xbrl/frames/us-gaap/{concept}/{unit}/{period}.json", sec=True)
    return {} if not data else {row["cik"]: row["val"] for row in data["data"]}


def first_available(cache, concepts, unit, period):
    """Merge concepts in priority order: a company's value comes from the first concept it reports."""
    out = {}
    for c in reversed(concepts):
        out.update(frame(cache, c, unit, period))
    return out


def load_fundamentals(cache, ticker_list):
    log("SEC: ticker→CIK map")
    tick = cache.get_json("https://www.sec.gov/files/company_tickers.json", sec=True)
    cik_of = {v["ticker"].upper(): int(v["cik_str"]) for v in tick.values()}

    quarters = recent_quarters(15)                          # newest first
    years = list(range(quarters[0][0] - 5, quarters[0][0] + 1))   # annual frames: enough for a 3-year CAGR
    eps_q, rev_q, eps_a, rev_a = {}, {}, {}, {}
    log(f"SEC: quarterly frames {quarters[-1]}..{quarters[0]}")
    for y, q in quarters:
        eps_q[(y, q)] = first_available(cache, EPS_CONCEPTS, "USD-per-shares", f"CY{y}Q{q}")
        rev_q[(y, q)] = first_available(cache, REV_CONCEPTS, "USD", f"CY{y}Q{q}")
    log("SEC: annual frames")
    for y in years:
        eps_a[y] = first_available(cache, EPS_CONCEPTS, "USD-per-shares", f"CY{y}")
        rev_a[y] = first_available(cache, REV_CONCEPTS, "USD", f"CY{y}")
    ni_a = {y: frame(cache, "NetIncomeLoss", "USD", f"CY{y}") for y in years}
    eq_i = {y: first_available(cache, ["StockholdersEquity",
                                       "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
                               "USD", f"CY{y}Q4I") for y in years}

    def q_series(qmap, amap, cik):
        s = {k: v[cik] for k, v in qmap.items() if cik in v}
        for y in years:                                      # 10-Ks rarely tag Q4: derive FY − (Q1+Q2+Q3)
            if (y, 4) not in s and cik in amap.get(y, {}) and all((y, k) in s for k in (1, 2, 3)):
                s[(y, 4)] = amap[y][cik] - sum(s[(y, k)] for k in (1, 2, 3))
        return s

    newest_ok = quarters[2]                                  # ignore filers whose latest quarter is stale
    rows = []
    for t in ticker_list:
        cik = cik_of.get(t.upper())
        if cik is None:
            continue
        eps = q_series(eps_q, eps_a, cik)
        rev = q_series(rev_q, rev_a, cik)
        latest = [k for k in sorted(eps, reverse=True) if (k[0] - 1, k[1]) in eps]
        r = {"ticker": t}
        if latest and latest[0] >= newest_ok:
            (y, q) = latest[0]
            prev = (y, q - 1) if q > 1 else (y - 1, 4)
            r["last_q"] = f"{y}Q{q}"
            r["eps_q"] = eps[(y, q)]
            r["eps_q_growth"] = growth(eps[(y, q)], eps[(y - 1, q)])
            r["eps_prev_q_growth"] = growth(eps.get(prev), eps.get((prev[0] - 1, prev[1])))
            r["sales_q_growth"] = growth(rev.get((y, q)), rev.get((y - 1, q)))
        ann = sorted(y for y in years if cik in eps_a[y])
        if ann and ann[-1] >= quarters[0][0] - 2:
            ya = ann[-1]
            base, end = eps_a.get(ya - 3, {}).get(cik), eps_a[ya][cik]
            if base and base > 0 and end > 0:
                r["eps_3y_cagr"] = ((end / base) ** (1 / 3) - 1) * 100
            yoy = [growth(eps_a.get(k, {}).get(cik), eps_a.get(k - 1, {}).get(cik)) for k in (ya - 2, ya - 1, ya)]
            r["eps_annual_growth"] = " / ".join("—" if g is None else f"{g:.0f}%" for g in yoy)
            ni, eq = ni_a[ya].get(cik), eq_i[ya].get(cik)
            if ni is not None and eq and eq > 0:
                r["roe"] = ni / eq * 100
        rows.append(r)
    return pd.DataFrame(rows)


# ── Market direction (M) ───────────────────────────────────────────────────────

def market_status(cfg):
    m = cfg["market"]
    rows = []
    d = yf.download(m["indexes"], period="300d", auto_adjust=True, group_by="ticker", progress=False)
    for sym in m["indexes"]:
        x = d[sym].dropna()
        c, v = x["Close"], x["Volume"]
        chg = c.pct_change() * 100
        is_dd = ((chg <= -m["distribution_min_drop_pct"]) & (v > v.shift(1))).tail(m["distribution_lookback"])
        last = c.iloc[-1]
        # IBD rule: a distribution day expires once the index closes 5%+ above that day's close
        dist = sum(1 for day in is_dd[is_dd].index if c.loc[day:].max() < c.loc[day] * 1.05)
        sma50, sma200 = c.rolling(50).mean().iloc[-1], c.rolling(200).mean().iloc[-1]
        if last < sma200 or (last < sma50 and dist >= 6):
            status = "Correction"
        elif last < sma50 or dist >= 5:
            status = "Uptrend under pressure"
        else:
            status = "Confirmed uptrend"
        rows.append({"index": sym, "close": round(last, 2), "vs_50d_pct": round((last / sma50 - 1) * 100, 1),
                     "vs_200d_pct": round((last / sma200 - 1) * 100, 1),
                     f"distribution_days_{m['distribution_lookback']}d": int(dist), "status": status})
    return pd.DataFrame(rows)


# ── Screen ─────────────────────────────────────────────────────────────────────

def screen(df, cfg):
    k = cfg["criteria"]
    ge = lambda col, thr: df[col].fillna(-1e9) >= thr
    checks = pd.DataFrame({
        "c_eps":   ge("eps_q_growth", k["min_eps_q_growth"]),
        "c_sales": ge("sales_q_growth", k["min_sales_q_growth"]),
        "a":       ge("eps_3y_cagr", k["min_eps_annual_cagr"]) & ge("roe", k["min_roe"]),
        "n":       df["off_high_pct"] <= k["max_off_high_pct"],
        "s":       ge("up_down_vol", k["min_up_down_vol"]),
        "l_rs":    df["rs"] >= k["min_rs"],
        "l_group": df["group_rank_pct"].fillna(100) <= k["max_group_rank_pct"],
    })
    trend = (df["price"] > df["sma50"]) & (df["price"] > df["sma200"])
    df["checks_passed"] = checks.sum(axis=1)
    df["checklist"] = checks.apply(lambda r: " ".join(
        (c.upper().replace("_", "-") if ok else "·") for c, ok in r.items()), axis=1)
    df["eps_accelerating"] = (df["eps_q_growth"] > df["eps_prev_q_growth"]).where(df["eps_prev_q_growth"].notna())
    req = pd.concat([checks, trend.rename("trend")], axis=1)[k["required"]].all(axis=1)
    keep = req & (df["checks_passed"] >= k["min_checks_passed"]) & (df["avg_dollar_vol"] >= k["min_avg_dollar_vol"])
    return df[keep].sort_values(["checks_passed", "rs"], ascending=False)


# ── Output ─────────────────────────────────────────────────────────────────────

WATCH_COLS = [
    ("ticker", "Ticker"), ("name", "Name"), ("industry", "Industry"), ("checks_passed", "Checks (of 7)"),
    ("checklist", "Checklist"), ("rs", "RS"), ("group_rank", "Group Rank"), ("group_rs", "Group RS"),
    ("price", "Price"), ("off_high_pct", "% Off 52w High"), ("last_q", "Last Qtr"),
    ("eps_q_growth", "EPS Q Gr %"), ("eps_prev_q_growth", "Prev Q EPS Gr %"), ("eps_accelerating", "EPS Accel"),
    ("sales_q_growth", "Sales Q Gr %"), ("eps_3y_cagr", "EPS 3y CAGR %"), ("eps_annual_growth", "Annual EPS Gr (3y)"),
    ("roe", "ROE %"), ("up_down_vol", "Up/Down Vol"), ("avg_dollar_vol", "Avg $Vol (M)"),
    ("ret_3m", "3m %"), ("ret_12m", "12m %"), ("market_cap", "Mkt Cap ($B)"),
]


def tidy(df, cols):
    out = df[[c for c, _ in cols]].copy()
    if "avg_dollar_vol" in out:
        out["avg_dollar_vol"] = out["avg_dollar_vol"] / 1e6
    if "market_cap" in out:
        out["market_cap"] = out["market_cap"] / 1e9
    for c in out.columns:
        if pd.api.types.is_float_dtype(out[c]):
            out[c] = out[c].round(1 if c not in ("price",) else 2)
    out.columns = [h for _, h in cols]
    return out


def to_values(df):
    def cell(x):
        if x is None or (isinstance(x, float) and math.isnan(x)) or x is pd.NA:
            return ""
        if isinstance(x, (bool,)) or str(type(x)).endswith("bool_'>"):
            return "Yes" if x else "No"
        return x.item() if hasattr(x, "item") else x
    return [list(df.columns)] + [[cell(v) for v in row] for row in df.itertuples(index=False)]


def write_sheet(cfg, tabs, run_note):
    import gspread
    from google.oauth2.service_account import Credentials
    o = cfg["output"]
    creds = Credentials.from_service_account_file(os.path.join(HERE, o["creds_file"]),
                                                  scopes=["https://www.googleapis.com/auth/spreadsheets"])
    sh = gspread.authorize(creds).open_by_key(o["sheet_id"])
    existing = {ws.title: ws for ws in sh.worksheets()}
    for title, df in tabs.items():
        values = [[run_note]] + to_values(df)
        ws = existing.get(title) or sh.add_worksheet(title=title, rows=len(values) + 10, cols=len(df.columns) + 2)
        ws.clear()
        ws.resize(rows=max(len(values) + 5, 20), cols=max(len(df.columns), 5))
        ws.update(values, "A1", value_input_option="USER_ENTERED")
        ws.format("A2:2", {"textFormat": {"bold": True}})
        ws.freeze(rows=2, cols=1)
        log(f"sheet tab '{title}': {len(df)} rows")
    return sh.url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "canslim_config.yaml"))
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--tickers", default="")
    args = ap.parse_args()
    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    cache = Cache(cfg)

    uni = load_universe(cfg, cache)
    log(f"universe: {len(uni)} stocks")
    close, high, vol = download_prices(uni["ticker"].tolist())
    tech = technicals(close, high, vol, cfg["rs"]["weights"])
    df = uni.merge(tech, left_on="ticker", right_index=True)
    log(f"ranked: {len(df)} stocks with price history")

    # Industry group strength
    g = df.groupby("industry").agg(members=("ticker", "size"), avg_score=("rs_score", "mean"),
                                   avg_rs=("rs", "mean"), ret_3m=("ret_3m", "median"))
    # rank by members' average RS rating (percentiles) so one outlier can't carry a group
    g = g[g["members"] >= cfg["groups"]["min_members"]].sort_values("avg_rs", ascending=False)
    g["group_rank"] = range(1, len(g) + 1)
    g["group_rank_pct"] = g["group_rank"] / len(g) * 100
    g["group_rs"] = (g["avg_rs"].rank(pct=True) * 98 + 1).round().astype(int)
    leaders = df.sort_values("rs", ascending=False).groupby("industry")["ticker"].apply(lambda s: ", ".join(s.head(5)))
    g["leaders"] = leaders
    df = df.merge(g[["group_rank", "group_rank_pct", "group_rs"]], left_on="industry", right_index=True, how="left")

    fund = load_fundamentals(cache, df["ticker"].tolist())
    df = df.merge(fund, on="ticker", how="left")
    for c in ("eps_q_growth", "eps_prev_q_growth", "sales_q_growth", "eps_3y_cagr", "roe"):
        if c not in df:
            df[c] = float("nan")
        df[c] = pd.to_numeric(df[c], errors="coerce")
    log(f"fundamentals: {df['eps_q_growth'].notna().sum()} stocks with quarterly EPS growth")

    mkt = market_status(cfg)
    watch = screen(df, cfg)
    log(f"watchlist: {len(watch)} stocks")

    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    mstat = "; ".join(f"{r['index']}: {r['status']}" for _, r in mkt.iterrows())
    note = (f"Updated {now} · Market: {mstat} · Ranked {len(df)} stocks · "
            f"Checklist = C-EPS C-SALES A N S L-RS L-GROUP ('·' = failed) · I = check IBD Acc/Dis & fund ownership")
    rs_cols = [("ticker", "Ticker"), ("name", "Name"), ("industry", "Industry"), ("rs", "RS"),
               ("group_rank", "Group Rank"), ("price", "Price"), ("off_high_pct", "% Off 52w High"),
               ("ret_3m", "3m %"), ("ret_12m", "12m %"), ("eps_q_growth", "EPS Q Gr %"),
               ("sales_q_growth", "Sales Q Gr %"), ("market_cap", "Mkt Cap ($B)")]
    grp = g.reset_index()[["group_rank", "industry", "group_rs", "members", "avg_rs", "ret_3m", "leaders"]]
    grp.columns = ["Rank", "Industry", "Group RS", "Stocks", "Avg RS", "Median 3m %", "Top RS names"]
    grp = grp.round(1)
    tabs = {
        "CANSLIM Watchlist": tidy(watch, WATCH_COLS),
        "RS Rankings": tidy(df.sort_values("rs", ascending=False).head(cfg["output"]["max_rs_rows"]), rs_cols),
        "Industry Groups": grp,
        "Market": mkt,
    }

    out_dir = os.path.join(HERE, cfg["output"]["csv_dir"])
    os.makedirs(out_dir, exist_ok=True)
    stamp = dt.date.today().isoformat()
    for title, t in tabs.items():
        t.to_csv(os.path.join(out_dir, f"canslim_{title.lower().replace(' ', '_')}_{stamp}.csv"), index=False)
    log(f"CSVs written to {out_dir}")

    for t in [s.strip().upper() for s in args.tickers.split(",") if s.strip()]:
        row = df[df["ticker"] == t]
        print(tidy(row, WATCH_COLS).T.to_string() if len(row) else f"{t}: not in universe")

    if not args.no_sheet:
        if not cfg["output"].get("sheet_id"):
            log("output.sheet_id not set — skipping Google Sheet (CSVs only)")
        else:
            log(f"Google Sheet updated: {write_sheet(cfg, tabs, note)}")
            import canslim_bases
            sh = canslim_bases.open_sheet(cfg)
            status = canslim_bases.build_status(canslim_bases.read_watchlist(sh, cfg), cfg, extra=df)
            canslim_bases.write_status(sh, status, canslim_bases.status_note(status))
            status.to_csv(os.path.join(out_dir, f"canslim_watchlist_status_{stamp}.csv"), index=False)
    print("\n" + mkt.to_string(index=False))
    print("\n" + tabs["CANSLIM Watchlist"].head(25)[["Ticker", "Industry", "Checks (of 7)", "RS", "Group Rank",
                                                      "EPS Q Gr %", "Sales Q Gr %", "% Off 52w High"]].to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
