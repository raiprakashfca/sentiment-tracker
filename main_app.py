import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from kiteconnect import KiteConnect
import datetime
import os

# CONFIG
GOOGLE_SHEET_NAME = "ZerodhaTokenStore"
GOOGLE_TAB_NAME = "Sheet1"
API_KEY = "your_api_key"
API_SECRET = "your_api_secret"

# Load gcreds from secrets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = {key: st.secrets["gcp_service_account"][key] for key in st.secrets["gcp_service_account"]}
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open(GOOGLE_SHEET_NAME).worksheet(GOOGLE_TAB_NAME)

# Streamlit UI
st.set_page_config(layout="wide")
st.title("📈 NIFTY Sentiment Tracker (Delta 0.05–0.60)")

with st.sidebar:
    st.header("🔐 Zerodha Login")
    req_token = st.text_input("Paste your request_token:")
    if st.button("Generate Access Token"):
        try:
            kite = KiteConnect(api_key=API_KEY)
            data = kite.generate_session(req_token, api_secret=API_SECRET)
            access_token = data["access_token"]
            sheet.update_acell("B2", access_token)
            st.success("Access token updated successfully in Google Sheet!")
        except Exception as e:
            st.error(f"Failed to generate access token: {e}")

# Display dummy message or recent log
if os.path.exists("greeks_log.csv"):
    df = pd.read_csv("greeks_log.csv")
    df["time"] = pd.to_datetime(df["time"])
    st.line_chart(df.set_index("time")[["delta_sum", "vega_sum", "theta_sum"]])
    st.dataframe(df.tail(10).sort_values(by="time", ascending=False), use_container_width=True)
else:
    st.info("🕒 No Greek log found yet. Run `fetch_option_data.py` locally to start logging.")
# Replace with working Streamlit app code using secrets
