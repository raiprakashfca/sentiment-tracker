# fetch_option_data.py
import os
import json
import pandas as pd
import datetime
import pytz
import toml
import time
import numpy as np
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from scipy.stats import norm

# -------------------- CONFIG --------------------
ist = pytz.timezone("Asia/Kolkata")
today_dt = datetime.datetime.now(ist)

# Holiday list for 2025 (add or update as needed)
nse_holidays = [
    datetime.date(2025,1,26), datetime.date(2025,2,26), datetime.date(2025,3,14),
    datetime.date(2025,3,31), datetime.date(2025,4,10), datetime.date(2025,4,14),
    datetime.date(2025,4,18), datetime.date(2025,5,1),  datetime.date(2025,8,15),
    datetime.date(2025,8,27), datetime.date(2025,10,2), datetime.date(2025,10,21),
    datetime.date(2025,10,22), datetime.date(2025,11,5), datetime.date(2025,12,25)
]
# Skip non-trading days
if today_dt.weekday() >= 5 or today_dt.date() in nse_holidays:
    print("❌ Market closed or holiday — exiting.")
    exit(0)

# Determine if it's the open snapshot time
is_open_snapshot = today_dt.strftime("%H:%M") == "09:15"

# -------------------- LOAD CREDENTIALS --------------------
secrets_path = os.path.expanduser("~/.streamlit/secrets.toml")
if os.path.exists(secrets_path):
    sec = toml.load(secrets_path)
    gcreds = json.loads(sec.get("GCREDS","{}"))
elif "GCREDS" in os.environ:
    gcreds = json.loads(os.environ["GCREDS"])
else:
    raise RuntimeError("❌ GCREDS not found in secrets.toml or environment.")

# Authorize Google Sheets
gscope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, gscope)
gc = gspread.authorize(creds)
wb = gc.open("ZerodhaTokenStore")
log_ws  = wb.worksheet("GreeksLog")
open_ws = wb.worksheet("GreeksOpen")

# Read API tokens from Sheet1
cfg = wb.worksheet("Sheet1")
api_key     = cfg.acell("A1").value.strip()
access_token= cfg.acell("C1").value.strip()

# Initialize Kite
def kite_call(fn, *args, retries=3, delay=2, **kwargs):
    for i in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            print(f"⚠️ API error: {e} — retry {i+1}/{retries}")
            time.sleep(delay)
    raise RuntimeError("API call failed after retries.")

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)
# Validate token
spot_data = kite_call(kite.ltp, ["NSE:NIFTY 50"]) 
spot_price = spot_data.get("NSE:NIFTY 50",{}).get("last_price")
if not spot_price:
    raise RuntimeError("❌ Invalid API Key or Access Token.")
print(f"✅ Validated token. Spot: {spot_price}")

# Fetch instrument list once
inst = pd.DataFrame(kite_call(kite.instruments, "NFO"))
nifty_opts = inst[(inst["name"]=="NIFTY") & (inst["segment"]=="NFO-OPT")]
# Determine nearest expiry
today = today_dt.date()
expiries = sorted(nifty_opts["expiry"].unique())
nearest = next(e for e in expiries if pd.to_datetime(e).date()>=today)
ce = nifty_opts[(nifty_opts["expiry"]==nearest)&(nifty_opts["instrument_type"]=="CE")]
pe = nifty_opts[(nifty_opts["expiry"]==nearest)&(nifty_opts["instrument_type"]=="PE")]

# Fetch LTPs
ce_ltp = kite_call(kite.ltp, ce["instrument_token"].tolist())
pe_ltp = kite_call(kite.ltp, pe["instrument_token"].tolist())
ce["ltp"] = ce["instrument_token"].apply(lambda x: ce_ltp.get(str(x),{}).get("last_price",0))
pe["ltp"] = pe["instrument_token"].apply(lambda x: pe_ltp.get(str(x),{}).get("last_price",0))

# Black-Scholes Greeks
T, r, sigma = 1/12, 0.06, 0.14
def bs_greeks(row):
    S, K = spot_price, row["strike"]
    d1 = (np.log(S/K)+(r+0.5*sigma**2)*T)/(sigma*np.sqrt(T))
    delta = norm.cdf(d1) if row["instrument_type"]=="CE" else -norm.cdf(-d1)
    vega = S*norm.pdf(d1)*np.sqrt(T)/100
    theta= -S*norm.pdf(d1)*sigma/(2*np.sqrt(T))/365
    return delta, vega, theta
ce[["delta","vega","theta"]] = ce.apply(bs_greeks,axis=1, result_type="expand")
pe[["delta","vega","theta"]] = pe.apply(bs_greeks,axis=1, result_type="expand")

# Aggregate sums within delta range
low,high = 0.05,0.6
sum_ce = ce[(ce["delta"]>=low)&(ce["delta"]<=high)]["delta"].sum()
sum_pe = pe[(pe["delta"].abs()>=low)&(pe["delta"].abs()<=high)]["delta"].sum()
sum_cv = ce["vega"].sum(); sum_pv = pe["vega"].sum()
sum_ct = ce["theta"].sum(); sum_pt = pe["theta"].sum()

# Prepare row
row = [today_dt.isoformat(), sum_ce, sum_pe, sum_cv, sum_pv, sum_ct, sum_pt]
# Append to GreeksLog
log_ws.append_row(row)
print("✅ Logged to Google Sheets (GreeksLog)")
# Write open snapshot
action = "📌 Open snapshot"
if is_open_snapshot:
    open_ws.clear()
    open_ws.append_row(row)
    print(action + " saved to GreeksOpen.")
