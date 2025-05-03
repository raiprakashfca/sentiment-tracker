import streamlit as st
import pandas as pd
import datetime
import pytz
import json
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ----------------- PAGE SETUP -----------------
st.set_page_config(page_title="📈 Sentiment Tracker", layout="wide")
\ n# ----------------- TIMEZONE SETUP -----------------
ist = pytz.timezone("Asia/Kolkata")
now = datetime.datetime.now(ist)

# ----------------- HEADER -----------------
col1, col2 = st.columns([8, 2])
with col1:
    st.title("📈 Option Greeks Sentiment Tracker")
    st.markdown(f"**🗓️ {now.strftime('%A, %d %B %Y, %I:%M:%S %p IST')}**")
with col2:
    st.metric(label="🕒 Market Time (IST)", value=now.strftime("%H:%M:%S"))

# ----------------- EXPLANATION -----------------
st.markdown("""
This dashboard tracks the *real-time change* in:
- Delta
- Vega
- Theta
for NIFTY Options (0.05 to 0.60 Delta Range).

**Interpretation:**
- Positive Delta Change → Bullish Bias
- Negative Delta Change → Bearish Bias
- Rising Vega → Volatility Expansion
- Rising Theta → Faster Premium Decay

Tracking both **CE** and **PE** separately.
""")

# ----------------- LOAD GOOGLE SHEET SECRETS -----------------
raw = st.secrets.get("GCREDS") or st.secrets.get("gcreds")
if not raw:
    st.error("❌ GCREDS not found. Cannot load data.")
    st.stop()
# GCREDS may be stored as dict or JSON string
if isinstance(raw, str):
    try:
        gcreds = json.loads(raw)
    except json.JSONDecodeError as e:
        st.error(f"❌ Invalid GCREDS JSON: {e}")
        st.stop()
else:
    gcreds = raw

# ----------------- GOOGLE SHEETS AUTH -----------------
scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
gc = gspread.authorize(creds)

# Open GreeksData sheet by key
greeks_wb = gc.open_by_key(st.secrets["GREEKS_SHEET_ID"])
df_log = pd.DataFrame(greeks_wb.worksheet("GreeksLog").get_all_records())
df_open = pd.DataFrame(greeks_wb.worksheet("GreeksOpen").get_all_records())

if df_log.empty or df_open.empty:
    st.error("❌ No data found in Google Sheets. Please run the fetch script.")
    st.stop()

# ----------------- CONVERT & COMPUTE -----------------
istamp_col = pd.to_datetime(df_log['timestamp'])
df_log['timestamp'] = (
    ist.localize( ist.normalize( ist.localize( ist.normalize(ist.localize( ist.normalize( ist.localize( ist.normalize(ist.localize( ist.normalize(ist.localize(ist.normalize(ist.localize(ist.normalize(ist.localize(ist.normalize(ist.localize(ist.normalize(ist.localize(ist.normalize(ist.localize(ist.normalize(ist.localize(ist.normalize(ist.localize(ist.normalize(ist.localize(ist.normalize(ist.localize(ist.normalize(ist.localize(ist.normalize(ist.localize(ist.generate(ist.normalize)
