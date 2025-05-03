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
# Load service-account creds from [gcreds] in secrets.toml
gcreds = st.secrets.get("gcreds")
if not gcreds:
    st.error("❌ 'gcreds' not found in Streamlit secrets. Paste your service-account JSON under [gcreds].")
    st.stop()

# Load GreeksData sheet ID
sheet_id = st.secrets.get("GREEKS_SHEET_ID")
if not sheet_id:
    st.error("❌ 'GREEKS_SHEET_ID' not found in Streamlit secrets. Add it as a top-level entry.")
    st.stop()

# ----------------- GOOGLE SHEETS AUTH -----------------
scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
gc = gspread.authorize(creds)

# Open GreeksData workbook
def open_sheet(key):
    try:
        return gc.open_by_key(key)
    except Exception as e:
        st.error(f"❌ Cannot open sheet {key}: {e}")
        st.stop()
wb = open_sheet(sheet_id)

# ----------------- LOAD WORKSHEETS -----------------
def get_df(ws_name, required=True):
    try:
        ws = wb.worksheet(ws_name)
    except Exception as e:
        if required:
            st.error(f"❌ Cannot access '{ws_name}' tab: {e}")
            st.stop()
        else:
            st.warning(f"⚠️ '{ws_name}' missing: {e}")
            return pd.DataFrame()
    # Use get_all_values to handle non-unique headers
    all_vals = ws.get_all_values()
    if not all_vals or len(all_vals) < 2:
        if required:
            st.error(f"❌ '{ws_name}' is empty or missing rows.")
            st.stop()
        else:
            return pd.DataFrame()
    headers = all_vals[0]
    rows = all_vals[1:]
    df = pd.DataFrame(rows, columns=headers)
    return df

# Load data

df_log = get_df("GreeksLog", required=True)
df_open = get_df("GreeksOpen", required=False)

# ----------------- BASELINE SELECTION -----------------

def color_positive(val):
    if val > 0:
        return 'color: green'
    elif val < 0:
        return 'color: red'
    else:
        return 'color: black'

st.subheader("📊 Live Greek Changes (vs Open)")
st.dataframe(
    df_disp.style
           .applymap(color_positive)
           .format("{:.2f}")
)

# ----------------- FOOTER & AUTO-REFRESH -----------------
st.caption(f"✅ Last updated: {now.strftime('%d-%b-%Y %I:%M:%S %p IST')}")
st.caption("🔄 Auto-refresh every 1 minute")
st_autorefresh(interval=60000)

st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:grey;'>"
    "Made with ❤️ by Prakash Rai in partnership with ChatGPT | Powered by Zerodha APIs"
    "</div>", unsafe_allow_html=True
)
