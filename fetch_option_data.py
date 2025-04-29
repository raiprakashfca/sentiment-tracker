import pandas as pd
import numpy as np
import datetime
import pytz
from kiteconnect import KiteConnect
from scipy.stats import norm
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ----------------- CONSTANTS -----------------
ist = pytz.timezone("Asia/Kolkata")
now = datetime.datetime.now(ist)

# ----------------- READ SECRETS -----------------
api_key = st.secrets["api_key"]
api_secret = st.secrets["api_secret"]
access_token = st.secrets["access_token"]
gcreds = st.secrets["gcreds"]

# ----------------- INITIATE KITE -----------------
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# ----------------- BLACK-SCHOLES GREEKS CALCULATOR -----------------
def calculate_greeks(option_type, spot, strike, expiry, price, iv):
    T = (expiry - now).total_seconds() / (365 * 24 * 60 * 60)
    r = 0.06  # risk-free rate assumed 6%
    sigma = iv / 100

    if T <= 0 or sigma <= 0:
        return 0, 0, 0

    d1 = (np.log(spot/strike) + (r + sigma**2/2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)

    if option_type == 'CE':
        delta = norm.cdf(d1)
    else:
        delta = -norm.cdf(-d1)

    vega = (spot * norm.pdf(d1) * np.sqrt(T)) / 100
    theta = -(spot * norm.pdf(d1) * sigma) / (2*np.sqrt(T)) - r*strike*np.exp(-r*T)*norm.cdf(d2 if option_type == 'CE' else -d2)
    theta /= 365

    return delta, vega, theta

# ----------------- FETCH INSTRUMENTS -----------------
instruments = kite.instruments("NFO")
nifty_options = [i for i in instruments if i["name"] == "NIFTY" and i["instrument_type"] in ("CE", "PE")]

# ----------------- FETCH SPOT PRICE -----------------
nifty_spot = kite.ltp(["NSE:NIFTY 50"])["NSE:NIFTY 50"]["last_price"]

# ----------------- FETCH OPTION CHAIN DATA -----------------
tokens = [i["instrument_token"] for i in nifty_options]
ltp_data = kite.ltp(tokens)

# ----------------- PROCESS DATA -----------------
rows = []
for inst in nifty_options:
    token = inst["instrument_token"]
    if token not in ltp_data:
        continue
    price = ltp_data[token]["last_price"]
    expiry = inst["expiry"]
    strike = inst["strike"]
    option_type = inst["instrument_type"]
    iv = 18  # assume 18% IV if not available dynamically

    delta, vega, theta = calculate_greeks(option_type, nifty_spot, strike, expiry, price, iv)

    rows.append({
        "option_type": option_type,
        "strike": strike,
        "expiry": expiry,
        "price": price,
        "delta": delta,
        "vega": vega,
        "theta": theta
    })

df = pd.DataFrame(rows)

# ----------------- FILTER STRIKES BY DELTA -----------------
df = df[(df["delta"].abs() >= 0.05) & (df["delta"].abs() <= 0.60)]

# ----------------- SUM GREEKS -----------------
ce_df = df[df["option_type"] == "CE"]
pe_df = df[df["option_type"] == "PE"]

summary = {
    "timestamp": now.strftime('%Y-%m-%d %H:%M:%S'),
    "ce_delta": ce_df["delta"].sum(),
    "pe_delta": pe_df["delta"].sum(),
    "ce_vega": ce_df["vega"].sum(),
    "pe_vega": pe_df["vega"].sum(),
    "ce_theta": ce_df["theta"].sum(),
    "pe_theta": pe_df["theta"].sum(),
}

# ----------------- SAVE TO CSV -----------------
csv_path = "greeks_log_historical.csv"

try:
    df_existing = pd.read_csv(csv_path)
    df_new = pd.concat([df_existing, pd.DataFrame([summary])], ignore_index=True)
except FileNotFoundError:
    df_new = pd.DataFrame([summary])

df_new.to_csv(csv_path, index=False)
print("✅ Greeks logged to CSV:", csv_path)

# ----------------- (Optional) BACKUP TO GOOGLE SHEETS -----------------
try:
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
    client = gspread.authorize(creds)
    sheet = client.open("SentimentTrackerStore").worksheet("LiveGreeks")

    sheet.append_row([
        summary["timestamp"],
        summary["ce_delta"],
        summary["pe_delta"],
        summary["ce_vega"],
        summary["pe_vega"],
        summary["ce_theta"],
        summary["pe_theta"]
    ])
    print("✅ Backup to Google Sheet successful")
except Exception as e:
    print(f"❌ Backup to Google Sheet failed: {e}")
