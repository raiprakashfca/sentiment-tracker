import os
import json
import time
import logging
import datetime
import pytz
import numpy as np
from scipy.stats import norm
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import WorksheetNotFound

# ----------------- Configuration -----------------
GCREDS_ENV_VAR       = "GCREDS"
GREEKS_SHEET_ENV_VAR = "GREEKS_SHEET_ID"
TOKEN_SHEET_ENV_VAR  = "TOKEN_SHEET_ID"

LOG_SHEET_NAME       = os.getenv("LOG_SHEET_NAME", "GreeksLog")
OPEN_SHEET_NAME      = os.getenv("OPEN_SHEET_NAME", "GreeksOpen")
ARCHIVE_SHEET_NAME   = os.getenv("ARCHIVE_SHEET_NAME", "GreeksArchive")

RISK_FREE_RATE       = float(os.getenv("RISK_FREE_RATE", "0.07"))
DELTA_MIN            = float(os.getenv("DELTA_MIN", "0.0"))
DELTA_MAX            = float(os.getenv("DELTA_MAX", "1.0"))
RETENTION_DAYS       = int(os.getenv("RETENTION_DAYS", "7"))

IST = pytz.timezone("Asia/Kolkata")
HEADER = [
    "timestamp",
    "nifty_ce_delta","nifty_ce_vega","nifty_ce_theta",
    "nifty_pe_delta","nifty_pe_vega","nifty_pe_theta",
    "bn_ce_delta","bn_ce_vega","bn_ce_theta",
    "bn_pe_delta","bn_pe_vega","bn_pe_theta"
]

# ----------------- Logging ------------------------
def setup_logging():
    logging.basicConfig(
        filename="fetch_option_data.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

# ----------------- Config loader -----------------
def load_config():
    greeks_key = os.getenv(GREEKS_SHEET_ENV_VAR)
    token_key  = os.getenv(TOKEN_SHEET_ENV_VAR)
    if not greeks_key or not token_key:
        raise RuntimeError(f"Missing env vars: {GREEKS_SHEET_ENV_VAR}, {TOKEN_SHEET_ENV_VAR}")
    return greeks_key, token_key

# ----------------- Google Sheets auth -------------
def authorize_sheets():
    creds_data = os.getenv(GCREDS_ENV_VAR)
    if creds_data:
        creds = json.loads(creds_data)
    elif os.path.exists("credentials.json"):
        with open("credentials.json") as f:
            creds = json.load(f)
    else:
        raise RuntimeError("Service account JSON not found in env or credentials.json")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds, scope)
    return gspread.authorize(credentials)

# ----------------- Fetch NSE Option Chain  ------------
def fetch_option_chain_nse(symbol: str) -> list:
    base = "https://www.nseindia.com"
    session = requests.Session()
    headers = {
        "Host": "www.nseindia.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"{base}/option-chain-indices?symbol={symbol}",
        "Origin": base,
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    # Prime cookies by visiting the option-chain page
    session.get(f"{base}/option-chain-indices?symbol={symbol}", headers=headers, timeout=5)
    time.sleep(1)  # brief pause
    # Now fetch JSON
    url = f"{base}/api/option-chain-indices?symbol={symbol}"
    resp = session.get(url, headers=headers, timeout=5)
    if resp.status_code != 200:
        logging.error("NSE API %s returned status %d", url, resp.status_code)
        return []
    data = resp.json()
    return data.get("records", {}).get("data", [])

# ----------------- Greeks calculation --------------
def calculate_greeks(S, K, T, r, vol, flag):
    d1 = (np.log(S/K) + (r + 0.5*vol*vol)*T) / (vol * np.sqrt(T))
    d2 = d1 - vol * np.sqrt(T)
    delta = norm.cdf(d1) if flag == "CE" else -norm.cdf(-d1)
    vega  = S * norm.pdf(d1) * np.sqrt(T)
    if flag == "CE":
        theta = -S * norm.pdf(d1) * vol/(2*np.sqrt(T)) - r * K * np.exp(-r*T) * norm.cdf(d2)
    else:
        theta = -S * norm.pdf(d1) * vol/(2*np.sqrt(T)) + r * K * np.exp(-r*T) * norm.cdf(-d2)
    return delta, vega, theta

# ----------------- Write to Google Sheets -------------
def write_sheets(client, greeks_key, row):
    book   = client.open_by_key(greeks_key)
    log_ws = book.worksheet(LOG_SHEET_NAME)
    open_ws= book.worksheet(OPEN_SHEET_NAME)
    # Ensure header
    vals = log_ws.get_all_values()
    if not vals or vals[0] != HEADER:
        log_ws.clear()
        log_ws.append_row(HEADER)
    log_ws.append_row(row, value_input_option='USER_ENTERED')
    # Archive old
    cutoff = (datetime.datetime.now(IST) - datetime.timedelta(days=RETENTION_DAYS)).date()
    all_vals = log_ws.get_all_values()
    archive = [r for r in all_vals[1:] if datetime.datetime.strptime(r[0], '%Y-%m-%d %H:%M:%S').date() < cutoff]
    if archive:
        try:
            arc_ws = book.worksheet(ARCHIVE_SHEET_NAME)
        except WorksheetNotFound:
            arc_ws = book.add_worksheet(ARCHIVE_SHEET_NAME, rows="100", cols=str(len(HEADER)))
            arc_ws.append_row(HEADER)
        arc_ws.append_rows(archive, value_input_option='USER_ENTERED')
        for idx in range(len(all_vals), 1, -1):
            if datetime.datetime.strptime(all_vals[idx-1][0], '%Y-%m-%d %H:%M:%S').date() < cutoff:
                log_ws.delete_row(idx)
    # Open snapshot
    ov = open_ws.get_all_values()
    today = datetime.datetime.now(IST).strftime('%Y-%m-%d')
    if len(ov) < 2 or not ov[1][0].startswith(today):
        open_ws.clear()
        open_ws.append_row(HEADER, value_input_option='USER_ENTERED')
        open_ws.append_row(row, value_input_option='USER_ENTERED')

# ----------------- Main Routine -------------------
def main():
    setup_logging()
    logging.info("Starting fetch_option_data via NSE API")
    greeks_key, token_key = load_config()
    client = authorize_sheets()

    names = {'nifty': 'NIFTY', 'bn': 'BANKNIFTY'}
    now = datetime.datetime.now(IST)
    results = {f"{k}_{o}_{m}": 0.0 for k in names for o in ['CE','PE'] for m in ['delta','vega','theta']}
    row = [now.strftime('%Y-%m-%d %H:%M:%S')]

    for key, symbol in names.items():
        data = fetch_option_chain_nse(symbol)
        if not data:
            logging.warning("No data from NSE for %s", symbol)
            continue
        S = data[0].get('underlyingValue', 0)
        for rec in data:
            K = rec.get('strikePrice')
            exp_dt = datetime.datetime.strptime(rec.get('expiryDate',''), '%d-%b-%Y')
            T = (exp_dt - now).total_seconds() / (365*24*3600)
            if T <= 0:
                continue
            for side in ['CE','PE']:
                opt = rec.get(side)
                if not opt:
                    continue
                price = opt.get('lastPrice', 0)
                iv = opt.get('impliedVolatility', 0) / 100.0
                if iv <= 0 or price <= 0:
                    continue
                d, v, t = calculate_greeks(S, K, T, RISK_FREE_RATE, iv, side)
                if DELTA_MIN <= abs(d) <= DELTA_MAX:
                    results[f"{key}_{side}_delta"] += d
                    results[f"{key}_{side}_vega"]  += v
                    results[f"{key}_{side}_theta"] += t
        # append sums for this symbol
        for side in ['CE','PE']:
            row += [
                round(results[f"{key}_{side}_delta"], 4),
                round(results[f"{key}_{side}_vega"], 2),
                round(results[f"{key}_{side}_theta"], 2)
            ]

    write_sheets(client, greeks_key, row)
    logging.info("Completed fetch via NSE API")

if __name__ == '__main__':
    main()
