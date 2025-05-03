import os
import json
import time
import datetime
from datetime import timedelta
import pytz
import pandas as pd
import numpy as np
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from scipy.stats import norm

# -------------------- CONFIG & DATE SELECTION --------------------
ist = pytz.timezone("Asia/Kolkata")
now = datetime.datetime.now(ist)
today = now.date()

# NSE Holidays for 2025 (update as needed)
nse_holidays = {
    datetime.date(2025,1,26), datetime.date(2025,2,26), datetime.date(2025,3,14),
    datetime.date(2025,3,31), datetime.date(2025,4,10), datetime.date(2025,4,14),
    datetime.date(2025,4,18), datetime.date(2025,5,1),  datetime.date(2025,8,15),
    datetime.date(2025,8,27), datetime.date(2025,10,2), datetime.date(2025,10,21),
    datetime.date(2025,10,22), datetime.date(2025,11,5), datetime.date(2025,12,25)
}

def get_last_trading_day(d, holidays):
    ld = d
    while ld.weekday() >= 5 or ld in holidays:
        ld -= timedelta(days=1)
    return ld

target_day = get_last_trading_day(today, nse_holidays)
print(f"ℹ️ Using trading date: {target_day}")

# snapshot at open only
is_open_snapshot = (now.strftime("%H:%M") == "09:15" and target_day == today)

# -------------------- LOAD SERVICE-ACCOUNT CREDS --------------------
raw = os.environ.get("GCREDS") or os.environ.get("gcreds")
if not raw:
    raise RuntimeError("❌ GCREDS not found in environment.")
try:
    gcreds = json.loads(raw)
except json.JSONDecodeError as e:
    raise RuntimeError(f"❌ GCREDS is not valid JSON: {e}")

# -------------------- GOOGLE SHEETS AUTH --------------------
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
service_account = gcreds.get("client_email", "<unknown>")
print(f"🔐 Using service account: {service_account}")
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
gc = gspread.authorize(creds)

# Open workbooks
try:
    token_wb = gc.open_by_key(os.environ["TOKEN_SHEET_ID"])
except Exception as e:
    raise RuntimeError(f"❌ Cannot open TOKEN_SHEET_ID: {e} - share with {service_account}")
try:
    data_wb = gc.open_by_key(os.environ["GREEKS_SHEET_ID"])
except Exception as e:
    raise RuntimeError(f"❌ Cannot open GREEKS_SHEET_ID: {e} - share with {service_account}")

# Read Zeodha tokens
t_cfg = token_wb.worksheet("Sheet1")
api_key = t_cfg.acell("A1").value.strip()
access_token = t_cfg.acell("C1").value.strip()

# Prepare worksheets
log_ws = data_wb.worksheet("GreeksLog")
open_ws = data_wb.worksheet("GreeksOpen")

# -------------------- KITE INITIALIZATION & VALIDATION --------------------
def kite_call(fn, *args, retries=3, delay=2, **kwargs):
    for i in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            print(f"⚠️ Kite API error: {e} (retry {i+1}/{retries})")
            time.sleep(delay)
    raise RuntimeError("❌ Kite API failed after retries")

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)
spot_data = kite_call(kite.ltp, ["NSE:NIFTY 50"])
spot_price = spot_data.get("NSE:NIFTY 50", {}).get("last_price")
if not spot_price:
    raise RuntimeError("❌ Invalid API Key or Access Token.")
print(f"✅ Spot price: {spot_price}")

# -------------------- FETCH & COMPUTE GREEKS --------------------
insts = pd.DataFrame(kite_call(kite.instruments, "NFO"))
nifty = insts[(insts["name"]=="NIFTY") & (insts["segment"]=="NFO-OPT")]
exp = sorted(nifty["expiry"].unique())
ne = next(e for e in exp if pd.to_datetime(e).date() >= target_day)
ce = nifty[(nifty["expiry"]==ne) & (nifty["instrument_type"]=="CE")]
pe = nifty[(nifty["expiry"]==ne) & (nifty["instrument_type"]=="PE")]

ce_ltp = kite_call(kite.ltp, ce["instrument_token"].astype(int).tolist())
pe_ltp = kite_call(kite.ltp, pe["instrument_token"].astype(int).tolist())
ce["ltp"] = ce["instrument_token"].apply(lambda x: ce_ltp.get(str(x), {}).get("last_price", 0))
pe["ltp"] = pe["instrument_token"].apply(lambda x: pe_ltp.get(str(x), {}).get("last_price", 0))

T, r, sigma = 1/12, 0.06, 0.14

def bs_greeks(row):
    S, K = spot_price, row["strike"]
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    delta = norm.cdf(d1) if row["instrument_type"]=="CE" else -norm.cdf(-d1)
    vega = S * norm.pdf(d1) * np.sqrt(T) / 100
    theta = -S * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) / 365
    return delta, vega, theta

ce[["delta","vega","theta"]] = ce.apply(bs_greeks, axis=1, result_type="expand")
pe[["delta","vega","theta"]] = pe.apply(bs_greeks, axis=1, result_type="expand")

low, high = 0.05, 0.6
sum_ce = ce.query("delta>=@low and delta<=@high")["delta"].sum()
sum_pe = pe.query("abs(delta)>=@low and abs(delta)<=@high")["delta"].sum()
sum_cv = ce["vega"].sum(); sum_pv = pe["vega"].sum()
sum_ct = ce["theta"].sum(); sum_pt = pe["theta"].sum()

row = [now.isoformat(), sum_ce, sum_pe, sum_cv, sum_pv, sum_ct, sum_pt]
log_ws.append_row(row)
print("✅ Logged to GreeksLog")

if is_open_snapshot:
    open_ws.clear()
    open_ws.append_row(row)
    print("📌 Saved open snapshot to GreeksOpen")
