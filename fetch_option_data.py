import os
import json
import logging
import datetime
import pytz
import numpy as np
import gspread
import yfinance as yf
import pandas as pd  # needed for DataFrame operations
from scipy.stats import norm
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
    d1 = (np.log(S/K) + (r + 0.5*vol**2)*T) / (vol * np.sqrt(T))
    d2 = d1 - vol*np.sqrt(T)
    delta = norm.cdf(d1) if flag=='CE' else -norm.cdf(-d1)
    vega = S * norm.pdf(d1) * np.sqrt(T)
    if flag=='CE':
        theta = -S*norm.pdf(d1)*vol/(2*np.sqrt(T)) - r*K*np.exp(-r*T)*norm.cdf(d2)
    else:
        theta = -S*norm.pdf(d1)*vol/(2*np.sqrt(T)) + r*K*np.exp(-r*T)*norm.cdf(-d2)
    return delta, vega, theta

# ----------------- Fetch via yfinance ----------------
def fetch_greeks_yf(ticker_symbol: str):
    """
    Fetch option chain using yfinance for given ticker.
    Returns dict with ce_delta, ce_vega, ce_theta, pe_delta, pe_vega, pe_theta.
    """
    # Prepare zero accumulator for fallback
    zero_acc = {'ce_delta':0.0,'ce_vega':0.0,'ce_theta':0.0,'pe_delta':0.0,'pe_vega':0.0,'pe_theta':0.0}
    try:
        tk = yf.Ticker(ticker_symbol)
        info = tk.info
        S = info.get('regularMarketPrice')
        if S is None:
            logging.warning("Cannot fetch underlying price for %s", ticker_symbol)
            return zero_acc
        # choose nearest expiry
        expiries = tk.options
        if not expiries:
            logging.warning("No expiry dates for %s", ticker_symbol)
            return zero_acc
        exp = expiries[0]
        chain = tk.option_chain(exp)
        calls = chain.calls
        puts  = chain.puts
    except Exception as e:
        logging.warning("Error fetching option chain for %s: %s", ticker_symbol, e)
        return zero_acc

    now = datetime.datetime.now(IST)
    try:
        exp_dt = datetime.datetime.strptime(exp, '%Y-%m-%d').replace(tzinfo=IST)
        T = (exp_dt - now).total_seconds() / (365*24*3600)
    except Exception:
        logging.warning("Invalid expiry date format %s for %s", exp, ticker_symbol)
        return zero_acc
    # allocate
    acc = {'ce_delta':0.0,'ce_vega':0.0,'ce_theta':0.0,'pe_delta':0.0,'pe_vega':0.0,'pe_theta':0.0}
    # process calls and puts
    for df, side in ((calls, 'CE'), (puts, 'PE')):
        # if not a DataFrame, skip
        if not isinstance(df, pd.DataFrame):
            continue
        for row in df.itertuples(index=False):
            K = getattr(row, 'strike', None)
            price = getattr(row, 'lastPrice', None)
            iv = getattr(row, 'impliedVolatility', None)
            if K is None or price is None or iv is None or T <= 0:
                continue
            # iv from yfinance is already decimal (e.g., 0.25)
            delta, vega, theta = calculate_greeks(S, K, T, RISK_FREE_RATE, iv, side)
            key_pref = side.lower()
            if DELTA_MIN <= abs(delta) <= DELTA_MAX:
                acc[f'{key_pref}_delta'] += delta
                acc[f'{key_pref}_vega']  += vega
                acc[f'{key_pref}_theta'] += theta
    return acc
    """
    Fetch option chain using yfinance for given ticker.
    Returns dict with ce_delta, ce_vega, ce_theta, pe_delta, pe_vega, pe_theta.
    """
    tk = yf.Ticker(ticker_symbol)
    info = tk.info
    S = info.get('regularMarketPrice')
    if S is None:
        raise RuntimeError(f"Cannot fetch underlying price for {ticker_symbol}")
    # choose nearest expiry
    expiries = tk.options
    if not expiries:
        raise RuntimeError(f"No expiry dates for {ticker_symbol}")
    exp = expiries[0]
    chain = tk.option_chain(exp)
    calls = chain.calls
    puts  = chain.puts
    now = datetime.datetime.now(IST)
    exp_dt = datetime.datetime.strptime(exp, '%Y-%m-%d').replace(tzinfo=IST)
    T = (exp_dt - now).total_seconds() / (365*24*3600)
    # allocate
    acc = {'ce_delta':0.0,'ce_vega':0.0,'ce_theta':0.0,'pe_delta':0.0,'pe_vega':0.0,'pe_theta':0.0}
    # process calls
    for opt in [calls, puts]:
        side = 'CE' if opt is calls else 'PE'
        for row in opt.itertuples(index=False):
            K = getattr(row, 'strike', None)
            price = getattr(row, 'lastPrice', None)
            iv = getattr(row, 'impliedVolatility', None)
            if K is None or price is None or iv is None:
                continue
            # iv from yfinance is decimal (e.g., 0.25)
            delta, vega, theta = calculate_greeks(S, K, T, RISK_FREE_RATE, iv, side)
            key_pref = side.lower()
            if DELTA_MIN <= abs(delta) <= DELTA_MAX:
                acc[f'{key_pref}_delta'] += delta
                acc[f'{key_pref}_vega']  += vega
                acc[f'{key_pref}_theta'] += theta
    return acc

# ----------------- Write to Sheets ------------------
def write_sheets(client, greeks_key, row):
    book    = client.open_by_key(greeks_key)
    log_ws  = book.worksheet(LOG_SHEET_NAME)
    open_ws = book.worksheet(OPEN_SHEET_NAME)
    vals = log_ws.get_all_values()
    if not vals or vals[0]!=HEADER:
        log_ws.clear()
        log_ws.append_row(HEADER)
    log_ws.append_row(row, value_input_option='USER_ENTERED')
    # archive
    cutoff = (datetime.datetime.now(IST)-datetime.timedelta(days=RETENTION_DAYS)).date()
    all_vals = log_ws.get_all_values()
    archive = [r for r in all_vals[1:] if datetime.datetime.strptime(r[0], '%Y-%m-%d %H:%M:%S').date()<cutoff]
    if archive:
        try:
            arc_ws = book.worksheet(ARCHIVE_SHEET_NAME)
        except WorksheetNotFound:
            arc_ws = book.add_worksheet(ARCHIVE_SHEET_NAME, rows='100', cols=str(len(HEADER)))
            arc_ws.append_row(HEADER)
        arc_ws.append_rows(archive, value_input_option='USER_ENTERED')
        for idx in range(len(all_vals),1,-1):
            rd = datetime.datetime.strptime(all_vals[idx-1][0], '%Y-%m-%d %H:%M:%S').date()
            if rd < cutoff:
                log_ws.delete_row(idx)
    ov = open_ws.get_all_values()
    today = datetime.datetime.now(IST).strftime('%Y-%m-%d')
    if len(ov)<2 or not ov[1][0].startswith(today):
        open_ws.clear(); open_ws.append_row(HEADER); open_ws.append_row(row)

# ----------------- Main ---------------------------
def main():
    setup_logging()
    logging.info('Starting fetch via yfinance')
    greeks_key, token_key = load_config()
    client = authorize_sheets()
    tickers = {'nifty':'^NSEI','bn':'^NSEBANK'}
    now = datetime.datetime.now(IST)
    row = [now.strftime('%Y-%m-%d %H:%M:%S')]
    for key, sym in tickers.items():
        acc = fetch_greeks_yf(sym)
        for side in ['ce','pe']:
            row += [round(acc[f'{side}_delta'],4), round(acc[f'{side}_vega'],2), round(acc[f'{side}_theta'],2)]
    print('DEBUG OUTPUT ROW:', row)
    write_sheets(client, greeks_key, row)
    logging.info('Completed fetch via yfinance')

if __name__=='__main__':
    main()
