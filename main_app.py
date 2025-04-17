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

# Load Google credentials from secrets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = {key: st.secrets["gcp_service_account"][key] for key in st.secrets["gcp_service_account"]}
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")

# Load API credentials and access token
api_key = sheet.acell("A1").value.strip()
api_secret = sheet.acell("B1").value.strip()
access_token = sheet.acell("C1").value.strip()

# ✅ Token Status Card
st.subheader("🔑 Access Token Status")

if access_token:
    now = datetime.datetime.now()
    try:
        timestamp = sheet.acell("D1").value  # Optional timestamp (if added during save)
        st.success(f"✅ Token found in C1.\n\n🕒 Last updated: `{timestamp}`" if timestamp else "✅ Token is available in C1.")
    except:
        st.success("✅ Token is available in C1.")
else:
    st.error("❌ No access token found in C1. Please generate a fresh token from sidebar.")

# Sidebar – Zerodha Token Generator
with st.sidebar:
    st.header("🔐 Zerodha Token Manager")
    st.markdown(f"✅ Using API Key from Sheet: `{api_key}`")

    try:
        kite = KiteConnect(api_key=api_key)
        login_url = kite.login_url()
        st.markdown(f"🔗 [Login to Zerodha]({login_url})")
    except Exception as e:
        st.error(f"❌ Error creating login URL: {e}")

    request_token = st.text_input("📋 Paste your request_token here:")

    if st.button("Generate Access Token"):
        try:
            session_data = kite.generate_session(request_token, api_secret=api_secret)
            access_token = session_data["access_token"]
            sheet.update_acell("C1", access_token)
            sheet.update_acell("D1", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))  # Save timestamp

            # Confirm write
            confirmed_token = sheet.acell("C1").value.strip()
            if confirmed_token == access_token:
                st.success("✅ Access token saved to Google Sheet (C1)!")
            else:
                st.error("⚠️ Token save failed or mismatch in C1. Please try again.")
        except Exception as e:
            st.error(f"❌ Token generation failed: {e}")

# Main content – Greek chart
if os.path.exists("greeks_log.csv"):
    df = pd.read_csv("greeks_log.csv")
    df["time"] = pd.to_datetime(df["time"])
    st.line_chart(df.set_index("time")[["delta_sum", "vega_sum", "theta_sum"]])
    st.dataframe(df.tail(10).sort_values(by="time", ascending=False), use_container_width=True)
else:
    st.info("🕒 No Greek log found yet. Run `fetch_option_data.py` to begin logging.")
