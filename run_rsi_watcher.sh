#!/bin/bash
# Daily RSI(14) watcher for QQQ/SPY — pings Discord on oversold (RSI <= 35).
# Suggested schedule: weekdays ~3:45pm ET (before the close).

set -e

TRADING_DIR="/Users/ankushsinghal/Documents/Trading"
PYTHON="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
LOG="$TRADING_DIR/rsi_watcher.log"

cd "$TRADING_DIR"

# Load .env if present
if [ -f "$TRADING_DIR/.env" ]; then
    set -a
    source "$TRADING_DIR/.env"
    set +a
fi

echo "" >> "$LOG"
echo "======================================" >> "$LOG"
echo "Run started: $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG"
echo "======================================" >> "$LOG"

"$PYTHON" "$TRADING_DIR/rsi_watcher.py" "$@" >> "$LOG" 2>&1

echo "Run finished: $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG"
