from kiteconnect import KiteConnect
import datetime
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import toml
import random

# Load Google credentials from secrets
with open(os.path.expanduser("~/.streamlit/secrets.toml"), "r") as f:
    secrets = toml.load(f)

gcreds = secrets["gcp_service_account"]
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
client = gspread.authorize(creds)
sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")

# ✅ Pull API Key and Access Token from correct cells
api_key = sheet.acell("A1").value.strip()
access_token = sheet.acell("C1").value.strip()

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# Fetch NIFTY Spot
nifty_spot = kite.ltp(["NSE:NIFTY 50"])["NSE:NIFTY 50"]["last_price"]

# Option chain dump
dump = kite.instruments("NSE")
option_instruments = [i for i in dump if i["segment"] == "NFO-OPT" and i["name"] == "NIFTY"]

# Nearest expiry
today = datetime.date.today()
expiry_dates = sorted(set(i["expiry"] for i in option_instruments if i["expiry"] >= today))
nearest_expiry = expiry_dates[0]
selected = [i for i in option_instruments if i["expiry"] == nearest_expiry]

# Simulated Greeks for now
greek_data = []
for inst in selected:
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

# Log Greeks
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

log_path = "greeks_log.csv"
if os.path.exists(log_path):
    log_entry.to_csv(log_path, mode="a", header=False, index=False)
else:
    log_entry.to_csv(log_path, index=False)

print(f"📊 Greeks logged at {timestamp}")
