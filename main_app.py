# main_app.py
import streamlit as st
import pandas as pd
import datetime
import pytz
import json
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from scipy.stats import norm
from streamlit_autorefresh import st_autorefresh

# ----------------- PAGE SETUP -----------------
st.set_page_config(page_title="📈 Sentiment Tracker", layout="wide")
ist = pytz.timezone("Asia/Kolkata")
now = datetime.datetime.now(ist)

# ----------------- HEADER -----------------
col1, col2 = st.columns([8, 2])
with col1:
    st.title("📈 Option Greeks Sentiment Tracker")
    st.markdown(f"**🗓️ {now.strftime('%A, %d %B %Y, %I:%M:%S %p IST')}**")
with col2:
    st.metric("🕒 Market Time (IST)", now.strftime("%H:%M:%S"))

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

# ----------------- LOAD GOOGLE SHEET DATA -----------------
# Auth via same service account JSON
raw = st.secrets.get("GCREDS") or st.secrets.get("gcreds")
gcreds = json.loads(raw)
scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
gc = gspread.authorize(creds)

# Open GreeksData sheet by ID
wb    = gc.open_by_key(st.secrets["GREEKS_SHEET_ID"])
df_log  = pd.DataFrame(wb.worksheet("GreeksLog").get_all_records())
df_open = pd.DataFrame(wb.worksheet("GreeksOpen").get_all_records())

if df_log.empty or df_open.empty:
    st.error("❌ No data in Google Sheets. Please run the logger once.")
    st.stop()

# Convert timestamps
df_log['timestamp'] = pd.to_datetime(df_log['timestamp']).dt.tz_localize('UTC').dt.tz_convert(ist)
open_vals = df_open.iloc[-1]

# ----------------- COMPUTE CHANGES -----------------
latest = df_log.iloc[-1]
data = {
    'CE Δ Change': latest['ce_delta'] - open_vals['ce_delta'],
    'PE Δ Change': latest['pe_delta'] - open_vals['pe_delta'],
    'CE Vega Δ'  : latest['ce_vega'] - open_vals['ce_vega'],
    'PE Vega Δ'  : latest['pe_vega'] - open_vals['pe_vega'],
    'CE Theta Δ' : latest['ce_theta'] - open_vals['ce_theta'],
    'PE Theta Δ' : latest['pe_theta'] - open_vals['pe_theta'],
}

# Color mapping
def color(val):
    return 'color: green' if val>0 else 'color: red' if val<0 else 'color: black'

st.subheader("📊 Live Greek Changes (vs 9:15 AM IST)")
st.dataframe(pd.DataFrame([data]).style.applymap(color).format("{:.2f}"))

# ----------------- FOOTER & REFRESH -----------------
st.caption(f"✅ Last updated: {now.strftime('%d-%b-%Y %I:%M:%S %p IST')}")
st.caption("🔄 Auto-refresh every 1 minute")
st_autorefresh(interval=60000)

st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:grey;'>"
    "Made with ❤️ by Prakash Rai in partnership with ChatGPT | Powered by Zerodha APIs"
    "</div>",
    unsafe_allow_html=True
)
