import streamlit as st
import pandas as pd
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from kiteconnect import KiteConnect

st.set_page_config(page_title="📈 Market Sentiment Tracker", layout="wide")
st.title("📊 NIFTY Option Greeks Sentiment Dashboard")

# -------------------- Zerodha Login Section --------------------
with st.sidebar:
    st.header("🔐 Zerodha Login")
    api_key = st.text_input("API Key", value="", type="default")
    api_secret = st.text_input("API Secret", value="", type="password")
    request_token = st.text_input("Paste Request Token", value="", type="default")

    if st.button("🎟 Generate Access Token"):
        if api_key and api_secret and request_token:
            try:
                kite = KiteConnect(api_key=api_key)
                data = kite.generate_session(request_token, api_secret=api_secret)
                access_token = data["access_token"]

                # Save to Google Sheet
                gcreds = json.loads(os.environ["GCREDS"])
                scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
                client = gspread.authorize(creds)
                sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")

                sheet.update("A1", api_key)
                sheet.update("B1", api_secret)
                sheet.update("C1", access_token)

                st.success("✅ Access token updated in Google Sheet.")
                st.code(access_token)
            except Exception as e:
                st.error(f"❌ Error generating session: {e}")
        else:
            st.warning("Please fill all fields.")

# -------------------- Load Log Files --------------------
if not os.path.exists("greeks_open.csv") or not os.path.exists("greeks_log.csv"):
    st.warning("⚠️ Greek log files not found yet. Please wait until 9:15 AM or trigger tracker manually.")
    st.stop()

open_df = pd.read_csv("greeks_open.csv")
log_df = pd.read_csv("greeks_log.csv")

# -------------------- Display Market Open Snapshot --------------------
st.subheader("📌 Market Open Baseline (9:15 AM)")
st.dataframe(open_df.style.format(precision=2))

# -------------------- Latest Greek Changes --------------------
st.subheader("📈 Latest Greek Change from Market Open")

latest = log_df.iloc[-1]

st.metric("CE Δ Delta", f"{latest['ce_delta_change']:.2f}", delta_color="inverse")
st.metric("PE Δ Delta", f"{latest['pe_delta_change']:.2f}")

col1, col2 = st.columns(2)
with col1:
    st.metric("CE Δ Vega", f"{latest['ce_vega_change']:.2f}")
    st.metric("CE Δ Theta", f"{latest['ce_theta_change']:.2f}")
with col2:
    st.metric("PE Δ Vega", f"{latest['pe_vega_change']:.2f}")
    st.metric("PE Δ Theta", f"{latest['pe_theta_change']:.2f}")

# -------------------- Trendline Charts --------------------
st.subheader("📊 Real-Time Greek Trends")

log_df["timestamp"] = pd.to_datetime(log_df["timestamp"])

tab1, tab2 = st.tabs(["🔵 CE Greeks", "🔴 PE Greeks"])

with tab1:
    st.line_chart(log_df.set_index("timestamp")[["ce_delta_change", "ce_vega_change", "ce_theta_change"]])

with tab2:
    st.line_chart(log_df.set_index("timestamp")[["pe_delta_change", "pe_vega_change", "pe_theta_change"]])

# -------------------- Raw Logs (Expandable) --------------------
with st.expander("🧾 View Raw Greek Logs"):
    st.dataframe(log_df.tail(20).style.format(precision=2))
