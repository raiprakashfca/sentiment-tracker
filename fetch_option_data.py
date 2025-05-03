# fetch_option_data.py
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

# Detect open snapshot (only at 09:15 IST on a trading day)
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
scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
gc = gspread.authorize(creds)

# Open token store and Greeks data workbooks
token_wb = gc.open_by_key(os.environ["TOKEN_SHEET_ID"])
data_wb  = gc.open_by_key(os.environ["GREEKS_SHEET_ID"])

# Read Zerodha API tokens
cfg           = token_wb.worksheet("Sheet1")
api_key       = cfg.acell("A1").value.strip()
access_token  = cfg.acell("C1").value.strip()

# Prepare worksheets
log_ws, open_ws = data_wb.worksheet("GreeksLog"), data_wb.worksheet("GreeksOpen")

# -------------------- KITE INITIALIZATION & VALIDATION --------------------
```python
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
spot = kite_call(kite.ltp, ["NSE:NIFTY 50"])\
.get("NSE:NIFTY 50", {}).get("last_price")
if not spot:
    raise RuntimeError("❌ Invalid API Key or Access Token.")
print(f"✅ Spot price: {spot}")
