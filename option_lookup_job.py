#!/usr/bin/env python3
"""
Daily Option Lookup — Cash-Secured-Put screener (runs on the Mac mini, no Base44).

Replicates the OptionWheel Pro "Option Lookup" (Power Mode) search:
  • fetch the option chain per ticker within a DTE window
  • keep puts with |delta| in range
  • ARR = (premium / strike) * (365 / DTE) * 100   (premium = bid, matching the app)
  • rank by ARR

...then adds the config's extra filters (open interest, target ARR), renders a PDF,
and posts it to Discord. Every threshold comes from optionlookup_config.yaml —
nothing is hard-coded here.

Usage:
  python3 option_lookup_job.py [--config optionlookup_config.yaml] [--dry-run] [--provider schwab|tradier]
  --dry-run : build the PDF but DO NOT post to Discord.
"""

import argparse
import datetime as dt
import os
import sys
import time

import requests
import yaml

# importing schwab_client loads the project's .env (SCHWAB_*, TRADIER_TOKEN, DISCORD_*)
import schwab_client
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# ── helpers ──────────────────────────────────────────────────────────────────
def log(msg):
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_config(path):
    with open(path) as f:
        return yaml.safe_load(f)


def _tickers_from_file(path):
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    with open(path) as f:
        return [ln.strip().upper() for ln in f if ln.strip() and not ln.startswith("#")]


def _tickers_from_google_sheet(src):
    # Read via the Sheets API (sheets.googleapis.com) with a service account.
    # NOTE: the public docs.google.com CSV export is intentionally NOT used —
    # this network resets connections to docs.google.com / www.google.com, while
    # the API host is reachable. The sheet must be shared with the service
    # account (viewer is enough).
    import gspread
    from google.oauth2.service_account import Credentials

    creds_file = src.get("creds_file", "csp-wheel-bot-e3194c27a5f7.json")
    if not os.path.isabs(creds_file):
        creds_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), creds_file)
    creds = Credentials.from_service_account_file(
        creds_file, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])

    last_err = None
    for attempt in range(3):
        try:
            gc = gspread.authorize(creds)
            sh = gc.open_by_key(src["sheet_id"])
            ws = sh.get_worksheet_by_id(int(src.get("gid", 0)))
            rows = ws.get_all_values()
            if not rows:
                return []
            header = rows[0]
            col = src.get("column")
            idx = header.index(col) if col in header else 0  # fall back to first column
            return [r[idx].strip().upper() for r in rows[1:]
                    if len(r) > idx and r[idx].strip()]
        except Exception as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise last_err


def resolve_universe(cfg):
    u = cfg["universe"]
    # Backward-compat: old single-source shape (source: file|inline).
    sources = u.get("sources")
    if not sources:
        if u.get("source") == "inline":
            sources = [{"type": "inline", "tickers": u.get("inline") or []}]
        else:
            sources = [{"type": "file", "path": u.get("path", "extra_tickers.txt")}]

    seen, out = set(), []
    for src in sources:
        try:
            if src["type"] == "file":
                tickers = _tickers_from_file(src["path"])
            elif src["type"] == "google_sheet":
                tickers = _tickers_from_google_sheet(src)
            elif src["type"] == "inline":
                tickers = [t.strip().upper() for t in (src.get("tickers") or []) if t.strip()]
            else:
                log(f"  universe: unknown source type '{src.get('type')}' — skipped")
                continue
            added = 0
            for t in tickers:
                if t and t not in seen:
                    seen.add(t)
                    out.append(t)
                    added += 1
            log(f"  universe source {src['type']}: {len(tickers)} tickers ({added} new)")
        except Exception as e:
            log(f"  universe source {src.get('type')} FAILED: {e}")
    return out


def to_float(v):
    try:
        f = float(v)
        return f if f == f else None  # drop NaN
    except (TypeError, ValueError):
        return None


# ── provider adapters ────────────────────────────────────────────────────────
# Each returns a list of normalized PUT contracts within the DTE window:
#   {strike, expiry(YYYY-MM-DD), dte, bid, mid, delta(abs), iv, oi}
# No delta/OI/ARR filtering here — the job applies those uniformly.

def fetch_chain_schwab(ticker, dte_min, dte_max):
    from schwab.client import Client
    client = schwab_client.get_client()
    today = dt.date.today()
    resp = client.get_option_chain(
        ticker.upper(),
        contract_type=Client.Options.ContractType.PUT,
        from_date=today + dt.timedelta(days=dte_min),
        to_date=today + dt.timedelta(days=dte_max),
    )
    resp.raise_for_status()
    data = resp.json()
    stock_price = to_float(data.get("underlyingPrice"))
    out = []
    for exp_key, strikes in (data.get("putExpDateMap") or {}).items():
        expiry = exp_key.split(":")[0]
        for _strike, arr in strikes.items():
            o = arr[0]
            bid = to_float(o.get("bid"))
            ask = to_float(o.get("ask"))
            delta = to_float(o.get("delta"))
            dte = o.get("daysToExpiration")
            if dte is None:
                dte = (dt.date.fromisoformat(expiry) - today).days
            out.append({
                "strike": to_float(o.get("strikePrice")),
                "expiry": expiry,
                "dte": int(dte),
                "bid": bid,
                "mid": (bid + ask) / 2 if (bid is not None and ask is not None) else bid,
                "delta": abs(delta) if delta is not None else None,
                "iv": to_float(o.get("volatility")),        # already a percent
                "oi": int(o.get("openInterest") or 0),
            })
    return stock_price, out


def fetch_chain_tradier(ticker, dte_min, dte_max):
    token = os.getenv("TRADIER_TOKEN")
    base = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com")
    hdr = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    today = dt.date.today()

    q = requests.get(f"{base}/v1/markets/quotes", headers=hdr,
                     params={"symbols": ticker.upper()}, timeout=20)
    q.raise_for_status()
    stock_price = to_float((q.json().get("quotes", {}).get("quote") or {}).get("last"))

    ex = requests.get(f"{base}/v1/markets/options/expirations", headers=hdr,
                      params={"symbol": ticker.upper()}, timeout=20)
    ex.raise_for_status()
    dates = (ex.json().get("expirations") or {}).get("date") or []
    valid = [d for d in dates if dte_min <= (dt.date.fromisoformat(d) - today).days <= dte_max]

    out = []
    for d in valid:
        ch = requests.get(f"{base}/v1/markets/options/chains", headers=hdr,
                          params={"symbol": ticker.upper(), "expiration": d, "greeks": "true"},
                          timeout=25)
        if not ch.ok:
            continue
        for c in ((ch.json().get("options") or {}).get("option") or []):
            if c.get("option_type") != "put":
                continue
            g = c.get("greeks") or {}
            delta = to_float(g.get("delta"))
            smv = to_float(g.get("smv_vol"))
            out.append({
                "strike": to_float(c.get("strike")),
                "expiry": d,
                "dte": (dt.date.fromisoformat(d) - today).days,
                "bid": to_float(c.get("bid")),
                "mid": ((to_float(c.get("bid")) or 0) + (to_float(c.get("ask")) or 0)) / 2,
                "delta": abs(delta) if delta is not None else None,
                "iv": smv * 100 if smv is not None else None,
                "oi": int(c.get("open_interest") or 0),
            })
    return stock_price, out


ADAPTERS = {"schwab": fetch_chain_schwab, "tradier": fetch_chain_tradier}


def fetch_chain(ticker, provider, fallback, dte_min, dte_max):
    order = [provider] + [p for p in (fallback or []) if p != provider]
    last_err = None
    for prov in order:
        fn = ADAPTERS.get(prov)
        if not fn:
            continue
        try:
            price, contracts = fn(ticker, dte_min, dte_max)
            return prov, price, contracts
        except Exception as e:
            last_err = e
            log(f"  {ticker}: provider '{prov}' failed: {e}")
    raise last_err or RuntimeError("no provider succeeded")


# ── screen ───────────────────────────────────────────────────────────────────
def screen(cfg):
    s = cfg["strategy"]
    provider = cfg.get("provider", "schwab")
    fallback = cfg.get("fallback", [])
    pause = float(cfg.get("run", {}).get("request_pause_secs", 0.4))
    basis = s.get("premium_basis", "bid")

    rows = []
    for ticker in resolve_universe(cfg):
        try:
            prov, price, contracts = fetch_chain(ticker, provider, fallback, s["dte_min"], s["dte_max"])
        except Exception as e:
            log(f"  {ticker}: SKIPPED ({e})")
            continue

        picks = []
        for c in contracts:
            strike, delta, dte = c["strike"], c["delta"], c["dte"]
            premium = c["mid"] if basis == "mid" else c["bid"]
            if None in (strike, delta, premium) or strike <= 0 or dte <= 0:
                continue
            if not (s["delta_min"] <= delta <= s["delta_max"]):
                continue
            if c["oi"] <= s["min_open_interest"]:
                continue
            arr = (premium / strike) * (365 / dte) * 100
            if arr <= s["target_arr"]:
                continue
            picks.append({
                "ticker": ticker, "provider": prov, "stock_price": price,
                "strike": strike, "expiry": c["expiry"], "dte": dte,
                "premium": premium, "delta": delta, "iv": c["iv"], "oi": c["oi"],
                "arr": arr, "pop": (1 - delta) * 100,
                "pct_otm": ((price - strike) / price * 100) if price else None,
                "breakeven": strike - premium,
            })

        key = {"arr": "arr", "premium": "premium", "pop": "pop"}[s.get("rank_by", "arr")]
        picks.sort(key=lambda r: r[key], reverse=True)
        picks = picks[: int(s.get("top_n_per_ticker", 3))]
        rows.extend(picks)
        log(f"  {ticker} [{prov}]: {len(picks)} qualifying (of {len(contracts)} contracts)")
        time.sleep(pause)

    key = {"arr": "arr", "premium": "premium", "pop": "pop"}[s.get("rank_by", "arr")]
    rows.sort(key=lambda r: r[key], reverse=True)
    return rows[: int(s.get("max_results", 40))]


# ── PDF ──────────────────────────────────────────────────────────────────────
def render_pdf(cfg, rows, out_path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    s = cfg["strategy"]
    styles = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=styles["Title"], fontSize=18, spaceAfter=4)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9,
                         textColor=colors.HexColor("#555555"), alignment=TA_CENTER)

    doc = SimpleDocTemplate(out_path, pagesize=landscape(letter),
                            leftMargin=0.4 * inch, rightMargin=0.4 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch)
    story = [Paragraph(cfg["output"].get("title", "Daily CSP Screen"), h)]
    # No provider shown — this PDF is shareable.
    crit = (f"{dt.datetime.now():%b %d, %Y %I:%M %p} PT &nbsp;|&nbsp; "
            f"Δ {s['delta_min']}–{s['delta_max']} &nbsp;|&nbsp; DTE {s['dte_min']}–{s['dte_max']} &nbsp;|&nbsp; "
            f"OI &gt; {s['min_open_interest']} &nbsp;|&nbsp; ARR &gt; {s['target_arr']}% &nbsp;|&nbsp; "
            f"premium: {s.get('premium_basis','bid')} &nbsp;|&nbsp; {len(rows)} candidates")
    story += [Paragraph(crit, sub), Spacer(1, 10)]

    if not rows:
        story.append(Paragraph("No contracts matched the criteria today.", styles["Normal"]))
    else:
        # Group by ticker; order groups by each ticker's best ARR (highest first),
        # rows within a group by ARR desc.
        groups = {}
        for r in rows:
            groups.setdefault(r["ticker"], []).append(r)
        order = sorted(groups, key=lambda t: max(x["arr"] for x in groups[t]), reverse=True)

        header = ["Ticker", "Price", "Δ", "Strike", "Expiry", "DTE", "Bid", "Premium",
                  "ARR%", "POP%", "% OTM", "OI", "Collateral", "Break-even"]
        data = [header]
        blank_rows, data_rows = [], []   # row indices for styling
        for gi, tkr in enumerate(order):
            grp = sorted(groups[tkr], key=lambda x: x["arr"], reverse=True)
            for j, r in enumerate(grp):
                premium_dollars = r["premium"] * 100          # Premium = bid × 100
                collateral = r["strike"] * 100 - premium_dollars  # Collateral = strike×100 − premium
                data.append([
                    r["ticker"] if j == 0 else "",            # show ticker once per group
                    f"${r['stock_price']:.2f}" if r["stock_price"] else "—",
                    f"{r['delta']:.2f}", f"${r['strike']:.2f}", r["expiry"], str(r["dte"]),
                    f"${r['premium']:.2f}", f"${premium_dollars:,.0f}",
                    f"{r['arr']:.1f}", f"{r['pop']:.0f}",
                    f"{r['pct_otm']:.1f}" if r["pct_otm"] is not None else "—",
                    str(r["oi"]), f"${collateral:,.0f}", f"${r['breakeven']:.2f}",
                ])
                data_rows.append(len(data) - 1)
            if gi < len(order) - 1:                            # empty row between tickers
                data.append([""] * len(header))
                blank_rows.append(len(data) - 1)

        col_w = [0.65, 0.65, 0.42, 0.65, 0.92, 0.4, 0.55, 0.8,
                 0.55, 0.5, 0.55, 0.5, 0.9, 0.82]
        tbl = Table(data, repeatRows=1, colWidths=[w * inch for w in col_w])
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),   # ticker column bold
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("TEXTCOLOR", (8, 1), (8, -1), colors.HexColor("#047857")),  # ARR green
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#1e293b")),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ]
        for r in data_rows:                                    # hairline under data rows only
            style.append(("LINEBELOW", (0, r), (-1, r), 0.25, colors.HexColor("#e2e8f0")))
        for r in blank_rows:                                   # keep separator rows slim/clean
            style.append(("TOPPADDING", (0, r), (-1, r), 1))
            style.append(("BOTTOMPADDING", (0, r), (-1, r), 1))
        tbl.setStyle(TableStyle(style))
        story.append(tbl)

    story += [Spacer(1, 12),
              Paragraph(f"Generated {dt.datetime.now():%Y-%m-%d %H:%M} PT • Informational only, not advice. "
                        f"Premiums are last quotes and move at the open.", sub)]
    doc.build(story)
    return out_path


# ── Discord ──────────────────────────────────────────────────────────────────
def post_discord(cfg, pdf_path, rows):
    webhook = os.getenv(cfg["output"].get("discord_webhook_env", "DISCORD_WEBHOOK_URL"))
    if not webhook:
        log("No Discord webhook in env — skipping post.")
        return
    top = ", ".join(f"{r['ticker']} {r['arr']:.0f}%" for r in rows[:3]) or "no qualifying setups"
    content = (f"📉 **Daily CSP Screen — {dt.date.today():%b %d, %Y}**\n"
               f"{len(rows)} candidates (Δ {cfg['strategy']['delta_min']}–{cfg['strategy']['delta_max']}, "
               f"DTE {cfg['strategy']['dte_min']}–{cfg['strategy']['dte_max']}, "
               f"OI>{cfg['strategy']['min_open_interest']}, ARR>{cfg['strategy']['target_arr']}%). "
               f"Top: {top}")
    with open(pdf_path, "rb") as f:
        resp = requests.post(webhook, data={"content": content},
                             files={"file": (os.path.basename(pdf_path), f, "application/pdf")}, timeout=30)
    resp.raise_for_status()
    log(f"Posted to Discord ({resp.status_code}).")


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                     "optionlookup_config.yaml"))
    ap.add_argument("--dry-run", action="store_true", help="build the PDF but do not post to Discord")
    ap.add_argument("--provider", help="override the config provider (schwab|tradier)")
    ap.add_argument("--force", action="store_true", help="run even on weekends (for testing)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.provider:
        cfg["provider"] = args.provider

    if not args.force and cfg.get("run", {}).get("skip_weekends", True) and dt.date.today().weekday() >= 5:
        log("Weekend — market closed, skipping run.")
        return

    log(f"Screening universe with provider={cfg.get('provider')} …")
    rows = screen(cfg)
    log(f"{len(rows)} candidates after filters.")

    if not rows and not cfg["output"].get("post_when_empty", True):
        log("No candidates and post_when_empty=false — nothing to do.")
        return

    pdf_dir = cfg["output"].get("pdf_dir", "reports")
    if not os.path.isabs(pdf_dir):
        pdf_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), pdf_dir)
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f"csp_screen_{dt.date.today():%Y%m%d}.pdf")
    render_pdf(cfg, rows, pdf_path)
    log(f"PDF: {pdf_path}")

    if args.dry_run:
        log("Dry run — not posting to Discord.")
    else:
        post_discord(cfg, pdf_path, rows)


if __name__ == "__main__":
    main()
