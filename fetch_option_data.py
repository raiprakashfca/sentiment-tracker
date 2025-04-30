import os
import json
import math
import time
import pandas as pd
from kiteconnect import KiteConnect
from datetime import datetime
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from scipy.stats import norm

# ---------- TIMEZONE ----------
ist = pytz.timezone("Asia/Kolkata")
now = datetime.now(ist)
date_str = now.strftime('%Y-%m-%d')
time_str = now.strftime('%H:%M')

# ---------- GOOGLE SHEET SETUP ----------
gcreds = None
if "GCREDS" in os.environ:
    try:
        gcreds = json.loads(os.environ["GCREDS"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
        sheet_client = gspread.authorize(creds)
        log_sheet = sheet_client.open("GreeksLog").worksheet("Live")
    except Exception as e:
        print("⚠️ Failed to connect to Google Sheets:", e)

# ---------- ZERODHA SETUP ----------
api_key = os.environ.get("ZERODHA_API_KEY")
access_token = os.environ.get("ZERODHA_ACCESS_TOKEN")
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# ---------- GET SPOT PRICE ----------
spot_price = kite.ltp(["NSE:NIFTY 50"])["NSE:NIFTY 50"]["last_price"]
print("🔍 NIFTY Spot:", spot_price)

# ---------- GET INSTRUMENTS ----------
instruments = kite.instruments("NFO")
nifty_opts = [i for i in instruments if i["name"] == "NIFTY" and i["instrument_type"] == "OPTIDX"]

# ---------- EXPIRY + ATM ----------
expiries = sorted(list(set([i["expiry"] for i in nifty_opts])))
nearest_expiry = expiries[0]
atm_strike = round(spot_price / 50) * 50

# ---------- BLACK-SCHOLES ----------
def black_scholes_greeks(option_type, S, K, T, r, sigma):
    d1 = (math.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option_type == "CE":
        delta = norm.cdf(d1)
        theta = (-S * norm.pdf(d1) * sigma / (2 * math.sqrt(T)) - r * K * math.exp(-r*T) * norm.cdf(d2)) / 365
    else:
        delta = -norm.cdf(-d1)
        theta = (-S * norm.pdf(d1) * sigma / (2 * math.sqrt(T)) + r * K * math.exp(-r*T) * norm.cdf(-d2)) / 365
    vega = S * norm.pdf(d1) * math.sqrt(T) / 100
    return round(delta, 4), round(theta, 2), round(vega, 2)

# ---------- GREEKS LOGIC ----------
greeks = {"ce_delta": 0, "pe_delta": 0, "ce_theta": 0, "pe_theta": 0, "ce_vega": 0, "pe_vega": 0}

for opt in nifty_opts:
    if opt["expiry"] != nearest_expiry:
        continue
    option_type = opt["instrument_type"]
    strike = opt["strike"]
    token = opt["instrument_token"]

    try:
        ltp = kite.ltp([token])[str(token)]["last_price"]
        iv = opt.get("implied_volatility", 0.18)  # fallback IV
        r = 0.06
        T = (opt["expiry"] - now.date()).days / 365
        if T <= 0:
            continue

        delta, theta, vega = black_scholes_greeks(option_type, spot_price, strike, T, r, iv)

        if 0.05 <= abs(delta) <= 0.60:
            if option_type == "CE":
                greeks["ce_delta"] += delta
                greeks["ce_theta"] += theta
                greeks["ce_vega"] += vega
            else:
                greeks["pe_delta"] += delta
                greeks["pe_theta"] += theta
                greeks["pe_vega"] += vega

    except Exception as e:
        print(f"⚠️ {option_type} {strike} skipped due to error: {e}")

# ---------- SAVE TO CSV ----------
df_row = {
    "timestamp": now.isoformat(),
    **greeks
}
log_path = "greeks_log_historical.csv"
open_path = "greeks_open.csv"

if os.path.exists(log_path):
    pd.read_csv(log_path).append(df_row, ignore_index=True).to_csv(log_path, index=False)
else:
    pd.DataFrame([df_row]).to_csv(log_path, index=False)

# Save open snapshot if it's 9:15 AM
if time_str == "09:15":
    pd.DataFrame([df_row]).to_csv(open_path, index=False)

# ---------- GOOGLE SHEET SYNC ----------
if gcreds:
    try:
        log_sheet.append_row([now.strftime('%H:%M:%S')] + list(greeks.values()))
    except Exception as e:
        print("⚠️ Sheet update failed:", e)
