import pandas as pd
import datetime
import time
import pytz
import os
import json
import gspread
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials

# ----------------- SETUP -----------------

# Timezone
ist = pytz.timezone("Asia/Kolkata")

# Load credentials from Streamlit/Environment
gcreds = json.loads(os.environ["GCREDS"])

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
client = gspread.authorize(creds)
sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")

api_key = sheet.acell("A1").value.strip()
access_token = sheet.acell("C1").value.strip()

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# ----------------- CHECK MARKET TIME -----------------

now = datetime.datetime.now(ist)
market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

if not (market_open <= now <= market_close):
    print(f"⏳ Outside market hours ({now.strftime('%H:%M:%S')}). Skipping fetch.")
    exit()

# ----------------- FETCH NIFTY OPTIONS -----------------

# Fetch instruments
instruments = pd.DataFrame(kite.instruments("NFO"))
nifty_options = instruments[
    (instruments["name"] == "NIFTY") &
    (instruments["segment"] == "NFO-OPT")
]

# Get Spot Price
nifty_spot = kite.ltp(["NSE:NIFTY 50"])["NSE:NIFTY 50"]["last_price"]

# Filter Near Month Expiry
nearest_expiry = sorted(nifty_options["expiry"].unique())[0]
nifty_options = nifty_options[nifty_options["expiry"] == nearest_expiry]

# Prepare strike list near spot
lower_strike = (nifty_spot // 50 - 10) * 50
upper_strike = (nifty_spot // 50 + 10) * 50
nifty_options = nifty_options[(nifty_options["strike"] >= lower_strike) & (nifty_options["strike"] <= upper_strike)]

# ----------------- FETCH LIVE LTP and Calculate Greeks -----------------

records = []
for idx, row in nifty_options.iterrows():
    try:
        ins_token = row["instrument_token"]
        ltp_data = kite.ltp([ins_token])[str(ins_token)]
        ltp = ltp_data["last_price"]
        strike = row["strike"]
        option_type = row["instrument_type"][-2:]
        
        # Approximate Delta (simple proxy model, real Black-Scholes too heavy for live)
        moneyness = (nifty_spot - strike) / nifty_spot
        if option_type == "CE":
            delta = max(0.05, min(0.95, 0.5 + moneyness))
        else:
            delta = max(-0.95, min(-0.05, 0.5 - moneyness))
        
        vega = abs(delta) * 0.1
        theta = -abs(delta) * 0.05
        
        records.append({
            "option_type": option_type,
            "delta": delta,
            "vega": vega,
            "theta": theta,
        })
        
    except Exception as e:
        print(f"⚠️ Failed to fetch LTP for {row['tradingsymbol']}: {e}")
        continue

df_greeks = pd.DataFrame(records)

# ----------------- FILTER DELTA RANGE -----------------

df_greeks = df_greeks[
    (df_greeks["delta"].abs() >= 0.05) & (df_greeks["delta"].abs() <= 0.60)
]

# ----------------- SUMMARIZE -----------------

ce = df_greeks[df_greeks["option_type"] == "CE"]
pe = df_greeks[df_greeks["option_type"] == "PE"]

timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
new_entry = {
    "timestamp": timestamp,
    "ce_delta": ce["delta"].sum(),
    "pe_delta": pe["delta"].sum(),
    "ce_vega": ce["vega"].sum(),
    "pe_vega": pe["vega"].sum(),
    "ce_theta": ce["theta"].sum(),
    "pe_theta": pe["theta"].sum()
}

# ----------------- APPEND TO greeks_log_historical.csv -----------------

try:
    historical = pd.read_csv("greeks_log_historical.csv")
    historical = pd.concat([historical, pd.DataFrame([new_entry])], ignore_index=True)
except FileNotFoundError:
    historical = pd.DataFrame([new_entry])

historical.to_csv("greeks_log_historical.csv", index=False)

# ----------------- Update greeks_open.csv if first 9:15 entry -----------------

if now.hour == 9 and now.minute < 20:  # Assume 9:15 to 9:19
    pd.DataFrame([new_entry]).to_csv("greeks_open.csv", index=False)

print(f"✅ Greeks updated at {timestamp}")
