# fetch_option_data.py
import os
import json
import time
import datetime
import pytz
import pandas as pd
import numpy as np
import toml
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from scipy.stats import norm

# -------------------- CONFIG --------------------
ist = pytz.timezone("Asia/Kolkata")
now = datetime.datetime.now(ist)
today = now.date()

# NSE Holidays for 2025
nse_holidays = [
    datetime.date(2025,1,26), datetime.date(2025,2,26), datetime.date(2025,3,14),
    datetime.date(2025,3,31), datetime.date(2025,4,10), datetime.date(2025,4,14),
    datetime.date(2025,4,18), datetime.date(2025,5,1),  datetime.date(2025,8,15),
    datetime.date(2025,8,27), datetime.date(2025,10,2), datetime.date(2025,10,21),
    datetime.date(2025,10,22), datetime.date(2025,11,5), datetime.date(2025,12,25)
]
# Skip weekends and holidays
if today.weekday() >= 5 or today in nse_holidays:
    print("❌ Market closed or holiday. Exiting.")
    exit(0)

# Determine if it's the open snapshot time
is_open_snapshot = now.strftime("%H:%M") == "09:15"

# -------------------- LOAD CREDENTIALS --------------------
# Attempt to load service account creds from Streamlit secrets TOML
secrets_path = os.path.expanduser("~/.streamlit/secrets.toml")
gcreds = None
if os.path.exists(secrets_path):
    sec = toml.load(secrets_path)
    # sec['gcreds'] is a dict when stored as TOML table
    if isinstance(sec.get("gcreds"), dict):
        gcreds = sec.get("gcreds")
    elif isinstance(sec.get("GCREDS"), dict):
        gcreds = sec.get("GCREDS")
# Fallback to environment variables
if not gcreds:
    raw = os.environ.get("GCREDS") or os.environ.get("gcreds")
    if raw:
        # Try JSON first
        try:
            gcreds = json.loads(raw)
        except json.JSONDecodeError:
            # Try parsing as TOML
            try:
                toml_data = toml.loads(raw)
                # Extract service account dict
                if isinstance(toml_data.get("gcreds"), dict):
                    gcreds = toml_data.get("gcreds")
                elif isinstance(toml_data.get("GCREDS"), dict):
                    gcreds = toml_data.get("GCREDS")
            except Exception:
                pass
# Final check
if not gcreds:
    raise RuntimeError("❌ GCREDS not found in Streamlit secrets TOML or environment variables.")
if not gcreds:
    raise RuntimeError("❌ GCREDS not found in Streamlit secrets TOML or environment variables.")

# -------------------- GOOGLE SHEETS AUTH -------------------- --------------------
scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
gc = gspread.authorize(creds)
wb = gc.open("ZerodhaTokenStore")
log_ws  = wb.worksheet("GreeksLog")
open_ws = wb.worksheet("GreeksOpen")
# Read API tokens
cfg = wb.worksheet("Sheet1")
api_key = cfg.acell("A1").value.strip()
access_token = cfg.acell("C1").value.strip()

# -------------------- KITE INITIALIZATION --------------------
def kite_call(fn, *args, retries=3, delay=2, **kwargs):
    for i in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            print(f"⚠️ Kite API error: {e} (retry {i+1}/{retries})")
            time.sleep(delay)
    raise RuntimeError("Kite API failed after retries")

from kiteconnect import KiteConnect
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)
# Validate token
spot_data = kite_call(kite.ltp, ["NSE:NIFTY 50"])
spot_price = spot_data.get("NSE:NIFTY 50",{}).get("last_price")
if not spot_price:
    raise RuntimeError("❌ Invalid API Key or Access Token.")
print(f"✅ Kite token validated. Spot price: {spot_price}")

# -------------------- FETCH INSTRUMENT LIST --------------------
instruments = pd.DataFrame(kite_call(kite.instruments, "NFO"))
nifty_opts = instruments[(instruments["name"]=="NIFTY") & (instruments["segment"]=="NFO-OPT")]
expiries = sorted(nifty_opts["expiry"].unique())
ne = next(e for e in expiries if pd.to_datetime(e).date() >= today)
ce = nifty_opts[(nifty_opts["expiry"]==ne)&(nifty_opts["instrument_type"]=="CE")]
pe = nifty_opts[(nifty_opts["expiry"]==ne)&(nifty_opts["instrument_type"]=="PE")]

# -------------------- FETCH OPTION PRICES --------------------
ce_ltp = kite_call(kite.ltp, ce["instrument_token"].tolist())
pe_ltp = kite_call(kite.ltp, pe["instrument_token"].tolist())
ce["ltp"] = ce["instrument_token"].apply(lambda x: ce_ltp.get(str(x),{}).get("last_price",0))
pe["ltp"] = pe["instrument_token"].apply(lambda x: pe_ltp.get(str(x),{}).get("last_price",0))

# -------------------- CALCULATE GREEKS --------------------
T, r, sigma = 1/12, 0.06, 0.14
def bs_greeks(row):
    S, K = spot_price, row["strike"]
    d1 = (np.log(S/K)+(r+0.5*sigma**2)*T)/(sigma*np.sqrt(T))
    delta = norm.cdf(d1) if row["instrument_type"]=="CE" else -norm.cdf(-d1)
    vega = S*norm.pdf(d1)*np.sqrt(T)/100
    theta = -S*norm.pdf(d1)*sigma/(2*np.sqrt(T))/365
    return delta, vega, theta
ce[["delta","vega","theta"]] = ce.apply(bs_greeks,axis=1,result_type="expand")
pe[["delta","vega","theta"]] = pe.apply(bs_greeks,axis=1,result_type="expand")

# -------------------- AGGREGATE & LOG --------------------
low,high = 0.05,0.6
sum_ce = ce[(ce["delta"]>=low)&(ce["delta"]<=high)]["delta"].sum()
sum_pe = pe[(pe["delta"].abs()>=low)&(pe["delta"].abs()<=high)]["delta"].sum()
sum_cv = ce["vega"].sum(); sum_pv = pe["vega"].sum()
sum_ct = ce["theta"].sum(); sum_pt = pe["theta"].sum()
row = [now.isoformat(), sum_ce, sum_pe, sum_cv, sum_pv, sum_ct, sum_pt]
log_ws.append_row(row)
print("✅ Logged to Google Sheets: GreeksLog")
if is_open_snapshot:
    open_ws.clear()
    open_ws.append_row(row)
    print("📌 Open snapshot saved to GreeksOpen")
