import os
import json
import time
import logging
import datetime
import pytz
import numpy as np
import gspread
from scipy.stats import norm
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import WorksheetNotFound
# nsepython import
from nsepython import get_optionchain

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

# ----------------- Config Loader ------------------
def load_config():
    greeks_key = os.getenv(GREEKS_SHEET_ENV_VAR)
    token_key  = os.getenv(TOKEN_SHEET_ENV_VAR)
    if not greeks_key or not token_key:
        raise RuntimeError(f"Missing env vars: {GREEKS_SHEET_ENV_VAR}, {TOKEN_SHEET_ENV_VAR}")
    return greeks_key, token_key

# ----------------- Google Sheets Auth ------------
def authorize_sheets():
    creds_data = os.getenv(GCREDS_ENV_VAR)
    if creds_data:
        creds = json.loads(creds_data)
    elif os.path.exists("credentials.json"):
        with open("credentials.json") as f:
            creds = json.load(f)
    else:
        raise RuntimeError("Service account JSON not found in env var or credentials.json")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds, scope)
    return gspread.authorize(credentials)

# ----------------- Black-Scholes Greeks ------------
def calculate_greeks(S, K, T, r, vol, flag):
    d1 = (np.log(S/K) + (r + 0.5 * vol**2) * T) / (vol * np.sqrt(T))
    d2 = d1 - vol * np.sqrt(T)
    delta = norm.cdf(d1) if flag == 'CE' else -norm.cdf(-d1)
    vega = S * norm.pdf(d1) * np.sqrt(T)
    if flag == 'CE':
        theta = -S * norm.pdf(d1) * vol/(2*np.sqrt(T)) - r * K * np.exp(-r*T) * norm.cdf(d2)
    else:
        theta = -S * norm.pdf(d1) * vol/(2*np.sqrt(T)) + r * K * np.exp(-r*T) * norm.cdf(-d2)
    return delta, vega, theta

# ----------------- Fetch via nsepython ----------------
def fetch_greeks_nse(index_symbol: str):
    """
    Fetch CE/PE option chain via nsepython for given index (e.g. 'NIFTY', 'BANKNIFTY').
    Returns:
      S       - underlying level
      results - dict accumulating delta/vega/theta sums
    """
    # get full chain
    chain = get_optionchain(index_symbol)
    # extract underlying
    records = chain.get('records', {})
    S = records.get('underlyingValue')
    # get expiry list
    expiries = records.get('expiryDates', [])
    if not expiries or S is None:
        logging.error('No underlying or expiry data for %s', index_symbol)
        return S, {}
    # choose nearest expiry
    expiry = expiries[0]
    # fetch for that expiry
    opt_data = records.get('data', [])
    # accumulate
    acc = {'ce_delta':0.0, 'ce_vega':0.0, 'ce_theta':0.0,
           'pe_delta':0.0, 'pe_vega':0.0, 'pe_theta':0.0}
    now = datetime.datetime.now(IST)
    exp_dt = datetime.datetime.strptime(expiry, '%d-%b-%Y')
    T = (exp_dt - now).total_seconds()/(365*24*3600)
    for rec in opt_data:
        K = rec.get('strikePrice')
        for side in ('CE','PE'):
            opt = rec.get(side)
            if not opt:
                continue
            price = opt.get('lastPrice')
            iv = opt.get('impliedVolatility')
            # skip invalid
            if not price or not iv or T<=0:
                continue
            # Greeks
            d,v,t = calculate_greeks(S, K, T, RISK_FREE_RATE, iv, side)
            key_pref = side.lower()
            if DELTA_MIN <= abs(d) <= DELTA_MAX:
                acc[f'{key_pref}_delta'] += d
                acc[f'{key_pref}_vega']  += v
                acc[f'{key_pref}_theta'] += t
    return S, acc

# ----------------- Write to Sheets ------------------
def write_sheets(client, greeks_key, row):
    book   = client.open_by_key(greeks_key)
    log_ws = book.worksheet(LOG_SHEET_NAME)
    open_ws= book.worksheet(OPEN_SHEET_NAME)
    # header
    vals = log_ws.get_all_values()
    if not vals or vals[0]!=HEADER:
        log_ws.clear()
        log_ws.append_row(HEADER)
    log_ws.append_row(row, value_input_option='USER_ENTERED')
    # archive
    cutoff = (datetime.datetime.now(IST) - datetime.timedelta(days=RETENTION_DAYS)).date()
    all_vals = log_ws.get_all_values()
    archive = [r for r in all_vals[1:] if datetime.datetime.strptime(r[0],'%Y-%m-%d %H:%M:%S').date()<cutoff]
    if archive:
        try: arc_ws=book.worksheet(ARCHIVE_SHEET_NAME)
        except: arc_ws=book.add_worksheet(ARCHIVE_SHEET_NAME,rows='100',cols=str(len(HEADER))); arc_ws.append_row(HEADER)
        arc_ws.append_rows(archive,value_input_option='USER_ENTERED')
        for idx in range(len(all_vals),1,-1):
            rd = datetime.datetime.strptime(all_vals[idx-1][0],'%Y-%m-%d %H:%M:%S').date()
            if rd<cutoff: log_ws.delete_row(idx)
    # open snapshot
    ov = open_ws.get_all_values()
    today = datetime.datetime.now(IST).strftime('%Y-%m-%d')
    if len(ov)<2 or not ov[1][0].startswith(today):
        open_ws.clear(); open_ws.append_row(HEADER); open_ws.append_row(row)

# ----------------- Main ---------------------------
def main():
    setup_logging(); logging.info('Starting fetch via nsepython')
    greeks_key, token_key = load_config()
    client = authorize_sheets()
    names = {'nifty':'NIFTY','bn':'BANKNIFTY'}
    now = datetime.datetime.now(IST)
    row = [now.strftime('%Y-%m-%d %H:%M:%S')]
    for key,sym in names.items():
        S, acc = fetch_greeks_nse(sym)
        # append
        for side in ['ce','pe']:
            row += [
                round(acc.get(f'{side}_delta',0),4),
                round(acc.get(f'{side}_vega',0),2),
                round(acc.get(f'{side}_theta',0),2)
            ]
    write_sheets(client, greeks_key, row)
    logging.info('Completed fetch via nsepython')

if __name__=='__main__': main()
