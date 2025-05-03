import streamlit as st
import pandas as pd
import datetime
import pytz
import json
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_autorefresh import st_autorefresh

# ----------------- PAGE SETUP -----------------
st.set_page_config(page_title="📈 Sentiment Tracker", layout="wide")

# ----------------- TIMEZONE SETUP -----------------
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

# ----------------- FETCH DATA FROM SHEETS -----------------
sheet_id = st.secrets.get("GREEKS_SHEET_ID")
if not sheet_id:
    st.error("❌ GREEKS_SHEET_ID not found in secrets.")
    st.stop()
wb = gc.open_by_key(sheet_id)
df_log = pd.DataFrame(wb.worksheet("GreeksLog").get_all_records())
df_open = pd.DataFrame(wb.worksheet("GreeksOpen").get_all_records())
if df_log.empty or df_open.empty:
    st.error("❌ No data found in Google Sheets. Please run the fetch scripts.")
    st.stop()

# ----------------- PROCESS DATA -----------------
# Convert timestamps to IST
df_log['timestamp'] = pd.to_datetime(df_log['timestamp'])
# if UTC-localized, convert; else localize then convert
try:
    df_log['timestamp'] = df_log['timestamp'].dt.tz_localize('UTC').dt.tz_convert(ist)
except ValueError:
    df_log['timestamp'] = df_log['timestamp'].dt.tz_convert(ist)

open_vals = df_open.iloc[-1]
latest = df_log.iloc[-1]

# Compute changes
changes = {
    'CE Δ Change': latest['ce_delta'] - open_vals['ce_delta'],
    'PE Δ Change': latest['pe_delta'] - open_vals['pe_delta'],
    'CE Vega Δ':   latest['ce_vega']  - open_vals['ce_vega'],
    'PE Vega Δ':   latest['pe_vega']  - open_vals['pe_vega'],
    'CE Theta Δ':  latest['ce_theta'] - open_vals['ce_theta'],
    'PE Theta Δ':  latest['pe_theta'] - open_vals['pe_theta'],
}

# Color mapping
def color_positive(val):
    return 'color: green' if val > 0 else 'color: red' if val < 0 else 'color: black'

st.subheader("📊 Live Greek Changes (vs 9:15 AM IST)")
st.dataframe(
    pd.DataFrame([changes])
      .style
      .applymap(color_positive)
      .format("{:.2f}")
)

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
