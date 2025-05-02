import streamlit as st
import pandas as pd
import datetime
import pytz
import toml
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
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

# ----------------- LOAD GOOGLE SHEET DATA -----------------
# ----------------- LOAD GOOGLE SHEET DATA -----------------
# Load GCREDS from Streamlit secrets, fallback to file or env var
gcreds = None
if hasattr(st, "secrets"):
    if "GCREDS" in st.secrets:
        gcreds = st.secrets["GCREDS"]
    elif "gcreds" in st.secrets:
        gcreds = st.secrets["gcreds"]
# fallback to local secrets file or env var
def _load_local_gcreds():
    path = os.path.expanduser("~/.streamlit/secrets.toml")
    if os.path.exists(path):
        sec = toml.load(path)
        if "GCREDS" in sec:
            return sec["GCREDS"]
        if "gcreds" in sec:
            return sec["gcreds"]
    if "GCREDS" in os.environ:
        return os.environ["GCREDS"]
    if "gcreds" in os.environ:
        return os.environ["gcreds"]
    return None

if gcreds is None:
    gcreds = _load_local_gcreds()

if gcreds is None:
    st.error("❌ GCREDS not found. Cannot load data.")
    st.stop()

# If gcreds is JSON string, parse to dict
if isinstance(gcreds, str):
    try:
        gcreds = json.loads(gcreds)
    except json.JSONDecodeError:
        st.error("❌ GCREDS is not valid JSON.")
        st.stop()

# Authorize gspread
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
gc = gspread.authorize(creds)
wb = gc.open("ZerodhaTokenStore")
# Read worksheets
log_ws = wb.worksheet("GreeksLog")
open_ws = wb.worksheet("GreeksOpen")
df_log = pd.DataFrame(log_ws.get_all_records())
df_open = pd.DataFrame(open_ws.get_all_records())

if df_log.empty or df_open.empty:
    st.error("❌ No data found in Google Sheets. Please run the fetch script.")
    st.stop()

# ----------------- TIMESTAMP CONVERSION -----------------
try:
    df_log['timestamp'] = pd.to_datetime(df_log['timestamp']).dt.tz_localize('UTC').dt.tz_convert(ist)
except Exception:
    df_log['timestamp'] = pd.to_datetime(df_log['timestamp'])
open_vals = df_open.iloc[-1]

# ----------------- MARKET STATUS -----------------
market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
if not (market_open <= now <= market_close):
    st.warning("🏁 **Market Closed** — Showing last trading snapshot.")

# ----------------- CALCULATE CHANGES -----------------
latest = df_log.iloc[-1]
data = {
    'ce_delta_change': latest['ce_delta'] - open_vals['ce_delta'],
    'pe_delta_change': latest['pe_delta'] - open_vals['pe_delta'],
    'ce_vega_change': latest['ce_vega'] - open_vals['ce_vega'],
    'pe_vega_change': latest['pe_vega'] - open_vals['pe_vega'],
    'ce_theta_change': latest['ce_theta'] - open_vals['ce_theta'],
    'pe_theta_change': latest['pe_theta'] - open_vals['pe_theta']
}

# ----------------- DISPLAY -----------------
def color(val):
    if val > 0:
        return 'color: green'
    elif val < 0:
        return 'color: red'
    return 'color: black'

st.subheader("📊 Live Greek Changes (vs 9:15 AM IST)")
st.dataframe(pd.DataFrame([data]).style.applymap(color).format("{:.2f}"))

# ----------------- FOOTER & REFRESH -----------------
st.caption(f"✅ Last updated at: {now.strftime('%d-%b-%Y %I:%M:%S %p IST')}")
st.caption("🔄 Auto-refreshes every 1 minute")
st_autorefresh(interval=60000)
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:grey;'>"
    "Made with ❤️ by Prakash Rai in partnership with ChatGPT | Powered by Zerodha APIs"
    "</div>", unsafe_allow_html=True
)
