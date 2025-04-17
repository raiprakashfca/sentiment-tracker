from kiteconnect import KiteConnect
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import datetime
import json
import os

# -------------------- CONFIG --------------------
NIFTY_INDEX_TOKEN = 256265
DELTA_LOWER = 0.05
DELTA_UPPER = 0.60
OPEN_LOG_PATH = "greeks_open.csv"
LIVE_LOG_PATH = "greeks_log.csv"
SHEET_NAME = "GreekSentimentLog"

# -------------------- GOOGLE SHEET SETUP --------------------
gcreds = json.loads(os.environ["GCREDS"])
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME)

ws_open = sheet.worksheet("OpenSnapshot")
ws_live = sheet.worksheet("LiveLog")

# -------------------- ZERODHA API SETUP --------------------
token_sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")
api_key = token_sheet.acell("A1").value.strip()
access_token = token_sheet.acell("C1").value.strip()

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# Validate token
try:
    profile = kite.profile()
    print(f"🟢 Access token valid for: {profile['user_name']}")
except Exception:
    print("🔴 Invalid access token. Please login again.")
    exit(1)

# -------------------- FETCH INSTRUMENTS --------------------
print("📥 Fetching instruments...")
instruments = kite.instruments("NFO")
nifty_options = [
    i for i in instruments
    if i["name"] == "NIFTY"
    and i["instrument_type"] in ["CE", "PE"]
    and i["segment"] == "NFO-OPT"
]

expiries = sorted(set(i["expiry"] for i in nifty_options))
if not expiries:
    print("❌ No expiry found.")
    exit(1)

nearest_expiry = expiries[0]
nifty_options = [i for i in nifty_options if i["expiry"] == nearest_expiry]

spot = kite.ltp(["NSE:NIFTY 50"])["NSE:NIFTY 50"]["last_price"]
print(f"📈 NIFTY Spot: {spot}")

tokens = [i["instrument_token"] for i in nifty_options]
quotes = kite.quote(tokens)

# -------------------- EXTRACT GREEKS (CE/PE SPLIT) --------------------
ce_rows, pe_rows = [], []

for inst in nifty_options:
    info = quotes.get(inst["instrument_token"], {}).get("greeks", None)
    if not info:
        continue

    delta = abs(info.get("delta", 0))
    if DELTA_LOWER <= delta <= DELTA_UPPER:
        entry = {
            "strike": inst["strike"],
            "delta": info.get("delta", 0),
            "vega": info.get("vega", 0),
            "theta": info.get("theta", 0)
        }
        if inst["instrument_type"] == "CE":
            ce_rows.append(entry)
        else:
            pe_rows.append(entry)

df_ce = pd.DataFrame(ce_rows)
df_pe = pd.DataFrame(pe_rows)

if df_ce.empty and df_pe.empty:
    print("⚠️ No strikes in delta range.")
    exit(0)

# -------------------- SUMMARIZE GREEKS --------------------
now = datetime.datetime.now()
today = now.strftime("%Y-%m-%d")
timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

def greek_summary(df):
    return {
        "delta_sum": df["delta"].sum(),
        "vega_sum": df["vega"].sum(),
        "theta_sum": df["theta"].sum()
    } if not df.empty else {"delta_sum": 0, "vega_sum": 0, "theta_sum": 0}

ce = greek_summary(df_ce)
pe = greek_summary(df_pe)

# -------------------- MARKET OPEN SNAPSHOT --------------------
if now.hour == 9 and now.minute < 20:
    open_data = pd.DataFrame([{
        "date": today,
        "ce_delta": ce["delta_sum"],
        "ce_vega": ce["vega_sum"],
        "ce_theta": ce["theta_sum"],
        "pe_delta": pe["delta_sum"],
        "pe_vega": pe["vega_sum"],
        "pe_theta": pe["theta_sum"]
    }])
    open_data.to_csv(OPEN_LOG_PATH, index=False)

    # Update Google Sheet
    ws_open.clear()
    ws_open.append_row(open_data.columns.tolist())
    ws_open.append_row(open_data.values.tolist()[0])

    print("📌 Market open snapshot saved.")
else:
    if not os.path.exists(OPEN_LOG_PATH):
        print("❗ No market open snapshot found.")
        exit(1)

    open_df = pd.read_csv(OPEN_LOG_PATH)
    open_row = open_df.iloc[0]

    log_row = pd.DataFrame([{
        "timestamp": timestamp,
        "ce_delta": ce["delta_sum"],
        "ce_delta_change": ce["delta_sum"] - open_row["ce_delta"],
        "ce_vega": ce["vega_sum"],
        "ce_vega_change": ce["vega_sum"] - open_row["ce_vega"],
        "ce_theta": ce["theta_sum"],
        "ce_theta_change": ce["theta_sum"] - open_row["ce_theta"],
        "pe_delta": pe["delta_sum"],
        "pe_delta_change": pe["delta_sum"] - open_row["pe_delta"],
        "pe_vega": pe["vega_sum"],
        "pe_vega_change": pe["vega_sum"] - open_row["pe_vega"],
        "pe_theta": pe["theta_sum"],
        "pe_theta_change": pe["theta_sum"] - open_row["pe_theta"]
    }])

    # Save to local log
    if os.path.exists(LIVE_LOG_PATH):
        log_row.to_csv(LIVE_LOG_PATH, mode="a", header=False, index=False)
    else:
        log_row.to_csv(LIVE_LOG_PATH, index=False)

    # Append to Google Sheet
    if ws_live.row_count == 0:
        ws_live.append_row(log_row.columns.tolist())

    ws_live.append_row(log_row.values.tolist()[0])

    print("📊 Greek log updated.")
    print(log_row)

# -------------------- Update token back to sheet --------------------
token_sheet.update("C1", [[access_token]])
print("🔄 Access token written to Google Sheet.")
