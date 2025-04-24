import pandas as pd
import numpy as np
import requests
from kiteconnect import KiteConnect
import datetime
import time
import os
import json
import math
from scipy.stats import norm
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ---------------------- CONFIG ----------------------
symbol = "NIFTY"
iv_input = float(input("Enter Implied Volatility (e.g., 0.15 for 15%): ").strip())
risk_free_rate = 0.06

# ---------------------- GOOGLE SHEET AUTH ----------------------
gcreds = json.loads(os.environ["GCREDS"])
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
client = gspread.authorize(creds)
sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")
api_key = sheet.acell("A1").value.strip()
access_token = sheet.acell("C1").value.strip()

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

print("🔐 API Key:", api_key)
print("🔑 Access Token:", access_token[:6] + "..." + access_token[-6:])

# ---------------------- GET TODAY + EXPIRY ----------------------
today = datetime.date.today()
nse_holidays = [
    datetime.date(2025, 4, 10),
    datetime.date(2025, 4, 14),
    datetime.date(2025, 4, 18),
]
if today in nse_holidays or today.weekday() >= 5:
    print("🚫 Market is closed today.")
    exit()

# ---------------------- LOAD INSTRUMENTS ----------------------
instr_file = "instruments.csv"
if not os.path.exists(instr_file):
    print("⬇️ Downloading instrument list from Zerodha...")
    url = "https://api.kite.trade/instruments"
    response = requests.get(url)
    with open(instr_file, "w") as f:
        f.write(response.text)
    print("✅ Instrument list cached.")
    
instruments = pd.read_csv(instr_file)
opt_chain = instruments[(instruments["segment"] == "NFO-OPT") & (instruments["name"] == symbol)]

# ---------------------- GET NEAREST EXPIRY ----------------------
expiries = sorted(opt_chain["expiry"].unique())
nearest_expiry = expiries[0]
opt_chain = opt_chain[opt_chain["expiry"] == nearest_expiry]
print(f"🎯 Nearest Expiry: {nearest_expiry}")

# ---------------------- BLACK-SCHOLES GREEKS ----------------------
def calculate_greeks(option_type, spot, strike, iv, time_to_expiry, price):
    try:
        d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * iv ** 2) * time_to_expiry) / (iv * math.sqrt(time_to_expiry))
        d2 = d1 - iv * math.sqrt(time_to_expiry)
        delta = norm.cdf(d1) if option_type == "CE" else -norm.cdf(-d1)
        vega = spot * norm.pdf(d1) * math.sqrt(time_to_expiry) / 100
        theta = (-spot * norm.pdf(d1) * iv / (2 * math.sqrt(time_to_expiry))) / 365
        if option_type == "PE":
            theta -= risk_free_rate * strike * math.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2) / 365
        else:
            theta -= risk_free_rate * strike * math.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2) / 365
        return delta, vega, theta
    except Exception:
        return 0, 0, 0

# ---------------------- HISTORICAL SNAPSHOT ----------------------
from_time = datetime.datetime.combine(today, datetime.time(9, 15))
to_time = datetime.datetime.combine(today, datetime.time(15, 30))
intervals = pd.date_range(from_time, to_time, freq="5min")

spot_token = 256265
spot_df = kite.historical_data(spot_token, from_time, to_time, interval="5minute")
spot_prices = pd.DataFrame(spot_df)["close"].values

open_log = None
log_records = []

for i, timestamp in enumerate(intervals):
    try:
        spot = spot_prices[i]
        time_to_expiry = (pd.to_datetime(nearest_expiry) - timestamp).total_seconds() / (365 * 24 * 60 * 60)

        ce_delta_sum = pe_delta_sum = ce_vega_sum = pe_vega_sum = ce_theta_sum = pe_theta_sum = 0

        for _, row in opt_chain.iterrows():
            try:
                token = row["instrument_token"]
                strike = row["strike"]
                opt_type = row["instrument_type"]  # CE or PE
                ltp_data = kite.ltp([f"{row['exchange']}:{row['tradingsymbol']}"])
                ltp = ltp_data[f"{row['exchange']}:{row['tradingsymbol']}"]["last_price"]
                delta, vega, theta = calculate_greeks(opt_type, spot, strike, iv_input, time_to_expiry, ltp)
                if 0.05 <= abs(delta) <= 0.60:
                    if opt_type == "CE":
                        ce_delta_sum += delta
                        ce_vega_sum += vega
                        ce_theta_sum += theta
                    else:
                        pe_delta_sum += delta
                        pe_vega_sum += vega
                        pe_theta_sum += theta
            except:
                continue

        snapshot = {
            "timestamp": timestamp,
            "ce_delta": ce_delta_sum,
            "pe_delta": pe_delta_sum,
            "ce_vega": ce_vega_sum,
            "pe_vega": pe_vega_sum,
            "ce_theta": ce_theta_sum,
            "pe_theta": pe_theta_sum,
        }

        if open_log is None:
            open_log = snapshot
            pd.DataFrame([snapshot]).to_csv("greeks_open.csv", index=False)
            print("✅ Saved 9:15 snapshot to greeks_open.csv")

        log_records.append({
            "timestamp": timestamp,
            "ce_delta_change": snapshot["ce_delta"] - open_log["ce_delta"],
            "pe_delta_change": snapshot["pe_delta"] - open_log["pe_delta"],
            "ce_vega_change": snapshot["ce_vega"] - open_log["ce_vega"],
            "pe_vega_change": snapshot["pe_vega"] - open_log["pe_vega"],
            "ce_theta_change": snapshot["ce_theta"] - open_log["ce_theta"],
            "pe_theta_change": snapshot["pe_theta"] - open_log["pe_theta"],
        })

        print(f"🕒 {timestamp.strftime('%H:%M')} | CE Δ: {round(ce_delta_sum,1)} | PE Δ: {round(pe_delta_sum,1)}")

    except Exception as e:
        print(f"⚠️ {timestamp.strftime('%H:%M')} – Skipped due to error: {e}")
        continue

# Save full log
pd.DataFrame(log_records).to_csv("greeks_log_historical.csv", index=False)
print("✅ Saved full log to greeks_log_historical.csv")
