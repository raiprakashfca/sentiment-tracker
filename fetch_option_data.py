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
GSHEET_CREDENTIALS_SECRET = "GCREDS"            # Streamlit secret key for service-account JSON
LOG_SHEET_ID_SECRET      = "GREEKS_SHEET_ID"    # Streamlit secret key for GreeksLog sheet
TOKEN_SHEET_ID_SECRET    = "TOKEN_SHEET_ID"     # Streamlit secret key for ZerodhaTokenStore sheet

# GreeksLog / Open sheet names
LOG_SHEET_NAME     = "GreeksLog"
OPEN_SHEET_NAME    = "GreeksOpen"
ARCHIVE_SHEET_NAME = "GreeksArchive"

# Black-Scholes and filters
RISK_FREE_RATE = 0.07
DELTA_MIN      = 0.05
DELTA_MAX      = 0.60
RETENTION_DAYS = 7

# ---------- HELPER: Load creds from Streamlit secrets ----------
def load_service_account():
    # in Streamlit environment, secrets are exposed via os.environ; fallback to file
    import os
    creds_json = os.getenv(GSHEET_CREDENTIALS_SECRET)
    if creds_json:
        creds_dict = json.loads(creds_json)
    elif os.path.exists("credentials.json"):
        creds_dict = json.load(open("credentials.json"))
    else:
        raise RuntimeError(f"Service account JSON not found in env var '{GSHEET_CREDENTIALS_SECRET}' or credentials.json file.")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

# ---------- MAIN SCRIPT ----------
def main():
    # Authenticate Google Sheets
    creds = load_service_account()
    client = gspread.authorize(creds)
    # Sheet IDs
    greeks_key = os.getenv(LOG_SHEET_ID_SECRET)
    token_key  = os.getenv(TOKEN_SHEET_ID_SECRET)
    if not greeks_key or not token_key:
        raise RuntimeError(f"Missing sheet ID env vars: {LOG_SHEET_ID_SECRET}, {TOKEN_SHEET_ID_SECRET}")

    # Open token store sheet to fetch Kite creds
    token_book = client.open_by_key(token_key)
    try:
        token_ws = token_book.worksheet("ZerodhaTokenStore")
    except WorksheetNotFound:
        token_ws = token_book.get_worksheet(0)
        print(f"Warning: 'ZerodhaTokenStore' not found, using first sheet '{token_ws.title}'")
    api_key = token_ws.acell('A1').value
    access_token = token_ws.acell('C1').value
    if not api_key or not access_token:
        raise RuntimeError("API credentials missing in ZerodhaTokenStore (A1/C1)")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    # Open GreeksLog and Open sheets
    book   = client.open_by_key(greeks_key)
    log_ws = book.worksheet(LOG_SHEET_NAME)
    open_ws = book.worksheet(OPEN_SHEET_NAME)

    # Ensure header row
    header = [
        "timestamp",
        "nifty_ce_delta","nifty_ce_vega","nifty_ce_theta",
        "nifty_pe_delta","nifty_pe_vega","nifty_pe_theta",
        "bn_ce_delta","bn_ce_vega","bn_ce_theta",
        "bn_pe_delta","bn_pe_vega","bn_pe_theta"
    ]
    vals = log_ws.get_all_values()
    if not vals or vals[0] != header:
        log_ws.clear()
        log_ws.append_row(header)

    # Fetch instruments once
    instruments = kite.instruments("NFO")

    # Use correct index symbols for LTP
    underlyings = {
        'nifty': 'NIFTY 50',    # correct index name in LTP
        'bn':    'BANKNIFTY'
    }

    # Prepare aggregation
    results = {f"{k}_{o}_{m}": 0.0
               for k in underlyings for o in ['ce','pe'] for m in ['delta','vega','theta']}

    # Timestamp IST
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)

    # Fetch underlying LTPs
    ltp_keys = [f"NSE:{sym}" for sym in underlyings.values()]
    ltp_data = kite.ltp(*ltp_keys)

    # Compute Greeks
    for key, sym in underlyings.items():
        ltp_key = f"NSE:{sym}"
        if ltp_key not in ltp_data:
            print(f"Warning: {ltp_key} missing in LTP response, skipping.")
            continue
        S = ltp_data[ltp_key]['last_price']
        # Filter options for this underlying
        opts = [i for i in instruments if i['name']==sym and i['segment']=='NFO-OPT']
        for inst in opts:
            flag = inst['instrument_type']  # 'CE' or 'PE'
            K = inst['strike']
            expiry = datetime.datetime.combine(inst['expiry'], datetime.time(15,30), tzinfo=ist)
            T = (expiry.astimezone(pytz.UTC) - now.astimezone(pytz.UTC)).total_seconds()/(365*24*3600)
            qdata = kite.quote(f"NFO:{inst['instrument_token']}")[f"NFO:{inst['instrument_token']}"]
            iv = qdata.get('implied_volatility',0)/100.0
            # Black-Scholes
            d1 = (np.log(S/K)+(RISK_FREE_RATE+0.5*iv*iv)*T)/(iv*np.sqrt(T)) if T>0 and iv>0 else None
            if d1 is None:
                continue
            d2 = d1 - iv*np.sqrt(T)
            delta = (norm.cdf(d1) if flag=='CE' else -norm.cdf(-d1))
            vega = S*norm.pdf(d1)*np.sqrt(T)
            theta = ((-S*norm.pdf(d1)*iv/(2*np.sqrt(T)) - RISK_FREE_RATE*K*np.exp(-RISK_FREE_RATE*T)*norm.cdf(d1))
                     if flag=='CE' else
                     (-S*norm.pdf(d1)*iv/(2*np.sqrt(T))+RISK_FREE_RATE*K*np.exp(-RISK_FREE_RATE*T)*norm.cdf(-d1)))
            # Filter by delta
            if abs(delta)>=DELTA_MIN and abs(delta)<=DELTA_MAX:
                results[f"{key}_{flag.lower()}_delta"] += delta
                results[f"{key}_{flag.lower()}_vega"]  += vega
                results[f"{key}_{flag.lower()}_theta"] += theta

    # Append row
    row = [now.strftime('%Y-%m-%d %H:%M:%S')]
    for k in ['nifty','bn']:
        for o in ['ce','pe']:
            row += [round(results[f"{k}_{o}_delta"],4),
                    round(results[f"{k}_{o}_vega"],2),
                    round(results[f"{k}_{o}_theta"],2)]
    log_ws.append_row(row)

    # Archive old rows
    cutoff = (now - datetime.timedelta(days=RETENTION_DAYS)).date()
    all_vals = log_ws.get_all_values()
    to_archive = []
    for idx, r in enumerate(all_vals[1:], start=2):
        try:
            d = datetime.datetime.strptime(r[0], '%Y-%m-%d %H:%M:%S').date()
        except:
            continue
        if d < cutoff:
            to_archive.append((idx, r))
    if to_archive:
        try:
            arc_ws = book.worksheet(ARCHIVE_SHEET_NAME)
        except WorksheetNotFound:
            arc_ws = book.add_worksheet(ARCHIVE_SHEET_NAME, rows=1, cols=len(header))
            arc_ws.append_row(header)
        for _, r in to_archive:
            arc_ws.append_row(r)
        for idx, _ in sorted(to_archive, reverse=True):
            log_ws.delete_row(idx)

    # Set open snapshot if first run
    vals_open = open_ws.get_all_values()
    if len(vals_open)<2 or not vals_open[1][0].startswith(now.strftime('%Y-%m-%d')):
        open_ws.clear()
        open_ws.append_row(header)
        open_ws.append_row(row)

    print(f"Logged Greeks at {now.strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == '__main__':
    main()
