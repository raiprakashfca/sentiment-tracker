import datetime
import pytz
import numpy as np
from scipy.stats import norm
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from kiteconnect import KiteConnect

# ---------- CONFIGURATION ----------
GSHEET_CREDENTIALS_FILE = "credentials.json"
LOG_SHEET_ID = "1RMI8YsExk0pQ-Q1PQ9YYYqRwZ52RKvJcbu-x9yu309k"
TOKEN_SHEET_ID = "1mANuCob4dz3jvjigeO1km96vBzZHr-4ZflZEXxR8-qU"
LOG_SHEET_NAME = "GreeksLog"
OPEN_SHEET_NAME = "GreeksOpen"
ARCHIVE_SHEET_NAME = "GreeksArchive"
RISK_FREE_RATE = 0.07
DELTA_MIN = 0.05
DELTA_MAX = 0.60
# Archive policy: keep last RETENTION_DAYS days in main sheet
RETENTION_DAYS = 7

# ---------- BLACK-SCHOLES GREEKS FUNCTION ----------
def bs_greeks(flag, S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return 0.0, 0.0, 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    vega = S * norm.pdf(d1) * np.sqrt(T)
    if flag == 'CE':
        delta = norm.cdf(d1)
        theta = (-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
                 - r * K * np.exp(-r * T) * norm.cdf(d1))
    else:
        delta = -norm.cdf(-d1)
        theta = (-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
                 + r * K * np.exp(-r * T) * norm.cdf(-d1))
    return float(delta), float(vega), float(theta)

# ---------- MAIN SCRIPT ----------
def main():
    # Google Sheets setup for credentials and logging
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GSHEET_CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)

    # Fetch Kite credentials from Google Sheet
    token_book = client.open_by_key(TOKEN_SHEET_ID)
    token_ws = token_book.worksheet("ZerodhaTokenStore")
    api_key = token_ws.acell('A1').value
    access_token = token_ws.acell('C1').value
    if not api_key or not access_token:
        raise ValueError("Missing Kite credentials in 'ZerodhaTokenStore' sheet (A1=API Key, C1=Access Token).")

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    # Open log workbook
    book = client.open_by_key(LOG_SHEET_ID)
    log_ws = book.worksheet(LOG_SHEET_NAME)
    open_ws = book.worksheet(OPEN_SHEET_NAME)

    # Ensure log sheet headers
    headers = [
        "timestamp",
        "nifty_ce_delta","nifty_ce_vega","nifty_ce_theta",
        "nifty_pe_delta","nifty_pe_vega","nifty_pe_theta",
        "bn_ce_delta","bn_ce_vega","bn_ce_theta",
        "bn_pe_delta","bn_pe_vega","bn_pe_theta"
    ]
    existing = log_ws.get_all_values()
    if not existing or existing[0] != headers:
        log_ws.clear()
        log_ws.append_row(headers)

    # Aggregate Greeks
    instruments = kite.instruments("NFO")
    underlyings = {'nifty': 'NIFTY', 'bn': 'BANKNIFTY'}
    results = {f"{k}_{o}_{m}": 0.0 for k in underlyings for o in ['ce','pe'] for m in ['delta','vega','theta']}

    # Current timestamp IST
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)

    # Fetch underlying LTPs
    ltp_data = kite.ltp(*[f"NSE:{sym}" for sym in underlyings.values()])

    # Compute and sum Greeks
    for key, sym in underlyings.items():
        S = ltp_data[f"NSE:{sym}"]["last_price"]
        opts = [i for i in instruments if i['name']==sym and i['segment']=='NFO-OPT']
        for inst in opts:
            flag = inst['instrument_type']
            K = inst['strike']
            exp_date = inst['expiry']
            expiry_dt = datetime.datetime.combine(exp_date, datetime.time(15,30), tzinfo=ist)
            T = (expiry_dt.astimezone(pytz.UTC) - now.astimezone(pytz.UTC)).total_seconds() / (365*24*3600)
            q = kite.quote(f"NFO:{inst['instrument_token']}")[f"NFO:{inst['instrument_token']}"]
            iv = q.get('implied_volatility', 0.0) / 100.0

            delta, vega, theta = bs_greeks(flag, S, K, T, RISK_FREE_RATE, iv)
            if DELTA_MIN <= abs(delta) <= DELTA_MAX:
                results[f"{key}_{flag.lower()}_delta"] += delta
                results[f"{key}_{flag.lower()}_vega"]  += vega
                results[f"{key}_{flag.lower()}_theta"] += theta

    # Build and append row
    row = [now.strftime('%Y-%m-%d %H:%M:%S')]
    for k in ['nifty','bn']:
        for o in ['ce','pe']:
            row += [round(results[f"{k}_{o}_delta"], 4),
                    round(results[f"{k}_{o}_vega"], 2),
                    round(results[f"{k}_{o}_theta"], 2)]
    log_ws.append_row(row)

    # Archive old rows based on date
    cutoff = (now - datetime.timedelta(days=RETENTION_DAYS)).date()
    all_vals = log_ws.get_all_values()
    to_archive = []
    for idx, r in enumerate(all_vals[1:], start=2):
        try:
            d = datetime.datetime.strptime(r[0], '%Y-%m-%d %H:%M:%S').date()
        except Exception:
            continue
        if d < cutoff:
            to_archive.append((idx, r))

    if to_archive:
        try:
            archive_ws = book.worksheet(ARCHIVE_SHEET_NAME)
        except gspread.WorksheetNotFound:
            archive_ws = book.add_worksheet(ARCHIVE_SHEET_NAME, rows=1, cols=len(headers))
            archive_ws.append_row(headers)
        for _, data_row in to_archive:
            archive_ws.append_row(data_row)
        for idx, _ in sorted(to_archive, reverse=True):
            log_ws.delete_row(idx)

    # First-run-of-day open snapshot
    vals_open = open_ws.get_all_values()
    if len(vals_open) < 2 or not vals_open[1][0].startswith(now.strftime('%Y-%m-%d')):
        open_ws.clear()
        open_ws.append_row(headers)
        open_ws.append_row(row)

    print(f"Logged Greeks at {now.strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == '__main__':
    main()
