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
# GCREDS can come from Streamlit secrets (nested dict) or env var
raw = st.secrets.get("gcreds") or st.secrets.get("GCREDS") or os.environ.get("GCREDS") or os.environ.get("gcreds")
if raw is None:
    st.error("❌ GCREDS not found in Streamlit secrets or environment variables. Ensure 'gcreds' section is present in secrets.toml or GCREDS env var is set.")
    st.stop()
# Determine type of raw and parse accordingly
if isinstance(raw, str):
    try:
        gcreds = json.loads(raw)
    except Exception as e:
        st.error(f"❌ Failed to parse GCREDS JSON string: {e}")
        st.stop()
else:
    # raw is likely a Secrets AttrDict or dict-like
    gcreds = raw

# ----------------- GOOGLE SHEETS AUTH ----------------- -----------------
scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
gc = gspread.authorize(creds)

# ----------------- FETCH DATA FROM SHEETS -----------------
# Attempt to read GREEKS_SHEET_ID from multiple locations
sheet_id = (
    st.secrets.get("GREEKS_SHEET_ID")
    or (st.secrets.get("gcreds") or {}).get("GREEKS_SHEET_ID")
    or os.environ.get("GREEKS_SHEET_ID")
    or os.environ.get("greeks_sheet_id")
)
if not sheet_id:
    st.error(
        "❌ GREEKS_SHEET_ID not found.\n"
        "Please add it under [gcreds] in secrets.toml with key GREEKS_SHEET_ID, "
        "or as a top-level secret, or set env var GREEKS_SHEET_ID."
    )
    st.stop()
# open the workbook
try:
    wb = gc.open_by_key(sheet_id)
except Exception as e:
    st.error(f"❌ Cannot open sheet {sheet_id}: {e}")
    st.stop()

# Load records

df_log = pd.DataFrame(wb.worksheet("GreeksLog").get_all_records())
df_open = pd.DataFrame(wb.worksheet("GreeksOpen").get_all_records())
if df_log.empty or df_open.empty:
    st.error("❌ No data found in Google Sheets. Please run the fetch scripts.")
    st.stop()

# ----------------- PROCESS DATA -----------------
# Convert timestamps to IST
df_log['timestamp'] = pd.to_datetime(df_log['timestamp'])
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
