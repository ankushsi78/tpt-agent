#!/usr/bin/env python3
"""Post the weekly CSP Wheel Bot performance report PDF to Discord.

Uploads the PDF as a file attachment to the free community channel webhook
(DISCORD_FREE_WEBHOOK_URL in Trading/.env).

Usage:
    python3 post_to_discord.py                     # latest report in reports/
    python3 post_to_discord.py --pdf /path/to.pdf  # specific file
    python3 post_to_discord.py --dry-run           # show what would be posted
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

ENV_FILE = Path("/Users/ankushsinghal/Documents/Trading/.env")
REPORTS_DIR = Path("/Users/ankushsinghal/Documents/Trading/reports")
WEBHOOK_ENV_KEY = "DISCORD_FREE_WEBHOOK_URL"


def read_webhook_url():
    if not ENV_FILE.exists():
        sys.exit(f"ERROR: {ENV_FILE} not found.")
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{WEBHOOK_ENV_KEY}="):
            url = line.split("=", 1)[1].strip().strip('"').strip("'")
            if url:
                return url
    sys.exit(f"ERROR: {WEBHOOK_ENV_KEY} not set in {ENV_FILE}.")


def latest_report():
    pdfs = sorted(REPORTS_DIR.glob("CSP_Wheel_Bot_Weekly_Report_*.pdf"))
    if not pdfs:
        sys.exit(f"ERROR: no CSP_Wheel_Bot_Weekly_Report_*.pdf found in "
                 f"{REPORTS_DIR}. Run generate_report.py first.")
    # filenames embed the expiry date, so lexicographic sort = chronological
    return pdfs[-1]


def week_from_filename(pdf: Path):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", pdf.name)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%d").strftime("%m/%d/%Y")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", help="Path to the report PDF "
                    "(default: newest report in reports/)")
    ap.add_argument("--message", help="Override the message text.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be posted without posting.")
    args = ap.parse_args()

    pdf = Path(args.pdf) if args.pdf else latest_report()
    if not pdf.exists():
        sys.exit(f"ERROR: {pdf} does not exist.")
    size_mb = pdf.stat().st_size / 1e6
    if size_mb > 8:
        sys.exit(f"ERROR: {pdf.name} is {size_mb:.1f} MB — over Discord's "
                 "8 MB webhook attachment limit.")

    week = week_from_filename(pdf)
    if args.message:
        content = args.message
    else:
        content = ("📊 **CSP Wheel Bot — Weekly Performance Report**"
                   + (f" · Week Ending {week}" if week else "")
                   + "\nThis week's expiration results, full portfolio "
                     "stats, and key takeaways — PDF attached.")

    if args.dry_run:
        print(f"Would post to {WEBHOOK_ENV_KEY} webhook:")
        print(f"  file:    {pdf}  ({size_mb:.2f} MB)")
        print(f"  message: {content}")
        return

    url = read_webhook_url()
    with open(pdf, "rb") as f:
        resp = requests.post(
            url,
            data={"content": content},
            files={"file": (pdf.name, f, "application/pdf")},
            timeout=30)
    if resp.status_code in (200, 204):
        print(f"Posted {pdf.name} to Discord (free community channel).")
    else:
        sys.exit(f"ERROR: Discord returned {resp.status_code}: "
                 f"{resp.text[:300]}")


if __name__ == "__main__":
    main()
