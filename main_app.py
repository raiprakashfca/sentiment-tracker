import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from kiteconnect import KiteConnect
import datetime
import os

# Streamlit setup
st.set_page_config(layout="wide")
st.title("📈 NIFTY Sentiment Tracker (Delta 0.05–0.60)")

# Load Google credentials from Streamlit secrets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = {key: st.secrets["gcp_service_account"][key] for key in st.secrets["gcp_service_account"]}
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")

# Load credentials from sheet
api_key = sheet.acell("A1").value.strip()
api_secret = sheet.acell("B1").value.strip()
access_token = sheet.acell("C1").value.strip()
last_updated = sheet.acell("D1").value if sheet.acell("D1").value else "Unknown"

# ✅ Show token status at top
st.subheader("🔑 Access Token Status")
if access_token:
    st.success(f"✅ Token is present in C1\n🕒 Last Updated: `{last_updated}`")
else:
    st.error("❌ No access token found in C1. Please generate a fresh token from the sidebar.")

# 🔧 Sidebar: Token manager
with st.sidebar:
    st.header("🔐 Zerodha Token Manager")
    st.markdown(f"🧾 Using API Key from Sheet: `{api_key}`")

    try:
        kite = KiteConnect(api_key=api_key)
        login_url = kite.login_url()
        st.markdown(f"🔗 [Login to Zerodha]({login_url})")
    except Exception as e:
        st.error(f"❌ Failed to generate login URL: {e}")

    request_token = st.text_input("📋 Paste your request_token here:")

    if st.button("Generate Access Token"):
        try:
            # Re-initialize Kite with same key
            kite = KiteConnect(api_key=api_key)
            session_data = kite.generate_session(request_token, api_secret=api_secret)
            access_token = session_data["access_token"]

            # Save access token and timestamp
            sheet.update_acell("C1", access_token)
            sheet.update_acell("D1", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            # 🔍 Confirm by re-reading the token
            confirmed_token = sheet.acell("C1").value.strip()
            if confirmed_token == access_token:
                st.success("✅ Access token saved and confirmed in Google Sheet (C1).")
            else:
                st.error(
                    f"⚠️ Token mismatch!\n\nExpected: `{access_token[:6]}...{access_token[-6:]}`\nFound: `{confirmed_token[:6]}...{confirmed_token[-6:]}`"
                )

        except Exception as e:
            st.error(f"❌ Token generation or sheet write failed: {e}")

# 📊 Main panel: Show latest Greeks log if available
if os.path.exists("greeks_log.csv"):
    df = pd.read_csv("greeks_log.csv")
    df["time"] = pd.to_datetime(df["time"])
    st.line_chart(df.set_index("time")[["delta_sum", "vega_sum", "theta_sum"]])
    st.dataframe(df.tail(10).sort_values(by="time", ascending=False), use_container_width=True)
else:
    st.info("🕒 No Greek log file found yet. Run `fetch_option_data.py` to begin logging.")
