import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from kiteconnect import KiteConnect
import datetime
import os

# Load Google creds from Streamlit secrets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = {key: st.secrets["gcp_service_account"][key] for key in st.secrets["gcp_service_account"]}
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")

# Streamlit layout
st.set_page_config(layout="wide")
st.title("📈 NIFTY Sentiment Tracker (Delta 0.05–0.60)")

# Sidebar – Zerodha login and token management
with st.sidebar:
    st.header("🔐 Zerodha Token Manager")

    # Load API credentials from sheet
    api_key = sheet.acell("A1").value.strip()
    api_secret = sheet.acell("B1").value.strip()

    st.markdown(f"✅ Using API Key from Google Sheet: `{api_key}`")

    try:
        kite = KiteConnect(api_key=api_key)
        login_url = kite.login_url()
        st.markdown(f"🔗 [Login to Zerodha]({login_url})")
    except Exception as e:
        st.error(f"⚠️ Error generating login URL: {e}")

    req_token = st.text_input("📋 Paste your request_token here:")

    if st.button("Generate Access Token"):
        try:
            data = kite.generate_session(req_token, api_secret=api_secret)
            access_token = data["access_token"]
            sheet.update_acell("C1", access_token)  # ✅ Save token to C1
            st.success("✅ Access token saved successfully in C1!")
        except Exception as e:
            st.error(f"❌ Token generation failed: {e}")

# Main content: Greek chart
if os.path.exists("greeks_log.csv"):
    df = pd.read_csv("greeks_log.csv")
    df["time"] = pd.to_datetime(df["time"])
    st.line_chart(df.set_index("time")[["delta_sum", "vega_sum", "theta_sum"]])
    st.dataframe(df.tail(10).sort_values(by="time", ascending=False), use_container_width=True)
else:
    st.info("🕒 No log file yet. Run `fetch_option_data.py` to begin logging.")
