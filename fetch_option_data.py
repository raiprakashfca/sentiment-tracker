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

RISK_FREE_RATE   = float(os.getenv("RISK_FREE_RATE", "0.07"))
DELTA_MIN        = float(os.getenv("DELTA_MIN", "0.0"))
DELTA_MAX        = float(os.getenv("DELTA_MAX", "1.0"))
RETENTION_DAYS   = int(os.getenv("RETENTION_DAYS", "7"))
QUOTE_BATCH_SIZE = int(os.getenv("QUOTE_BATCH_SIZE", "50"))

CACHE_FILE = os.getenv("INSTRUMENT_CACHE_FILE", "instrument_cache.pkl")
CACHE_TTL  = int(os.getenv("INSTRUMENT_CACHE_TTL_HOURS", "24")) * 3600

HEADER = [
    "timestamp",
    "nifty_ce_delta","nifty_ce_vega","nifty_ce_theta",
    "nifty_pe_delta","nifty_pe_vega","nifty_pe_theta",
    "bn_ce_delta","bn_ce_vega","bn_ce_theta",
    "bn_pe_delta","bn_pe_vega","bn_pe_theta"
]

IST = pytz.timezone("Asia/Kolkata")

## Setup logging
def setup_logging():
    logging.basicConfig(
        filename="fetch_option_data.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

## Load config from env
def load_config():
    greeks_key = os.getenv(GREEKS_SHEET_ENV_VAR)
    token_key  = os.getenv(TOKEN_SHEET_ENV_VAR)
    if not greeks_key or not token_key:
        raise RuntimeError(f"Missing env vars: {GREEKS_SHEET_ENV_VAR}, {TOKEN_SHEET_ENV_VAR}")
    return greeks_key, token_key

## Authorize Google Sheets
def authorize_sheets():
    creds_data = os.getenv(GCREDS_ENV_VAR)
    if creds_data:
        creds = json.loads(creds_data) if isinstance(creds_data, str) else creds_data
    elif os.path.exists("credentials.json"):
        with open("credentials.json") as f:
            creds = json.load(f)
    else:
        raise RuntimeError(f"Service account JSON not found in '{GCREDS_ENV_VAR}' or credentials.json")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds, scope)
    return gspread.authorize(credentials)

## Get Kite client and token sheet
def get_kite_client(client, token_key):
    book = client.open_by_key(token_key)
    try:
        ws = book.worksheet("ZerodhaTokenStore")
    except WorksheetNotFound:
        ws = book.get_worksheet(0)
        logging.warning("ZerodhaTokenStore not found, using sheet '%s'", ws.title)
    api_key      = ws.acell("A1").value
    access_token = ws.acell("C1").value
    if not api_key or not access_token:
        raise RuntimeError("Missing API credentials in ZerodhaTokenStore")
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite, ws

def reload_kite_token(kite, ws):
    api_key      = ws.acell("A1").value
    access_token = ws.acell("C1").value
    kite.api_key = api_key
    kite.set_access_token(access_token)
    logging.info("Refreshed Kite token from sheet")

## Cache instrument list
        
def get_all_instruments(kite):
    if os.path.exists(CACHE_FILE) and time.time() - os.path.getmtime(CACHE_FILE) < CACHE_TTL:
        try:
            with open(CACHE_FILE, 'rb') as f:
                instruments = pickle.load(f)
            logging.info("Loaded %d instruments from cache", len(instruments))
            return instruments
        except Exception as e:
            logging.warning("Cache load failed: %s", e)
    instruments = kite.instruments('NFO')
    try:
        with open(CACHE_FILE, 'wb') as f:
            pickle.dump(instruments, f)
        logging.info("Cached %d instruments", len(instruments))
    except Exception as e:
        logging.warning("Cache write failed: %s", e)
    return instruments

## Safe Kite calls with retry

def safe_ltp(kite, ws, symbols):
    try:
        return kite.ltp(*symbols)
    except Exception as e:
        logging.warning("LTP error: %s, retrying", e)
        reload_kite_token(kite, ws)
        return kite.ltp(*symbols)


def safe_quote(kite, ws, tokens):
    all_q = {}
    for start in range(0, len(tokens), QUOTE_BATCH_SIZE):
        batch = tokens[start:start+QUOTE_BATCH_SIZE]
        try:
            q = kite.quote(batch)
        except Exception as e:
            logging.warning("Quote error batch %d-%d: %s", start, start+len(batch), e)
            reload_kite_token(kite, ws)
            q = kite.quote(batch)
        all_q.update(q)
    return all_q

## Black-Scholes fallback and Greeks

def fallback_iv(S, K, T, r, price, flag):
    def bs_price(vol):
        d1 = (np.log(S/K)+(r+0.5*vol**2)*T)/(vol*np.sqrt(T))
        d2 = d1-vol*np.sqrt(T)
        if flag=='CE':
            return S*norm.cdf(d1)-K*np.exp(-r*T)*norm.cdf(d2)
        return K*np.exp(-r*T)*norm.cdf(-d2)-S*norm.cdf(-d1)
    lo, hi = 1e-6,5.0
    for _ in range(50):
        mid = (lo+hi)/2
        if bs_price(mid)>price: hi=mid
        else: lo=mid
    return (lo+hi)/2


def calculate_greeks(S, K, T, r, vol, flag):
    d1 = (np.log(S/K)+(r+0.5*vol**2)*T)/(vol*np.sqrt(T))
    d2 = d1-vol*np.sqrt(T)
    delta = norm.cdf(d1) if flag=='CE' else -norm.cdf(-d1)
    vega  = S*norm.pdf(d1)*np.sqrt(T)
    if flag=='CE':
        theta = -S*norm.pdf(d1)*vol/(2*np.sqrt(T)) - r*K*np.exp(-r*T)*norm.cdf(d2)
    else:
        theta = -S*norm.pdf(d1)*vol/(2*np.sqrt(T)) + r*K*np.exp(-r*T)*norm.cdf(-d2)
    return delta, vega, theta

## Write to Google Sheets

def write_sheets(client, greeks_key, row):
    book = client.open_by_key(greeks_key)
    log_ws = book.worksheet(LOG_SHEET_NAME)
    open_ws= book.worksheet(OPEN_SHEET_NAME)

    vals = log_ws.get_all_values()
    if not vals or vals[0]!=HEADER:
        log_ws.clear()
        log_ws.append_row(HEADER)
    log_ws.append_row(row)

    cutoff = (datetime.datetime.now(IST)-datetime.timedelta(days=RETENTION_DAYS)).date()
    all_vals = log_ws.get_all_values()
    archive = [r for r in all_vals[1:] if datetime.datetime.strptime(r[0],'%Y-%m-%d %H:%M:%S').date()<cutoff]
    if archive:
        try: arc_ws = book.worksheet(ARCHIVE_SHEET_NAME)
        except: arc_ws = book.add_worksheet(ARCHIVE_SHEET_NAME, rows=100, cols=len(HEADER)); arc_ws.append_row(HEADER)
        for r in archive: arc_ws.append_row(r)
        for idx in range(len(all_vals),1,-1):
            rd = datetime.datetime.strptime(all_vals[idx-1][0],'%Y-%m-%d %H:%M:%S').date()
            if rd<cutoff: log_ws.delete_row(idx)

    ov = open_ws.get_all_values()
    today = datetime.datetime.now(IST).strftime('%Y-%m-%d')
    if len(ov)<2 or not ov[1][0].startswith(today):
        open_ws.clear(); open_ws.append_row(HEADER); open_ws.append_row(row)

## Main

def main():
    setup_logging(); logging.info("Starting fetch_option_data")
    greeks_key, token_key = load_config()
    client = authorize_sheets()
    kite, token_ws = get_kite_client(client, token_key)
    instruments = get_all_instruments(kite)

    names = {'nifty':'NIFTY','bn':'BANKNIFTY'}
    ltp_map = {'nifty':['NIFTY 50','NIFTY'],'bn':['NIFTY BANK','BANKNIFTY']}

    ltp_keys = [f"NSE:{s}" for vs in ltp_map.values() for s in vs]
    ltp_data = safe_ltp(kite, token_ws, ltp_keys)
    now = datetime.datetime.now(IST)

    results = {f"{k}_{o}_{m}":0 for k in names for o in['ce','pe'] for m in['delta','vega','theta']}
    row = [now.strftime('%Y-%m-%d %H:%M:%S')]

    for key,name in names.items():
        sym = next((s for s in ltp_map[key] if f"NSE:{s}" in ltp_data), None)
        if not sym: logging.warning("No LTP for %s",key); continue
        S = ltp_data[f"NSE:{sym}"]['last_price']
        opts = [i for i in instruments if i['name']==name]
        tokens = [f"NFO:{i['instrument_token']}" for i in opts]
        quotes = safe_quote(kite, token_ws, tokens)
        for inst in opts:
            q = quotes.get(f"NFO:{inst['instrument_token']}");
            if not q: continue
            iv = q.get('implied_volatility',0)/100; price=q.get('last_price')
            exp_dt = IST.localize(datetime.datetime.combine(inst['expiry'],datetime.time(15,30)))
            T=(exp_dt.astimezone(pytz.UTC)-now.astimezone(pytz.UTC)).total_seconds()/(365*24*3600)
            if (not iv or iv<=0) and price: iv=fallback_iv(S,inst['strike'],T,RISK_FREE_RATE,price,inst['instrument_type'])
            if T<=0 or iv<=0: continue
            d,v,t = calculate_greeks(S,inst['strike'],T,RISK_FREE_RATE,iv,inst['instrument_type'])
            if DELTA_MIN<=abs(d)<=DELTA_MAX:
                results[f"{key}_{inst['instrument_type'].lower()}_delta"]+=d
                results[f"{key}_{inst['instrument_type'].lower()}_vega"]+=v
                results[f"{key}_{inst['instrument_type'].lower()}_theta"]+=t
        for o in ['ce','pe']:
            row+= [round(results[f"{key}_{o}_delta"],4),round(results[f"{key}_{o}_vega"],2),round(results[f"{key}_{o}_theta"],2)]

    write_sheets(client, greeks_key, row)
    logging.info("Completed fetch_option_data")

if __name__=='__main__':
    main()
