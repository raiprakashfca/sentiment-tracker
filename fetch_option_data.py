#!/usr/bin/env python3
import os
import json
import datetime
import pytz
import numpy as np
from scipy.stats import norm
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from kiteconnect import KiteConnect
from gspread.exceptions import WorksheetNotFound

# ---------- CONFIGURATION ----------
GCREDS_ENV_VAR       = "GCREDS"
GREEKS_SHEET_ENV_VAR = "GREEKS_SHEET_ID"
TOKEN_SHEET_ENV_VAR  = "TOKEN_SHEET_ID"

LOG_SHEET_NAME       = "GreeksLog"
OPEN_SHEET_NAME      = "GreeksOpen"
ARCHIVE_SHEET_NAME   = "GreeksArchive"

RISK_FREE_RATE       = 0.07
DELTA_MIN            = 0.0
DELTA_MAX            = 1.0
RETENTION_DAYS       = 7

# Expected header row
HEADER = [
    "timestamp",
    "nifty_ce_delta","nifty_ce_vega","nifty_ce_theta",
    "nifty_pe_delta","nifty_pe_vega","nifty_pe_theta",
    "bn_ce_delta","bn_ce_vega","bn_ce_theta",
    "bn_pe_delta","bn_pe_vega","bn_pe_theta"
]

# ---------- HELPER: Load Service Account ----------
def load_service_account():
    creds_data = os.getenv(GCREDS_ENV_VAR)
    if creds_data:
        creds_dict = json.loads(creds_data) if isinstance(creds_data, str) else creds_data
    elif os.path.exists("credentials.json"):
        with open("credentials.json") as f:
            creds_dict = json.load(f)
    else:
        raise RuntimeError(f"Service account JSON not found in env var '{GCREDS_ENV_VAR}' or credentials.json")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

# ---------- MAIN SCRIPT ----------
def main():
    # --- Debug: start of main ---
    print("[Fetch] Starting fetch_option_data.py at", datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    # Authenticate Google Sheets
    creds = load_service_account()
    client = gspread.authorize(creds)

    # Sheet IDs
    greeks_key = os.getenv(GREEKS_SHEET_ENV_VAR)
    token_key  = os.getenv(TOKEN_SHEET_ENV_VAR)
    if not greeks_key or not token_key:
        raise RuntimeError(f"Missing env vars: {GREEKS_SHEET_ENV_VAR}, {TOKEN_SHEET_ENV_VAR}")

    # Fetch Kite credentials
    token_book = client.open_by_key(token_key)
    try:
        token_ws = token_book.worksheet("ZerodhaTokenStore")
    except WorksheetNotFound:
        token_ws = token_book.get_worksheet(0)
        print(f"Warning: 'ZerodhaTokenStore' not found, using '{token_ws.title}'")
    api_key      = token_ws.acell('A1').value
    access_token = token_ws.acell('C1').value
    if not api_key or not access_token:
        raise RuntimeError("Missing API credentials in ZerodhaTokenStore (A1/C1)")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    # Open sheets
    book    = client.open_by_key(greeks_key)
    log_ws  = book.worksheet(LOG_SHEET_NAME)
    open_ws = book.worksheet(OPEN_SHEET_NAME)

    # Ensure header exists
    vals = log_ws.get_all_values()
    if not vals or vals[0] != HEADER:
        log_ws.clear()
        log_ws.append_row(HEADER)
        vals = log_ws.get_all_values()

    # Fetch all instruments
    instruments = kite.instruments("NFO")

    # Underlying mappings
    instrument_names = {'nifty': 'NIFTY', 'bn': 'BANKNIFTY'}
    ltp_symbol_map   = {'nifty': ['NIFTY 50', 'NIFTY'], 'bn': ['NIFTY BANK', 'BANKNIFTY'] }

    # Prepare aggregation
    results = {f"{k}_{o}_{m}": 0.0
               for k in instrument_names for o in ['ce','pe'] for m in ['delta','vega','theta']}

    # Timestamp
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)

    # Fetch underlying spot LTPs
    ltp_keys = [f"NSE:{sym}" for syms in ltp_symbol_map.values() for sym in syms]
    ltp_data = kite.ltp(*ltp_keys)
    print("Available spot LTP keys:", list(ltp_data.keys()))

    # Compute Greeks
    for key, name in instrument_names.items():
        # Determine spot symbol
        sym = next((s for s in ltp_symbol_map[key] if f"NSE:{s}" in ltp_data), None)
        print(f"{key.upper()} resolved to spot symbol: {sym}")
        if not sym:
            continue
        S = ltp_data[f"NSE:{sym}"]['last_price']
        # Filter option instruments
        opts = [i for i in instruments if i['name']==name and i['segment']=='NFO-OPT']
        print(f"Found {len(opts)} option instruments for {name}")
        for inst in opts:
            flag = inst['instrument_type']  # CE or PE
            K    = inst['strike']
            exp_dt = datetime.datetime.combine(inst['expiry'], datetime.time(15,30), tzinfo=ist)
            T = (exp_dt.astimezone(pytz.UTC) - now.astimezone(pytz.UTC)).total_seconds()/(365*24*3600)

            # Robust quote fetch
            qdict = kite.quote(f"NFO:{inst['instrument_token']}")
            if not qdict:
                continue
            _, quote = next(iter(qdict.items()))
            iv = quote.get('implied_volatility', 0.0) / 100.0

            # Skip invalid
            if T <= 0 or iv <= 0:
                continue

            # Black-Scholes Greeks
            d1 = (np.log(S/K) + (RISK_FREE_RATE + 0.5*iv*iv)*T) / (iv * np.sqrt(T))
            delta = norm.cdf(d1) if flag=='CE' else -norm.cdf(-d1)
            vega  = S * norm.pdf(d1) * np.sqrt(T)
            theta = ((-S * norm.pdf(d1) * iv/(2*np.sqrt(T)) - RISK_FREE_RATE * K * np.exp(-RISK_FREE_RATE*T) * norm.cdf(d1))
                     if flag=='CE' else
                     (-S * norm.pdf(d1) * iv/(2*np.sqrt(T)) + RISK_FREE_RATE * K * np.exp(-RISK_FREE_RATE*T) * norm.cdf(-d1)))

            # Apply filter
            if DELTA_MIN <= abs(delta) <= DELTA_MAX:
                results[f"{key}_{flag.lower()}_delta"] += delta
                results[f"{key}_{flag.lower()}_vega"]  += vega
                results[f"{key}_{flag.lower()}_theta"] += theta

    # Append row
    row = [now.strftime('%Y-%m-%d %H:%M:%S')]
    for k in instrument_names:
        for o in ['ce','pe']:
            row += [round(results[f"{k}_{o}_delta"],4),
                    round(results[f"{k}_{o}_vega"],2),
                    round(results[f"{k}_{o}_theta"],2)]
    log_ws.append_row(row)

    # Archive old rows
    cutoff = (now - datetime.timedelta(days=RETENTION_DAYS)).date()
    all_vals = log_ws.get_all_values()
    to_archive = [(idx, r) for idx, r in enumerate(all_vals[1:], start=2)
                  if datetime.datetime.strptime(r[0], '%Y-%m-%d %H:%M:%S').date() < cutoff]
    if to_archive:
        try:
            arc_ws = book.worksheet(ARCHIVE_SHEET_NAME)
        except WorksheetNotFound:
            arc_ws = book.add_worksheet(ARCHIVE_SHEET_NAME, rows=1, cols=len(HEADER))
            arc_ws.append_row(HEADER)
        for _, r in to_archive:
            arc_ws.append_row(r)
        for idx, _ in sorted(to_archive, reverse=True):
            log_ws.delete_row(idx)

    # Initialize open snapshot
    vals_open = open_ws.get_all_values()
    if len(vals_open) < 2 or not vals_open[1][0].startswith(now.strftime('%Y-%m-%d')):
        open_ws.clear()
        open_ws.append_row(HEADER)
        open_ws.append_row(row)

    print(f"Logged Greeks at {now.strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == '__main__':
    main()
