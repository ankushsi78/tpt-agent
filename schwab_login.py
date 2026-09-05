#!/usr/bin/env python3
"""
One-time Schwab OAuth login.

Run this once (and again roughly every 7 days when the refresh token expires):

    python3 schwab_login.py

It opens a browser to Schwab, you log in and approve, and the resulting token
is cached to schwab_token.json. After that, schwab_client.py reuses the token
silently until it expires.

Requires in .env:
    SCHWAB_API_KEY=<client id from developer.schwab.com>
    SCHWAB_API_SECRET=<client secret>
    SCHWAB_CALLBACK_URL=https://127.0.0.1:8182   (must match the app registration)
"""

from schwab_client import get_client, get_account_hash, account_summary

if __name__ == "__main__":
    print("Starting Schwab login flow — a browser window will open.")
    print("You'll see a self-signed cert warning on 127.0.0.1 — that's expected; proceed.\n")
    client = get_client(interactive=True)
    print("\nLogin successful. Token cached to schwab_token.json\n")
    h = get_account_hash(client)
    account_summary(client, h)
