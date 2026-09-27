#!/bin/bash
# Daily Option Lookup CSP screener → PDF → Discord. Driven by optionlookup_config.yaml.
cd /Users/ankushsinghal/Documents/Trading || exit 1
PY="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
"$PY" option_lookup_job.py "$@" >> logs/option_lookup.log 2>&1
