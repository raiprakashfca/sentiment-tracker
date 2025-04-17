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

# ✅ Always read API key from A1 and access token from C1
api_key = sheet.acell("A1").value.strip()
access_token = sheet.acell("C1").value.strip()

# Initialize Kite
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# Test API call
nifty_spot = kite.ltp(["NSE:NIFTY 50"])["NSE:NIFTY 50"]["last_price"]

# Proceed with mock Greek analysis (can be replaced with actual Greeks)
dump = kite.instruments("NSE")
option_instruments = [i for i in dump if i["segment"] == "NFO-OPT" and i["name"] == "NIFTY"]
expiry_dates = sorted(set(i["expiry"] for i in option_instruments if i["expiry"] >= datetime.date.today()))
nearest_expiry = expiry_dates[0]
selected = [i for i in option_instruments if i["expiry"] == nearest_expiry]

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

# Log summary
summary = pd.DataFrame([{
    "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "delta_sum": df["delta"].sum(),
    "vega_sum": df["vega"].sum(),
    "theta_sum": df["theta"].sum()
}])

log_path = "greeks_log.csv"
if os.path.exists(log_path):
    summary.to_csv(log_path, mode="a", header=False, index=False)
else:
    summary.to_csv(log_path, index=False)

print("✅ Greeks logged successfully")
