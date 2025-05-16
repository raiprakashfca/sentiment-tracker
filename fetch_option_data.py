#!/usr/bin/env python3
import os
import json
import pickle
import time
import logging
import datetime
import pytz
import numpy as np
from scipy.stats import norm
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import WorksheetNotFound
from kiteconnect import KiteConnect

# ----------------- Configuration -----------------
GCREDS_ENV_VAR       = "GCREDS"
GREEKS_SHEET_ENV_VAR = "GREEKS_SHEET_ID"
TOKEN_SHEET_ENV_VAR  = "TOKEN_SHEET_ID"

LOG_SHEET_NAME       = os.getenv("LOG_SHEET_NAME", "GreeksLog")
OPEN_SHEET_NAME      = os.getenv("OPEN_SHEET_NAME", "GreeksOpen")
ARCHIVE_SHEET_NAME   = os.getenv("ARCHIVE_SHEET_NAME", "GreeksArchive")

RISK_FREE_RATE = float(os.getenv("RISK_FREE_RATE", "0.07"))
DELTA_MIN      = float(os.getenv("DELTA_MIN", "0.0"))
DELTA_MAX      = float(os.getenv("DELTA_MAX", "1.0"))
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "7"))
QUOTE_BATCH_SIZE = int(os.getenv("QUOTE_BATCH_SIZE", "50"))

CACHE_FILE = os.getenv("INSTRUMENT_CACHE_FILE", "instrument_cache.pkl")
CACHE_TTL   = int(os.getenv("INSTRUMENT_CACHE_TTL_HOURS", "24")) * 3600  # seconds

# Expected header row
HEADER = [
    "timestamp",
    "nifty_ce_delta","nifty_ce_vega","nifty_ce_theta",
    "nifty_pe_delta","nifty_pe_vega","nifty_pe_theta",
    "bn_ce_delta","bn_ce_vega","bn_ce_theta",
    "bn_pe_delta","bn_pe_vega","bn_pe_theta"
]

# Timezone
IST = pytz.timezone("Asia/Kolkata")

# ----------------- Setup Logging -----------------
def setup_logging():
    logging.basicConfig(
        filename="fetch_option_data.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

# ----------------- Config Loader -----------------
def load_config():
    greeks_key = os.getenv(GREEKS_SHEET_ENV_VAR)
    token_key  = os.getenv(TOKEN_SHEET_ENV_VAR)
    if not greeks_key or not token_key:
        raise RuntimeError(f"Missing env vars: {GREEKS_SHEET_ENV_VAR}, {TOKEN_SHEET_ENV_VAR}")
    return greeks_key, token_key

# ----------------- Google Sheets Auth -------------
def authorize_sheets():
    creds_data = os.getenv(GCREDS_ENV_VAR)
    if creds_data:
        creds = json.loads(creds_data) if isinstance(creds_data, str) else creds_data
    elif os.path.exists("credentials.json"):
        with open("credentials.json") as f:
            creds = json.load(f)
    else:
        raise RuntimeError(f"Service account JSON not found in env var '{GCREDS_ENV_VAR}' or credentials.json")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds, scope)
    return gspread.authorize(credentials)

# ----------------- Kite Auth ----------------------
def get_kite_client(client, token_key):
    book = client.open_by_key(token_key)
    try:
        ws = book.worksheet("ZerodhaTokenStore")
    except WorksheetNotFound:
        ws = book.get_worksheet(0)
        logging.warning("ZerodhaTokenStore not found; using first sheet '%s'", ws.title)
    api_key      = ws.acell("A1").value
    access_token = ws.acell("C1").value
    if not api_key or not access_token:
        raise RuntimeError("Missing API credentials in ZerodhaTokenStore (A1/C1)")
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite, ws

def reload_kite_token(kite, ws):
    api_key      = ws.acell("A1").value
    access_token = ws.acell("C1").value
    kite.api_key = api_key
    kite.set_access_token(access_token)
    logging.info("Refreshed Kite token from sheet")

# ----------------- Instrument Cache ----------------
def get_all_instruments(kite):
    if os.path.exists(CACHE_FILE) and (time.time() - os.path.getmtime(CACHE_FILE)) < CACHE_TTL:
        try:
            with open(CACHE_FILE, "rb") as f:
                instruments = pickle.load(f)
            logging.info("Loaded instruments from cache (%d entries)", len(instruments))
            return instruments
        except Exception as e:
            logging.warning("Failed to load cache: %s", e)
    instruments = kite.instruments("NFO")
    try:
        with open(CACHE_FILE, "wb") as f:
            pickle.dump(instruments, f)
        logging.info("Cached %d instruments", len(instruments))
    except Exception as e:
        logging.warning("Failed to write cache: %s", e)
    return instruments

# ----------------- Safe Kite Calls -----------------
def safe_ltp(kite, ws, symbols):
    try:
        return kite.ltp(*symbols)
    except Exception as e:
        logging.warning("LTP fetch error: %s – retrying", e)
        reload_kite_token(kite, ws)
        return kite.ltp(*symbols)

def safe_quote(kite, ws, tokens):
    all_quotes = {}
    for i in range(0, len(tokens), QUOTE_BATCH_SIZE):
        batch = tokens[i:i+QUOTE_BATCH_SIZE]
        try:
            quotes = kite.quote(batch)
        except Exception as e:
            logging.warning("Quote fetch error for batch %d-%d: %s – retrying", i, i+len(batch), e)
            reload_kite_token(kite, ws)
            quotes = kite.quote(batch)
        all_quotes.update(quotes)
    return all_quotes

# ----------------- Greeks Calculations ------------
def fallback_iv(S, K, T, r, price, flag):
    def bs_price(vol):
        d1 = (np.log(S/K) + (r + 0.5*vol*vol)*T) / (vol*np.sqrt(T))
        d2 = d1 - vol*np.sqrt(T)
        if flag == "CE":
            return S*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
        else:
            return K*np.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1)
    low, high = 1e-6, 5.0
    for _ in range(50):
        mid = (low + high) / 2
        if bs_price(mid) > price:
            high = mid
        else:
            low = mid
    return (low + high) / 2

def calculate_greeks(S, K, T, r, vol, flag):
    d1 = (np.log(S/K) + (r + 0.5*vol*vol)*T) / (vol*np.sqrt(T))
    d2 = d1 - vol*np.sqrt(T)
    delta = norm.cdf(d1) if flag == "CE" else -norm.cdf(-d1)
    vega  = S * norm.pdf(d1) * np.sqrt(T)
    if flag == "CE":
        theta = -S*norm.pdf(d1)*vol/(2*np.sqrt(T)) - r*K*np.exp(-r*T)*norm.cdf(d2)
    else:
        theta = -S*norm.pdf(d1)*vol/(2*np.sqrt(T)) + r*K*np.exp(-r*T)*norm.cdf(-d2)
    return delta, vega, theta

# ----------------- Sheet Writes --------------------
def write_sheets(client, greeks_key, log_row):
    book    = client.open_by_key(greeks_key)
    log_ws  = book.worksheet(LOG_SHEET_NAME)
    open_ws = book.worksheet(OPEN_SHEET_NAME)

    vals = log_ws.get_all_values()
    to_append = []
    if not vals or vals[0] != HEADER:
        log_ws.clear()
        to_append.append(HEADER)
    to_append.append(log_row)
    log_ws.append_rows(to_append, value_input_option='USER_ENTERED')

    cutoff = (datetime.datetime.now(IST) - datetime.timedelta(days=RETENTION_DAYS)).date()
    all_vals = log_ws.get_all_values()
    archive_rows = [r for r in all_vals[1:]
                    if datetime.datetime.strptime(r[0], '%Y-%m-%d %H:%M:%S').date() < cutoff]
    if archive_rows:
        try:
            arc_ws = book.worksheet(ARCHIVE_SHEET_NAME)
        except WorksheetNotFound:
            arc_ws = book.add_worksheet(ARCHIVE_SHEET_NAME, rows="100", cols=str(len(HEADER)))
            arc_ws.append_row(HEADER)
        arc_ws.append_rows(archive_rows, value_input_option='USER_ENTERED')
        for idx in range(len(all_vals), 1, -1):
            row_date = datetime.datetime.strptime(all_vals[idx-1][0], '%Y-%m-%d %H:%M:%S').date()
            if row_date < cutoff:
                log_ws.delete_rows(idx)

    open_vals = open_ws.get_all_values()
    today_str = datetime.datetime.now(IST).strftime('%Y-%m-%d')
    if len(open_vals) < 2 or not open_vals[1][0].startswith(today_str):
        open_ws.clear()
        open_ws.append_rows([HEADER, log_row], value_input_option='USER_ENTERED')

# ----------------- Main Routine -------------------
def main():
    setup_logging()
    logging.info("===== Starting fetch_option_data.py =====")

    greeks_key, token_key = load_config()
    client, token_key  = authorize_sheets(), token_key
    kite, token_ws      = get_kite_client(client, token_key)
    instruments         = get_all_instruments(kite)

    instrument_names = {'nifty': 'NIFTY', 'bn': 'BANKNIFTY'}
    ltp_map = {'nifty': ['NIFTY 50','NIFTY'], 'bn': ['NIFTY BANK','BANKNIFTY']}

    ltp_keys = [f"NSE:{sym}" for syms in ltp_map.values() for sym in syms]
    ltp_data = safe_ltp(kite, token_ws, ltp_keys)
    now = datetime.datetime.now(IST)

    results = {f"{k}_{o}_{m}": 0.0 for k in instrument_names for o in ['ce','pe'] for m in ['delta','vega','theta']}

    for key, name in instrument_names.items():
        sym = next((s for s in ltp_map[key] if f"NSE:{s}" in ltp_data), None)
        if not sym:
            logging.warning("Spot LTP missing for %s", key)
            continue
        S = ltp_data[f"NSE:{sym}"+]['last_price']
        opts = [i for i in instruments if i['name']==name and i['segment']=='NFO-OPT']
        tokens = [f"NFO:{i['instrument_token']}" for i in opts]
        quotes = safe_quote(kite, token_ws, tokens)
        for inst in opts:
            quote     = quotes.get(f"NFO:{inst['instrument_token']}")
            if not quote:
                continue
            iv    = quote.get('implied_volatility',0)/100.0
            price = quote.get('last_price')
            exp_naive = datetime.datetime.combine(inst['expiry'], datetime.time(15,30))
            exp_dt    = IST.localize(exp_naive)
            T = (exp_dt.astimezone(pytz.UTC) - now.astimezone(pytz.UTC)).total_seconds()/(365*24*3600)
            if (not iv or iv<=0) and price:
                iv = fallback_iv(S, inst['strike'], T, RISK_FREE_RATE, price, inst['instrument_type'])
            if T<=0 or iv<=0:
                continue
            delta, vega, theta = calculate_greeks(S, inst['strike'], T, RISK_FREE_RATE, iv, inst['instrument_type'])
            if DELTA_MIN <= abs(delta) <= DELTA_MAX:
                results[f"{key}_{inst['instrument_type'].lower()}_delta"] += delta
                results[f"{key}_{inst['instrument_type'].lower()}_vega"]  += vega
                results[f"{key}_{inst['instrument_type'].lower()}_theta"] += theta

    log_row = [now.strftime('%Y-%m-%d %H:%M:%S')]
    for k in instrument_names:
        for o in ['ce','pe']:
            log_row += [round(results[f"{k}_{o}_delta"],4), round(results[f"{k}_{o}_vega"],2), round(results[f"{k}_{o}_theta"],2)]

    write_sheets(client, greeks_key, log_row)
    logging.info("===== Completed fetch_option_data.py =====")

if __name__ == '__main__':
    main()
