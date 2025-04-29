import pandas as pd
import datetime
import gspread
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials
import pytz
import streamlit as st

# ----------------- SETUP TIMEZONE -----------------
ist = pytz.timezone("Asia/Kolkata")
now = datetime.datetime.now(ist)

# ----------------- READ STREAMLIT SECRETS -----------------
api_key = st.secrets["api_key"]
api_secret = st.secrets["api_secret"]
access_token = st.secrets["access_token"]
gcreds = st.secrets["gcreds"]

# ----------------- INIT KITE -----------------
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# ----------------- FETCH DATA -----------------
try:
    nifty_spot = kite.ltp(["NSE:NIFTY 50"])["NSE:NIFTY 50"]["last_price"]
    print(f"✅ Fetched NIFTY Spot: {nifty_spot} at {now.strftime('%H:%M:%S')}")
except Exception as e:
    print(f"❌ Failed to fetch NIFTY Spot: {e}")
    raise SystemExit()

# ----------------- LOG TO GOOGLE SHEET -----------------
try:
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
    client = gspread.authorize(creds)
    sheet = client.open("SentimentTrackerStore").worksheet("LiveGreeks")

    # Example update — you can customize
    sheet.append_row([
        now.strftime('%Y-%m-%d %H:%M:%S'),
        nifty_spot
    ])
    print("✅ Logged data to Google Sheet.")
except Exception as e:
    print(f"❌ Failed to log data to Google Sheet: {e}")
