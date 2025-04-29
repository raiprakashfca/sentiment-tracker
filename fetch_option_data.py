# ✅ fetch_option_data.py

import pandas as pd
import datetime
import os
import json
from kiteconnect import KiteConnect
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --------------- SETUP ---------------
gcreds = json.loads(os.environ["GCREDS"])
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
client = gspread.authorize(creds)
sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")

api_key = sheet.acell("A1").value.strip()
access_token = sheet.acell("C1").value.strip()

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# --------------- MARKET TIME ---------------
ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
now = datetime.datetime.now(ist)

# --------------- FETCH INSTRUMENTS ---------------
try:
    instruments = kite.instruments("NSE")
    df_instruments = pd.DataFrame(instruments)
except Exception as e:
    print(f"❌ Failed to fetch instruments: {e}")
    exit()

# --------------- FILTER NIFTY OPTIONS ---------------
df_options = df_instruments[
    (df_instruments["name"] == "NIFTY") &
    (df_instruments["segment"] == "NFO-OPT") &
    (df_instruments["exchange"] == "NFO")
]

# --------------- GET SPOT PRICE ---------------
try:
    spot = kite.ltp(["NSE:NIFTY 50"])["NSE:NIFTY 50"]["last_price"]
except Exception as e:
    print(f"❌ Failed to fetch NIFTY spot: {e}")
    exit()

# --------------- SELECT STRIKE RANGE ---------------
atm = round(spot / 50) * 50
strike_range = list(range(atm - 500, atm + 550, 50))

# --------------- FETCH OPTION LTPs ---------------
option_tokens = df_options[
    (df_options["strike"].isin(strike_range)) &
    (df_options["expiry"] >= now.date())
]["instrument_token"].tolist()

try:
    quotes = kite.ltp(option_tokens)
except Exception as e:
    print(f"❌ Failed fetching quotes: {e}")
    exit()

# --------------- ESTIMATE DELTA ---------------
def estimate_delta(option_type, strike, spot):
    diff = abs(strike - spot)
    if diff > 500:
        return 0.05
    elif diff > 400:
        return 0.10
    elif diff > 300:
        return 0.20
    elif diff > 200:
        return 0.30
    elif diff > 100:
        return 0.40
    else:
        return 0.50

records = []

for token, data in quotes.items():
    try:
        opt = df_options[df_options["instrument_token"] == token].iloc[0]
        strike = opt["strike"]
        expiry = opt["expiry"]
        option_type = opt["instrument_type"]
        ltp = data["last_price"]

        est_delta = estimate_delta(option_type, strike, spot)

        if 0.05 <= est_delta <= 0.60:
            records.append({
                "timestamp": now,
                "option_type": option_type,
                "strike": strike,
                "expiry": expiry,
                "ltp": ltp,
                "delta": est_delta,
            })
    except Exception:
        continue

df_greeks = pd.DataFrame(records)

# --------------- SUMMARIZE GREEKS ---------------
summary = {
    "timestamp": now,
    "ce_delta": df_greeks[df_greeks["option_type"] == "CE"]["delta"].sum(),
    "pe_delta": df_greeks[df_greeks["option_type"] == "PE"]["delta"].sum(),
    "ce_vega": 0,
    "pe_vega": 0,
    "ce_theta": 0,
    "pe_theta": 0,
}

df_summary = pd.DataFrame([summary])

# --------------- SAVE ---------------
if not os.path.exists("greeks_log_historical.csv"):
    df_summary.to_csv("greeks_log_historical.csv", index=False)
else:
    df_existing = pd.read_csv("greeks_log_historical.csv")
    df_existing = pd.concat([df_existing, df_summary], ignore_index=True)
    df_existing.to_csv("greeks_log_historical.csv", index=False)

# Save 9:15 AM Open
if now.strftime("%H:%M") == "09:15":
    df_summary.to_csv("greeks_open.csv", index=False)

print("✅ Live Greeks captured successfully.")
