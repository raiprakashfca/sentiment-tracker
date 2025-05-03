# fetch_option_data.py
import os
import json
import time
import datetime
import pytz
import pandas as pd
import numpy as np
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from scipy.stats import norm

# -------------------- CONFIG --------------------
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

# Skip weekends and holidays
if today.weekday() >= 5 or today in nse_holidays:
    print("❌ Market closed or holiday. Exiting.")
    exit(0)

# Determine if it's the open‐snapshot time
is_open_snapshot = now.strftime("09:15") == now.strftime("%H:%M")  # True only at exactly 09:15

# -------------------- LOAD CREDENTIALS --------------------
# Expect full service‐account JSON in GCREDS env var
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

# Open two separate workbooks by ID
token_wb = gc.open_by_key(os.environ["TOKEN_SHEET_ID"])
data_wb  = gc.open_by_key(os.environ["GREEKS_SHEET_ID"])

# Fetch your API tokens from ZerodhaTokenStore → Sheet1
cfg          = token_wb.worksheet("Sheet1")
api_key      = cfg.acell("A1").value.strip()
access_token = cfg.acell("C1").value.strip()

# Prepare your logging tabs
log_ws, open_ws = data_wb.worksheet("GreeksLog"), data_wb.worksheet("GreeksOpen")

# -------------------- KITE “fn with retry” --------------------
def kite_call(fn, *args, retries=3, delay=2, **kwargs):
    for i in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            print(f"⚠️ Kite API error: {e} (retry {i+1}/{retries})")
            time.sleep(delay)
    raise RuntimeError("Kite API failed after retries")

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# Validate token
spot_data  = kite_call(kite.ltp, ["NSE:NIFTY 50"])
spot_price = spot_data.get("NSE:NIFTY 50", {}).get("last_price")
if not spot_price:
    raise RuntimeError("❌ Invalid API Key or Access Token.")
print(f"✅ Spot price: {spot_price}")

# -------------------- FETCH & GREEKS --------------------
insts    = pd.DataFrame(kite_call(kite.instruments, "NFO"))
nifty    = insts[(insts["name"]=="NIFTY") & (insts["segment"]=="NFO-OPT")]
exp      = sorted(nifty["expiry"].unique())
nearest  = next(e for e in exp if pd.to_datetime(e).date()>=today)
ce_opts  = nifty[(nifty["expiry"]==nearest)&(nifty["instrument_type"]=="CE")]
pe_opts  = nifty[(nifty["expiry"]==nearest)&(nifty["instrument_type"]=="PE")]

ce_ltp   = kite_call(kite.ltp, ce_opts["instrument_token"].tolist())
pe_ltp   = kite_call(kite.ltp, pe_opts["instrument_token"].tolist())
ce_opts["ltp"] = ce_opts["instrument_token"].apply(lambda x: ce_ltp[str(x)]["last_price"])
pe_opts["ltp"] = pe_opts["instrument_token"].apply(lambda x: pe_ltp[str(x)]["last_price"])

T, r, σ = 1/12, 0.06, 0.14
def bs(row):
    S, K = spot_price, row["strike"]
    d1    = (np.log(S/K)+(r+0.5*σ**2)*T)/(σ*np.sqrt(T))
    Δ     = norm.cdf(d1) if row["instrument_type"]=="CE" else -norm.cdf(-d1)
    vega  = S*norm.pdf(d1)*np.sqrt(T)/100
    theta = -S*norm.pdf(d1)*σ/(2*np.sqrt(T))/365
    return Δ, vega, theta

ce_opts[["delta","vega","theta"]] = ce_opts.apply(bs, axis=1, result_type="expand")
pe_opts[["delta","vega","theta"]] = pe_opts.apply(bs, axis=1, result_type="expand")

low,high = 0.05,0.6
sum_ce = ce_opts.query("delta>=@low and delta<=@high")["delta"].sum()
sum_pe = pe_opts.query("abs(delta)>=@low and abs(delta)<=@high")["delta"].sum()
sum_cv = ce_opts["vega"].sum(); sum_pv = pe_opts["vega"].sum()
sum_ct = ce_opts["theta"].sum(); sum_pt = pe_opts["theta"].sum()

row = [now.isoformat(), sum_ce, sum_pe, sum_cv, sum_pv, sum_ct, sum_pt]
log_ws.append_row(row)
print("✅ Logged to GreeksLog")

if is_open_snapshot:
    open_ws.clear()
    open_ws.append_row(row)
    print("📌 Saved GreeksOpen")
