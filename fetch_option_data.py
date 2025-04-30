import os
import json
import pandas as pd
import datetime
import pytz
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials
import gspread
import numpy as np
from scipy.stats import norm

# -------------------- TIME --------------------
ist = pytz.timezone("Asia/Kolkata")
now = datetime.datetime.now(ist)

# -------------------- GCREDS --------------------
gcreds = json.loads(os.environ["GCREDS"])
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
client = gspread.authorize(creds)
sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")

api_key = sheet.acell("A1").value.strip()
access_token = sheet.acell("C1").value.strip()

# -------------------- INIT KITE --------------------
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# -------------------- TOKEN TEST --------------------
try:
    spot_price = kite.ltp(["NSE:NIFTY 50"])["NSE:NIFTY 50"]["last_price"]
    print(f"✅ Valid token. Spot: {spot_price}")
except Exception as e:
    print(f"❌ Invalid API Key or Access Token: {e}")
    exit(1)

# -------------------- LOAD INSTRUMENTS --------------------
print("🔄 Loading instrument list...")
instruments = pd.DataFrame(kite.instruments("NFO"))
nifty_opts = instruments[(instruments["name"] == "NIFTY") & (instruments["segment"] == "NFO-OPT")]

# -------------------- SELECT EXPIRY --------------------
today = datetime.date.today()
future_expiries = sorted(nifty_opts["expiry"].unique())
nearest_expiry = next(e for e in future_expiries if pd.to_datetime(e).date() >= today)
print(f"🎯 Nearest expiry: {nearest_expiry}")

# -------------------- FILTER OPTIONS --------------------
ce_opts = nifty_opts[(nifty_opts["expiry"] == nearest_expiry) & (nifty_opts["instrument_type"] == "CE")]
pe_opts = nifty_opts[(nifty_opts["expiry"] == nearest_expiry) & (nifty_opts["instrument_type"] == "PE")]

# -------------------- CALCULATE DELTA RANGE --------------------
def black_scholes_delta(option_type, S, K, T, r, sigma):
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    if option_type == "CE":
        return norm.cdf(d1)
    else:
        return -norm.cdf(-d1)

def get_greeks(row, S, T, r, sigma):
    K = row["strike"]
    option_type = row["instrument_type"]
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    delta = black_scholes_delta(option_type, S, K, T, r, sigma)
    vega = S * norm.pdf(d1) * np.sqrt(T) / 100
    theta = (-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))) / 365
    return pd.Series([delta, vega, theta])

# -------------------- MARKET SETTINGS --------------------
T = 1 / 12  # ~22 trading days
r = 0.06
iv = 0.14  # You can tune this

# -------------------- LTP FETCH --------------------
print("📡 Fetching option prices...")
ce_ltp = kite.ltp(ce_opts["instrument_token"].astype(int).tolist())
pe_ltp = kite.ltp(pe_opts["instrument_token"].astype(int).tolist())

ce_opts["ltp"] = ce_opts["instrument_token"].apply(lambda x: ce_ltp[str(x)]["last_price"])
pe_opts["ltp"] = pe_opts["instrument_token"].apply(lambda x: pe_ltp[str(x)]["last_price"])

# -------------------- APPLY GREEKS --------------------
ce_opts[["delta", "vega", "theta"]] = ce_opts.apply(get_greeks, axis=1, args=(spot_price, T, r, iv))
pe_opts[["delta", "vega", "theta"]] = pe_opts.apply(get_greeks, axis=1, args=(spot_price, T, r, iv))

# -------------------- FILTER BY DELTA RANGE --------------------
ce_filtered = ce_opts[(ce_opts["delta"] >= 0.05) & (ce_opts["delta"] <= 0.6)]
pe_filtered = pe_opts[(pe_opts["delta"].abs() >= 0.05) & (pe_opts["delta"].abs() <= 0.6)]

# -------------------- SUM GREEKS --------------------
timestamp = now.strftime("%Y-%m-%d %H:%M:%S%z")
data = {
    "timestamp": timestamp,
    "ce_delta": ce_filtered["delta"].sum(),
    "pe_delta": pe_filtered["delta"].sum(),
    "ce_vega": ce_filtered["vega"].sum(),
    "pe_vega": pe_filtered["vega"].sum(),
    "ce_theta": ce_filtered["theta"].sum(),
    "pe_theta": pe_filtered["theta"].sum()
}
print(f"✅ Greeks logged at {timestamp}")

# -------------------- SAVE TO CSV --------------------
row = pd.DataFrame([data])

if not os.path.exists("greeks_log_historical.csv"):
    row.to_csv("greeks_log_historical.csv", index=False)
else:
    row.to_csv("greeks_log_historical.csv", mode='a', header=False, index=False)

# Save open snapshot if 9:15
if now.strftime("%H:%M") == "09:15":
    row.rename(columns={
        "ce_delta": "ce_delta_open", "pe_delta": "pe_delta_open",
        "ce_vega": "ce_vega_open", "pe_vega": "pe_vega_open",
        "ce_theta": "ce_theta_open", "pe_theta": "pe_theta_open"
    }).to_csv("greeks_open.csv", index=False)
