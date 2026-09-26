# Graph Report - sentiment-tracker  (2026-09-26)

## Corpus Check
- 7 files · ~2,880 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 3 file(s) not represented in the graph (top: (none) 2, .csv 1)

## Summary
- 68 nodes · 67 edges · 32 communities (4 shown, 28 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `dac5445b`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- fetch_option_data.py
- main_app.py
- io
- playwright_sync_api
- pytest
- re
- ref_http
- shutil
- socket
- subprocess
- sys
- ref_crypto
- trailmark_diagram
- urllib_error
- typing
- urllib_parse
- urllib_request
- zipfile
- backfill_greeks.py
- collections
- struct
- pathlib
- html
- csv
- argparse
- tempfile
- ref
- ref_path
- ref_child_process
- ref_fs
- 📈 NIFTY Sentiment Tracker (Options Greeks Based)
- CLAUDE.md

## God Nodes (most connected - your core abstractions)
1. `main()` - 6 edges
2. `fetch_greeks_yf()` - 4 edges
3. `📈 NIFTY Sentiment Tracker (Options Greeks Based)` - 4 edges
4. `setup_logging()` - 2 edges
5. `load_config()` - 2 edges
6. `authorize_sheets()` - 2 edges
7. `calculate_greeks()` - 2 edges
8. `write_sheets()` - 2 edges
9. `Fetch option chain using yfinance for given ticker. Returns dict with ce_delta,…` - 1 edges
10. `graphify` - 1 edges

## Surprising Connections (you probably didn't know these)
- None detected - all connections are within the same source files.

## Import Cycles
- None detected.

## Communities (32 total, 28 thin omitted)

### Community 0 - "fetch_option_data.py"
Cohesion: 0.26
Nodes (11): authorize_sheets(), calculate_greeks(), fetch_greeks_yf(), load_config(), main(), Fetch option chain using yfinance for given ticker. Returns dict with ce_delta,…, setup_logging(), write_sheets() (+3 more)

### Community 1 - "main_app.py"
Cohesion: 0.31
Nodes (6): datetime, os, pandas, pytz, streamlit, streamlit_autorefresh

### Community 21 - "backfill_greeks.py"
Cohesion: 0.19
Nodes (9): gspread, json, kiteconnect, math, numpy, oauth2client_service_account, requests, scipy_stats (+1 more)

### Community 443 - "📈 NIFTY Sentiment Tracker (Options Greeks Based)"
Cohesion: 0.40
Nodes (4): 🚀 Features, 📈 NIFTY Sentiment Tracker (Options Greeks Based), 🔐 Secrets Format, 🛠️ Setup

## Knowledge Gaps
- **4 isolated node(s):** `graphify`, `🚀 Features`, `🛠️ Setup`, `🔐 Secrets Format`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 45 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **28 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What connects `graphify`, `🚀 Features`, `🛠️ Setup` to the rest of the system?**
  _4 weakly-connected nodes found - possible documentation gaps or missing edges._