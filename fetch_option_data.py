from kiteconnect import KiteConnect
import datetime
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import random
from streamlit.runtime.secrets import secrets as st_secrets

# CONFIG
GOOGLE_SHEET_NAME = "ZerodhaTokenStore"
GOOGLE_TAB_NAME = "Sheet1"

# Load credentials from secrets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = {key: st_secrets["gcp_service_account"][key] for key in st_secrets["gcp_service_account"]}
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open(GOOGLE_SHEET_NAME).worksheet(GOOGLE_TAB_NAME)

# Get access token and manually entered API key (update this if stored elsewhere)
access_token = sheet.acell("B2").value.strip()
api_key = sheet.acell("A2").value.strip() if sheet.acell("A2").value else "your_api_key_here"

# Setup KiteConnect
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# Fetch NIFTY Spot Price
nifty_spot = kite.ltp(["NSE:NIFTY 50"])["NSE:NIFTY 50"]["last_price"]

# Get all NIFTY option instruments
all_instruments = kite.instruments("NSE")
nifty_options = [i for i in all_instruments if i["segment"] == "NFO-OPT" and i["name"] == "NIFTY"]

# Find nearest expiry
today = datetime.date.today()
expiries = sorted(set(i["expiry"] for i in nifty_options if i["expiry"] >= today))
nearest_expiry = expiries[0]

# Filter options for that expiry
selected_options = [i for i in nifty_options if i["expiry"] == nearest_expiry]

# Simulated Greeks (replace with real calc later)
greek_data = []
for inst in selected_options:
    delta = round(random.uniform(0.03, 0.65), 2)
    vega = round(random.uniform(2, 6), 2)
    theta = round(random.uniform(-20, -5), 2)

    if 0.05 <= abs(delta) <= 0.60:
        greek_data.append({
            "strike": inst["strike"],
            "type": inst["instrument_type"],
            "delta": delta,
            "vega": vega,
            "theta": theta
        })

df = pd.DataFrame(greek_data)

# Summarize and save
delta_sum = df["delta"].sum()
vega_sum = df["vega"].sum()
theta_sum = df["theta"].sum()
timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

log_entry = pd.DataFrame([{
    "time": timestamp,
    "delta_sum": delta_sum,
    "vega_sum": vega_sum,
    "theta_sum": theta_sum
}])

# Save to CSV
log_path = "greeks_log.csv"
if os.path.exists(log_path):
    log_entry.to_csv(log_path, mode="a", header=False, index=False)
else:
    log_entry.to_csv(log_path, index=False)

print(f"📊 Greeks logged at {timestamp}")
