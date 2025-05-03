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
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        if df.empty and required:
            raise ValueError(f"Worksheet '{ws_name}' is empty.")
        return df
    except Exception as e:
        if required:
            st.error(f"❌ Error loading '{ws_name}': {e}")
            st.stop()
        else:
            st.warning(f"⚠️ '{ws_name}' missing or empty. {e}")
            return pd.DataFrame()

df_log  = get_df("GreeksLog",   required=True)
df_open = get_df("GreeksOpen",  required=False)

# ----------------- BASELINE SELECTION -----------------
if not df_open.empty and "ce_delta_open" in df_open.columns:
    open_vals = df_open.iloc[-1]
else:
    open_vals = df_log.iloc[0]

# Latest values
today_rec = df_log.iloc[-1]

# ----------------- COMPUTE CHANGES -----------------
changes = {}
for side in ["ce","pe"]:
    for greek in ["delta","vega","theta"]:
        key_latest = f"{side}_{greek}"
        key_open   = f"{side}_{greek}_open"
        latest_val = float(today_rec.get(key_latest, 0))
        open_val   = float(open_vals.get(key_open, 0))
        changes[f"{side.upper()} {greek.capitalize()} Δ"] = latest_val - open_val

# ----------------- DISPLAY -----------------
# Build a one-row DataFrame
df_disp = pd.DataFrame([changes])

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
