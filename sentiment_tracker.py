from kiteconnect import KiteConnect
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import datetime
import json
import os

# -------------------- CONFIG --------------------
# Fixed instrument token for NIFTY
NIFTY_INDEX_TOKEN = 256265
DELTA_LOWER = 0.05
DELTA_UPPER = 0.60

# -------------------- LOAD GOOGLE SHEET --------------------
gcreds = json.loads(os.environ["GCREDS"])
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
client = gspread.authorize(creds)
sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")

api_key = sheet.acell("A1").value.strip()
api_secret = sheet.acell("B1").value.strip()
access_token = sheet.acell("C1").value.strip()

# -------------------- INIT KITE --------------------
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# ✅ Fetch profile to confirm token works
try:
    profile = kite.profile()
    print(f"🟢 Access token valid for: {profile['user_name']}")
except Exception as e:
    print("🔴 Invalid access token. Please login again.")
    exit(1)

# -------------------- FETCH OPTION CHAIN --------------------
print("📥 Fetching instruments...")
instruments = kite.instruments("NFO")
nifty_options = [
    i for i in instruments
    if i["name"] == "NIFTY"
    and i["instrument_type"] in ["CE", "PE"]
    and i["segment"] == "NFO-OPT"
]

# ✅ Get nearest expiry
expiries = sorted(set(i["expiry"] for i in nifty_options))
nearest_expiry = expiries[0]
print(f"📅 Nearest Expiry: {nearest_expiry}")

# Filter by expiry
nifty_options = [i for i in nifty_options if i["expiry"] == nearest_expiry]

# Get LTP for NIFTY
spot = kite.ltp([f"NSE:NIFTY 50"])["NSE:NIFTY 50"]["last_price"]
print(f"📈 NIFTY Spot: {spot}")

# -------------------- FETCH MARKET QUOTES --------------------
tokens = [i["instrument_token"] for i in nifty_options]
quote = kite.quote(tokens)

# -------------------- EXTRACT GREEKS + FILTER --------------------
greek_rows = []

for inst in nifty_options:
    token = inst["instrument_token"]
    info = quote.get(token, {}).get("greeks", None)
    if not info:
        continue

    delta = abs(info.get("delta", 0))
    if DELTA_LOWER <= delta <= DELTA_UPPER:
        greek_rows.append({
            "strike": inst["strike"],
            "type": inst["instrument_type"],
            "delta": info.get("delta", 0),
            "vega": info.get("vega", 0),
            "theta": info.get("theta", 0)
        })

df = pd.DataFrame(greek_rows)
if df.empty:
    print("⚠️ No strikes found in delta range.")
    exit(0)

# -------------------- SUMMARIZE --------------------
delta_sum = df["delta"].sum()
vega_sum = df["vega"].sum()
theta_sum = df["theta"].sum()

log_entry = pd.DataFrame([{
    "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "delta_sum": delta_sum,
    "vega_sum": vega_sum,
    "theta_sum": theta_sum
}])

# Save log
log_path = "greeks_log.csv"
if os.path.exists(log_path):
    log_entry.to_csv(log_path, mode="a", header=False, index=False)
else:
    log_entry.to_csv(log_path, index=False)

# -------------------- PRINT SUMMARY --------------------
print("✅ Greek Summary:")
print(log_entry)

# -------------------- WRITE BACK ACCESS TOKEN --------------------
# Validate live token and store back in sheet if changed
current_session = kite._access_token
if current_session != access_token:
    sheet.update("C1", current_session)
    print("🔄 Access token refreshed in sheet.")
