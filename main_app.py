import streamlit as st
import pandas as pd
import datetime
import pytz
import os
import json
import toml
from oauth2client.service_account import ServiceAccountCredentials
import gspread
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

# ----------------- DESCRIPTION -----------------
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

# ----------------- LOAD CREDENTIALS -----------------
try:
    # 1) Streamlit Cloud secrets
    if hasattr(st, 'secrets') and 'GCREDS' in st.secrets:
        raw = st.secrets['GCREDS']
        gcreds = json.loads(raw) if isinstance(raw, str) else raw
    else:
        # 2) Local secrets.toml (GitHub Actions)
        path = os.path.expanduser('~/.streamlit/secrets.toml')
        if os.path.exists(path):
            sec = toml.load(path)
            gcreds = json.loads(sec.get('GCREDS', '{}'))
        # 3) Environment variable
        elif 'GCREDS' in os.environ:
            gcreds = json.loads(os.environ['GCREDS'])
        else:
            raise KeyError('GCREDS')
except Exception as e:
    st.error(f"❌ GCREDS not found. Cannot load data: {e}")
    st.stop()

# ----------------- AUTHORIZE GOOGLE SHEETS -----------------
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
gc = gspread.authorize(creds)
wb = gc.open('ZerodhaTokenStore')

df_log = pd.DataFrame(wb.worksheet('GreeksLog').get_all_records())
df_open = pd.DataFrame(wb.worksheet('GreeksOpen').get_all_records())

if df_log.empty or df_open.empty:
    st.error("❌ No data found in Google Sheets. Please run the fetch script.")
    st.stop()

# ----------------- TIMESTAMP CONVERSION -----------------
try:
    df_log['timestamp'] = pd.to_datetime(df_log['timestamp'], utc=True).dt.tz_convert(ist)
except Exception:
    df_log['timestamp'] = pd.to_datetime(df_log['timestamp'])
open_vals = df_open.iloc[-1]

# ----------------- MARKET STATUS -----------------
open_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
close_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
if not (open_time <= now <= close_time):
    st.warning("🏁 **Market Closed** — Showing last snapshot.")

# ----------------- CALCULATE CHANGES -----------------
latest = df_log.iloc[-1]
changes = {
    'CE Δ': latest['ce_delta'] - open_vals['ce_delta'],
    'PE Δ': latest['pe_delta'] - open_vals['pe_delta'],
    'CE Vega': latest['ce_vega']  - open_vals['ce_vega'],
    'PE Vega': latest['pe_vega']  - open_vals['pe_vega'],
    'CE Theta':latest['ce_theta'] - open_vals['ce_theta'],
    'PE Theta':latest['pe_theta'] - open_vals['pe_theta']
}

# ----------------- COLOR CODING -----------------
def color(val):
    return 'color: green' if val>0 else 'color: red' if val<0 else 'color: black'

# ----------------- DISPLAY -----------------
st.subheader("📊 Live Greek Changes vs 9:15 AM IST")
st.dataframe(
    pd.DataFrame([changes]).style
      .applymap(color)
      .format("{:.2f}")
)

# ----------------- LAST REFRESH -----------------
st.caption(f"✅ Last updated: {now.strftime('%d-%b-%Y %I:%M:%S %p IST')}")

# ----------------- AUTO REFRESH -----------------
st.caption("🔄 Auto-refresh every 1 min")
st_autorefresh(interval=60000)

# ----------------- FOOTER -----------------
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:grey;'>"
    "Made with ❤️ by Prakash Rai in partnership with ChatGPT | Powered by Zerodha APIs"
    "</div>", unsafe_allow_html=True
)
