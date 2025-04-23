import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from kiteconnect import KiteConnect
from sentiment_tracker import summary  # ⬅️ Live/historical Greek summary

st.set_page_config(page_title="📈 Market Sentiment Tracker", layout="wide")
st.title("📊 NIFTY Option Greeks Sentiment Dashboard")

# -------------------- Google Sheet Setup --------------------
try:
    gcreds = json.loads(st.secrets["GCREDS"])
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
    client = gspread.authorize(creds)
    token_sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")
except Exception as e:
    st.error(f"❌ Failed to connect to Google Sheets: {e}")
    st.stop()

# -------------------- Fetch API Key & Secret --------------------
try:
    api_key = token_sheet.acell("A1").value.strip()
    api_secret = token_sheet.acell("B1").value.strip()
except Exception as e:
    st.error(f"❌ Failed to read API Key/Secret: {e}")
    st.stop()

# -------------------- Zerodha Login Section --------------------
with st.sidebar:
    st.header("🔐 Zerodha Login")
    st.info(f"📎 API Key (fetched): `{api_key}`")
    st.markdown(f"[🔗 Click to login](https://kite.zerodha.com/connect/login?api_key={api_key})", unsafe_allow_html=True)
    request_token = st.text_input("Paste Request Token")

    if st.button("🎟 Generate Access Token"):
        if request_token:
            try:
                kite = KiteConnect(api_key=api_key)
                data = kite.generate_session(request_token, api_secret=api_secret)
                access_token = data["access_token"]
                token_sheet.update("C1", [[access_token]])
                st.success("✅ Access token saved to Google Sheet (C1)")
                st.code(access_token)
            except Exception as e:
                st.error(f"❌ Error generating session: {e}")
        else:
            st.warning("⚠️ Please paste the request token.")

    st.markdown("---")
    st.info(f"📂 Greek Data Source: `{summary['source']}`")
    st.caption(f"🕒 Latest Timestamp: {summary['timestamp']}")

# -------------------- Market Open Baseline --------------------
st.subheader("📌 Market Open Baseline (9:15 AM)")
st.dataframe(summary["open_df"].style.format(precision=2), use_container_width=True)

# -------------------- Latest Greek Change --------------------
st.subheader("📈 Latest Greek Change from Market Open")

metrics = summary["metrics"]
st.metric("CE Δ Delta", f"{metrics['ce_delta_change']:.2f}")
st.metric("PE Δ Delta", f"{metrics['pe_delta_change']:.2f}")

col1, col2 = st.columns(2)
with col1:
    st.metric("CE Δ Vega", f"{metrics['ce_vega_change']:.2f}")
    st.metric("CE Δ Theta", f"{metrics['ce_theta_change']:.2f}")
with col2:
    st.metric("PE Δ Vega", f"{metrics['pe_vega_change']:.2f}")
    st.metric("PE Δ Theta", f"{metrics['pe_theta_change']:.2f}")

# -------------------- Greek Trends --------------------
st.subheader("📊 Real-Time Greek Trends")

df = summary["log_df"]
tab1, tab2 = st.tabs(["🔵 CE Greeks", "🔴 PE Greeks"])

with tab1:
    st.line_chart(df.set_index("timestamp")[["ce_delta_change", "ce_vega_change", "ce_theta_change"]])
with tab2:
    st.line_chart(df.set_index("timestamp")[["pe_delta_change", "pe_vega_change", "pe_theta_change"]])

# -------------------- Raw Logs --------------------
with st.expander("🧾 View Greek Log (latest 20 rows)"):
    st.dataframe(df.tail(20).style.format(precision=2), use_container_width=True)
