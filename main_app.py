import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from kiteconnect import KiteConnect
import datetime
import os

# Streamlit Page Setup
st.set_page_config(layout="wide")
st.title("📈 NIFTY Sentiment Tracker (Delta 0.05–0.60)")

# Load Google credentials from Streamlit Secrets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = {key: st.secrets["gcp_service_account"][key] for key in st.secrets["gcp_service_account"]}
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")

# Sidebar: Zerodha Token Generator
with st.sidebar:
    st.header("🔐 Zerodha API Login")

    # Step 1: Enter API Key and Secret
    user_api_key = st.text_input("🔑 Enter your API Key", type="password")
    user_api_secret = st.text_input("🧪 Enter your API Secret", type="password")

    if user_api_key and user_api_secret:
        try:
            kite = KiteConnect(api_key=user_api_key)
            login_url = kite.login_url()
            st.markdown(f"🔗 [Click here to Login to Zerodha]({login_url})")
        except Exception as e:
            st.error(f"⚠️ Error creating login URL: {e}")

        # Step 2: Enter request_token
        req_token = st.text_input("📋 Paste your request_token here:")

        # Step 3: Generate access token
        if st.button("Generate Access Token"):
            try:
                data = kite.generate_session(req_token, api_secret=user_api_secret)
                access_token = data["access_token"]
                sheet.update_acell("B2", access_token)
                st.success("✅ Access token saved to Google Sheet!")
            except Exception as e:
                st.error(f"❌ Token generation failed: {e}")
    else:
        st.warning("👆 Please enter both API Key and API Secret to proceed.")

# Main Area: Show Sentiment Logs if available
if os.path.exists("greeks_log.csv"):
    df = pd.read_csv("greeks_log.csv")
    df["time"] = pd.to_datetime(df["time"])
    st.line_chart(df.set_index("time")[["delta_sum", "vega_sum", "theta_sum"]])
    st.dataframe(df.tail(10).sort_values(by="time", ascending=False), use_container_width=True)
else:
    st.info("🕒 No Greek log found yet. Run `fetch_option_data.py` to begin logging.")
